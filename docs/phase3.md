# Phase 3 architecture (frontend)

Phase 3 adds a Next.js 16 app that drives the Phase 2 backend: enter a prospect,
run the pipeline, review signals/problems/solutions, then edit, approve, and
regenerate outreach drafts.

## Stack

- **Next.js 16** (Turbopack, App Router, `src/` dir), **React 19**.
- **Tailwind CSS v4** via `@tailwindcss/postcss` and `@import "tailwindcss"` in
  `src/app/globals.css` (no `tailwind.config.js`).
- TypeScript strict, import alias `@/*` → `src/*`.
- The whole UI is a single **client component** (`src/app/page.tsx`, `"use client"`).

> Next 16 differs from older Next versions. `frontend/AGENTS.md` requires reading
> the version-matched docs under `frontend/node_modules/next/dist/docs/` before
> editing. Note `layout.tsx` uses the generated global `LayoutProps<"/">` type.

## Structure

```
src/lib/types.ts        TS types mirroring the backend API schemas
src/lib/api.ts          fetch client (base URL NEXT_PUBLIC_API_BASE_URL)
src/components/ui.tsx   Badge, Section, ScoreBar, Spinner, Empty
src/components/ProspectForm.tsx      controlled prospect form (+ demo prefill)
src/components/AnalysisPanels.tsx    Signals / Knowledge / Problems / Solutions
src/components/OutreachCard.tsx      edit / approve / regenerate a draft
src/app/page.tsx        page orchestration + header/health
```

## Data flow

1. `getHealth()` on mount → header shows backend status, analysis mode,
   provider/model, RAG readiness, version.
2. `analyze(prospect)` → `AnalyzeResponse` (`bundle`, `knowledge`, `problems`,
   `solutions`, `outreach`).
3. `listMessages(prospect_id)` → canonical `OutreachMessage[]` (the analyze
   response's `outreach` is `OutreachDraft[]`, so listing reuses the stored
   records with `id`/`status`).
4. Card actions call `updateMessage` (PATCH → `EDITED`), `approveMessage`
   (`APPROVED`), `regenerateMessage` (re-runs generation from the stored
   analysis). Each returns the updated message and replaces it in state.

## Notes and constraints

- **API field names differ from the drafts model.** `OutreachDraft` uses `body`
  (not `content`); `OutreachMessage` uses `content`. Types in `types.ts` reflect
  this exactly.
- **Resetting card state.** `OutreachCard` is keyed by
  `` `${message.id}-${message.updated_at}` `` in `page.tsx`, so an updated record
  remounts the card and seeds subject/body from the fresh message. This avoids
  syncing props to state inside an effect, which the React 19 lint rule
  `react-hooks/set-state-in-effect` rejects.
- **Errors.** `api.ts` maps backend error bodies
  (`{ error, message, detail }`) to `ApiRequestError` with a stable `code`; the
  page renders `[code] message`. A network failure (backend down) surfaces as
  `network_error`.
- **Demo honesty.** When `bundle.mode === "mock"` the research panel shows an
  amber notice that sources are synthetic demo data.
- **CORS.** Backend `app/main.py` already allows `http://localhost:3000` and
  `http://127.0.0.1:3000`.

## Verification

- `npm run lint` — clean.
- `npm run build` — compiles, type-checks, prerenders `/` (static).
- Runtime smoke: `npm run start` served `/` with HTTP 200 and rendered the
  header title and the analyze form.
