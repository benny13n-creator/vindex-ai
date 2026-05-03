# Vindex AI

> Production-grade legal AI assistant for Serbian lawyers. RAG-based system serving complex legal queries against 13,500+ indexed legal provisions from 65+ Serbian laws.

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-009688.svg)](https://fastapi.tiangolo.com/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991.svg)](https://openai.com/)
[![Pinecone](https://img.shields.io/badge/Pinecone-Vector%20DB-1B1F23.svg)](https://www.pinecone.io/)
[![Deployed on Render](https://img.shields.io/badge/Deployed-Render-46E3B7.svg)](https://render.com/)

---

## What it does

Vindex AI helps Serbian lawyers do in seconds what currently takes hours: search relevant legal provisions, find supporting case law, and draft legal motions grounded in actual statutes.

The system handles three main workflows:

- **Legal Q&A** — answers complex legal questions with citations to specific articles, paragraphs, and case law
- **Document drafting** — generates first drafts of motions, complaints, and contracts based on lawyer's input + retrieved legal context
- **Legal analysis** — analyzes uploaded documents (PDF) against relevant law and flags issues

Deployed in production. Currently serving beta users (practicing lawyers in Serbia).

---

## Architecture


┌─────────────────────────┐
                │   Frontend (HTML/JS)    │
                │   Single-page app       │
                └───────────┬─────────────┘
                            │
                            ▼
                ┌─────────────────────────┐
                │   FastAPI Backend       │
                │   (api.py)              │
                │                         │
                │   /api/pitanje (Q&A)    │
                │   /api/nacrt   (draft)  │
                │   /api/analiza (review) │
                └─────┬───────────┬───────┘
                      │           │
                      ▼           ▼
          ┌──────────────┐  ┌──────────────┐
          │   Pinecone   │  │   OpenAI     │
          │  Vector DB   │  │   GPT-4o     │
          │              │  │              │
          │ 13,500+ legal│  │ Generation + │
          │ provisions   │  │ Query exp.   │
          │ 3072 dim     │  │              │
          └──────┬───────┘  └──────────────┘
                 │
                 ▼
          ┌──────────────┐
          │  Supabase    │
          │  (auth +     │
          │   user data) │
          └──────────────┘



          ---

## Tech Stack

**Backend**
- Python 3.11
- FastAPI (async API server)
- Pinecone (vector DB, 3072-dim embeddings, AWS us-east-1)
- OpenAI GPT-4o (generation + query expansion)
- Supabase (Postgres + Row-Level Security + Auth)

**RAG Pipeline**
- Custom semantic chunker preserving legal article structure
- 4-way query expansion (each user question becomes 4 semantically distinct retrieval queries)
- Re-ranking layer for relevance optimization
- Citation tracking (every answer references exact article + paragraph)

**Infrastructure**
- Deployed on Render (FastAPI service + static frontend)
- Docker containerized
- Stress-tested for concurrent user load

**Data Pipeline**
- Custom scrapers for paragraf.rs (primary Serbian legal database)
- BeautifulSoup + PDF parsing for law ingestion
- Automated re-indexing scripts for legal updates

---

## What I built

- End-to-end RAG system from scratch — ingestion, chunking, indexing, retrieval, generation
- Custom semantic chunker that respects Serbian legal document structure (article → paragraph → item)
- Query expansion strategy that improved retrieval recall by ~40% over baseline single-query RAG
- Production deployment with monitoring and stress-testing
- Web3 integration module (`vindex_web3/`) — bridges blockchain events with legal frameworks (Serbian Law of Obligations / ZOO), demonstrating cross-domain RAG application

---

## Repository structure

├── api.py                  # FastAPI backend (main entry)
├── main.py                 # Core RAG pipeline
├── semantic_chunker.py     # Custom legal-aware chunker
├── ingest_kz.py            # Law ingestion pipeline
├── reindex_agentic.py      # Re-indexing with agentic enhancement
├── pdf_tools.py            # PDF parsing utilities
├── stress_test.py          # Load testing
├── vindex_web3/            # Web3 → legal mapping module
├── data/laws/              # Source legal documents
├── templates/              # Document drafting templates
├── supabase_setup.sql      # Database schema
├── Dockerfile              # Container config
└── requirements.txt        # Dependencies

---

## Status

- ✅ Production deployment (Render)
- ✅ 13,500+ legal provisions indexed
- ✅ Beta users actively using the system
- 🔄 Multi-agent pipeline in development (Intake → Writer → Reviewer with quality scoring)
- 🔄 Tier system rollout (Basic / PRO)

---

## About the builder

Built solo by [Benjamin Nađ](https://www.linkedin.com/in/benjamin-na%C4%91-890864394/) — AI Product Engineer with 2+ years of hands-on LLM + agent work. Focus areas: production RAG systems, multi-agent pipelines, Web3 + AI integration.

For collaboration, technical questions, or licensing inquiries — please reach out via LinkedIn.
