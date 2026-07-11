"""
VitiCare — Retrieval Evaluation Harness (Context Precision)

Measures context precision: of the chunks retrieved for a given question,
what fraction are actually relevant to answering it? This is the standard
RAGAS-style metric for judging retrieval quality (not answer quality).

For each test question:
  1. Retrieve top-k chunks (same retrieval used by the real agent)
  2. Ask Claude (as an impartial judge) to rate each chunk's relevance
  3. Precision = (# relevant chunks) / (# retrieved chunks)

Overall context precision = average across all test questions.

Requires: pip3 install groq voyageai python-dotenv psycopg2-binary pgvector
Run from project root: python3 Backend/evaluate_retrieval.py
"""

import os
import sys
import json
import time

from groq import Groq, RateLimitError
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from research_agent import search_by_source, embed_query  # noqa: E402
from db import similarity_search  # noqa: E402

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY)
# Judge calls don't need top-tier reasoning, so they use the smaller/faster
# instant model — this keeps them off the main agent's daily quota.
JUDGE_MODEL = "llama-3.1-8b-instant"

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval_results.json")

TOP_K = 5

# Stratified test set: 5 questions per treatment category actually present in
# the corpus (tacrolimus, phototherapy, JAK inhibitors, corticosteroids,
# surgical, systemic/emerging), rather than an arbitrary/unstratified list —
# this makes the "stratified sample" claim defensible.
TEST_QUESTIONS = [
    # --- Tacrolimus ---
    {"category": "tacrolimus", "question": "Does tacrolimus work for treating vitiligo?"},
    {"category": "tacrolimus", "question": "Is topical tacrolimus more effective for facial and neck vitiligo than for lesions on the body?"},
    {"category": "tacrolimus", "question": "How does tacrolimus ointment compare to topical corticosteroids in effectiveness for vitiligo?"},
    {"category": "tacrolimus", "question": "Is long-term tacrolimus use considered safe for children with vitiligo?"},
    {"category": "tacrolimus", "question": "Does combining tacrolimus with phototherapy improve repigmentation compared to tacrolimus alone?"},

    # --- Phototherapy ---
    {"category": "phototherapy", "question": "What is narrowband UVB phototherapy and how effective is it for vitiligo?"},
    {"category": "phototherapy", "question": "How effective is excimer laser treatment for vitiligo compared to other phototherapy options?"},
    {"category": "phototherapy", "question": "What is PUVA therapy and how does it compare to narrowband UVB for treating vitiligo?"},
    {"category": "phototherapy", "question": "How many phototherapy sessions are typically needed before visible repigmentation appears?"},
    {"category": "phototherapy", "question": "Does combining phototherapy with topical treatments work better than either approach alone?"},

    # --- JAK inhibitors ---
    {"category": "jak_inhibitors", "question": "How does ruxolitinib cream work for vitiligo repigmentation?"},
    {"category": "jak_inhibitors", "question": "What were the results of the TRuE-V phase 3 clinical trials for ruxolitinib cream?"},
    {"category": "jak_inhibitors", "question": "Are oral JAK inhibitors being studied as a treatment for vitiligo?"},
    {"category": "jak_inhibitors", "question": "What side effects are associated with topical ruxolitinib cream for vitiligo?"},
    {"category": "jak_inhibitors", "question": "How does ritlecitinib compare to ruxolitinib for treating vitiligo?"},

    # --- Corticosteroids ---
    {"category": "corticosteroids", "question": "Are topical corticosteroids effective for treating vitiligo?"},
    {"category": "corticosteroids", "question": "What is the role of intralesional corticosteroid injections in vitiligo treatment?"},
    {"category": "corticosteroids", "question": "Are oral mini-pulse corticosteroids used to stop the progression of active vitiligo?"},
    {"category": "corticosteroids", "question": "What are the risks of long-term topical corticosteroid use on facial vitiligo?"},
    {"category": "corticosteroids", "question": "How do potent topical corticosteroids compare to tacrolimus for treating childhood vitiligo?"},

    # --- Surgical ---
    {"category": "surgical", "question": "What are the surgical options for vitiligo, like melanocyte transplantation?"},
    {"category": "surgical", "question": "What is segmental vitiligo and why is it often a better candidate for surgical treatment?"},
    {"category": "surgical", "question": "How does suction blister grafting work for stable vitiligo patches?"},
    {"category": "surgical", "question": "Who is considered a good candidate for melanocyte-keratinocyte transplantation procedures?"},
    {"category": "surgical", "question": "What is the success rate of surgical repigmentation techniques for stable vitiligo?"},

    # --- Systemic / emerging ---
    {"category": "systemic_emerging", "question": "Does vitamin D supplementation help with vitiligo?"},
    {"category": "systemic_emerging", "question": "What causes vitiligo at a biological/autoimmune level?"},
    {"category": "systemic_emerging", "question": "Are there genetic factors that predict who is likely to develop vitiligo?"},
    {"category": "systemic_emerging", "question": "Are antioxidant supplements effective as an adjunct treatment for vitiligo?"},
    {"category": "systemic_emerging", "question": "What is the relapse rate after successful vitiligo repigmentation treatment?"},
]

JUDGE_PROMPT_TEMPLATE = """You are an impartial evaluator judging retrieval quality for a \
medical research assistant. Given a QUESTION and a RETRIEVED PASSAGE, judge whether the \
passage is genuinely relevant and useful for answering the question — not just topically \
similar, but actually containing information that would help answer it.

QUESTION: {question}

RETRIEVED PASSAGE:
{passage}

Respond with ONLY a JSON object, no other text: {{"relevant": true}} or {{"relevant": false}}
"""


def judge_relevance(question: str, passage: str, max_retries: int = 3) -> bool:
    for attempt in range(max_retries):
        try:
            response = groq_client.chat.completions.create(
                model=JUDGE_MODEL,
                messages=[{
                    "role": "user",
                    "content": JUDGE_PROMPT_TEMPLATE.format(question=question, passage=passage),
                }],
            )
            text = response.choices[0].message.content.strip()
            try:
                cleaned = text.replace("```json", "").replace("```", "").strip()
                parsed = json.loads(cleaned)
                return bool(parsed.get("relevant", False))
            except (json.JSONDecodeError, AttributeError):
                return "true" in text.lower()
        except RateLimitError:
            wait = 20 * (attempt + 1)
            print(f"  Rate limited, waiting {wait}s before retry...")
            time.sleep(wait)
    raise RuntimeError("Exceeded max retries due to rate limiting.")


def retrieve_combined(question: str, top_k: int = TOP_K):
    """Retrieves top_k chunks across BOTH sources combined, ranked by similarity."""
    embedding = embed_query(question)
    return similarity_search(embedding, top_k=top_k)


def evaluate_question(question: str, category: str) -> dict:
    retrieved = retrieve_combined(question, top_k=TOP_K)

    if not retrieved:
        return {"question": question, "category": category, "precision": 0.0, "retrieved_count": 0, "relevant_count": 0}

    judgments = []
    for chunk in retrieved:
        is_relevant = judge_relevance(question, chunk["chunk_text"])
        judgments.append({
            "title": chunk["title"],
            "similarity": round(chunk["similarity"], 3),
            "relevant": is_relevant,
        })
        time.sleep(2.5)  # Groq free tier allows ~30 requests/minute for llama-3.1-8b-instant

    relevant_count = sum(1 for j in judgments if j["relevant"])
    precision = relevant_count / len(retrieved)

    return {
        "question": question,
        "category": category,
        "precision": round(precision, 3),
        "retrieved_count": len(retrieved),
        "relevant_count": relevant_count,
        "judgments": judgments,
    }


def category_breakdown(results: list) -> dict:
    by_category = {}
    for r in results:
        by_category.setdefault(r["category"], []).append(r["precision"])
    return {
        cat: round(sum(scores) / len(scores), 3)
        for cat, scores in sorted(by_category.items())
    }


def main():
    print(f"Evaluating context precision across {len(TEST_QUESTIONS)} stratified test questions...\n")

    results = []
    for i, item in enumerate(TEST_QUESTIONS, start=1):
        question, category = item["question"], item["category"]
        print(f"[{i}/{len(TEST_QUESTIONS)}] ({category}) {question}")
        result = evaluate_question(question, category)
        results.append(result)
        print(f"  Precision: {result['precision']} ({result['relevant_count']}/{result['retrieved_count']} relevant)\n")

        # Save after every question, so a crash partway through doesn't lose progress
        partial_precision = sum(r["precision"] for r in results) / len(results)
        with open(RESULTS_FILE, "w") as f:
            json.dump({
                "overall_precision_so_far": round(partial_precision, 3),
                "precision_by_category_so_far": category_breakdown(results),
                "questions_completed": len(results),
                "questions_total": len(TEST_QUESTIONS),
                "per_question_results": results,
            }, f, indent=2)

    overall_precision = sum(r["precision"] for r in results) / len(results)

    print("=" * 60)
    print(f"OVERALL CONTEXT PRECISION: {overall_precision:.3f}")
    for cat, score in category_breakdown(results).items():
        print(f"  {cat}: {score}")
    print("=" * 60)
    print(f"\nFull results saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()