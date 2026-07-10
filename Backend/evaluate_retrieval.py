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

# Realistic test questions spanning different treatments/topics in the corpus
TEST_QUESTIONS = [
    "Does tacrolimus work for treating vitiligo?",
    "What is narrowband UVB phototherapy and how effective is it for vitiligo?",
    "How does ruxolitinib cream work for vitiligo repigmentation?",
    "Are topical corticosteroids effective for vitiligo?",
    "What are the surgical options for vitiligo like melanocyte transplantation?",
    "Does vitamin D supplementation help with vitiligo?",
    "How is vitiligo treated differently in children versus adults?",
    "What is the psychological impact of vitiligo on quality of life?",
    "What causes vitiligo at a biological/autoimmune level?",
    "How effective is excimer laser treatment for vitiligo compared to other options?",
    "What is segmental vitiligo and how is it treated differently from generalized vitiligo?",
    "What are realistic expectations for how long vitiligo treatment takes to show results?",
    "Does combining phototherapy with topical treatments work better than either alone?",
    "What is the relapse rate after successful vitiligo treatment?",
    "Are there genetic factors that predict who gets vitiligo?",
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


def evaluate_question(question: str) -> dict:
    retrieved = retrieve_combined(question, top_k=TOP_K)

    if not retrieved:
        return {"question": question, "precision": 0.0, "retrieved_count": 0, "relevant_count": 0}

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
        "precision": round(precision, 3),
        "retrieved_count": len(retrieved),
        "relevant_count": relevant_count,
        "judgments": judgments,
    }


def main():
    print(f"Evaluating context precision across {len(TEST_QUESTIONS)} test questions...\n")

    results = []
    for i, question in enumerate(TEST_QUESTIONS, start=1):
        print(f"[{i}/{len(TEST_QUESTIONS)}] {question}")
        result = evaluate_question(question)
        results.append(result)
        print(f"  Precision: {result['precision']} ({result['relevant_count']}/{result['retrieved_count']} relevant)\n")

        # Save after every question, so a crash partway through doesn't lose progress
        partial_precision = sum(r["precision"] for r in results) / len(results)
        with open(RESULTS_FILE, "w") as f:
            json.dump({
                "overall_precision_so_far": round(partial_precision, 3),
                "questions_completed": len(results),
                "questions_total": len(TEST_QUESTIONS),
                "per_question_results": results,
            }, f, indent=2)

    overall_precision = sum(r["precision"] for r in results) / len(results)

    print("=" * 60)
    print(f"OVERALL CONTEXT PRECISION: {overall_precision:.3f}")
    print("=" * 60)
    print(f"\nFull results saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()