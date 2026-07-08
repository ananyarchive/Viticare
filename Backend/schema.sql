-- VitiCare Research Agent — Database Schema
-- Run this once to set up the tables needed for the RAG pipeline.
--
-- Usage: psql viticare -f Backend/schema.sql

-- Documents table: one row per source document (a PubMed abstract or
-- a ClinicalTrials.gov entry), before chunking.
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    source TEXT NOT NULL,              -- 'pubmed' or 'clinicaltrials'
    external_id TEXT NOT NULL,         -- PMID or NCT number
    title TEXT NOT NULL,
    url TEXT,
    publish_date DATE,
    raw_text TEXT NOT NULL,
    fetched_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (source, external_id)
);

-- Chunks table: documents get split into smaller pieces for embedding,
-- since embedding models work better on focused passages than whole
-- documents, and retrieval is more precise at the chunk level.
CREATE TABLE IF NOT EXISTS chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(1024),  -- Voyage AI's voyage-3 embedding dimension
    created_at TIMESTAMP DEFAULT NOW()
);

-- Index for fast similarity search (cosine distance is standard for
-- normalized embeddings like Voyage's)
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks
    USING hnsw (embedding vector_cosine_ops);

-- Log of research questions asked, for an audit trail / demo-able history
CREATE TABLE IF NOT EXISTS research_queries (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    retrieved_chunk_ids INTEGER[],
    answer TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
