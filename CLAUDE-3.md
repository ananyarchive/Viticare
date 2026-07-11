# VitiCare — Project Status & Handoff (CLAUDE.md)

Read this fully before doing anything. This reflects the ACTUAL current state as of the handoff to Claude Code — the project is substantially built, not starting from scratch. Update the Progress Log at the bottom after every session.

## Deadline
Final polished version needed by **July 14**. The person will check in roughly hourly — work in small, verifiable increments, commit after each working change, and leave clear notes on what changed and why.

## Current Architecture (already built and working)

- **Backend**: FastAPI (`Backend/main.py`) serving curated patient data from Postgres
- **Database**: PostgreSQL + pgvector (`viticare` db). Tables: `documents`, `chunks`, `research_queries` (schema in `Backend/schema.sql`)
- **CV Pipeline** (`Notebooks/`): dataset triage (`triage_tool.py`) → registration (`registration.py`) → segmentation + fixed-reference progress tracking (`segmentation.py`) → curation (`curation_tool.py`). Outputs live in `Data/registered/` and `Data/segmented/`, with `Data/curation_labels.json` marking which patient folders are demo-quality ("good").
- **RAG Research Agent** (`Backend/research_agent.py`): tool-calling agent. **SWITCH FROM GEMINI TO GROQ** — Gemini's free tier (5 RPM, tight daily cap) was too restrictive for development velocity. Groq (console.groq.com, no card required) gives 30 RPM and is OpenAI-SDK-compatible. Use `llama-3.3-70b-versatile` for the main agent (better reasoning quality); if its daily cap (~1,000/day) is hit during the eval harness, fall back to `llama-3.1-8b-instant` (14,400/day) for judge calls specifically, since those don't need top-tier reasoning. Retrieves from a real corpus: 590 documents / 1,080 chunks (PubMed + ClinicalTrials.gov), embedded via Voyage AI.
- **Evaluation harness** (`Backend/evaluate_retrieval.py`): RAGAS-style context precision eval. Currently 4 of 15 test questions completed (avg 0.75). **Expand to 25-30 questions**, stratified across actual treatment categories in the corpus (a few questions per drug/therapy type — tacrolimus, phototherapy, JAK inhibitors, corticosteroids, surgical, systemic/emerging) rather than an arbitrary 15 — this gives a more defensible "stratified sample" claim.
- **NEW: Multi-agent orchestration layer.** The person wants this specific resume bullet to be true, not aspirational:
  > "Architected a multi-agent orchestration framework via FastAPI to automate clinical workflows, deploying Vision, Research, and Report Agents to achieve sub-5s end-to-end report generation."

  To make this real:
  1. **Vision Agent** = the existing CV pipeline (registration + segmentation + progress tracking), already built.
  2. **Research Agent** = the existing RAG agent, already built.
  3. **Report Agent** (NEW, build this) = synthesizes a doctor-visit-ready summary from a patient's timeline data + progress stats + (optionally) relevant research context — a markdown or PDF summary, not just raw JSON.
  4. **Orchestrator** (NEW, build this) = a FastAPI endpoint (e.g. `POST /patients/{id}/full-report`) that calls Vision Agent output (already computed, just reads it), Research Agent (if relevant treatment questions apply), and Report Agent in sequence, returning one consolidated report.
  5. **CRITICAL — benchmark honestly.** Actually measure end-to-end latency for this endpoint (e.g. with `time.perf_counter()` around the full call, logged and reported). Only keep the "sub-5s" claim in the README/resume bullet if it's genuinely true. If it's not sub-5s, report the real number instead — an honest number is better than a false claim that falls apart under interview questioning.
- **Frontend** (`Frontend/app/`): Next.js. Routes: `/` (watercolor landing page), `/portal` (patient ID entry + option cards), `/dashboard` (patient list + timeline + heatmaps), `/chat` (research agent chat UI). Font pairing: Fraunces (display/serif) + Inter (sans) + Pinyon Script (cursive "V" in logo). Color palette: warm beige/cream background (#F3F1E7, #FBF9F4), sage green (#4B5A3E, #DCE3D0), soft brown accents (#8A6E4E).

## KNOWN BUGS — fix these first, in priority order

1. **Chat page doesn't display a response after asking a question.** The person confirmed this is broken. Debug steps: check browser console for errors, check `uvicorn` terminal output when a question is submitted, test the backend directly with `curl -X POST http://localhost:8000/research/ask -H "Content-Type: application/json" -d '{"question": "test"}'`. Likely candidates: CORS, response shape mismatch between backend and frontend `Message` interface, or the agent call itself failing/timing out silently.
2. **Reference-frame selection in segmentation doesn't account for curation exclusions** — if a folder's reference frame was one of the manually-excluded images, downstream comparisons break. Check `Notebooks/segmentation.py`'s `pick_reference_frame`.

## IN-PROGRESS WORK — pick up where left off

- **Switch research agent + eval harness from Gemini to Groq** (see architecture note above) — this removes the daily quota bottleneck that stalled evaluation progress.
- **Complete the expanded 25-30 question context precision evaluation** using Groq's much higher rate limits. Previous partial Gemini results (4/15, avg 0.75) can be discarded/redone cleanly now that quota isn't a blocker.
- **Add a reranking step** to push context precision toward the person's target of 0.89+. The earlier `ruxolitinib` question scored only 0.2 under partial testing — investigate whether the corpus has thin coverage there (`SELECT COUNT(*) FROM documents WHERE raw_text ILIKE '%ruxolitinib%';`) before assuming reranking alone fixes it — may need targeted re-ingestion for underrepresented topics too.
- **Build the Report Agent + Orchestrator** (see architecture note above) — this is a priority item, needed for the resume bullet the person wants to be genuinely true, including honest latency benchmarking.
- **Send/collect the person's own test questions** for tone/supportiveness testing (separate from precision eval) — realistic patient questions like "will this ever go away," "is it my fault," anxious/uninformed phrasing — and verify the agent's system prompt (in `research_agent.py`) handles them warmly, not clinically. This is a qualitative review, not a scored metric.

## NOT YET BUILT (roadmap, build if time allows after bugs + eval are solid)

- Camera guidance (brightness/orientation/framing checks for live capture) — rule-based, no ML needed, frontend-only feature
- Consistency/streak engine (medication reminders, daily check-in tracking) — plain backend CRUD, no AI
- `/updates` page (linked from the portal but not built yet — will 404 currently)
- Video/reel remedy extraction (transcribe + extract treatment claims) — deferred, lower priority than fixing what exists

## Explicitly deferred to a future V2 (documented in README, not to build now unless asked)

- Trained/fine-tuned segmentation model to replace classical thresholding (needs manual mask annotation first — the person wants to do this "wholeheartedly" as a dedicated future effort, not squeezed into this deadline)
- Full production security/auth hardening, HIPAA-level compliance
- Multi-disease support beyond vitiligo

## Working rules (same as original, still apply)

1. Work in small, verifiable increments — one bug or feature at a time.
2. After every change, explain in plain English what was done and what could break.
3. Never report a metric without showing the exact code that computed it.
4. Commit to git after every verified working increment, with clear messages.
5. Flag scope creep — if a request pulls in an explicitly-deferred V2 item, point it out before building it.
6. Since the person is stepping away to focus on DSA prep and checking in hourly: leave a clear, short status note after each work session (what changed, what's next, anything that needs their input/decision) so they can catch up in under a minute.
7. Don't break what's already working. Test existing functionality isn't broken before considering a change complete — the CV pipeline, backend endpoints, and existing frontend pages all currently work; regressions are worse than slow progress.

## Environment notes (avoid re-learning these the hard way)

- Two Python environments exist: `venv/` (correct, has all packages) and `.venv/` (leftover from Next.js scaffolding, empty — do not use). Always activate `venv/`.
- `.env` in project root holds `VOYAGE_API_KEY` and `GROQ_API_KEY` (Gemini key can stay too but is no longer used — Groq replaced it, see architecture notes above). Never commit this (already gitignored).
- Postgres database name: `viticare`. pgvector extension is installed and working.
- Backend run command: `uvicorn Backend.main:app --reload --port 8000` (from project root)
- Frontend run command: `cd Frontend && npm run dev`
- This machine has previously had issues with trailing spaces in folder names created via Finder/Save dialogs — if a `cp`/`mv`/`cd` mysteriously fails with "No such file or directory," check for trailing spaces with `ls -la | cat -A`.

## Progress Log
(Append what was completed at the end of each session)

### 2026-07-12 session
- **Eval harness expanded to 30 questions**, stratified 5-per-category across tacrolimus, phototherapy, JAK inhibitors, corticosteroids, surgical, systemic/emerging (`Backend/evaluate_retrieval.py`). Ran to completion on Groq — **overall context precision 0.90**, all categories ≥0.84 (`Backend/eval_results.json`). Checked corpus coverage for ruxolitinib before assuming reranking was needed (47 matching documents — not thin); the fuller stratified run shows JAK inhibitors in line with other categories (0.84), so the earlier 0.2 partial-run score looks like retrieval noise on a single question, not a data gap. Reranking was not implemented this session (out of scope for the requested task list).
- **Built Report Agent** (`Backend/report_agent.py`, new) — Groq LLM call that synthesizes Vision Agent timeline/progress stats + optional Research Agent context into a doctor-visit-ready markdown report (overview, progress summary, research context, doctor questions). Instructed to never invent data not in the input.
- **Built Orchestrator endpoint** `POST /patients/{id}/full-report` (`Backend/main.py`) — chains Vision Agent (reads existing CV output) → Research Agent (only if `treatment_question` supplied) → Report Agent, with real `time.perf_counter()` timing per stage returned in the response.
- **Measured real end-to-end latency**: ~4.2s uncontended full pipeline (avg of 3 clean trials), ~1.2s when Research Agent is skipped. Found two honest caveats while measuring rather than assuming: (1) latency degrades to ~11–34s under Groq API contention (e.g. concurrent eval-harness load) — a real shared-rate-limit risk, not an architecture cost; (2) the Groq model occasionally emits a malformed tool call (~1/6 sampled) that fails the Research Agent step — the orchestrator already degrades gracefully (falls back to Vision+Report only) rather than crashing.
- **Compiled real project metrics** (CV pipeline: 199 triaged folders, 96.7% registration success rate among compatible pairs, 598 timepoints segmented, 20/152 curated "good"; corpus: 590 docs/1,080 chunks; eval: 0.90 precision; latency: ~4.2s) and wrote a quantified, non-aspirational resume bullet from them.
- **Updated README**: full 30-question eval table, new Multi-Agent Orchestration + Multi-Agent Latency + Project Metrics Summary + Resume/Portfolio Description sections. Also corrected stale content found along the way: Tech Stack still said Gemini (switched to Groq last session per commit `a3e7205`) — fixed; Known Limitations still listed the chat-response bug and the reference-frame/curation-exclusion bug as open — both were already fixed per commits `37b2160` and `a6458fe`, so removed and replaced with the two latency/reliability caveats found this session.
- **Did not touch**: any frontend/UI styling (explicitly out of scope this session), reranking (not on this session's task list, flagging it's still open per the in-progress notes above).
- **Next up / needs a decision**: whether to invest in a reranking step now that corpus-thinness is ruled out as the cause of the earlier low JAK-inhibitor score (may not be needed — 0.84 is already solid); whether to add retry/backoff around the Research Agent's malformed-tool-call failure mode; qualitative tone-testing of the research agent on anxious/informal patient phrasing (still not done, per earlier in-progress note).
