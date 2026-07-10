"""
VitiCare — Research Agent

Given a user's question about a vitiligo treatment, this agent:
  1. Lets the LLM (Groq-hosted Llama) decide which tool(s) to call (search
     PubMed chunks, search ClinicalTrials chunks, or both)
  2. Retrieves the most relevant chunks from Postgres/pgvector
  3. Has the LLM synthesize a grounded, cited, LAYMAN-FRIENDLY answer —
     never answering from its own memory, always from retrieved evidence

Requires: pip3 install groq voyageai python-dotenv psycopg2-binary pgvector
"""

import os
import sys
import json

from groq import Groq
import voyageai
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db import similarity_search, log_research_query  # noqa: E402

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not set. Add it to your .env file.")
if not VOYAGE_API_KEY:
    raise RuntimeError("VOYAGE_API_KEY not set. Add it to your .env file.")

groq_client = Groq(api_key=GROQ_API_KEY)
voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)

MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are VitiCare's research assistant. You help people understand \
vitiligo treatments based ONLY on the evidence retrieved by your tools — never from \
your own general knowledge, since the person needs to trust that every claim is grounded \
in a real, citable source.

CRITICAL STYLE RULES:
- Explain things in plain, everyday language, like a knowledgeable friend, NOT a clinical \
textbook. Avoid jargon where possible; when a technical term is necessary, explain it simply.
- Do NOT front-load a long list of side effects or scary warnings. Keep tone calm and \
informative, not alarming.
- Structure every answer with these sections, in this order:
  1. **What it is / how it works** (plain-language mechanism)
  2. **What the evidence shows** (strength of evidence, in plain terms — e.g. "several \
studies suggest..." vs "one small trial found...")
  3. **Worth knowing** (a BRIEF, non-alarming note of anything important — timelines, \
realistic expectations, or the single most relevant caveat, not an exhaustive list)
  4. **Sources** (list the titles/URLs actually used)
- If retrieved evidence is thin, conflicting, or doesn't clearly answer the question, say \
so honestly rather than overstating confidence.
- Always use your search tools before answering. Never answer from memory alone.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_pubmed_evidence",
            "description": "Searches embedded PubMed research abstracts about vitiligo treatments for passages relevant to a query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for, e.g. 'tacrolimus effectiveness for facial vitiligo'"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_clinical_trials_evidence",
            "description": "Searches embedded ClinicalTrials.gov trial summaries about vitiligo treatments for passages relevant to a query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for, e.g. 'ruxolitinib cream clinical trial results'"}
                },
                "required": ["query"],
            },
        },
    },
]


def embed_query(query: str):
    result = voyage_client.embed([query], model="voyage-3", input_type="query")
    return result.embeddings[0]


def search_by_source(query: str, source_filter: str, top_k: int = 5):
    embedding = embed_query(query)
    all_results = similarity_search(embedding, top_k=top_k * 3)  # overfetch, then filter
    filtered = [r for r in all_results if r["source"] == source_filter][:top_k]
    return filtered


def format_results_for_llm(results: list) -> str:
    if not results:
        return "No relevant results found."
    formatted = []
    for r in results:
        formatted.append(
            f"[{r['source'].upper()} | {r['external_id']}] {r['title']}\n"
            f"URL: {r['url']}\n"
            f"Excerpt: {r['chunk_text']}\n"
        )
    return "\n---\n".join(formatted)


def ask_research_agent(question: str) -> dict:
    """
    Runs the full tool-calling loop: the LLM decides which searches to run,
    we execute them against Postgres, feed results back, and the LLM
    synthesizes a final grounded answer.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    all_retrieved_chunk_ids = []
    first_turn = True

    while True:
        response = groq_client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            # Force the first turn to call a tool — with tool_choice="auto",
            # this model occasionally emits a malformed pseudo-function-call
            # as plain text instead of a real tool call. Forcing "required"
            # only on turn one (when it must search anyway, per the system
            # prompt) avoids that failure mode without blocking it from
            # giving a final text answer on later turns.
            tool_choice="required" if first_turn else "auto",
        )
        first_turn = False
        message = response.choices[0].message

        if not message.tool_calls:
            final_text = message.content
            log_research_query(question, all_retrieved_chunk_ids, final_text)
            return {
                "answer": final_text,
                "sources_used": len(all_retrieved_chunk_ids),
            }

        messages.append(message)
        for tc in message.tool_calls:
            args = json.loads(tc.function.arguments)
            query = args.get("query", question)
            source_filter = (
                "pubmed" if tc.function.name == "search_pubmed_evidence" else "clinicaltrials"
            )
            results = search_by_source(query, source_filter)
            all_retrieved_chunk_ids.extend(r["chunk_id"] for r in results)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": format_results_for_llm(results),
            })


if __name__ == "__main__":
    import sys as _sys
    question = " ".join(_sys.argv[1:]) or "Does tacrolimus work for vitiligo?"
    print(f"Question: {question}\n")
    result = ask_research_agent(question)
    print(result["answer"])
    print(f"\n[{result['sources_used']} source chunks retrieved]")