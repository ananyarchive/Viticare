# VitiCare

**An AI-powered longitudinal monitoring platform for vitiligo — think "Fitbit for vitiligo."**

![Landing page](screenshots/landing.png)

Vitiligo diagnosis isn't the hard part — tracking whether treatment is actually working is. Patients spend months comparing photos taken under different lighting and angles, unsure if a patch is improving, spreading, or staying the same. VitiCare turns that guesswork into an objective, longitudinal record: a computer vision pipeline that measures real change over time, paired with an evidence-grounded research assistant that explains treatment options in plain language — never guessing, always citing real sources.

This is a portfolio/demo build (V1), not a production medical device. It's built on real clinical imaging data and real research literature, with honest documentation of where the current approach works well and where it doesn't yet.

---

## What it actually does

### 1. Computer Vision Pipeline (classical CV, no training required)
- **Image registration** — aligns photos of the same lesion taken at different times/angles (ORB feature matching + homography), with an automatic check that skips pairs from incompatible imaging types (e.g. a normal photo vs. a Wood's lamp/UV scan) rather than forcing a broken alignment.
- **Segmentation** — isolates the lesion region using GrabCut-based subject/background separation, local adaptive brightness thresholding, and shape-based filtering (rejecting thin/elongated false positives like nails or hair strands).
- **Fixed-reference progress tracking** — rather than re-detecting the lesion boundary independently on every photo (which is unreliable on fainter frames), the pipeline picks the clearest detection as a reference boundary and tracks brightness change within that exact region across all other timepoints. This produces a soft, semi-transparent heatmap overlay — green where repigmentation occurred, red where the lesion spread — scaled by how much change actually happened.

![Dashboard with repigmentation tracking](screenshots/dashboard.png)
![Heatmap close-up showing tracked regions](screenshots/heatmap-closeup.png)

### 2. Full-Stack Dashboard
- **FastAPI backend** serving curated patient timelines, images, and computed progress metrics
- **Next.js frontend** with a watercolor-themed landing page, patient portal, and a per-patient dashboard showing timeline, repigmentation %, and visual progress overlays

![Patient portal entry](screenshots/portal-entry.png)
![Patient portal options](screenshots/portal-options.png)

### 3. Agentic Research Assistant (RAG)
- **Real corpus**: 590 documents (420 PubMed abstracts + 170 ClinicalTrials.gov entries) covering vitiligo treatments — tacrolimus, phototherapy, JAK inhibitors, corticosteroids, surgical options, and more — embedded into **1,080 chunks** via Voyage AI, stored in **Postgres + pgvector**.
- **Tool-calling agent**: given a question, the model (Groq-hosted `llama-3.3-70b-versatile`) decides whether to search PubMed evidence, ClinicalTrials evidence, or both, retrieves real passages, and only then synthesizes an answer — never from memory alone.
- **Plain-language by design**: every answer is structured as *what it is → what the evidence shows → worth knowing → sources*, deliberately avoiding front-loaded clinical jargon or alarming side-effect lists, without sacrificing honesty about evidence strength or limitations.

![Research chat interface](screenshots/chat.png)

### 4. Multi-Agent Orchestration (Vision + Research + Report)
A single FastAPI endpoint, `POST /patients/{id}/full-report`, chains three agents in sequence to turn raw tracking data into a doctor-visit-ready summary:

1. **Vision Agent** — the CV pipeline above (registration → segmentation → progress tracking); the orchestrator just reads its already-computed output, it doesn't re-run the pipeline per request.
2. **Research Agent** — the RAG agent above; runs only if the caller supplies a `treatment_question` relevant to the patient's case, and is skipped entirely otherwise.
3. **Report Agent** (`Backend/report_agent.py`, new) — a Groq-hosted LLM call that synthesizes the Vision Agent's timeline/progress stats and (if present) the Research Agent's grounded answer into a markdown report: an overview, a plain-language progress summary, relevant research context, and data-informed questions to bring to a doctor. It's instructed to never invent numbers not present in the input.

Every stage is timed with `time.perf_counter()` and the real breakdown is returned in the response — see [Multi-Agent Latency](#multi-agent-latency-measured) below for actual measured numbers, not assumed ones.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js, React, TypeScript, TailwindCSS |
| Backend | FastAPI, Python |
| Database | PostgreSQL + pgvector |
| Computer Vision | OpenCV (GrabCut, adaptive thresholding, ORB feature matching) |
| Embeddings | Voyage AI (voyage-3) |
| LLM (research + report agents) | Groq (`llama-3.3-70b-versatile`; `llama-3.1-8b-instant` for eval judging) |
| Data Sources | NCBI PubMed E-utilities API, ClinicalTrials.gov API v2 |

---

## Evaluation: Retrieval Quality (Context Precision)

Using a RAGAS-style LLM-as-judge methodology: for each test question, the top-5 retrieved chunks are independently judged for genuine relevance (not just topical similarity), and precision = relevant / retrieved.

**Full results: 30 questions, stratified 5-per-category across the six treatment types actually present in the corpus** (`Backend/evaluate_retrieval.py`, results in `Backend/eval_results.json`):

| Category | Precision |
|---|---|
| Tacrolimus | 0.96 |
| Systemic / emerging | 0.96 |
| Corticosteroids | 0.92 |
| Surgical | 0.88 |
| Phototherapy | 0.84 |
| JAK inhibitors | 0.84 |
| **Overall (30 questions)** | **0.90** |

An earlier partial run (4 questions) had flagged a ruxolitinib/JAK-inhibitor question scoring 0.2, suspected to be thin corpus coverage. Before assuming that, the corpus was checked directly (`SELECT COUNT(*) FROM documents WHERE raw_text ILIKE '%ruxolitinib%'` → 47 matching documents) — coverage was not thin, so that low score reflected retrieval noise, not a data gap. The fuller 30-question stratified run confirms JAK inhibitors score in line with other categories (0.84), consistent with that diagnosis.

---

## Multi-Agent Latency (measured)

The `/patients/{id}/full-report` orchestrator endpoint's end-to-end latency was measured directly with `time.perf_counter()` around each agent stage (not assumed) across multiple real requests against the live backend:

| Scenario | Vision Agent | Research Agent | Report Agent | **Total** |
|---|---|---|---|---|
| Full pipeline (Vision + Research + Report), uncontended | ~0.01s | ~2.8s | ~1.3s | **~4.2s** (avg of 3 clean trials: 4.13s, 4.17s, 4.32s) |
| Vision + Report only (no `treatment_question` supplied) | ~0.01s | 0s (skipped) | ~1.2s | **~1.2s** (avg of 2 trials) |

**Two honest caveats, found by actually measuring instead of assuming:**
- **Latency is sensitive to Groq API contention.** Five back-to-back requests fired without spacing (competing with this session's own eval-harness run for the same rate limit) measured 10.9s–34.1s, averaging ~24.6s — over 5x the uncontended number. The architecture's own per-stage cost is genuinely ~4.2s; shared third-party rate limits are a real, separate operational risk worth knowing about before treating "~4.2s" as a hard guarantee under load.
- **The Groq-hosted model occasionally emits a malformed tool call** (observed in roughly 1 of 6 sampled requests) that fails Research Agent tool-call validation. The orchestrator catches this and degrades gracefully — it still returns a full report (Vision + Report only, research context omitted) rather than failing the request.

---

## Project Metrics Summary

All numbers below are measured from the actual pipeline/data/code in this repo, not aspirational — see the sections above for how each was computed.

| Area | Metric |
|---|---|
| CV pipeline — triage | 199 patient folders passed dataset triage |
| CV pipeline — registration | 246 compatible baseline→follow-up pairs attempted, 238 succeeded (**96.7%** success rate); 153 additional pairs correctly skipped as incompatible imaging types (e.g. normal photo vs. Wood's lamp scan) rather than forced into a broken alignment |
| CV pipeline — segmentation | 598 timepoints segmented across 199 folders; 129 timepoints have full fixed-reference progress/heatmap stats |
| CV pipeline — curation | 20 of 152 manually-reviewed patient folders marked demo-quality ("good") |
| Research corpus | 590 documents (420 PubMed + 170 ClinicalTrials.gov) → 1,080 embedded chunks (Voyage AI `voyage-3`) in Postgres + pgvector |
| Retrieval evaluation | **0.90 overall context precision** across 30 questions, stratified 5-per-category across 6 treatment types |
| Multi-agent orchestration | 3-agent pipeline (Vision → Research → Report) behind one FastAPI endpoint; **~4.2s measured end-to-end latency** uncontended, ~1.2s when the Research Agent stage is skipped |

---

## Resume / Portfolio Description

> Built VitiCare, a full-stack vitiligo-tracking platform combining a classical computer-vision pipeline (OpenCV registration + segmentation) with an evidence-grounded RAG research agent over a 590-document/1,080-chunk pgvector corpus, reaching **0.90 context precision** across a 30-question stratified evaluation. Architected a 3-agent FastAPI orchestration pipeline (Vision, Research, Report agents) that synthesizes doctor-visit-ready clinical summaries, measuring **~4.2s real end-to-end latency** via direct instrumentation. Achieved a **96.7% image-registration success rate** across a 199-patient longitudinal imaging dataset.

---

## Known Limitations & Roadmap

Being upfront about these is intentional — they reflect real engineering tradeoffs made under a defined timeline, not oversights.

- **Segmentation false positives**: classical thresholding correctly identifies "locally bright" regions, but Wood's lamp imaging causes other anatomical features (fingernails, ear cartilage) to fluoresce similarly to depigmented skin. Shape-based filtering reduces but doesn't eliminate this. **Planned V2**: manually annotate a labeled mask dataset and train/fine-tune a proper segmentation model to replace the classical thresholding approach.
- **2D registration limitations**: homography-based alignment handles translation/scale/in-plane rotation well, but not full 3D head/body pose changes between photos.
- **Orchestrator latency under API contention**: the ~4.2s measured full-pipeline latency holds under normal single-request conditions, but degrades significantly (measured 11–34s) when the Research Agent's calls compete with other concurrent Groq API usage against the same rate limit — see [Multi-Agent Latency](#multi-agent-latency-measured).
- **Intermittent malformed tool calls**: the Groq-hosted model occasionally emits a tool call the SDK can't validate, failing the Research Agent step for that request (~1 in 6 sampled). The orchestrator degrades gracefully rather than crashing, but the underlying model quirk isn't fixed.
- **Camera-guidance capture** (brightness/orientation/framing checks) and the consistency/streak engine are planned but not yet built in this version.
- **Not clinically validated**: this is a demo/portfolio project using public research data and a public clinical imaging dataset — not a diagnostic or medical device.

---

## Data Sources

- Clinical imaging: [AVRES-WL dataset](https://github.com/AIM-D/AVRES-WL) (pre/mid/post-treatment vitiligo lesion photos under Wood's lamp imaging)
- Research corpus: NCBI PubMed, ClinicalTrials.gov (public APIs, queried live during ingestion)

## Setup

See `Backend/`, `Frontend/`, and `Notebooks/` for component-specific setup. Requires PostgreSQL with the `pgvector` extension, a Voyage AI API key, and a Groq API key.

```bash
# Backend
pip3 install -r Backend/requirements.txt
psql viticare -f Backend/schema.sql
uvicorn Backend.main:app --reload --port 8000

# Frontend
cd Frontend && npm install && npm run dev
```

---

## License

MIT
