# FinSight — Comprehensive Implementation Plan

## Context

FinSight is a portfolio-grade applied AI project: an API that ingests public company earnings communications from SEC EDGAR, extracts features (sentiment, topics, metrics), ranks companies by signal strength with a LightGBM model, flags anomalies, and layers RAG + a LangGraph agent on top — deployed on Cloud Run with CI/CD, drift monitoring, and an evaluation harness that later ships as an open-source package ("EvalKit").

This plan defines **what gets built, in what order, and how each feature is tested and validated**. Implementation specifics of each feature are deliberately deferred to when that feature is picked up.

Decisions already made:
- **Data source pivot:** SEC EDGAR does not host earnings *call transcripts*. FinSight targets **earnings communications from EDGAR filings** instead: 8-K earnings releases (EX-99 press-release exhibits, incl. prepared remarks when furnished) and 10-K/10-Q narrative sections (MD&A, Risk Factors). Fully public, no licensing issues.
- **Cloud Run from Layer 0:** the commit → PR → CI → merge → deployed-to-Cloud-Run pipeline exists before any feature work. Local Docker (Dockerfile + docker-compose) is part of the same Layer 0 work.
- **Layers are work streams, not phases:** Layer 0 = architecture/infra, Layer 1 = applied ML, Layer 2 = LLM intelligence, Layer 3 = EvalKit. The implementation order below interleaves them; layer number has no timeline implication.
- **Eval is inline, not last:** evaluation harnesses are built alongside the first model / first retriever. Layer 3 is the *extraction and productization* of eval tooling that already exists and has been used.

## Working agreements

- **Every feature is a branch + PR into `main`**, gated by CI. One feature = one PR (sub-features may split into smaller PRs).
- **User runs all git commands** (branch, commit, push, PR merge); Claude drafts them. GitHub settings (branch protection) done by the user via drafted `gh` commands or the GitHub UI.
- **No live external calls in CI.** SEC EDGAR, market data, and LLM APIs are tested against recorded fixtures/mocks; live integration is validated manually or via scheduled non-blocking smoke jobs.
- **Defaults:** Python 3.12+, `uv` for env/deps, `src/` layout, `pytest`, `ruff` (lint+format), `mypy`, GitHub Actions, GCP (Cloud Run, Artifact Registry, Cloud Scheduler), Postgres + pgvector, Redis.
- **Zero-cost constraint:** the project must run at ~$0/month. Production Postgres+pgvector on a **Neon or Supabase free tier** (not Cloud SQL); production caching on **Upstash Redis free tier** (not Memorystore); Cloud Run scale-to-zero (min-instances=0); Artifact Registry image-cleanup policy; local docker-compose keeps real Postgres+Redis. GCP billing account required for free tier — set a $1 budget alert during 0.5.
- **LLM strategy — model-agnostic by design, decided by our own evals:** every Layer 2 LLM call (generation, judge) goes through a thin provider-agnostic interface from the first line of code, with a fake model backend for CI. Phase 1: **Claude Haiku 4.5** (`claude-haiku-4-5`, $1/$5 per MTok; prepaid Console credits with auto-reload OFF — a structural spend cap, start with $5, realistic project total $5–20 depending on eval iterations). Phase 2: add a **Gemini free-tier** backend. Phase 3: head-to-head bake-off scored by the project's own eval harness (feature 2.5), then pick the default provider and document the decision. This doubles as a learning exercise and the first real demonstration of the eval platform. Cost controls: CI uses recorded/mocked LLM calls; tune against a small eval subset, full golden set only at checkpoints. Embeddings and BERTScore/FinBERT run locally via open-source models — no API cost.

---

## Layer 0 — Architecture baseline

### 0.1 Project scaffold
Python project skeleton: `pyproject.toml` (uv), `src/finsight/` layout, pytest with a trivial passing test, ruff + mypy configured, pre-commit hooks, expanded `.gitignore`, README updated with dev setup.
**Validate:** `uv sync && pytest && ruff check && mypy` all pass locally from a fresh clone.

### 0.2 CI pipeline
GitHub Actions workflow on every PR and push to `main`: lint → typecheck → tests (with coverage report). Cache uv deps for speed.
**Validate:** open a scratch PR with a deliberate lint error and a failing test → CI red; fix → CI green.

### 0.3 Branch protection
Protect `main`: require a PR, require the CI status checks to pass, block direct pushes and force-pushes. (Solo repo: no reviewer-count requirement, otherwise self-merge is blocked.)
**Validate:** a direct `git push` to `main` is rejected; a PR with red CI cannot be merged; green PR merges cleanly.

### 0.4 Walking skeleton: FastAPI + Docker + local stack
Minimal async FastAPI app (`/healthz`, `/version`), settings from env vars (pydantic-settings), structured JSON logging. Multi-stage Dockerfile. `docker-compose.yml` with the app + Postgres (pgvector image) + Redis; health checks on all services.
**Validate:** `docker compose up` → `/healthz` returns 200 and reports DB/Redis connectivity; image builds in CI.

### 0.5 Cloud Run CD
GCP project setup (user account/billing), Artifact Registry, Workload Identity Federation for GitHub Actions (no long-lived service-account keys). CD job: on merge to `main`, build + push image, deploy to Cloud Run, then run a post-deploy smoke test against the live URL. Secrets via Secret Manager.
**Validate:** merge a trivial change → new revision live within minutes, smoke test green in the Actions run; `/healthz` reachable at the public URL.

### 0.6 Database migrations
Alembic wired to the app; first migration creates the base schema. Migrations run automatically on deploy (or as a release step).
**Validate:** migration applies cleanly on a fresh local DB and on the Cloud SQL/managed instance; migration up/down tested in CI against a Postgres service container.

**Layer 0 exit criterion:** a one-line code change flows branch → PR → green CI → merge → deployed to Cloud Run with zero manual steps besides PR merge.

---

## Layer 1 — Applied AI (ingestion → features → ranking → monitoring)

### 1.1 EDGAR ingestion client
Company universe (start: S&P 500 tickers → CIK mapping from EDGAR's public JSON). Fetch filing indexes and documents (8-K + EX-99 exhibits, 10-K/10-Q) via EDGAR full-text/submissions APIs. Respect SEC fair-access rules (declared User-Agent, ≤10 req/s, backoff). Store raw documents + filing metadata in Postgres; ingestion is idempotent (re-runs don't duplicate).
**Test/validate:** recorded HTTP fixtures (respx/vcr) for unit tests — no live SEC calls in CI; idempotency test (ingest twice → same row count); one manual live backfill of ~20 companies × 4 quarters, spot-checked against EDGAR's website.

### 1.2 Document parsing & normalization
HTML/text extraction from filings and exhibits: strip boilerplate, extract narrative sections (press-release body, MD&A), preserve metadata (company, filing type, period, filed-at). Output: clean normalized documents table — the single corpus both Layer 1 features and Layer 2 RAG consume.
**Test/validate:** golden-file tests — a fixed set of ~10 real filings checked in as fixtures with expected extracted text; parser changes that alter output fail visibly and require updating goldens deliberately.

### 1.3 Target definition & dataset construction (decision spike)
Define what "signal strength" means before modeling: proposed target = forward N-day abnormal return (vs sector or market index) after the filing date, using a free daily-prices source (e.g. Stooq/yfinance). Build the point-in-time dataset joining documents ↔ labels. Explicit leakage rules: features may only use information available at filing time; time-based train/validation splits only.
**Test/validate:** leakage unit tests (no feature timestamp exceeds filing timestamp); label-computation tests against hand-calculated examples; a short written decision record in `docs/` documenting the target choice and its caveats.

### 1.4 Baseline evaluation harness *(seed of EvalKit)*
Ranking-quality metrics before the first model exists: information coefficient (Spearman), NDCG@k, top-vs-bottom decile spread; time-based cross-validation splitter; comparison against naive baselines (random, momentum). Lives in its own module (`finsight/evaluation/`) with clean boundaries — this is deliberately the code that Layer 3 later extracts.
**Test/validate:** harness tested on synthetic data with known answers (a perfect predictor scores 1.0, random scores ~0); baseline numbers recorded.

### 1.5 Feature pipeline v1 (one PR per feature family)
a) **Sentiment/tone** — finance-tuned model (e.g. FinBERT) over narrative sections; tone-change vs the company's prior filing. b) **Metric extraction** — revenue/EPS/guidance mentions via rules + patterns. c) **Topic signals** — topic model or keyword clusters over the corpus. Features materialized to a feature table keyed by (company, filing) with computation timestamps.
**Test/validate:** unit tests on synthetic snippets with known expected outputs; feature distribution snapshot tests (alert on wild shifts when re-running over the fixture corpus); reproducibility check — same input, same features.

### 1.6 Ranking model + MLflow
LightGBM ranker/regressor on the 1.5 features against the 1.3 target. MLflow tracking for params, metrics (from the 1.4 harness), and model artifacts; model registry for the "current production model."
**Test/validate:** gate = must beat naive baselines from 1.4 on time-split validation (document the margin honestly — financial signal is weak; a small but consistent IC is a valid result); training is a single reproducible command; MLflow run recorded per experiment.

### 1.7 Serving endpoints + caching
`GET /rankings` (latest ranked universe), `GET /companies/{ticker}` (signals, features, recent filings). Batch scoring job writes predictions to DB; API reads from DB. Redis caching with sensible TTLs and cache-invalidation on new scores.
**Test/validate:** API contract tests (schema-validated responses); cache behavior tests (second call hits cache, invalidation works); post-deploy smoke extended to hit `/rankings` in prod.

### 1.8 Scheduled pipeline runs
Cloud Scheduler → Cloud Run job: periodic ingest of new filings → parse → featurize → score → refresh rankings. Failures alert (email or GitHub issue).
**Test/validate:** trigger the job manually in prod and watch a new filing flow end-to-end into `/rankings`; simulate a failure → alert fires.

### 1.9 Anomaly detection
Flag unusual filings: language shift vs the company's own history (embedding distance / tone delta), metric surprises. Exposed on the company endpoint and as `GET /anomalies`.
**Test/validate:** injected-anomaly tests (synthetic filing with radically shifted language must flag; a near-duplicate must not); precision spot-check on a manual sample of real flagged filings.

### 1.10 Drift & model monitoring
Feature drift (PSI/KS vs training distribution), prediction drift, and score-decay tracking (rolling realized IC as labels mature), computed by a scheduled job; dashboard or report endpoint; alert thresholds. *Ordering note: land this after 1.8 so there's accumulating production history to monitor — it's the last Layer 1 feature by design.*
**Test/validate:** replay test — feed the drift job a deliberately shifted feature sample → alert triggers; unshifted sample → quiet; dashboard shows real history after a week of scheduled runs.

---

## Layer 2 — LLM intelligence (RAG → agent)

*Depends on 1.2 (normalized corpus). Can start once 1.2 lands — it does not wait for Layer 1 to finish; in practice interleaves with 1.6–1.10.*

### 2.1 Chunking, embeddings, pgvector store
Chunking strategy for filings (section-aware), embedding pipeline, pgvector storage with metadata filters (company, filing type, date). Backfill job over the existing corpus.
**Test/validate:** unit tests for chunker (boundaries, overlap, metadata retention); embedding pipeline tested with a fake embedder in CI; retrieval sanity test on a fixture corpus ("known passage is top-1 for its own query").

### 2.2 Golden Q&A eval set + retrieval evaluation *(before any tuning)*
Hand-build ~50 question → known-source-passage pairs over the fixture corpus (mix: metric lookups, guidance questions, cross-quarter comparisons). Retrieval metrics: recall@k, MRR. This is the yardstick every retrieval change is judged by — extends the 1.4 harness module.
**Test/validate:** the eval runs as a CI job (fixture corpus, deterministic); baseline dense-retrieval numbers recorded.

### 2.3 Hybrid retrieval + reranker
Add BM25/sparse alongside dense, fusion, then a reranker stage. Every change measured against 2.2.
**Test/validate:** gate = hybrid+rerank beats the dense-only baseline on recall@k/MRR; eval regression check in CI so future changes can't silently degrade retrieval.

### 2.4 RAG answer endpoint (streaming)
`POST /ask`: retrieval → grounded answer with citations, streamed (SSE). Guardrails: answers must cite retrieved passages; refuse when retrieval confidence is low.
**Test/validate:** RAGAS-style faithfulness + answer-relevance on the golden set (LLM calls recorded/mocked in CI; full run manual or scheduled); contract tests for the streaming protocol; manual spot-check of ~20 answers for hallucinated numbers — the fatal failure mode in finance.

### 2.5 LLM provider bake-off (Claude vs Gemini)
Add a Gemini free-tier backend to the provider interface alongside Claude Haiku 4.5. Run the identical RAG pipeline (2.4) with each provider over the golden Q&A set and score both with the eval harness: faithfulness, answer relevance, citation grounding, latency, and cost per query. Pick the default provider for the agent (2.6) from the results and record a decision doc in `docs/` with the scorecard.
**Test/validate:** both backends pass the same provider-interface contract test suite; a reproducible eval scorecard is produced for each provider; decision documented with the numbers. This is the eval platform's first real head-to-head use — a dry run for EvalKit's "compare models-under-test" API (3.2).

### 2.6 LangGraph agent
Conversational agent (on the bake-off-winning provider) with tools: document retrieval (2.3), rankings API (1.7), company metrics lookup, anomaly lookup (1.9). Conversation memory, streaming, multi-step tool use ("compare MSFT's last two quarters' guidance and how its ranking moved").
**Test/validate:** scripted multi-turn scenario tests asserting correct tool selection and argument passing (mocked tools in CI); small agent task eval set (~15 tasks) scored end-to-end for task completion; latency budget check.

### 2.7 Tracing & online evaluation
Trace logging for RAG/agent requests (inputs, retrieved chunks, tool calls, outputs), sampled online eval (LLM-as-judge on a slice of real traffic), thumbs-up/down feedback capture on responses.
**Test/validate:** every prod request produces a complete trace; sampled judge scores land in the dashboard; feedback endpoint round-trips.

---

## Layer 3 — EvalKit extraction & OSS release

*Starts only after 1.4/2.2 eval code has been exercised for weeks — Layer 3 is extraction, not invention.*

### 3.1 Extract `evalkit` package
Pull `finsight/evaluation/` into a separate workspace package (`packages/evalkit/`) in the monorepo with zero FinSight-specific imports; FinSight becomes its first consumer.
**Test/validate:** FinSight's test suite and eval CI jobs still pass consuming the extracted package; metric outputs are bit-identical pre/post extraction (parity test).

### 3.2 Unified eval API
One coherent API across ML eval (ranking metrics, time-split CV) and LLM eval (RAGAS, BERTScore, LLM-as-judge adapters). Pluggable datasets, metrics, and model-under-test interfaces.
**Test/validate:** both FinSight use cases (ranking eval, RAG eval) expressed in the new API with no loss of function; adapter unit tests with mocked scorers.

### 3.3 W&B Weave integration
Eval runs log to Weave: datasets, per-example scores, run comparisons, unified dashboard across ML and LLM evals.
**Test/validate:** FinSight's real eval runs visible and comparable in Weave; integration is optional (library works without W&B creds).

### 3.4 CI templates & drift alerting
Reusable GitHub Actions template: run an eval suite on PR, fail on regression vs a baseline. Drift-tracking utility that alerts when scores degrade across scheduled runs.
**Test/validate:** dogfood — FinSight's own retrieval/RAG regression gates (2.3/2.4) migrate to the template; a synthetic regression PR gets correctly blocked.

### 3.5 Docs, packaging, release
Quickstart docs, two worked examples (evaluate a RAG pipeline; evaluate a ranking model), API reference, PyPI packaging, versioning, license, then extraction to its own public repo with its own CI.
**Test/validate:** fresh-environment test — `pip install evalkit` in a clean venv, run the quickstart verbatim, it works; release checklist completed.

---

## Layer 4 — Light frontend (last, after all other layers)

*A thin UI over the existing API — no business logic in the frontend; everything it shows comes from endpoints that already exist and are already tested. Default stack: React + Vite + Tailwind SPA, served as static files from the existing FastAPI service (no new deploy target or infra). Exact stack revisited when picked up.*

### 4.1 Frontend scaffold + rankings view
Vite/React scaffold in `frontend/`, build wired into the Docker image (multi-stage: build static assets, serve via FastAPI). First screen: rankings table from `GET /rankings` (sortable, signal scores, anomaly badges).
**Test/validate:** frontend build + lint added to CI; component smoke tests; deployed page loads on the Cloud Run URL and renders live rankings; post-deploy smoke extended to fetch the index page.

### 4.2 Company detail view
Per-company page from `GET /companies/{ticker}`: signal history, extracted features, recent filings with links to EDGAR source documents, anomaly flags.
**Test/validate:** component tests with mocked API responses; one Playwright end-to-end test against the local compose stack (open rankings → click company → detail renders).

### 4.3 Chat interface (agent)
Chat panel streaming from the agent endpoint (2.6): SSE token streaming, rendered citations linking to source filings, conversation history within a session.
**Test/validate:** streaming-rendering test against a mocked SSE endpoint; Playwright scenario (ask a question → streamed answer with citations appears); manual QA pass for the demo-critical flows.

---

## Implementation order (single sequence across layers)

1. **0.1 → 0.2 → 0.3 → 0.4 → 0.5 → 0.6** (baseline; strictly sequential)
2. **1.1 → 1.2** (corpus exists — unblocks both Layer 1 modeling and Layer 2 RAG)
3. **1.3 → 1.4** (target + eval yardstick before any model)
4. **1.5 → 1.6 → 1.7 → 1.8** (features → model → serving → automation)
5. **2.1 → 2.2 → 2.3 → 2.4 → 2.5** (RAG track incl. provider bake-off; may interleave with step 4 after 1.2)
6. **1.9, 1.10** (anomalies; drift — deliberately late, needs accumulated prod history)
7. **2.6 → 2.7** (agent on the winning provider, then online eval)
8. **3.1 → 3.2 → 3.3 → 3.4 → 3.5** (EvalKit extraction & release)
9. **4.1 → 4.2 → 4.3** (frontend — very last, once every API it consumes is stable)

Dependency rules worth keeping: nothing in Layer 1 modeling starts before 1.3/1.4 exist; nothing in Layer 2 retrieval gets tuned before 2.2 exists; Layer 3 never starts before its source code has real usage history.

## Verification (plan-level)

- **Layer 0 done:** trivial change flows PR → CI → merge → Cloud Run automatically; direct pushes to `main` blocked.
- **Every feature PR:** carries its tests per the sections above; CI green is the merge gate; production smoke test green after merge.
- **Standing checks:** eval regression gates (1.4-based for ranking, 2.2-based for retrieval/RAG) run in CI from the moment they exist, so quality is monotonically protected while features accumulate.
