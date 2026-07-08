"""
VitiCare — Dataset Triage Tool
Run this to go through each patient folder in the AVRES-WL dataset and tag it as:
  c = clean (same patient/lesion, consistent, plausible timeline)
  m = mixed (different patients/lesions in one folder — do not use)
  a = ambiguous (unclear — skip for now)
  s = skip without tagging (decide later)
  q = quit (progress is saved, you can resume later)

Requires: pip install matplotlib pillow
Run from your project root: python notebooks/triage_tool.py
"""

import json
import os
from pathlib import Path

import matplotlib.pyplot as plt
from PIL import Image

DATASET_DIR = Path("data/raw/AVRES-WL")
LABELS_FILE = Path("data/triage_labels.json")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}


def load_labels():
    if LABELS_FILE.exists():
        with open(LABELS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_labels(labels):
    LABELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LABELS_FILE, "w") as f:
        json.dump(labels, f, indent=2)


def get_patient_folders():
    if not DATASET_DIR.exists():
        raise FileNotFoundError(
            f"Could not find {DATASET_DIR}. Make sure you've cloned the dataset "
            f"into data/raw/AVRES-WL first."
        )
    folders = [f for f in sorted(DATASET_DIR.iterdir()) if f.is_dir()]
    return folders


def get_images_in_folder(folder: Path):
    images = [
        f for f in sorted(folder.iterdir())
        if f.suffix.lower() in IMAGE_EXTENSIONS
    ]
    return images


def show_folder(folder: Path, images: list):
    n = len(images)
    fig, axes = plt.subplots(1, n, figsize=(4 * n, 4))
    if n == 1:
        axes = [axes]
    for ax, img_path in zip(axes, images):
        img = Image.open(img_path)
        ax.imshow(img)
        ax.set_title(img_path.name, fontsize=8)
        ax.axis("off")
    fig.suptitle(f"Folder: {folder.name}  ({n} images)")
    plt.tight_layout()
    plt.show(block=False)
    plt.pause(0.1)


def main():
    labels = load_labels()
    folders = get_patient_folders()
    total = len(folders)
    print(f"Found {total} folders in {DATASET_DIR}")
    print(f"Already tagged: {len(labels)}\n")

    for i, folder in enumerate(folders):
        if folder.name in labels:
            continue  # already tagged, skip

        images = get_images_in_folder(folder)
        if not images:
            print(f"[{i+1}/{total}] {folder.name}: no images found, skipping")
            continue

        show_folder(folder, images)

        print(f"\n[{i+1}/{total}] Folder: {folder.name}  ({len(images)} images)")
        answer = input("Tag this folder — (c)lean / (m)ixed / (a)mbiguous / (s)kip / (q)uit: ").strip().lower()
        plt.close("all")

        if answer == "q":
            print("Saving progress and quitting.")
            save_labels(labels)
            break
        elif answer in ("c", "m", "a"):
            tag_map = {"c": "clean", "m": "mixed", "a": "ambiguous"}
            labels[folder.name] = tag_map[answer]
            save_labels(labels)  # save after every tag, so nothing is lost
        else:
            print("Skipped without tagging (will show again next run).")

    clean_count = sum(1 for v in labels.values() if v == "clean")
    mixed_count = sum(1 for v in labels.values() if v == "mixed")
    ambiguous_count = sum(1 for v in labels.values() if v == "ambiguous")
    print(f"\nDone for now. Tagged so far: {clean_count} clean, {mixed_count} mixed, {ambiguous_count} ambiguous.")
    print(f"Labels saved to {LABELS_FILE}")


if __name__ == "__main__":
    main()
