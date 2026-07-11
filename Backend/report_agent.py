"""
VitiCare — Report Agent

The third agent in the pipeline: takes the Vision Agent's already-computed
CV output (timeline + progress stats) and, optionally, Research Agent
context, and synthesizes a doctor-visit-ready markdown summary — something
a patient can actually bring to an appointment instead of raw JSON.

Requires: pip3 install groq python-dotenv
"""

import os
import sys
import json

from groq import Groq
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not set. Add it to your .env file.")

groq_client = Groq(api_key=GROQ_API_KEY)
MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are VitiCare's report-writing assistant. You turn a patient's \
computer-vision tracking data (and, if provided, relevant treatment research) into a \
concise, doctor-visit-ready summary — something a patient can print or pull up on their \
phone during an appointment.

CRITICAL RULES:
- Only use the data given to you. Never invent measurements, dates, or research findings \
that aren't present in the input.
- If the data is sparse (few timepoints, no clear trend), say so honestly rather than \
overstating confidence.
- Write for the patient, not a clinician — plain language, calm tone.

Structure the report in markdown with these sections, in this order:
1. **Overview** — how many timepoints were tracked, over what span
2. **Progress Summary** — what the tracked lesion area/brightness data shows in plain terms \
(improving, stable, spreading, or unclear), citing the actual numbers given
3. **Relevant Research Context** — only include this section if research context was \
provided; summarize it in 2-3 sentences relevant to this patient's situation
4. **Questions to Bring to Your Doctor** — 2-4 specific, data-informed questions based on \
what the tracking data actually shows
"""


def _compact_timeline(timeline: list) -> list:
    """Strips image URLs etc, keeping only the numeric data the report needs."""
    compact = []
    for tp in timeline:
        entry = {
            "source_file": tp.get("source_file"),
            "lesion_area_pct_of_image": tp.get("lesion_area_pct_of_image"),
            "num_regions_detected": tp.get("num_regions_detected"),
        }
        if "progress_stats" in tp:
            entry["progress_stats"] = tp["progress_stats"]
        compact.append(entry)
    return compact


def generate_report(patient_id: str, timeline: list, summary: dict, research_context: str = None) -> str:
    """
    Synthesizes the final markdown report.

    timeline: the "timeline" list from GET /patients/{id}/timeline (Vision Agent output)
    summary: the dict from GET /patients/{id}/summary (Vision Agent output)
    research_context: optional plain-text answer from the Research Agent, if a
        treatment question was relevant to this patient
    """
    prompt_parts = [
        f"Patient ID: {patient_id}",
        "",
        "VISION AGENT TIMELINE DATA (tracked lesion measurements over time):",
        json.dumps(_compact_timeline(timeline), indent=2),
        "",
        "VISION AGENT SUMMARY:",
        json.dumps(summary, indent=2),
    ]
    if research_context:
        prompt_parts += ["", "RESEARCH AGENT CONTEXT (relevant treatment evidence):", research_context]

    response = groq_client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(prompt_parts)},
        ],
    )
    return response.choices[0].message.content


if __name__ == "__main__":
    # Quick manual smoke test with fabricated data
    fake_timeline = [
        {"source_file": "t0.jpg", "lesion_area_pct_of_image": 2.1, "num_regions_detected": 1},
        {"source_file": "t1.jpg", "lesion_area_pct_of_image": 1.4, "num_regions_detected": 1,
         "progress_stats": {"repigmentation_pct_of_region": 33.0, "mean_brightness_change": -12.5}},
    ]
    fake_summary = {"patient_id": "demo", "timepoint_count": 2, "latest_repigmentation_pct": 33.0, "trend": "improving"}
    print(generate_report("demo", fake_timeline, fake_summary))
