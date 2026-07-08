"""
VitiCare — Image Registration
Aligns each pair of consecutive timepoints within a clean patient folder,
so later images overlap correctly with the first (baseline) image.

Uses classical feature matching (ORB) + homography — no training required,
works directly on the clinical images.

Requires: pip install opencv-python numpy matplotlib pillow
Run from project root: python3 Notebooks/registration.py
"""

import json
from pathlib import Path

import cv2
import numpy as np
import matplotlib.pyplot as plt

DATASET_DIR = Path("Data/raw/AVRES-WL")
LABELS_FILE = Path("Data/triage_labels.json")
OUTPUT_DIR = Path("Data/registered")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}


def load_clean_folders():
    with open(LABELS_FILE, "r") as f:
        labels = json.load(f)
    return [name for name, tag in labels.items() if tag == "clean"]


def get_images_in_folder(folder: Path):
    return [
        f for f in sorted(folder.iterdir())
        if f.suffix.lower() in IMAGE_EXTENSIONS
    ]


def images_look_compatible(img1, img2):
    """
    Basic sanity check: flags cases where two images look like they're from
    completely different imaging types (e.g. a normal lit photo vs a Wood's
    lamp/UV scan), where feature-matching registration would produce garbage.

    This is a heuristic, not a perfect classifier — it checks:
    1. Overall color balance similarity (UV shots skew heavily blue/dark)
    2. Whether one image is mostly a dark circular vignette (common in
       Wood's lamp captures) while the other isn't
    """
    def mean_color(img):
        return img.reshape(-1, 3).mean(axis=0)  # BGR means

    def dark_fraction(img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return float((gray < 30).mean())

    c1, c2 = mean_color(img1), mean_color(img2)
    color_diff = np.linalg.norm(c1 - c2)

    dark1, dark2 = dark_fraction(img1), dark_fraction(img2)
    dark_diff = abs(dark1 - dark2)

    # Thresholds are deliberately conservative — flag only clear mismatches
    if color_diff > 90 or dark_diff > 0.35:
        return False
    return True


def register_pair(img_baseline, img_followup):
    """
    Aligns img_followup onto img_baseline using ORB feature matching + homography.
    Returns the warped follow-up image (same size/alignment as baseline) and
    a status string: "ok", "failed", or "skipped_incompatible".
    """
    if not images_look_compatible(img_baseline, img_followup):
        return img_followup, "skipped_incompatible"

    gray1 = cv2.cvtColor(img_baseline, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img_followup, cv2.COLOR_BGR2GRAY)

    orb = cv2.ORB_create(nfeatures=2000)
    kp1, des1 = orb.detectAndCompute(gray1, None)
    kp2, des2 = orb.detectAndCompute(gray2, None)

    if des1 is None or des2 is None or len(kp1) < 10 or len(kp2) < 10:
        return img_followup, "failed"

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = matcher.match(des1, des2)
    matches = sorted(matches, key=lambda m: m.distance)

    if len(matches) < 10:
        return img_followup, "failed"

    good_matches = matches[: max(20, int(len(matches) * 0.5))]

    src_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)

    homography, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

    if homography is None:
        return img_followup, "failed"

    # Sanity-check the homography itself — reject wild/degenerate warps
    det = np.linalg.det(homography[:2, :2])
    if det < 0.1 or det > 10:
        return img_followup, "failed"

    h, w = img_baseline.shape[:2]
    warped = cv2.warpPerspective(img_followup, homography, (w, h))
    return warped, "ok"


def process_folder(folder_name: str):
    folder = DATASET_DIR / folder_name
    images = get_images_in_folder(folder)

    if len(images) < 2:
        print(f"  Skipping {folder_name}: fewer than 2 images")
        return None

    baseline_path = images[0]
    baseline_img = cv2.imread(str(baseline_path))

    if baseline_img is None:
        print(f"  Skipping {folder_name}: could not read baseline image")
        return None

    out_folder = OUTPUT_DIR / folder_name
    out_folder.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_folder / "t0_baseline.jpg"), baseline_img)

    results = {"folder": folder_name, "timepoints": []}

    for i, followup_path in enumerate(images[1:], start=1):
        followup_img = cv2.imread(str(followup_path))
        if followup_img is None:
            print(f"  Warning: could not read {followup_path.name}, skipping this timepoint")
            continue

        warped, status = register_pair(baseline_img, followup_img)
        out_name = f"t{i}_registered.jpg"
        cv2.imwrite(str(out_folder / out_name), warped)

        results["timepoints"].append({
            "index": i,
            "source_file": followup_path.name,
            "registration_status": status,
            "output_file": out_name,
        })

        print(f"  t{i} ({followup_path.name}): registration {status}")

    return results


def show_comparison(folder_name: str):
    """Quick visual check: show baseline + all registered follow-ups side by side."""
    out_folder = OUTPUT_DIR / folder_name
    images = sorted(out_folder.iterdir())
    n = len(images)
    fig, axes = plt.subplots(1, n, figsize=(4 * n, 4))
    if n == 1:
        axes = [axes]
    for ax, img_path in zip(axes, images):
        img = cv2.imread(str(img_path))
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        ax.imshow(img_rgb)
        ax.set_title(img_path.name, fontsize=8)
        ax.axis("off")
    fig.suptitle(f"Registered: {folder_name}")
    plt.tight_layout()
    plt.show()


def main():
    clean_folders = load_clean_folders()
    print(f"Found {len(clean_folders)} clean folders to process\n")

    all_results = []
    for folder_name in clean_folders:
        print(f"Processing {folder_name}...")
        result = process_folder(folder_name)
        if result:
            all_results.append(result)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "registration_results.json", "w") as f:
        json.dump(all_results, f, indent=2)

    ok_count = sum(
        1 for r in all_results for tp in r["timepoints"] if tp["registration_status"] == "ok"
    )
    failed_count = sum(
        1 for r in all_results for tp in r["timepoints"] if tp["registration_status"] == "failed"
    )
    skipped_count = sum(
        1 for r in all_results for tp in r["timepoints"] if tp["registration_status"] == "skipped_incompatible"
    )
    total = sum(len(r["timepoints"]) for r in all_results)
    print(f"\nDone. Out of {total} timepoint pairs:")
    print(f"  OK (successfully registered): {ok_count}")
    print(f"  Failed (attempted but low quality): {failed_count}")
    print(f"  Skipped (incompatible imaging types, e.g. normal photo vs UV scan): {skipped_count}")
    print(f"Results saved to {OUTPUT_DIR / 'registration_results.json'}")
    print(f"Registered images saved under {OUTPUT_DIR}/<folder_name>/")

    fully_ok_folders = [
        r["folder"] for r in all_results
        if r["timepoints"] and all(tp["registration_status"] == "ok" for tp in r["timepoints"])
    ]

    if fully_ok_folders:
        preview_folder = fully_ok_folders[0]
        print(f"\nShowing a visual check for a fully-successful folder: {preview_folder}")
        show_comparison(preview_folder)
    else:
        print("\nNo fully-successful folder found to preview.")


if __name__ == "__main__":
    main()
