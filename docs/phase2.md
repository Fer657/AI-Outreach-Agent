# Phase 2 architecture

Phase 2 wraps the Phase 1 stages in a LangGraph pipeline and adds problem
evaluation, solution matching, outreach generation, and the review workflow.

## Pipeline (LangGraph)

`app/graph/workflow.py` builds a linear graph over `AnalysisState`
(`app/graph/state.py`), with one node per stage (`app/graph/nodes.py`):

```
START
  └─ research_node     ResearchService.run + persist prospect & research run
  └─ knowledge_node    RAG query → top-k internal knowledge chunks
  └─ problem_eval      infer problems from signals (+ knowledge)
  └─ solution_match    match Northstar services to each problem
  └─ outreach_node     generate EMAIL + LINKEDIN drafts
  └─ persist_node      save messages, analysis bundle, link them
END
```

Node names must **not** collide with `AnalysisState` keys — that is why the
nodes are named `research_node`, `problem_eval`, `solution_match`, etc. rather
than `research`, `problems`, `solutions`.

`run_analysis(settings, llm, rag, database, prospect)` compiles and invokes the
graph, returning the final `AnalysisState`.

## Engine selection

`ANALYSIS_MODE` (`app/config.py`) decides how problems, solutions and outreach
are produced per stage:

- `auto` (default): heuristic in `RESEARCH_MODE=mock`, LLM in live mode.
- `heuristic`: deterministic rules only.
- `llm`: always try the LLM, fall back to heuristics on failure.

The resolved engine is recorded on the analysis as `llm`, `mixed` or
`heuristic`, derived from per-stage flags (`problems_llm`, `solutions_llm`,
`outreach_llm`) in `AnalysisState`.

## Stages

- **Problem evaluation** (`app/analysis/problem_eval.py`): signals are grouped
  and framed as tentative problems ("may", "could") with a severity. Inference
  never drops the underlying source URL.
- **Solution matching** (`app/analysis/solution_match.py`): each problem is
  matched to Northstar capabilities using the retrieved knowledge chunks.
- **Outreach** (`app/outreach/generator.py`): `heuristic_draft` produces
  subject + body for EMAIL and LINKEDIN; `generate_outreach` returns one draft
  per channel. `generate_draft` is the shared entry point for LLM/heuristic.

## Persistence (SQLite)

`app/storage/db.py` adds an `analyses` table storing the full `AnalysisBundle`
JSON, plus message migrations (`analysis_id`, `subject`, `confidence`,
`referenced_sources`). Persist order is message-first: drafts are saved, the
bundle is written (`save_analysis`), then
`link_messages_to_analysis` ties messages to the analysis.

Migrations run after table creation but **before** indexes, because indexes may
reference newly-added columns (`_SCHEMA` → `_migrate` → `_INDEXES`).

## Review workflow (`app/api/routes.py`)

| Method | Path                            | Behavior                                    |
| ------ | ------------------------------- | ------------------------------------------- |
| GET    | `/api/prospects/{id}/messages`  | List messages for a prospect                |
| PATCH  | `/api/outreach/{id}`            | Apply edits, set status `EDITED`            |
| POST   | `/api/outreach/{id}/approve`    | Set status `APPROVED`                       |
| POST   | `/api/outreach/{id}/regenerate` | Reload the stored bundle, regenerate draft  |

Regeneration reads the persisted `AnalysisBundle` via `get_analysis` so it works
across restarts without re-running research.

## Demo caveat

Northstar Labs and ApexFlow are fictional. Mock research is synthetic and
heuristic output is illustrative only — never treat generated outreach as
verified fact about a real company.
