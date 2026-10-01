# Northstar Labs — AI B2B Sales Intelligence (Phase 3)

Prospect research → business-signal extraction → internal knowledge retrieval
(RAG) → inferred problem evaluation → solution matching → outreach drafts,
orchestrated with LangGraph and served over FastAPI. Phase 3 adds a Next.js
frontend that drives the whole flow and the human-in-the-loop
`DRAFT → EDITED → APPROVED` workflow with regeneration.

> **Demo data notice.** Northstar Labs and ApexFlow are fictional demonstration
> companies. The `knowledge/` documents and `northstar/mock/hubspot_research.json`
> fixture are synthetic. Nothing generated from them is real, verified research
> and must not be presented to end users as factual.

## Layout

```
backend/                 FastAPI app (app/)
  app/config.py          env-driven settings
  app/llm/               provider-agnostic LLM layer (openrouter|deepseek|ollama)
  app/research/          query gen, Tavily, website, X, dedupe, rank, mock
  app/signals/           LLM signal extraction (+ precomputed mock signals)
  app/analysis/          problem evaluation + solution matching (heuristic/LLM)
  app/outreach/          outreach draft generation (heuristic/LLM)
  app/graph/             LangGraph pipeline (state, nodes, workflow)
  app/rag/               markdown chunker, Ollama embeddings, FAISS store
  app/storage/           SQLite persistence (prospects, runs, analyses, messages)
  app/api/               routes + schemas
frontend/                Next.js 16 app (src/)
  src/lib/               typed API client (api.ts) + shared types (types.ts)
  src/components/        prospect form, analysis panels, outreach card
  src/app/               App Router entry (page.tsx, layout.tsx)
knowledge/               internal knowledge base (markdown → RAG)
northstar/               source PDFs + mock/ fixtures
docs/                    architecture and API notes
```

## Setup

Requires Python 3.12 and (optionally) [Ollama](https://ollama.com) for local LLM
and embeddings.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env    # then edit if you want live mode / real keys
```

For RAG (embeddings) with the default config:

```powershell
ollama pull nomic-embed-text
ollama pull qwen3:8b           # only needed for live-mode signal extraction
ollama serve                   # if not already running
```

## Run

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Interactive docs: http://localhost:8000/docs

### Frontend

Requires Node 20+ (built with Node 24). Start the backend first, then:

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local   # optional: override NEXT_PUBLIC_API_BASE_URL
npm run dev
```

Open http://localhost:3000. The UI calls the backend at
`NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`) and shows a
connection indicator plus the active analysis mode/provider. The backend already
allows CORS from `http://localhost:3000`.

`npm run lint` and `npm run build` (which type-checks) both pass.

## Modes

- `RESEARCH_MODE=mock` (default): fully offline. Research comes from
  `northstar/mock/<company-slug>_research.json` and signals are precomputed, so
  **no LLM and no external API are needed** for the research demo. The
  `/api/analyze` knowledge step still needs Ollama for embeddings.
- `RESEARCH_MODE=live`: uses Tavily (`TAVILY_API_KEY`), the company website, and
  the official X API if configured. Signals are extracted with the configured
  LLM. (Behavior in live mode is not yet exercised by the demo.)
- `ANALYSIS_MODE` controls problem evaluation, solution matching and outreach:
  `auto` (default) uses deterministic heuristics in mock mode and the LLM in
  live mode; `heuristic` always uses rules; `llm` always tries the LLM (falling
  back to heuristics on failure).

## Endpoints

| Method | Path                              | Purpose                                                    |
| ------ | --------------------------------- | ---------------------------------------------------------- |
| GET    | `/api/health`                     | Liveness + configuration summary                           |
| POST   | `/api/research`                   | Run research + signal extraction, persist the run          |
| POST   | `/api/analyze`                    | Full pipeline: research → knowledge → problems → solutions → outreach |
| GET    | `/api/prospects/{id}/messages`    | List generated outreach messages for a prospect            |
| PATCH  | `/api/outreach/{id}`              | Edit a draft (sets status `EDITED`)                        |
| POST   | `/api/outreach/{id}/approve`      | Approve a message (status `APPROVED`)                      |
| POST   | `/api/outreach/{id}/regenerate`   | Regenerate a draft from the stored analysis                |

Example:

```powershell
$body = @{ prospect_name="Alex Morgan"; company="HubSpot"; job_title="VP of Sales"; company_url="https://www.hubspot.com/" } | ConvertTo-Json
$r = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/analyze -ContentType application/json -Body $body
Invoke-RestMethod -Uri "http://localhost:8000/api/prospects/$($r.prospect_id)/messages"
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/outreach/$($r.outreach[0].id)/approve"
```

Errors return `{ "error", "message", "detail" }` with stable `error` codes
(`validation_error`, `no_results`, `research_error`, `llm_error`, `rag_error`,
`not_found`, ...).

## Configuration

All settings come from `backend/.env` (see `.env.example`). Key variables:
`LLM_PROVIDER`, `RESEARCH_MODE`, `ANALYSIS_MODE`, `TAVILY_API_KEY`,
`OLLAMA_MODEL`, `OLLAMA_EMBED_MODEL`, `RAG_TOP_K`, `RAG_CHUNK_SIZE`,
`RAG_CHUNK_OVERLAP`. API keys are **never** hardcoded; `.env` is git-ignored.

Generated artifacts (SQLite DB and FAISS index) live in `backend/data/`.

## Phase boundary

Phases 1–3 are built: the LangGraph backend and the Next.js frontend that drives
it end to end (analyze, review signals/problems/solutions, then edit, approve,
and regenerate outreach). The frontend is a single-page client app; there is no
auth or multi-user/tenancy layer.
