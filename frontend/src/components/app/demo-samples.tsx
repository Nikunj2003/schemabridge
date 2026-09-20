"use client";

import { useEffect, useState } from "react";
import { Dialog } from "@/components/ui/dialog";
import { api, type SampleFile } from "@/lib/api";

/**
 * The sample exports, and what each combination is built to provoke.
 *
 * Every behaviour claimed below is one the test suite pins against these exact
 * files, so the guide cannot promise something the engine does not do. The files
 * are fetched rather than hardcoded: a deployment missing its fixtures should
 * show nothing to download instead of four broken links.
 */

type Scenario = {
  title: string;
  files: string[];
  outcome: string;
  detail: string;
  /** Whether the run stops for a decision. Measured against these files, not assumed. */
  asks: boolean;
  /** Short label for the badge, so "no questions" is not the only alternative. */
  badge: string;
};

const SCENARIOS: Scenario[] = [
  {
    title: "A clean file, start to finish",
    badge: "No questions",
    files: ["employees-clean.csv"],
    outcome: "Runs to delivery without asking you anything",
    detail:
      "Headers already match the built-in contract, every value validates on the first pass, and all three records reach the destination. The audit shows the rule engine doing all of it and no model request being made.",
    asks: false,
  },
  {
    title: "Two exports that disagree",
    badge: "Asks you",
    files: ["employees-legacy.csv", "employees-hr-export.csv"],
    outcome: "Reconciles what it can, then asks about the rest",
    detail:
      "Terse headers (emp_id, emp_nm, doj) are matched without being told how, and rows for the same employee are merged across both files. Then it stops: E-1003 carries two different joining dates, one column is genuinely ambiguous, and a date like 03/04/2026 is two real dates. Those become questions.",
    asks: true,
  },
  {
    title: "An Excel workbook with an unknown column",
    badge: "Uses the model",
    files: ["employees-directory.xlsx"],
    outcome: "Spends one model request, then finishes on its own",
    detail:
      "Typed Excel dates arrive as calendar dates and most headers resolve without help, but no alias table recognises “Cost Centre Ref”. That single column is what the model is asked about. Nothing blocks, so the run completes — and it offers to remember the answer, which is what makes the next export need no model at all.",
    asks: false,
  },
  {
    title: "Everything at once",
    badge: "Asks you",
    files: ["employees-legacy.csv", "employees-hr-export.csv", "employees-directory.xlsx"],
    outcome: "The full picture, in one run",
    detail:
      "Three files, two formats, overlapping people. The widest demonstration of reconciliation, escalation and delivery together — and the best way to see the counters and the audit trail carry their weight.",
    asks: true,
  },
];

export function DemoSamples() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-surface px-2.5 py-1 text-[12.5px] font-medium text-ink-muted transition-colors hover:bg-sunken hover:text-ink"
      >
        <IconInfo />
        Demo files
      </button>
      <Dialog open={open} onOpenChange={setOpen} title="Demo files">
        <Contents />
      </Dialog>
    </>
  );
}

function Contents() {
  const [files, setFiles] = useState<SampleFile[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api
      .samples()
      .then((result) => live && setFiles(result.files))
      .catch(() => live && setError("The sample files could not be listed."));
    return () => {
      live = false;
    };
  }, []);

  const available = new Set((files ?? []).map((file) => file.name));

  return (
    <div className="px-5 py-5 sm:px-6">
      <p className="max-w-[64ch] text-[13.5px] leading-relaxed text-ink-muted">
        Synthetic exports written to exercise specific behaviour. Download the ones a
        scenario names, then upload them together — the combination is what decides
        whether the run finishes on its own or stops to ask you something.
      </p>

      {error && (
        <p role="alert" className="mt-4 rounded-md border border-problem/40 bg-problem-soft px-3 py-2 text-[13px]">
          {error}
        </p>
      )}

      <ol className="mt-5 space-y-3">
        {SCENARIOS.map((scenario, index) => (
          <li key={scenario.title} className="rounded-lg border border-line bg-canvas px-4 py-3.5">
            <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
              <span className="text-[12px] font-semibold text-ink-subtle tnum">{index + 1}</span>
              <h3 className="text-[14px] font-semibold">{scenario.title}</h3>
              <span
                className={
                  scenario.asks
                    ? "rounded-full bg-attention-soft px-2 py-0.5 text-[11px] font-medium text-attention"
                    : "rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-medium text-accent-ink"
                }
              >
                {scenario.badge}
              </span>
            </div>

            <p className="mt-1.5 text-[13px] font-medium text-ink">{scenario.outcome}</p>
            <p className="mt-1 max-w-[68ch] text-[12.5px] leading-relaxed text-ink-muted">
              {scenario.detail}
            </p>

            <div className="mt-3 flex flex-wrap gap-2">
              {scenario.files.map((name) => (
                <SampleLink key={name} name={name} available={files === null || available.has(name)} />
              ))}
            </div>
          </li>
        ))}
      </ol>

      <p className="mt-5 text-[12px] leading-relaxed text-ink-subtle">
        Upload order does not matter — the files are read together. Uploading the same
        export twice is safe: rows for one person are merged rather than duplicated.
      </p>
    </div>
  );
}

function SampleLink({ name, available }: { name: string; available: boolean }) {
  if (!available) {
    return (
      <span className="rounded-md border border-line bg-sunken px-2.5 py-1 text-[12px] text-ink-subtle line-through">
        {name}
      </span>
    );
  }
  return (
    <a
      href={api.sampleUrl(name)}
      download={name}
      className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-surface px-2.5 py-1 text-[12px] font-medium text-ink transition-colors hover:bg-sunken"
    >
      <IconDownload />
      <span className="raw">{name}</span>
    </a>
  );
}

function IconInfo() {
  return (
    <svg viewBox="0 0 24 24" className="size-3.5 shrink-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5" />
      <path d="M12 7.6v.2" strokeWidth="2.4" />
    </svg>
  );
}

function IconDownload() {
  return (
    <svg viewBox="0 0 24 24" className="size-3.5 shrink-0 text-accent" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19h14" />
    </svg>
  );
}
