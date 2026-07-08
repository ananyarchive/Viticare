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
- **Tool-calling agent**: given a question, the model decides whether to search PubMed evidence, ClinicalTrials evidence, or both, retrieves real passages, and only then synthesizes an answer — never from memory alone.
- **Plain-language by design**: every answer is structured as *what it is → what the evidence shows → worth knowing → sources*, deliberately avoiding front-loaded clinical jargon or alarming side-effect lists, without sacrificing honesty about evidence strength or limitations.

![Research chat interface](screenshots/chat.png)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js, React, TypeScript, TailwindCSS |
| Backend | FastAPI, Python |
| Database | PostgreSQL + pgvector |
| Computer Vision | OpenCV (GrabCut, adaptive thresholding, ORB feature matching) |
| Embeddings | Voyage AI (voyage-3) |
| LLM (research agent) | Gemini 2.5 Flash (tool-calling / function-calling) |
| Data Sources | NCBI PubMed E-utilities API, ClinicalTrials.gov API v2 |

---

## Evaluation: Retrieval Quality (Context Precision)

Using a RAGAS-style LLM-as-judge methodology: for each test question, the top-5 retrieved chunks are independently judged for genuine relevance (not just topical similarity), and precision = relevant / retrieved.

**Partial results (4 of 15 test questions completed):**

| Question | Precision |
|---|---|
| Does tacrolimus work for treating vitiligo? | 1.0 |
| What is narrowband UVB phototherapy and how effective is it? | 0.8 |
| How does ruxolitinib cream work for repigmentation? | 0.2 |
| Are topical corticosteroids effective for vitiligo? | 1.0 |

**Average so far: 0.75.** Full 15-question evaluation is in progress (limited by free-tier API rate limits during development). The ruxolitinib result flags a genuine, identified weak spot — likely due to thinner corpus coverage on JAK inhibitors relative to more established treatments — and is a concrete, prioritized target for retrieval improvement (candidate fix: adding a reranking step, discussed below).

---

## Known Limitations & Roadmap

Being upfront about these is intentional — they reflect real engineering tradeoffs made under a defined timeline, not oversights.

- **Chat interface response handling**: the frontend chat currently has an intermittent issue displaying the agent's response after submission — under active debugging.
- **Segmentation false positives**: classical thresholding correctly identifies "locally bright" regions, but Wood's lamp imaging causes other anatomical features (fingernails, ear cartilage) to fluoresce similarly to depigmented skin. Shape-based filtering reduces but doesn't eliminate this. **Planned V2**: manually annotate a labeled mask dataset and train/fine-tune a proper segmentation model to replace the classical thresholding approach.
- **2D registration limitations**: homography-based alignment handles translation/scale/in-plane rotation well, but not full 3D head/body pose changes between photos.
- **Reference-frame selection**: the fixed-region tracking approach currently doesn't account for manually-curated exclusions when selecting which frame to use as the reference — an edge case to patch.
- **Retrieval precision on underrepresented topics** (e.g. ruxolitinib): candidate fix is adding a cross-encoder reranking step on top of vector similarity search.
- **Camera-guidance capture** (brightness/orientation/framing checks) and the consistency/streak engine are planned but not yet built in this version.
- **Not clinically validated**: this is a demo/portfolio project using public research data and a public clinical imaging dataset — not a diagnostic or medical device.

---

## Data Sources

- Clinical imaging: [AVRES-WL dataset](https://github.com/AIM-D/AVRES-WL) (pre/mid/post-treatment vitiligo lesion photos under Wood's lamp imaging)
- Research corpus: NCBI PubMed, ClinicalTrials.gov (public APIs, queried live during ingestion)

## Setup

See `Backend/`, `Frontend/`, and `Notebooks/` for component-specific setup. Requires PostgreSQL with the `pgvector` extension, a Voyage AI API key, and a Gemini API key.

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
