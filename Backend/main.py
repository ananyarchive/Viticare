"""
VitiCare Backend — FastAPI app

Serves curated patient folders (from Data/curation_labels.json, only
folders tagged "good") along with their images, heatmaps, and measurements
(from Data/segmented/segmentation_results.json).

This does NOT re-run any CV pipeline — it just reads what Notebooks/
already computed and exposes it over HTTP for the frontend to consume.

Run from project root: uvicorn Backend.main:app --reload --port 8000
Then visit http://localhost:8000/docs for interactive API docs.
"""

import json
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.append(str(Path(__file__).resolve().parent))
from research_agent import ask_research_agent  # noqa: E402

DATA_DIR = Path("Data")
SEGMENTED_DIR = DATA_DIR / "segmented"
CURATION_FILE = DATA_DIR / "curation_labels.json"
SEGMENTATION_RESULTS_FILE = SEGMENTED_DIR / "segmentation_results.json"

app = FastAPI(title="VitiCare API", version="0.1.0")

# Allow the frontend (running on a different port during development)
# to call this API directly from the browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this before real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the actual image files (photos, masks, heatmaps) as static files,
# so the frontend can just use an <img> tag pointing at these URLs
app.mount("/images", StaticFiles(directory=str(SEGMENTED_DIR)), name="images")


def load_curation():
    if not CURATION_FILE.exists():
        return {}
    with open(CURATION_FILE, "r") as f:
        return json.load(f)


def load_segmentation_results():
    if not SEGMENTATION_RESULTS_FILE.exists():
        return []
    with open(SEGMENTATION_RESULTS_FILE, "r") as f:
        return json.load(f)


def get_good_folder_names():
    curation = load_curation()
    return [name for name, info in curation.items() if info.get("quality") == "good"]


@app.get("/")
def root():
    return {
        "message": "VitiCare API is running",
        "docs": "/docs",
        "good_patient_folders": len(get_good_folder_names()),
    }


@app.get("/patients")
def list_patients():
    """
    Returns the list of curated 'good' patient folders — these are the
    ones verified during manual curation to have reasonable segmentation
    quality, safe to show in the demo dashboard.
    """
    good_names = get_good_folder_names()
    curation = load_curation()

    patients = []
    for name in good_names:
        excluded = curation[name].get("excluded_images", [])
        patients.append({
            "id": name,
            "excluded_images": excluded,
        })
    return {"patients": patients, "count": len(patients)}


@app.get("/patients/{patient_id}/timeline")
def get_patient_timeline(patient_id: str):
    """
    Returns the full timeline for one patient: each timepoint's image URL,
    outlined/segmented image URL, heatmap URL (if available), and the
    measurements computed during segmentation.
    """
    good_names = get_good_folder_names()
    if patient_id not in good_names:
        raise HTTPException(
            status_code=404,
            detail=f"Patient folder '{patient_id}' not found or not marked as curated/good.",
        )

    curation = load_curation()
    excluded = set(curation[patient_id].get("excluded_images", []))

    all_results = load_segmentation_results()
    folder_result = next((r for r in all_results if r["folder"] == patient_id), None)

    if folder_result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No segmentation results found for patient '{patient_id}'.",
        )

    timeline = []
    for tp in folder_result["timepoints"]:
        source_file = tp["source_file"]
        if source_file in excluded:
            continue  # respect manual exclusions from curation

        entry = {
            "source_file": source_file,
            "raw_image_url": f"/images/{patient_id}/{source_file}",
            "outlined_image_url": f"/images/{patient_id}/outlined_{source_file}",
            "mask_image_url": f"/images/{patient_id}/mask_{source_file}",
            "lesion_area_pct_of_image": tp.get("lesion_area_pct_of_image"),
            "num_regions_detected": tp.get("num_regions_detected"),
            "measurements": tp.get("measurements", []),
        }

        # Heatmap only exists for successfully-compared follow-up frames
        if "diff_vs_reference" in tp:
            entry["heatmap_image_url"] = f"/images/{patient_id}/heatmap_{source_file}"
            entry["progress_stats"] = tp["diff_vs_reference"]

        timeline.append(entry)

    return {
        "patient_id": patient_id,
        "timepoint_count": len(timeline),
        "timeline": timeline,
    }


class ResearchQuestion(BaseModel):
    question: str


@app.post("/research/ask")
def ask_research(payload: ResearchQuestion):
    """
    Runs the agentic RAG research agent: the LLM decides which evidence
    sources to search (PubMed / ClinicalTrials.gov embeddings in pgvector),
    retrieves relevant chunks, and synthesizes a cited, grounded answer.
    """
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    try:
        return ask_research_agent(payload.question)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Research agent failed: {e}")


@app.get("/patients/{patient_id}/summary")
def get_patient_summary(patient_id: str):
    """
    A quick-glance summary for a dashboard card: latest repigmentation %,
    number of timepoints, and overall trend direction.
    """
    timeline_response = get_patient_timeline(patient_id)
    timeline = timeline_response["timeline"]

    frames_with_progress = [tp for tp in timeline if "progress_stats" in tp]

    if not frames_with_progress:
        return {
            "patient_id": patient_id,
            "timepoint_count": len(timeline),
            "summary": "Not enough comparable timepoints to compute a trend yet.",
        }

    latest = frames_with_progress[-1]["progress_stats"]

    return {
        "patient_id": patient_id,
        "timepoint_count": len(timeline),
        "latest_repigmentation_pct": latest.get("repigmentation_pct_of_region"),
        "latest_mean_brightness_change": latest.get("mean_brightness_change"),
        "trend": "improving" if latest.get("mean_brightness_change", 0) < 0 else "progressing/stable",
    }
