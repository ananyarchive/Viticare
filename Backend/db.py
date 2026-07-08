"""
VitiCare — Database connection helper for the research agent pipeline.

Provides simple functions to connect to Postgres, insert documents/chunks
with their embeddings, and run similarity search queries.

Requires: pip3 install psycopg2-binary pgvector
"""

import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector

DB_NAME = os.environ.get("VITICARE_DB_NAME", "viticare")
DB_HOST = os.environ.get("VITICARE_DB_HOST", "localhost")
DB_PORT = os.environ.get("VITICARE_DB_PORT", "5432")
DB_USER = os.environ.get("VITICARE_DB_USER", None)  # defaults to system user


def _to_pgvector_literal(embedding) -> str:
    """Converts a Python list/array embedding into pgvector's expected text format."""
    return "[" + ",".join(str(float(x)) for x in embedding) + "]"


@contextmanager
def get_connection():
    conn = psycopg2.connect(
        dbname=DB_NAME,
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
    )
    register_vector(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_document(source: str, external_id: str, title: str, url: str, publish_date, raw_text: str):
    """
    Inserts a document if it doesn't already exist (by source + external_id).
    Returns the document's id either way.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents (source, external_id, title, url, publish_date, raw_text)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source, external_id) DO UPDATE
                    SET title = EXCLUDED.title
                RETURNING id
                """,
                (source, external_id, title, url, publish_date, raw_text),
            )
            return cur.fetchone()[0]


def insert_chunks(document_id: int, chunks_with_embeddings: list):
    """
    chunks_with_embeddings: list of (chunk_index, chunk_text, embedding_vector) tuples
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO chunks (document_id, chunk_index, chunk_text, embedding)
                VALUES %s
                """,
                [
                    (document_id, idx, text, _to_pgvector_literal(embedding))
                    for idx, text, embedding in chunks_with_embeddings
                ],
                template="(%s, %s, %s, %s::vector)",
            )


def similarity_search(query_embedding, top_k: int = 5):
    """
    Returns the top_k most similar chunks to the query embedding, joined
    with their parent document's metadata (title, url, source).
    """
    embedding_literal = _to_pgvector_literal(query_embedding)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    chunks.id,
                    chunks.chunk_text,
                    documents.title,
                    documents.url,
                    documents.source,
                    documents.external_id,
                    1 - (chunks.embedding <=> %s::vector) AS similarity
                FROM chunks
                JOIN documents ON documents.id = chunks.document_id
                ORDER BY chunks.embedding <=> %s::vector
                LIMIT %s
                """,
                (embedding_literal, embedding_literal, top_k),
            )
            rows = cur.fetchall()
            return [
                {
                    "chunk_id": r[0],
                    "chunk_text": r[1],
                    "title": r[2],
                    "url": r[3],
                    "source": r[4],
                    "external_id": r[5],
                    "similarity": float(r[6]),
                }
                for r in rows
            ]


def log_research_query(question: str, retrieved_chunk_ids: list, answer: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO research_queries (question, retrieved_chunk_ids, answer)
                VALUES (%s, %s, %s)
                """,
                (question, retrieved_chunk_ids, answer),
            )