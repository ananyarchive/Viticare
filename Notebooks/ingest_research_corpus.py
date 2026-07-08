"""
VitiCare — Research Corpus Ingestion

Pulls real vitiligo treatment literature from two public sources:
  1. PubMed (via NCBI's E-utilities API) — research abstracts
  2. ClinicalTrials.gov (via their public API v2) — trial summaries

Chunks each document, embeds the chunks with Voyage AI, and stores
everything in Postgres (pgvector) for the research agent to search later.

Requires: pip3 install requests voyageai python-dotenv psycopg2-binary pgvector
Run from project root: python3 Notebooks/ingest_research_corpus.py
"""

import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
import voyageai
from dotenv import load_dotenv

sys.path.append(str(__file__).rsplit("/Notebooks", 1)[0] + "/Backend")
from db import insert_document, insert_chunks, get_connection  # noqa: E402

load_dotenv()

VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY")
if not VOYAGE_API_KEY or VOYAGE_API_KEY == "your_key_here":
    raise RuntimeError("VOYAGE_API_KEY not set. Add it to your .env file in the project root.")

voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)

# With a payment method on file, Voyage's standard rate limits are much higher.
# Keep a small delay anyway to be a good API citizen and avoid transient errors.
SECONDS_BETWEEN_EMBED_CALLS = 1.5

SEARCH_TERMS = [
    # Core treatments
    "vitiligo tacrolimus treatment",
    "vitiligo pimecrolimus topical",
    "vitiligo narrowband UVB phototherapy",
    "vitiligo PUVA psoralen treatment",
    "vitiligo ruxolitinib JAK inhibitor",
    "vitiligo topical corticosteroid",
    "vitiligo excimer laser treatment",
    "vitiligo excimer lamp therapy",
    "vitiligo repigmentation mechanism",
    "vitiligo depigmentation mechanism",
    # Surgical / procedural
    "vitiligo surgical treatment melanocyte transplant",
    "vitiligo skin grafting",
    "vitiligo micrografting technique",
    "vitiligo suction blister grafting",
    # Systemic / emerging
    "vitiligo oral corticosteroid mini-pulse",
    "vitiligo methotrexate treatment",
    "vitiligo afamelanotide",
    "vitiligo antioxidant supplementation",
    "vitiligo vitamin D treatment",
    "vitiligo gingko biloba",
    # Population / context specific
    "vitiligo pediatric children treatment",
    "vitiligo facial treatment outcomes",
    "vitiligo segmental vitiligo treatment",
    "vitiligo non-segmental generalized treatment",
    "vitiligo quality of life psychological impact",
    "vitiligo autoimmune pathogenesis",
    "vitiligo genetics susceptibility",
    "vitiligo combination therapy phototherapy topical",
    "vitiligo relapse recurrence after treatment",
    "vitiligo new emerging therapies 2024",
]

RESULTS_PER_TERM = 20  # increased from 8 for broader corpus coverage

CHUNK_SIZE_WORDS = 200
CHUNK_OVERLAP_WORDS = 40


def chunk_text(text: str) -> list:
    """Splits text into overlapping word-based chunks for embedding."""
    words = text.split()
    if len(words) <= CHUNK_SIZE_WORDS:
        return [text]

    chunks = []
    start = 0
    while start < len(words):
        end = start + CHUNK_SIZE_WORDS
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += CHUNK_SIZE_WORDS - CHUNK_OVERLAP_WORDS
    return chunks


def is_already_ingested(source: str, external_id: str) -> bool:
    """Checks whether this document already has embedded chunks stored."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM chunks
                JOIN documents ON documents.id = chunks.document_id
                WHERE documents.source = %s AND documents.external_id = %s
                """,
                (source, external_id),
            )
            return cur.fetchone()[0] > 0


def embed_and_store(source: str, external_id: str, title: str, url: str, publish_date, raw_text: str):
    if not raw_text or len(raw_text.strip()) < 50:
        return  # skip empty/too-short documents

    if is_already_ingested(source, external_id):
        print(f"  Skipping (already ingested): {title[:70]}")
        return

    doc_id = insert_document(source, external_id, title, url, publish_date, raw_text)

    chunks = chunk_text(raw_text)
    embeddings = voyage_client.embed(
        chunks, model="voyage-3", input_type="document"
    ).embeddings

    chunks_with_embeddings = [
        (idx, chunk, embedding) for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]
    insert_chunks(doc_id, chunks_with_embeddings)
    print(f"  Stored {len(chunks)} chunk(s) for: {title[:70]}")

    time.sleep(SECONDS_BETWEEN_EMBED_CALLS)


def fetch_pubmed(query: str, max_results: int = RESULTS_PER_TERM):
    """Searches PubMed, then fetches abstracts for the resulting IDs."""
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    search_params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": "relevance",
    }
    resp = requests.get(search_url, params=search_params, timeout=15)
    resp.raise_for_status()
    id_list = resp.json().get("esearchresult", {}).get("idlist", [])

    if not id_list:
        return

    fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    fetch_params = {
        "db": "pubmed",
        "id": ",".join(id_list),
        "retmode": "xml",
        "rettype": "abstract",
    }
    resp = requests.get(fetch_url, params=fetch_params, timeout=20)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        title_el = article.find(".//ArticleTitle")
        abstract_els = article.findall(".//AbstractText")

        pmid = pmid_el.text if pmid_el is not None else None
        title = "".join(title_el.itertext()) if title_el is not None else "Untitled"
        abstract = " ".join("".join(el.itertext()) for el in abstract_els) if abstract_els else ""

        year_el = article.find(".//PubDate/Year")
        publish_date = None
        if year_el is not None and year_el.text:
            try:
                publish_date = datetime(int(year_el.text), 1, 1).date()
            except ValueError:
                pass

        if pmid and abstract:
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            try:
                embed_and_store("pubmed", pmid, title, url, publish_date, abstract)
            except Exception as e:
                print(f"  Error embedding PMID {pmid}: {e}")
                time.sleep(SECONDS_BETWEEN_EMBED_CALLS)  # still back off before continuing

    time.sleep(0.4)  # be polite to NCBI's rate limits


def fetch_clinical_trials(query: str, max_results: int = RESULTS_PER_TERM):
    """Searches ClinicalTrials.gov API v2 for relevant trial summaries."""
    url = "https://clinicaltrials.gov/api/v2/studies"
    params = {
        "query.term": query,
        "pageSize": max_results,
        "format": "json",
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    for study in data.get("studies", []):
        protocol = study.get("protocolSection", {})
        identification = protocol.get("identificationModule", {})
        description = protocol.get("descriptionModule", {})
        status_module = protocol.get("statusModule", {})

        nct_id = identification.get("nctId")
        title = identification.get("briefTitle", "Untitled trial")
        summary = description.get("briefSummary", "")
        detailed = description.get("detailedDescription", "")
        full_text = f"{summary} {detailed}".strip()

        start_date_str = status_module.get("startDateStruct", {}).get("date")
        publish_date = None
        if start_date_str:
            try:
                publish_date = datetime.strptime(start_date_str[:7], "%Y-%m").date()
            except ValueError:
                pass

        if nct_id and full_text:
            trial_url = f"https://clinicaltrials.gov/study/{nct_id}"
            try:
                embed_and_store("clinicaltrials", nct_id, title, trial_url, publish_date, full_text)
            except Exception as e:
                print(f"  Error embedding {nct_id}: {e}")
                time.sleep(SECONDS_BETWEEN_EMBED_CALLS)

    time.sleep(0.4)


def main():
    print("Starting research corpus ingestion...\n")

    for term in SEARCH_TERMS:
        print(f"PubMed: '{term}'")
        try:
            fetch_pubmed(term)
        except Exception as e:
            print(f"  Error fetching PubMed for '{term}': {e}")

        print(f"ClinicalTrials.gov: '{term}'")
        try:
            fetch_clinical_trials(term)
        except Exception as e:
            print(f"  Error fetching ClinicalTrials.gov for '{term}': {e}")

        print()

    print("Ingestion complete.")


if __name__ == "__main__":
    main()
