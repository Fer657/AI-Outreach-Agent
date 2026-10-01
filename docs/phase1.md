# Phase 1 architecture

## Pipeline

```
ProspectInput
  └─ query generation            app/research/query_generator.py
  └─ search (live)               tavily_client.py + website_fetcher.py + x_client.py
     OR mock load                app/research/mock.py  (northstar/mock/*.json)
  └─ de-duplicate                app/research/dedupe.py
  └─ score & select              app/research/ranker.py
       relevance (0.40) · source quality (0.35) · recency (0.25); MIN_RELEVANCE=2.5
  └─ signal extraction           app/signals/extractor.py (LLM) or precomputed (mock)
  └─ ResearchBundle              app/models/research.py

/api/analyze additionally:
  └─ RAG retrieve                app/rag/retriever.py
       markdown → chunks → Ollama embeddings → FAISS (cosine) → top-k
```

## Design decisions

- **Provider-agnostic LLM.** Application code depends only on `LLMProvider`
  (`app/llm/base.py`). OpenRouter, DeepSeek and Ollama are interchangeable via
  `LLM_PROVIDER`; DeepSeek-specific behavior never leaks into app logic.
- **Fact vs. inference.** Signals carry only observable statements plus a real
  `source_url`. The extractor discards any signal whose source URL does not match
  retrieved evidence (`app/signals/extractor.py`). Inference/flagship framing is
  left to Phase 2 problem evaluation.
- **No X scraping.** `app/research/x_client.py` uses the official X API when
  `X_API_BEARER_TOKEN` is set, otherwise a single user-supplied public URL, and
  is a no-op otherwise.
- **Local RAG.** Embeddings run through Ollama (`nomic-embed-text`, 768-dim), so
  internal knowledge never leaves the machine. The FAISS index is cached in
  `backend/data/rag_index/` and rebuilds only when the embed model changes.
- **Deterministic, non-agentic research.** Ranking and filtering are plain,
  auditable code — no autonomous agents in Phase 1.

## Persistence (SQLite)

`prospects` → `research_runs` (full bundle JSON) → `generated_messages`
(`channel`, `status ∈ {DRAFT, EDITED, APPROVED}`, timestamps). Phase 1 writes
prospects and research runs; the message table is ready for Phase 2.

## Errors

Typed errors in `app/errors.py` (`ConfigError`, `ResearchError`,
`SearchAPIError`, `NoResultsError`, `LLMError`, `RAGError`, `StorageError`) map
to stable HTTP codes and are serialized by handlers in `app/main.py`.
