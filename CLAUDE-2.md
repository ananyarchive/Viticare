# VitiCare — Project Blueprint (CLAUDE.md)

This file is the source of truth for this project. Read it fully before making changes. Update the "Decisions Log" and "Progress Log" sections at the end of every work session.

## Vision

VitiCare is a longitudinal disease-monitoring platform for vitiligo. It is NOT a diagnosis app — diagnosis already happened. The problem is tracking whether treatment is working over time, objectively, across photos taken under inconsistent lighting/angles.

This is a portfolio/demo build (V1), using the AVRES-WL public dataset (github.com/AIM-D/AVRES-WL — pre/mid/post treatment vitiligo lesion photos under Wood's lamp imaging, from a retrospective repigmentation study), built in ~1 week, prioritizing:
1. A real, measured computer vision pipeline (registration + segmentation + tracking + scoring)
2. A real agentic RAG research assistant (tool-calling, citation-backed)
3. A deployed, working full-stack app

Explicitly OUT of scope for V1 (do not build unless asked): community layer, doctor PDF report generation, consistency/streak engine, multi-disease support, production-grade auth/security hardening, HIPAA compliance. Note these as "future roadmap" in the README, don't build them.

## Human-in-the-loop working rules (IMPORTANT — read every session)

The person directing this project is a strong product thinker but does not write code themselves. As Claude Code, you must:

1. **Work in small, single-purpose increments.** One feature or one endpoint at a time. Never implement multiple unrelated features in one pass.
2. **After every increment, explain in plain English** what you built, what it does, and what could break. Assume no prior codebase familiarity.
3. **Never report a metric, accuracy number, or performance figure without showing the exact code/script that computed it.** The person will re-run it themselves. Fabricated or estimated metrics are not acceptable — if something can't be measured yet, say so explicitly.
4. **Commit to git after every verified working increment**, with a clear commit message. Do not let unverified changes stack up.
5. **Ask before making architecture decisions that trade off cost, complexity, or time** (e.g. "use SAM2 vs fine-tune a U-Net" or "Railway vs Azure for deploy speed"). Present the tradeoff briefly, let the person choose.
6. **After every architectural or non-trivial decision, append one line to the Decisions Log below** — what was decided and why. This will be used for resume writing and interview prep later, so keep it factual and specific.
7. **Flag scope creep.** If a request would pull in an out-of-scope feature (see above), point it out before building it.
8. **No unnecessary AI.** If something can be plain backend logic (e.g. area-change % calculation, adherence tracking), do not route it through an LLM call.

## Tech Stack

- Frontend: Next.js, React, TypeScript, TailwindCSS
- Backend: FastAPI, Python, SQLAlchemy, Pydantic
- Database: PostgreSQL + pgvector
- Storage: local disk for V1 (swap to S3/Azure Blob later if time allows)
- Computer Vision: PyTorch, OpenCV, SAM2 (or lightweight U-Net fallback), torchvision
- LLM: Claude (Anthropic API) via Claude Sonnet, tool use / function calling
- RAG: Voyage AI embeddings, pgvector for retrieval
- Deployment: Railway or Render (backend + DB), Vercel (frontend) — fastest path to a live link; Azure migration is future roadmap, not V1
- Auth: skip or minimal (single demo user) for V1

## Dataset Notes (AVRES-WL)

- Location: `data/raw/AVRES-WL/` (cloned from GitHub, gitignored — not pushed to our own repo)
- Structure: one folder per patient/lesion, containing 2-4 images (not consistently named), sorted chronologically by filename/date order
- Treat the first image in a sorted folder as baseline (t0), each subsequent image as a follow-up timepoint (t1, t2, t3...). Do NOT hardcode for exactly 2 images — pipeline must support N timepoints per folder.
- These are Wood's lamp (UV) clinical images, not normal phone photos. This is an important honesty point for the README: the core algorithm (registration, segmentation, progress scoring) is validated on this clinical dataset; it is a SEPARATE, unvalidated claim to say it works equally well on normal-light phone photos. Do not imply the model was trained/tested on phone images.
- No pixel-level segmentation masks provided — masks must be self-generated (e.g. SAM2-prompted) and manually spot-checked. Report any IoU/Dice metrics as measured against this self-verified pseudo-ground-truth, and say so explicitly in the README. Do not call it clinically validated ground truth.
- Do not redistribute the raw dataset images in our own public repo. Link to the source repo instead.
- Before building the full pipeline, manually spot-check a couple of 3-4 image folders to confirm chronological ordering looks visually correct (earlier image = more depigmented, later = more repigmented).
- **KNOWN DATA QUALITY ISSUE — mixed patients within folders:** some folders contain images from different patients/lesions mixed together, not a single clean timeline. This MUST be triaged before any registration/tracking/metrics work — running the pipeline across mismatched images would produce meaningless, effectively fabricated results.

### Required Day 1 task: Dataset triage tool (before any CV pipeline work)

Build a simple local script/notebook that displays each patient folder's images side by side in a grid (basic matplotlib/PIL grid viewer is enough — no need for a full UI). The person (non-clinical, but knows what to look for) will go through folders manually and tag each one as:
- `clean` — same patient, same lesion, consistent body region/framing/skin tone across all images, plausible gradual change over time
- `mixed` — images clearly do not belong to the same patient/lesion (different body region, discontinuous lesion shape, inconsistent skin tone/lighting) — do not use
- `ambiguous` — unclear, skip for V1

Save these tags to a simple CSV/JSON (e.g. `data/triage_labels.json`) mapping folder name → tag. Only `clean` folders should be used in the vision pipeline going forward.

Target: aim for 15-25 verified `clean` folders, prioritizing any with 3-4 timepoints (strongest demo case for showing progress over time). Do not attempt to triage or use the entire dataset — this is a scoped subset for a portfolio demo, not exhaustive data cleaning.

Document this triage step and its results explicitly in the README as a real data engineering decision (e.g. "N of M folders were manually verified as clean single-patient timelines from the public dataset and used for the core pipeline") — this is a legitimate, honest part of the project story, not something to hide.

## Camera Guidance vs Core Algorithm (important scoping note)

These are two SEPARATE components, not one unified trained system:
1. **Core CV pipeline** (registration, segmentation, tracking, progress scoring) — built and validated against AVRES-WL clinical images only.
2. **Live camera guidance** (brightness/orientation/framing checks during capture) — a rule-based, dataset-free feature that runs on the live camera feed. It does not require training and is not fit to the AVRES-WL dataset. It uses simple heuristics (histogram brightness check, device orientation/basic frame analysis, MediaPipe or similar for body/region framing) — no custom model training needed here.

Do NOT attempt to build a UV/Wood's-lamp image style transfer or domain translation model to bridge these two. That is out of scope — too complex for the timeline and not necessary. State clearly in the README that phone-photo generalization of the core algorithm is future work, not yet validated.

## Data Model (core entities)

```
Patient
  └─ BodyRegion (e.g. left forearm, face)
       └─ Lesion (tracked across time, has an ID)
            ├─ Measurement (area, VASI-style score, timestamp)
            └─ Image (raw upload, registered/aligned version, mask overlay)
```

Key tables (adjust as needed, but keep lesion as a first-class tracked object, not just "photo #N"):
- `patients`
- `body_regions`
- `images` (patient_id, region_id, file_path, captured_at, registration_reference_image_id nullable)
- `lesions` (region_id, first_seen_image_id, status: active/resolved)
- `measurements` (lesion_id, image_id, area_px, area_pct_of_region, vasi_score, iou_vs_previous)
- `research_queries` (question, retrieved_doc_ids, answer, citations, created_at) — for the RAG agent

## Vision Pipeline (build order)

1. Image registration: align each pair of consecutive timepoints within a patient folder (t0→t1, t1→t2, etc.) using OpenCV feature matching / homography
2. Segmentation: produce a lesion mask per image (SAM2-prompted or lightweight model), since no ground-truth masks are provided in the dataset
3. Metrics: manually verify/correct masks on a small subset, then compute IoU/Dice against that self-verified subset — report this honestly as "self-verified pseudo-ground-truth," not clinical ground truth
4. Area-change % and a VASI-style score between each consecutive pair of timepoints
5. Basic tracking: match lesions across all available timepoints in a folder (2, 3, or 4) via IoU overlap, assign persistent lesion IDs — do not hardcode to a fixed number of timepoints
6. For folders with 3-4 timepoints, build the fuller timeline view first — this is the strongest demo case ("progress over time," not just before/after)

No LLM involvement in this pipeline. Pure CV/backend logic.

## Agentic Research Agent (build order)

1. Ingest a corpus: PubMed abstracts + ClinicalTrials.gov entries relevant to vitiligo treatments (public APIs, no auth needed for basic access)
2. Embed corpus with Voyage AI embeddings into pgvector
3. Build two tools the agent can call: `search_pubmed(query)`, `search_clinical_trials(query)`
4. Orchestrator: takes user question → agent decides which tool(s) to call → retrieves → ranks → Claude synthesizes an answer
5. Answer format must include: mechanism, strength of evidence, limitations, citations. Never answer from Claude's own memory — always ground in retrieved docs.
6. Log every query/answer/citations to `research_queries` table (this becomes a demo-able audit trail)

## Camera Guidance (frontend)

- Real-time checks before allowing capture: brightness (histogram-based), orientation (device orientation API or simple frame analysis), distance/framing (basic heuristic, not ML)
- Compare against previous capture's conditions where possible
- This is heuristic engineering, not ML — keep it simple and explainable

## Metrics to actually measure and report (only these, only if verified)

- [ ] Segmentation IoU/Dice on held-out test set
- [ ] Registration alignment error (pixel offset before/after)
- [ ] Number of documents embedded in RAG corpus
- [ ] RAG retrieval + response latency
- [ ] API response latency (upload → processed result)

Do not report anything not in this list without discussing it first.

## Deploy Checklist (Day 7)

- [ ] Backend deployed (Railway/Render), env vars set, DB migrated
- [ ] Frontend deployed (Vercel), pointed at deployed backend
- [ ] End-to-end smoke test on the live URL, not just localhost
- [ ] README written: architecture diagram (text is fine), setup instructions, measured metrics, roadmap/future work section

---

## Decisions Log
(Append one line per decision, in the format: `YYYY-MM-DD — decision — reason`)

## Progress Log
(Append what was completed at the end of each session, in the format: `Day N — what was built — what was verified — what's still broken`)
