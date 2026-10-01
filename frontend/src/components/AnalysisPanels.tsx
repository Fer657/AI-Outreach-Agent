import { Badge, Empty, ScoreBar, Section } from "./ui";
import type {
  Problem,
  RetrievedChunk,
  Severity,
  Signal,
  SolutionMatch,
} from "@/lib/types";

const SEVERITY_TONE: Record<Severity, "danger" | "warning" | "info"> = {
  HIGH: "danger",
  MEDIUM: "warning",
  LOW: "info",
};

function signalLabel(value: string): string {
  const spaced = value.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1).toLowerCase();
}

export function SignalsPanel({ signals }: { signals: Signal[] }) {
  return (
    <Section title="Signals" count={signals.length}>
      {signals.length === 0 ? (
        <Empty>No signals were extracted.</Empty>
      ) : (
        <ul className="flex flex-col gap-3">
          {signals.map((signal, index) => (
            <li
              key={`${signal.source_url}-${index}`}
              className="rounded-lg border border-zinc-100 bg-zinc-50/60 p-3"
            >
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <Badge tone="accent">{signalLabel(signal.signal_type)}</Badge>
                <a
                  href={signal.source_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm font-semibold text-zinc-800 hover:text-indigo-700 hover:underline"
                >
                  {signal.title}
                </a>
              </div>
              <p className="text-sm text-zinc-600">{signal.description}</p>
              {signal.evidence && (
                <blockquote className="mt-2 border-l-2 border-zinc-200 pl-3 text-xs italic text-zinc-500">
                  {signal.evidence}
                </blockquote>
              )}
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-400">
                <span>{signal.source_name}</span>
                {signal.published_date && <span>· {signal.published_date}</span>}
                <span>· retrieved {signal.retrieved_date.slice(0, 10)}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

export function KnowledgePanel({ chunks }: { chunks: RetrievedChunk[] }) {
  return (
    <Section title="Knowledge retrieved" count={chunks.length}>
      {chunks.length === 0 ? (
        <Empty>No knowledge chunks matched this prospect.</Empty>
      ) : (
        <ul className="flex flex-col gap-3">
          {chunks.map((chunk) => (
            <li
              key={chunk.chunk_id}
              className="rounded-lg border border-zinc-100 p-3"
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="text-sm font-semibold text-zinc-800">
                  {chunk.heading || chunk.source}
                </span>
                <Badge>{chunk.score.toFixed(3)}</Badge>
              </div>
              <p className="text-xs text-zinc-400">{chunk.source}</p>
              <p className="mt-1 line-clamp-4 text-sm text-zinc-600">
                {chunk.text}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

export function ProblemsPanel({
  problems,
  selectedTitle,
  onSelect,
}: {
  problems: Problem[];
  selectedTitle: string | null;
  onSelect: (title: string) => void;
}) {
  return (
    <Section
      title="Problems"
      count={problems.length}
      action={
        <span className="text-xs text-zinc-400">Click one to build a draft</span>
      }
    >
      {problems.length === 0 ? (
        <Empty>No problems were identified.</Empty>
      ) : (
        <ul className="flex flex-col gap-3">
          {problems.map((problem) => {
            const selected = problem.title === selectedTitle;
            return (
              <li key={problem.title}>
                <button
                  type="button"
                  onClick={() => onSelect(problem.title)}
                  aria-pressed={selected}
                  className={`w-full rounded-lg border p-3 text-left transition ${
                    selected
                      ? "border-indigo-400 bg-indigo-50/60 ring-2 ring-indigo-100"
                      : "border-zinc-100 hover:border-indigo-200 hover:bg-zinc-50"
                  }`}
                >
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <Badge tone={SEVERITY_TONE[problem.severity]}>
                      {problem.severity}
                    </Badge>
                    <span className="text-sm font-semibold text-zinc-800">
                      {problem.title}
                    </span>
                    <span className="ml-auto text-xs text-zinc-400">
                      confidence {(problem.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p className="text-sm text-zinc-600">{problem.description}</p>
                  <p className="mt-1 text-xs text-zinc-500">
                    {problem.rationale}
                  </p>
                  {problem.source_urls.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {problem.source_urls.map((url) => (
                        <span
                          key={url}
                          className="max-w-full truncate rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-500"
                        >
                          {hostname(url)}
                        </span>
                      ))}
                    </div>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
}

export function SolutionsPanel({
  solutions,
  selectedProblemTitle,
  selected,
  onSelect,
}: {
  solutions: SolutionMatch[];
  selectedProblemTitle: string | null;
  selected: SolutionMatch | null;
  onSelect: (solution: SolutionMatch) => void;
}) {
  const matching = selectedProblemTitle
    ? solutions.filter((s) => s.problem_title === selectedProblemTitle)
    : solutions;
  const visible = matching.length > 0 ? matching : solutions;
  const fallback = matching.length === 0 && selectedProblemTitle !== null;

  return (
    <Section
      title="Solution matches"
      count={visible.length}
      action={
        <span className="text-xs text-zinc-400">
          {selectedProblemTitle ? "for the selected problem" : "Click one to build a draft"}
        </span>
      }
    >
      {visible.length === 0 ? (
        <Empty>No solution matches were found.</Empty>
      ) : (
        <>
          {fallback && (
            <p className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
              No match is keyed to the selected problem; showing all matches.
            </p>
          )}
          <ul className="flex flex-col gap-3">
            {visible.map((solution, index) => {
              const isSelected =
                selected !== null &&
                selected.service === solution.service &&
                selected.problem_title === solution.problem_title;
              return (
                <li key={`${solution.service}-${index}`}>
                  <button
                    type="button"
                    onClick={() => onSelect(solution)}
                    aria-pressed={isSelected}
                    className={`w-full rounded-lg border p-3 text-left transition ${
                      isSelected
                        ? "border-indigo-400 bg-indigo-50/60 ring-2 ring-indigo-100"
                        : "border-zinc-100 hover:border-indigo-200 hover:bg-zinc-50"
                    }`}
                  >
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <Badge tone="accent">{solution.service}</Badge>
                      <span className="text-xs text-zinc-400">
                        for “{solution.problem_title}”
                      </span>
                    </div>
                    <p className="text-sm text-zinc-600">
                      {solution.how_it_helps}
                    </p>
                    <div className="mt-2">
                      <ScoreBar
                        label="relevance"
                        value={solution.relevance_score}
                      />
                    </div>
                    {solution.rationale && (
                      <p className="mt-1 text-xs text-zinc-500">
                        {solution.rationale}
                      </p>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </Section>
  );
}

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
