"use client";

import { useState } from "react";

import { Badge, Spinner } from "./ui";
import {
  approveMessage,
  regenerateMessage,
  updateMessage,
} from "@/lib/api";
import type { OutreachMessage, OutreachStatus } from "@/lib/types";

const STATUS_TONE: Record<
  OutreachStatus,
  "neutral" | "warning" | "success"
> = {
  DRAFT: "neutral",
  EDITED: "warning",
  APPROVED: "success",
};

export function OutreachCard({
  message,
  onUpdated,
}: {
  message: OutreachMessage;
  onUpdated: (message: OutreachMessage) => void;
}) {
  const [subject, setSubject] = useState(message.subject ?? "");
  const [content, setContent] = useState(message.content);
  const [busy, setBusy] = useState<null | "save" | "approve" | "regenerate">(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  const dirty =
    subject !== (message.subject ?? "") || content !== message.content;

  async function run(
    kind: "save" | "approve" | "regenerate",
    fn: () => Promise<OutreachMessage>,
  ) {
    setBusy(kind);
    setError(null);
    try {
      onUpdated(await fn());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <article className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
      <header className="mb-3 flex flex-wrap items-center gap-2">
        <Badge tone="info">{message.channel}</Badge>
        <Badge tone={STATUS_TONE[message.status]}>{message.status}</Badge>
        {message.confidence !== null && (
          <Badge>confidence {message.confidence.toFixed(1)}/10</Badge>
        )}
        <span className="ml-auto text-xs text-zinc-400">
          #{message.id} · updated {message.updated_at.slice(0, 19).replace("T", " ")}
        </span>
      </header>

      {message.problem_title && (
        <p className="mb-3 text-xs text-zinc-400">
          For “{message.problem_title}”
          {message.service ? ` · ${message.service}` : ""}
        </p>
      )}

      <label className="mb-2 flex flex-col gap-1">
        <span className="text-xs font-medium text-zinc-500">Subject</span>
        <input
          type="text"
          value={subject}
          onChange={(event) => setSubject(event.target.value)}
          className="rounded-lg border border-zinc-200 px-3 py-2 text-sm font-medium text-zinc-800 outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
        />
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-zinc-500">Body</span>
        <textarea
          value={content}
          onChange={(event) => setContent(event.target.value)}
          rows={10}
          className="resize-y rounded-lg border border-zinc-200 px-3 py-2 text-sm leading-relaxed text-zinc-800 outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
        />
      </label>

      {message.referenced_sources.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-xs font-medium text-zinc-500">
            Referenced sources
          </p>
          <div className="flex flex-wrap gap-1.5">
            {message.referenced_sources.map((url) => (
              <a
                key={url}
                href={url}
                target="_blank"
                rel="noreferrer"
                className="max-w-full truncate rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-500 hover:text-indigo-700"
              >
                {url}
              </a>
            ))}
          </div>
        </div>
      )}

      {error && (
        <p className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {error}
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={!dirty || busy !== null}
          onClick={() =>
            void run("save", () =>
              updateMessage(message.id, { subject, content }),
            )
          }
          className="rounded-lg bg-zinc-800 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:bg-zinc-300"
        >
          {busy === "save" ? <Spinner /> : "Save edits"}
        </button>
        <button
          type="button"
          disabled={busy !== null || message.status === "APPROVED"}
          onClick={() => void run("approve", () => approveMessage(message.id))}
          className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-zinc-300"
        >
          {busy === "approve" ? <Spinner /> : "Approve"}
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() =>
            void run("regenerate", () => regenerateMessage(message.id))
          }
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-semibold text-zinc-700 transition hover:bg-zinc-50 disabled:cursor-not-allowed disabled:text-zinc-300"
        >
          {busy === "regenerate" ? <Spinner className="border-zinc-300 border-t-zinc-700" /> : "Regenerate"}
        </button>
      </div>
    </article>
  );
}
