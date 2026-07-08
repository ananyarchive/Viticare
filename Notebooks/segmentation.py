"""
VitiCare — Segmentation + Longitudinal Progress Heatmap

Step 1 (segmentation): isolates vitiligo lesion regions in each registered
image using color-space thresholding (classical CV, no training needed —
Wood's lamp imaging makes depigmented skin fluoresce distinctly, so this
works well without a trained model).

Step 2 (diff/heatmap): compares lesion masks across timepoints within a
folder to produce a per-pixel change map — green where repigmentation
occurred, red where the lesion spread, showing changes a manual side-by-side
photo comparison would likely miss.

Requires: pip install opencv-python numpy matplotlib
Run from project root: python3 Notebooks/segmentation.py
"""

import json
from pathlib import Path

import cv2
import numpy as np
import matplotlib.pyplot as plt

REGISTERED_DIR = Path("Data/registered")
OUTPUT_DIR = Path("Data/segmented")
REGISTRATION_RESULTS_FILE = Path("Data/registered/registration_results.json")


def load_registration_status():
    """Returns a dict: folder_name -> {source_file: status} for quick lookup."""
    with open(REGISTRATION_RESULTS_FILE, "r") as f:
        results = json.load(f)
    status_map = {}
    for r in results:
        status_map[r["folder"]] = {
            tp["output_file"]: tp["registration_status"] for tp in r["timepoints"]
        }
    return status_map


def extract_subject_mask(img_bgr):
    """
    Separates the person (skin/body) from the background using GrabCut.
    Runs on a downscaled copy for speed (GrabCut is slow at full resolution),
    then upscales the resulting mask back to the original size.
    """
    h, w = img_bgr.shape[:2]

    # Downscale for speed — segmentation quality barely suffers, runtime does
    scale = 400 / max(h, w)
    if scale < 1.0:
        small = cv2.resize(img_bgr, (int(w * scale), int(h * scale)))
    else:
        small = img_bgr
        scale = 1.0

    sh, sw = small.shape[:2]
    mask = np.zeros((sh, sw), np.uint8)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)
    rect = (int(sw * 0.05), int(sh * 0.05), int(sw * 0.90), int(sh * 0.90))

    try:
        cv2.grabCut(small, mask, rect, bgd_model, fgd_model, 3, cv2.GC_INIT_WITH_RECT)
        subject_mask_small = np.where(
            (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0
        ).astype(np.uint8)
    except cv2.error:
        subject_mask_small = np.zeros((sh, sw), np.uint8)
        x, y, rw, rh = rect
        subject_mask_small[y:y + rh, x:x + rw] = 255

    # Upscale mask back to original image size
    subject_mask = cv2.resize(subject_mask_small, (w, h), interpolation=cv2.INTER_NEAREST)
    return subject_mask


def is_patch_shaped(contour):
    """
    Filters out contours that are long and thin (nails, hair strands, ear rims)
    versus blob-like (an actual lesion patch tends to be roughly round/oval,
    not a thin line or crescent).

    Uses two shape measures:
    - Solidity: area / convex hull area. A solid blob is close to 1.0;
      a thin curved sliver (like an ear rim or hair strand) is much lower.
    - Aspect ratio of the bounding box: very elongated shapes (like a nail
      or hair strand) have a high ratio; round patches are closer to 1.0.
    """
    area = cv2.contourArea(contour)
    if area < 1:
        return False

    hull = cv2.convexHull(contour)
    hull_area = cv2.contourArea(hull)
    solidity = area / hull_area if hull_area > 0 else 0

    x, y, w, h = cv2.boundingRect(contour)
    aspect_ratio = max(w, h) / max(min(w, h), 1)

    # Tuned to reject thin/curved shapes while keeping blob-like patches
    if solidity < 0.55:
        return False
    if aspect_ratio > 3.5:
        return False

    return True


def segment_lesion(img_bgr):
    """
    Isolates likely vitiligo (depigmented) regions in three stages:
    1. Separate the person from the background entirely (GrabCut) —
       hair, curtains, equipment, etc. are excluded up front.
    2. Within ONLY that subject region, find locally bright spots
       (a lesion patch relative to its surrounding skin).
    3. Filter by SHAPE — keep only blob-like regions, rejecting thin/
       elongated shapes that are more likely nails, hair, or ear rims.

    Returns a binary mask (255 = lesion, 0 = not lesion) and contours found.
    """
    h, w = img_bgr.shape[:2]

    subject_mask = extract_subject_mask(img_bgr)

    # Erode the subject mask inward slightly — this excludes the outer rim
    # of the subject (fingertips, ear edges, hairline boundary), which is
    # where nails/cartilage/hair-adjacent false positives tend to sit.
    erosion_kernel = np.ones((15, 15), np.uint8)
    subject_mask_eroded = cv2.erode(subject_mask, erosion_kernel, iterations=1)

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)

    block_size = max(51, (min(h, w) // 6) | 1)
    adaptive = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, block_size, -8
    )

    mask = cv2.bitwise_and(adaptive, subject_mask_eroded)

    kernel = np.ones((7, 7), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    img_area = h * w
    good_contours = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < img_area * 0.003 or area > img_area * 0.35:
            continue
        if not is_patch_shaped(c):
            continue
        good_contours.append(c)

    largest_contour = max(good_contours, key=cv2.contourArea) if good_contours else None

    clean_mask = np.zeros_like(mask)
    cv2.drawContours(clean_mask, good_contours, -1, 255, -1)

    return clean_mask, largest_contour, good_contours


def draw_outline_and_measurements(img_bgr, contours):
    """Draws outlines around detected lesion regions and returns measurements."""
    output = img_bgr.copy()
    measurements = []

    for c in contours:
        cv2.drawContours(output, [c], -1, (0, 255, 0), 2)  # green outline
        x, y, w, h = cv2.boundingRect(c)
        area_px = cv2.contourArea(c)
        measurements.append({
            "area_px": float(area_px),
            "bounding_width_px": int(w),
            "bounding_height_px": int(h),
        })

    total_area = sum(m["area_px"] for m in measurements)
    img_area = img_bgr.shape[0] * img_bgr.shape[1]
    area_pct = (total_area / img_area) * 100 if img_area > 0 else 0

    return output, measurements, area_pct


def pick_reference_frame(images_by_name, masks):
    """
    Picks the frame with the LARGEST detected lesion area to use as the
    reference boundary — this is usually the clearest, most confident
    detection, and avoids using a faint/ambiguous frame as the reference.
    """
    best_name, best_mask, best_area = None, None, -1
    for name, mask in masks:
        area = int((mask > 0).sum())
        if area > best_area:
            best_name, best_mask, best_area = name, mask, area
    return best_name, best_mask


def measure_brightness_within_region(img_bgr, region_mask):
    """
    Given a FIXED region (drawn once on the reference frame), measures the
    average brightness of that same region in this image. Since images are
    already registered/aligned, the same region_mask coordinates should
    correspond to the same physical area across timepoints.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    region_pixels = gray[region_mask > 0]
    if region_pixels.size == 0:
        return None
    return float(region_pixels.mean())


def compute_fixed_region_diff(reference_img, region_mask, followup_img):
    """
    Compares brightness within a FIXED lesion region (defined once on the
    reference frame) between the reference and a follow-up image.

    Since a vitiligo patch is BRIGHTER than skin under Wood's lamp,
    a DECREASE in brightness within this region over time suggests
    repigmentation (skin returning to normal, darker tone under UV).
    An INCREASE suggests further depigmentation/spreading.

    Produces a soft overlay: light green where brightness dropped
    (repigmentation), light red where it rose (progression), scaled by
    how much change occurred — not just a flat on/off color.
    """
    ref_gray = cv2.cvtColor(reference_img, cv2.COLOR_BGR2GRAY).astype(np.int16)
    fup_gray = cv2.cvtColor(followup_img, cv2.COLOR_BGR2GRAY).astype(np.int16)

    delta = fup_gray - ref_gray  # positive = got brighter, negative = got darker
    delta_masked = np.where(region_mask > 0, delta, 0)

    overlay = followup_img.copy()

    # Normalize delta magnitude for visualization (cap at +/-60 brightness units)
    cap = 60
    delta_clipped = np.clip(delta_masked, -cap, cap)
    intensity = (np.abs(delta_clipped) / cap * 255).astype(np.uint8)

    green_layer = np.zeros_like(overlay)
    green_layer[:, :, 1] = intensity  # green channel
    red_layer = np.zeros_like(overlay)
    red_layer[:, :, 2] = intensity  # red channel

    repigmenting = delta_masked < -10  # got meaningfully darker
    progressing = delta_masked > 10   # got meaningfully brighter

    alpha = 0.55
    overlay_repigment = cv2.addWeighted(green_layer, alpha, overlay, 1 - alpha, 0)
    overlay_progress = cv2.addWeighted(red_layer, alpha, overlay, 1 - alpha, 0)

    overlay[repigmenting] = overlay_repigment[repigmenting]
    overlay[progressing] = overlay_progress[progressing]

    region_area = int((region_mask > 0).sum())
    mean_delta = float(delta_masked[region_mask > 0].mean()) if region_area > 0 else 0
    repigmented_px = int(repigmenting.sum())
    progressed_px = int(progressing.sum())

    repigmentation_pct = (repigmented_px / region_area * 100) if region_area > 0 else 0

    return overlay, {
        "region_area_px": region_area,
        "mean_brightness_change": round(mean_delta, 2),
        "repigmented_px": repigmented_px,
        "progressed_px": progressed_px,
        "repigmentation_pct_of_region": round(repigmentation_pct, 2),
    }


def process_folder(folder: Path, registration_status: dict):
    images = sorted(folder.iterdir())
    if len(images) < 1:
        return None

    out_folder = OUTPUT_DIR / folder.name
    out_folder.mkdir(parents=True, exist_ok=True)

    # Clean up any stale files from previous runs/versions of this script,
    # so old leftover output can never be mistaken for a fresh result
    for stale_file in out_folder.glob("*"):
        stale_file.unlink()

    masks = []
    images_by_name = {}
    folder_result = {"folder": folder.name, "timepoints": []}
    folder_status = registration_status.get(folder.name, {})

    for img_path in images:
        img = cv2.imread(str(img_path))
        if img is None:
            continue

        mask, largest_contour, contours = segment_lesion(img)
        outlined, measurements, area_pct = draw_outline_and_measurements(img, contours)

        cv2.imwrite(str(out_folder / f"outlined_{img_path.name}"), outlined)
        cv2.imwrite(str(out_folder / f"mask_{img_path.name}"), mask)

        masks.append((img_path.name, mask))
        images_by_name[img_path.name] = img
        folder_result["timepoints"].append({
            "source_file": img_path.name,
            "lesion_area_pct_of_image": round(area_pct, 2),
            "num_regions_detected": len(measurements),
            "measurements": measurements,
        })

    # Pick the frame with the LARGEST detected patch as the reference —
    # its boundary is reused for all other timepoints, instead of re-detecting
    # (and possibly missing) the patch independently on every single frame.
    if len(masks) >= 2:
        ref_name, ref_mask = pick_reference_frame(images_by_name, masks)
        ref_img = images_by_name[ref_name]

        if ref_mask is not None and (ref_mask > 0).sum() > 0:
            for name, img in images_by_name.items():
                if name == ref_name:
                    continue
                # Only compare frames that were successfully registered
                # against the baseline — unaligned frames can't be reliably
                # compared region-for-region.
                if folder_status.get(name) != "ok":
                    continue

                if img.shape[:2] != ref_img.shape[:2]:
                    img = cv2.resize(img, (ref_img.shape[1], ref_img.shape[0]))

                overlay, diff_stats = compute_fixed_region_diff(ref_img, ref_mask, img)
                cv2.imwrite(str(out_folder / f"heatmap_{name}"), overlay)
                diff_stats["reference_frame"] = ref_name
                for tp in folder_result["timepoints"]:
                    if tp["source_file"] == name:
                        tp["diff_vs_reference"] = diff_stats

    return folder_result


def show_example(folder_name: str):
    out_folder = OUTPUT_DIR / folder_name
    outlined_imgs = sorted(out_folder.glob("outlined_*"))
    heatmap_imgs = sorted(out_folder.glob("heatmap_*"))

    n = len(outlined_imgs)
    fig, axes = plt.subplots(2, n, figsize=(4 * n, 8))

    for i, img_path in enumerate(outlined_imgs):
        img = cv2.cvtColor(cv2.imread(str(img_path)), cv2.COLOR_BGR2RGB)
        ax = axes[0, i] if n > 1 else axes[0]
        ax.imshow(img)
        ax.set_title(img_path.name, fontsize=8)
        ax.axis("off")

    for i in range(n):
        ax = axes[1, i] if n > 1 else axes[1]
        if i == 0:
            ax.axis("off")
            ax.set_title("baseline (no diff)", fontsize=8)
            continue
        heatmap_name = f"heatmap_{outlined_imgs[i].name.replace('outlined_', '')}"
        heatmap_path = out_folder / heatmap_name
        if heatmap_path.exists():
            img = cv2.cvtColor(cv2.imread(str(heatmap_path)), cv2.COLOR_BGR2RGB)
            ax.imshow(img)
            ax.set_title(f"diff: {heatmap_name}", fontsize=8)
        ax.axis("off")

    fig.suptitle(f"Segmentation + Progress Heatmap: {folder_name}")
    plt.tight_layout()
    plt.show()


def main():
    import sys

    folders = [f for f in sorted(REGISTERED_DIR.iterdir()) if f.is_dir()]
    print(f"Found {len(folders)} registered folders to segment\n")

    # If a folder name is passed as a command-line argument, just preview
    # that one folder's existing results instead of reprocessing everything
    if len(sys.argv) > 1:
        target_folder = sys.argv[1]
        print(f"Previewing existing results for folder: {target_folder}")
        show_example(target_folder)
        return

    registration_status = load_registration_status()

    all_results = []
    for i, folder in enumerate(folders, start=1):
        result = process_folder(folder, registration_status)
        if result:
            all_results.append(result)
        print(f"[{i}/{len(folders)}] Processed {folder.name}: {len(result['timepoints']) if result else 0} timepoints")

    with open(OUTPUT_DIR / "segmentation_results.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nDone. Results saved to {OUTPUT_DIR / 'segmentation_results.json'}")
    print(f"Outlined images, masks, and heatmaps saved under {OUTPUT_DIR}/<folder_name>/")

    # Preview a folder with multiple timepoints, detected regions, AND at
    # least one real generated heatmap (proves it wasn't a mixed-modality/
    # skipped folder like the all-photo-vs-UV cases)
    good_examples = [
        r["folder"] for r in all_results
        if len(r["timepoints"]) >= 3
        and all(tp["num_regions_detected"] > 0 for tp in r["timepoints"])
        and any("diff_vs_reference" in tp for tp in r["timepoints"])
    ]
    if good_examples:
        print(f"\nShowing example: {good_examples[0]}")
        show_example(good_examples[0])
    else:
        print("\nNo strong multi-timepoint example found to preview — check results JSON manually.")


if __name__ == "__main__":
    main()
