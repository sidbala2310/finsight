# FinSight — Earnings Call Intelligence API

An end-to-end applied AI API that ingests public earnings call transcripts from [SEC EDGAR](https://www.sec.gov/edgar), runs a feature pipeline (sentiment, topic modeling, metric extraction), ranks companies by signal strength, flags anomalies, and serves results via a streaming FastAPI endpoint — deployed to Cloud Run with drift monitoring and a full CI/CD pipeline.

**Who it's for:** hedge funds, research desks, and compliance teams that need structured signal from unstructured earnings calls.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              EvalKit — evaluation harness            │
│   ML eval (offline + A/B) · LLM eval (RAGAS +        │
│   BERTScore) · W&B Weave unified dashboard           │
└──────────────┬───────────────────────┬───────────────┘
               ▼                       ▼
┌──────────────────────────┐ ┌──────────────────────────┐
│   Layer 1 — Applied AI   │ │  Layer 2 — LLM intel     │
│  Feature pipeline        │ │  RAG pipeline            │
│  (LightGBM, anomaly      │ │  (pgvector, hybrid       │
│   detection)             │ │   retrieval, reranker)   │
│  Drift monitoring +      │ │  LangGraph agent         │
│  MLflow tracking         │ │  (streaming, memory,     │
│                          │ │   tools)                 │
└──────────────┬───────────┘ └───────────┬──────────────┘
               ▲                         ▲
┌──────────────┴─────────────────────────┴───────────────┐
│              Shared infrastructure                     │
│   FastAPI · Docker · Cloud Run · CI/CD · Redis caching │
└──────────────────────────┬─────────────────────────────┘
                           ▲
┌──────────────────────────┴─────────────────────────────┐
│        SEC EDGAR — public earnings transcripts         │
└────────────────────────────────────────────────────────┘
```

### Layer 1 — Applied AI

Classic ML over transcript-derived features:

- **Ingestion** — pull earnings call transcripts from SEC EDGAR (fully public, no licensing issues)
- **Feature pipeline** — sentiment, topic modeling, and financial metric extraction
- **Ranking** — LightGBM model scores companies by signal strength
- **Anomaly detection** — flag unusual language or metric shifts between calls
- **Ops** — MLflow experiment tracking, drift detection, model monitoring

### Layer 2 — LLM intelligence

Retrieval and agentic Q&A over the transcript corpus:

- **RAG pipeline** — pgvector storage, hybrid (dense + sparse) retrieval, reranking
- **LangGraph agent** — streaming responses with conversation memory and tool use

### Layer 3 — EvalKit

An evaluation harness spanning both layers, planned as a standalone open-source release:

- Offline and A/B metrics for the ML models
- RAGAS + BERTScore + LLM-as-judge for the RAG/agent stack
- Unified dashboards via W&B Weave

### Shared infrastructure

FastAPI (async, streaming endpoints) · Docker · Google Cloud Run · CI/CD with automated model deployment · Redis inference caching

## Roadmap

| Phase | Scope | Timeline |
|-------|-------|----------|
| Layer 1 | EDGAR ingestion, feature pipeline, LightGBM ranking, MLflow + drift monitoring | Weeks 1–2 |
| Layer 2 | RAG pipeline, LangGraph agent | Weeks 2–3 |
| Layer 3 | EvalKit harness, open-source release | Weeks 4–5 |

## Status

🚧 Early planning — architecture defined, implementation starting with Layer 1.
