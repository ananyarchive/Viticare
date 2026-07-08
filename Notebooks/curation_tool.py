"""
VitiCare — Segmentation Curation Tool

Re-browse all segmented folders, judge segmentation QUALITY (not just whether
the folder is a valid patient timeline), and optionally drop specific images
within a folder that don't fit well with the rest (e.g. an outlier timepoint,
or one that's a different body region than the others).

For each folder, shows the outlined images side by side. You can:
  g = good  (segmentation looks reasonable, usable for demo)
  b = bad   (false positives like nails/ears/hair — skip for demo)
  d = drop specific image(s) from this folder, then re-tag the rest
  s = skip for now (decide later)
  q = quit (progress is saved, resume anytime)

Requires: pip install matplotlib pillow opencv-python
Run from project root: python3 Notebooks/curation_tool.py
"""

import json
from pathlib import Path

import cv2
import matplotlib.pyplot as plt

SEGMENTED_DIR = Path("Data/segmented")
CURATION_FILE = Path("Data/curation_labels.json")


def load_curation():
    if CURATION_FILE.exists():
        with open(CURATION_FILE, "r") as f:
            return json.load(f)
    return {}


def save_curation(labels):
    CURATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CURATION_FILE, "w") as f:
        json.dump(labels, f, indent=2)


def get_outlined_images(folder: Path):
    return sorted(folder.glob("outlined_*"))


def show_folder(folder_name: str, outlined_images, excluded=None):
    excluded = excluded or []
    n = len(outlined_images)
    if n == 0:
        return
    fig, axes = plt.subplots(1, n, figsize=(4 * n, 4))
    if n == 1:
        axes = [axes]
    for ax, img_path in zip(axes, outlined_images):
        img = cv2.cvtColor(cv2.imread(str(img_path)), cv2.COLOR_BGR2RGB)
        ax.imshow(img)
        label = img_path.name.replace("outlined_", "")
        title = f"[{label}]"
        if label in excluded:
            title += "\n(EXCLUDED)"
        ax.set_title(title, fontsize=8)
        ax.axis("off")
    fig.suptitle(f"Folder: {folder_name}")
    plt.tight_layout()
    plt.show(block=False)
    plt.pause(0.1)


def main():
    labels = load_curation()
    folders = [f for f in sorted(SEGMENTED_DIR.iterdir()) if f.is_dir()]
    total = len(folders)
    print(f"Found {total} segmented folders")
    print(f"Already curated: {len(labels)}\n")

    for i, folder in enumerate(folders):
        if folder.name in labels:
            continue

        outlined_images = get_outlined_images(folder)
        if not outlined_images:
            continue

        excluded = []

        while True:
            show_folder(folder.name, outlined_images, excluded)
            print(f"\n[{i+1}/{total}] Folder: {folder.name}  ({len(outlined_images)} images, {len(excluded)} excluded)")
            answer = input(
                "Tag — (g)ood / (b)ad / (d)rop an image / (s)kip / (q)uit: "
            ).strip().lower()
            plt.close("all")

            if answer == "q":
                print("Saving progress and quitting.")
                save_curation(labels)
                return

            elif answer == "d":
                available = [img.name.replace("outlined_", "") for img in outlined_images]
                print("Images in this folder:", ", ".join(available))
                to_drop = input("Enter the filename(s) to drop (comma-separated): ").strip()
                names_to_drop = [n.strip() for n in to_drop.split(",") if n.strip()]
                for name in names_to_drop:
                    if name in available and name not in excluded:
                        excluded.append(name)
                    else:
                        print(f"  (couldn't find '{name}' — check spelling)")
                # loop back and re-show the folder with updated exclusions

            elif answer in ("g", "b"):
                tag_map = {"g": "good", "b": "bad"}
                labels[folder.name] = {
                    "quality": tag_map[answer],
                    "excluded_images": excluded,
                }
                save_curation(labels)
                break

            elif answer == "s":
                break  # move on without saving a tag, will reappear next run

            else:
                print("Didn't recognize that input, try again.")

    good_count = sum(1 for v in labels.values() if v["quality"] == "good")
    bad_count = sum(1 for v in labels.values() if v["quality"] == "bad")
    print(f"\nDone for now. Tagged so far: {good_count} good, {bad_count} bad.")
    print(f"Saved to {CURATION_FILE}")


if __name__ == "__main__":
    main()
