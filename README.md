# FinSight — Earnings Intelligence API

An end-to-end applied AI API that ingests public company earnings communications from [SEC EDGAR](https://www.sec.gov/edgar) — 8-K earnings releases, 10-K/10-Q narrative sections, and XBRL financial facts — runs a feature pipeline (sentiment, topic modeling, metric extraction), ranks companies by signal strength, flags anomalies, and layers RAG + an agentic chat interface on top. Deployed on Cloud Run with CI/CD, drift monitoring, and an evaluation harness that will ship as a standalone open-source package (**EvalKit**).

The full feature-by-feature build plan lives in [`planning/implementation-plan.md`](https://github.com/sidbala2310/finsight/blob/main/planning/implementation-plan.md).

## Data

FinSight uses SEC filings rather than earnings call transcripts (which are licensed content, not public SEC data):

- **Textual** — 8-K Item 2.02 earnings press releases (EX-99 exhibits, incl. prepared remarks when furnished), 10-K/10-Q MD&A and Risk Factors sections
- **Numerical** — standardized financial facts (revenue, EPS, margins) from EDGAR's free XBRL `companyfacts` APIs
- **Market data** — daily prices from free sources, used only to construct the training target (forward abnormal return after a filing)

The model's core hypothesis: text-derived signals (management tone, tone *change* vs the prior quarter, guidance language, risk-factor churn) carry information beyond the raw fundamentals they accompany.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│           Layer 3 — EvalKit (evaluation harness)         │
│   Ranking metrics · retrieval eval · RAGAS/BERTScore ·   │
│   LLM-as-judge · W&B Weave — extracted to OSS package    │
└──────────────┬───────────────────────┬───────────────────┘
               ▼                       ▼
┌──────────────────────────┐ ┌──────────────────────────────┐
│   Layer 1 — Applied AI   │ │   Layer 2 — LLM intelligence │
│  Feature pipeline        │ │  RAG pipeline (pgvector,     │
│  (FinBERT sentiment,     │ │   hybrid retrieval, rerank)  │
│   XBRL metrics, topics)  │ │  Provider-agnostic LLM layer │
│  GBDT ranking (LightGBM  │ │   (Claude ↔ Gemini bake-off) │
│   vs XGBoost bake-off)   │ │  LangGraph agent (streaming, │
│  IVW feature importance  │ │   memory, tools)             │
│  Anomaly detection       │ │                              │
│  MLflow · drift monitor  │ │                              │
└──────────────┬───────────┘ └───────────┬──────────────────┘
               ▲                         ▲
┌──────────────┴─────────────────────────┴───────────────────┐
│         Layer 0 — Shared infrastructure                    │
│  FastAPI · Docker · Cloud Run (scale-to-zero) · GitHub     │
│  Actions CI/CD · Postgres + pgvector · Redis caching       │
└──────────────────────────┬─────────────────────────────────┘
                           ▲
┌──────────────────────────┴─────────────────────────────────┐
│   SEC EDGAR — filings (8-K, 10-K/10-Q) + XBRL facts        │
└────────────────────────────────────────────────────────────┘

  Layer 4 — light React frontend (rankings, company detail,
  agent chat) served from the same FastAPI service
```

Layers are **work streams, not sequential phases** — infrastructure and evaluation are built first and grow alongside the features they support, rather than being bolted on at the end.

### Layer 0 — Architecture baseline

Built before any feature work: FastAPI walking skeleton, Docker + docker-compose (Postgres/pgvector, Redis), GitHub Actions CI, branch-protected trunk, and continuous deployment to Cloud Run. Every feature lands as a PR gated by CI and deploys automatically on merge.

### Layer 1 — Applied AI

- **Ingestion** — EDGAR filings for an S&P 500 universe, rate-limit-compliant, idempotent
- **Parsing** — clean narrative sections into a normalized corpus (shared with Layer 2)
- **Features** — FinBERT sentiment and tone-change, XBRL fundamentals, guidance/topic signals
- **Ranking** — LightGBM and XGBoost trained head-to-head against forward abnormal returns (plus naive and linear baselines) on identical time-split CV; the winner is registered as the production model via MLflow
- **Explainability** — feature rankings via inverse-variance-weighted (IVW) meta-analysis of per-fold importance estimates, avoiding the high-cardinality and gain-averaging biases of default GBDT importances — critical for honestly answering whether text signals add value beyond fundamentals
- **Anomaly detection** — language and metric shifts vs each company's own history
- **Ops** — MLflow tracking, scheduled pipeline runs, feature/prediction drift monitoring

### Layer 2 — LLM intelligence

- **RAG pipeline** — section-aware chunking, pgvector, hybrid (dense + sparse) retrieval, reranking — every change gated by retrieval eval metrics
- **Provider-agnostic LLM layer** — all generation and LLM-as-judge calls go through a pluggable interface; Claude and Gemini backends are compared head-to-head with the project's own eval harness before a default is chosen
- **Streaming Q&A** — `POST /ask` with citations and low-confidence refusal
- **LangGraph agent** — conversational access to retrieval, rankings, metrics, and anomalies with memory and multi-step tool use

### Layer 3 — EvalKit

Evaluation is built inline from the first model (ranking metrics, golden Q&A retrieval set, RAGAS-style scoring) and later **extracted** — not invented at the end — into a standalone OSS package: unified ML + LLM eval API, W&B Weave integration, CI regression-gate templates, PyPI release.

### Layer 4 — Frontend

A light React SPA served as static files from the FastAPI service: rankings table, company detail with links to source filings, and a streaming chat panel for the agent.

## Operating cost

Designed to run at ~$0/month: Cloud Run scale-to-zero, free-tier managed Postgres (Neon/Supabase) and Redis (Upstash), free public data sources, and locally-run open-source models for embeddings and sentiment. The only paid touchpoint is metered LLM API usage during Layer 2 development, capped by prepaid credits.

## Status

🚧 Planning complete — implementation begins with Layer 0 (project scaffold + CI/CD). See [`planning/implementation-plan.md`](https://github.com/sidbala2310/finsight/blob/main/planning/implementation-plan.md) for the feature-by-feature sequence and validation criteria.
