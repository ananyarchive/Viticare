"""
VitiCare — Research Agent

Given a user's question about a vitiligo treatment, this agent:
  1. Lets Claude decide which tool(s) to call (search PubMed chunks,
     search ClinicalTrials chunks, or both)
  2. Retrieves the most relevant chunks from Postgres/pgvector
  3. Has Claude synthesize a grounded, cited, LAYMAN-FRIENDLY answer —
     never answering from its own memory, always from retrieved evidence

Requires: pip3 install anthropic voyageai python-dotenv psycopg2-binary pgvector
"""

import os
import sys
import json

import google.generativeai as genai
import voyageai
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db import similarity_search, log_research_query  # noqa: E402

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set. Add it to your .env file.")
if not VOYAGE_API_KEY:
    raise RuntimeError("VOYAGE_API_KEY not set. Add it to your .env file.")

genai.configure(api_key=GEMINI_API_KEY)
voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)

MODEL = "gemini-2.5-flash"

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
        "function_declarations": [
            {
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
            {
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
        ]
    }
]


def embed_query(query: str):
    result = voyage_client.embed([query], model="voyage-3", input_type="query")
    return result.embeddings[0]


def search_by_source(query: str, source_filter: str, top_k: int = 5):
    embedding = embed_query(query)
    all_results = similarity_search(embedding, top_k=top_k * 3)  # overfetch, then filter
    filtered = [r for r in all_results if r["source"] == source_filter][:top_k]
    return filtered


def format_results_for_claude(results: list) -> str:
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
    Runs the full tool-calling loop: Gemini decides which searches to run,
    we execute them against Postgres, feed results back, and Gemini
    synthesizes a final grounded answer.
    """
    model = genai.GenerativeModel(
        model_name=MODEL,
        system_instruction=SYSTEM_PROMPT,
        tools=TOOLS,
    )
    chat = model.start_chat()
    all_retrieved_chunk_ids = []

    response = chat.send_message(question)

    while True:
        function_calls = [
            part.function_call
            for part in response.candidates[0].content.parts
            if part.function_call
        ]

        if not function_calls:
            final_text = response.text
            log_research_query(question, all_retrieved_chunk_ids, final_text)
            return {
                "answer": final_text,
                "sources_used": len(all_retrieved_chunk_ids),
            }

        function_response_parts = []
        for fc in function_calls:
            query = fc.args.get("query", question)
            source_filter = (
                "pubmed" if fc.name == "search_pubmed_evidence" else "clinicaltrials"
            )
            results = search_by_source(query, source_filter)
            all_retrieved_chunk_ids.extend(r["chunk_id"] for r in results)

            function_response_parts.append(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=fc.name,
                        response={"result": format_results_for_claude(results)},
                    )
                )
            )

        response = chat.send_message(
            genai.protos.Content(parts=function_response_parts)
        )


if __name__ == "__main__":
    import sys as _sys
    question = " ".join(_sys.argv[1:]) or "Does tacrolimus work for vitiligo?"
    print(f"Question: {question}\n")
    result = ask_research_agent(question)
    print(result["answer"])
    print(f"\n[{result['sources_used']} source chunks retrieved]")