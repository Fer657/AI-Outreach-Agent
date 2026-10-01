"use client";

import { useCallback, useEffect, useState } from "react";

import { ProspectForm } from "@/components/ProspectForm";
import {
  KnowledgePanel,
  ProblemsPanel,
  SignalsPanel,
  SolutionsPanel,
} from "@/components/AnalysisPanels";
import { OutreachCard } from "@/components/OutreachCard";
import { Badge, Empty, Section, Spinner } from "@/components/ui";
import {
  analyze,
  ApiRequestError,
  generateOutreach,
  getHealth,
  listMessages,
} from "@/lib/api";
import type {
  AnalyzeResponse,
  HealthResponse,
  OutreachMessage,
  ProspectInput,
  SolutionMatch,
} from "@/lib/types";

export default function Home() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [messages, setMessages] = useState<OutreachMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ code: string; message: string } | null>(
    null,
  );
  const [selectedProblem, setSelectedProblem] = useState<string | null>(null);
  const [selectedSolution, setSelectedSolution] =
    useState<SolutionMatch | null>(null);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() =>
        setHealth({
          status: "unreachable",
          app: "unknown",
          version: "unknown",
          environment: "unknown",
          research_mode: "unknown",
          analysis_mode: "unknown",
          llm_provider: "unknown",
          llm_model: "unknown",
          rag_index_ready: false,
          knowledge_dir: "",
          database: "",
        }),
      );
  }, []);

  const onSubmit = useCallback(async (prospect: ProspectInput) => {
    setLoading(true);
    setError(null);
    setResult(null);
    setMessages([]);
    setSelectedProblem(null);
    setSelectedSolution(null);
    try {
      const data = await analyze(prospect);
      setResult(data);
      setMessages(await listMessages(data.prospect_id));
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setError({ code: err.code, message: err.message });
      } else {
        setError({ code: "error", message: "Unexpected error." });
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const onSelectProblem = useCallback((title: string) => {
    setSelectedProblem(title);
    setSelectedSolution(null);
  }, []);

  const onSelectSolution = useCallback((solution: SolutionMatch) => {
    setSelectedSolution(solution);
  }, []);

  const onGenerate = useCallback(async () => {
    if (!result || !selectedProblem || !selectedSolution) return;
    setGenerating(true);
    setError(null);
    try {
      const created = await generateOutreach(result.analysis_id, {
        problem_title: selectedProblem,
        service: selectedSolution.service,
      });
      setMessages((prev) => [...created, ...prev]);
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setError({ code: err.code, message: err.message });
      } else {
        setError({ code: "error", message: "Unexpected error." });
      }
    } finally {
      setGenerating(false);
    }
  }, [result, selectedProblem, selectedSolution]);

  const onMessageUpdated = useCallback((updated: OutreachMessage) => {
    setMessages((prev) =>
      prev.map((message) => (message.id === updated.id ? updated : message)),
    );
  }, []);

  const online = health?.status === "ok";

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-zinc-900">
            Northstar Sales Intelligence
          </h1>
          <p className="text-sm text-zinc-500">
            Research → signals → problems → solutions → outreach.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex items-center gap-1.5 text-xs text-zinc-500">
            <span
              className={`h-2 w-2 rounded-full ${
                online ? "bg-emerald-500" : "bg-rose-500"
              }`}
            />
            {online ? "backend online" : "backend offline"}
          </span>
          {health && online && (
            <>
              <Badge tone="accent">analysis: {health.analysis_mode}</Badge>
              <Badge>{health.llm_provider}</Badge>
              {health.llm_model && <Badge>{health.llm_model}</Badge>}
              <Badge tone={health.rag_index_ready ? "success" : "warning"}>
                RAG {health.rag_index_ready ? "ready" : "missing"}
              </Badge>
              <Badge>v{health.version}</Badge>
            </>
          )}
        </div>
      </header>

      {error && (
        <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
          <span className="font-semibold">[{error.code}]</span> {error.message}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[360px_1fr]">
        <div className="flex flex-col gap-6">
          <ProspectForm onSubmit={onSubmit} loading={loading} />
          {result && <ResearchSummary result={result} />}
          {result && <SignalsPanel signals={result.bundle.signals} />}
        </div>

        <div className="flex flex-col gap-6">
          {!result ? (
            <div className="rounded-xl border border-dashed border-zinc-300 bg-white/60 p-10 text-center text-sm text-zinc-400">
              Run an analysis to see problems, solution matches, and outreach
              drafts.
            </div>
          ) : (
            <>
              <ProblemsPanel
                problems={result.problems}
                selectedTitle={selectedProblem}
                onSelect={onSelectProblem}
              />
              <SolutionsPanel
                solutions={result.solutions}
                selectedProblemTitle={selectedProblem}
                selected={selectedSolution}
                onSelect={onSelectSolution}
              />
              <KnowledgePanel chunks={result.knowledge} />
              <Section
                title="Outreach drafts"
                count={messages.length}
                action={
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-zinc-400">
                      {selectedProblem && selectedSolution
                        ? `“${selectedProblem}” · ${selectedSolution.service}`
                        : "select a problem and a solution"}
                    </span>
                    <button
                      type="button"
                      onClick={onGenerate}
                      disabled={!selectedProblem || !selectedSolution || generating}
                      className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-zinc-300"
                    >
                      {generating && <Spinner />}
                      {generating ? "Generating…" : "Generate drafts"}
                    </button>
                  </div>
                }
              >
                {messages.length === 0 ? (
                  <Empty>
                    Pick a problem and a solution above, then generate email and
                    LinkedIn drafts.
                  </Empty>
                ) : (
                  <div className="flex flex-col gap-4">
                    {messages.map((message) => (
                      <OutreachCard
                        key={`${message.id}-${message.updated_at}`}
                        message={message}
                        onUpdated={onMessageUpdated}
                      />
                    ))}
                  </div>
                )}
              </Section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function ResearchSummary({ result }: { result: AnalyzeResponse }) {
  const { bundle } = result;
  const stats = bundle.stats;
  const mocked = bundle.mode === "mock";

  return (
    <Section title="Research" count={bundle.evidence.length}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge tone={result.mode === "live" ? "success" : "neutral"}>
          {result.mode} mode
        </Badge>
        <Badge tone="accent">{result.engine}</Badge>
        {bundle.company_url && (
          <a
            href={bundle.company_url}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-indigo-600 hover:underline"
          >
            {bundle.company_url}
          </a>
        )}
      </div>

      {mocked && (
        <p className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
          Mock mode: sources below are synthetic demo data, not real facts.
        </p>
      )}

      <dl className="grid grid-cols-2 gap-2 text-xs">
        <Stat label="Queries" value={stats.queries_run} />
        <Stat label="Raw results" value={stats.raw_results} />
        <Stat label="After dedupe" value={stats.after_dedupe} />
        <Stat label="Evidence selected" value={stats.selected_evidence} />
      </dl>

      <p className="mt-3 text-xs text-zinc-400">
        Generated {bundle.generated_at.slice(0, 19).replace("T", " ")}
      </p>
    </Section>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-zinc-50 px-3 py-2">
      <dt className="text-zinc-400">{label}</dt>
      <dd className="text-sm font-semibold tabular-nums text-zinc-800">
        {value}
      </dd>
    </div>
  );
}
