"use client";

import { useState } from "react";

import { Spinner } from "./ui";
import type { ProspectInput } from "@/lib/types";

const DEMO: ProspectInput = {
  prospect_name: "Dana Whitfield",
  company: "HubSpot",
  job_title: "VP of Growth",
  company_url: "https://www.hubspot.com",
  referral: null,
  x_post_url: null,
};

const EMPTY: ProspectInput = {
  prospect_name: "",
  company: "",
  job_title: "",
  company_url: "",
  referral: "",
  x_post_url: "",
};

export function ProspectForm({
  onSubmit,
  loading,
}: {
  onSubmit: (input: ProspectInput) => void | Promise<void>;
  loading: boolean;
}) {
  const [form, setForm] = useState<ProspectInput>(EMPTY);

  const set =
    (key: keyof ProspectInput) =>
    (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm((prev) => ({ ...prev, [key]: event.target.value }));

  const canSubmit = form.prospect_name.trim() !== "" && form.company.trim() !== "";

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit && !loading) void onSubmit(form);
      }}
      className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-800">Prospect</h2>
        <button
          type="button"
          onClick={() => setForm(DEMO)}
          className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
        >
          Load demo prospect
        </button>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field
          label="Prospect name"
          required
          value={form.prospect_name}
          onChange={set("prospect_name")}
          placeholder="Dana Whitfield"
        />
        <Field
          label="Company"
          required
          value={form.company}
          onChange={set("company")}
          placeholder="HubSpot"
        />
        <Field
          label="Job title"
          value={form.job_title ?? ""}
          onChange={set("job_title")}
          placeholder="VP of Growth"
        />
        <Field
          label="Company URL"
          value={form.company_url ?? ""}
          onChange={set("company_url")}
          placeholder="https://example.com"
        />
        <Field
          label="Referral / warm intro"
          value={form.referral ?? ""}
          onChange={set("referral")}
          placeholder="Optional"
        />
        <Field
          label="X post URL"
          value={form.x_post_url ?? ""}
          onChange={set("x_post_url")}
          placeholder="Optional"
        />
      </div>

      <button
        type="submit"
        disabled={!canSubmit || loading}
        className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-zinc-300"
      >
        {loading ? (
          <>
            <Spinner /> Running analysis…
          </>
        ) : (
          "Run analysis"
        )}
      </button>
      <p className="mt-2 text-center text-xs text-zinc-400">
        Runs research → knowledge → problems → solutions → outreach.
      </p>
    </form>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  required,
}: {
  label: string;
  value: string;
  onChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-zinc-500">
        {label}
        {required && <span className="text-rose-500"> *</span>}
      </span>
      <input
        type="text"
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        required={required}
        className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-800 outline-none transition placeholder:text-zinc-300 focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
      />
    </label>
  );
}
