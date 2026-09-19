"use client";

import { useState } from "react";
import { Button, ButtonLink } from "@/components/ui/button";
import { Badge, type Tone } from "@/components/ui/status";
import { RESULT_RECORDS, RESULT_SUMMARY, type RecordRow } from "@/lib/sample";
import { cn } from "@/lib/utils";

const STATE: Record<RecordRow["state"], { tone: Tone; label: string }> = {
  sent: { tone: "ok", label: "Sent" },
  failed: { tone: "problem", label: "Refused" },
  skipped: { tone: "neutral", label: "Skipped" },
  retrying: { tone: "attention", label: "Retrying" },
  ready: { tone: "working", label: "Ready" },
};

type Filter = "all" | "sent" | "failed" | "skipped";

/**
 * What happened, once the migration is finished.
 *
 * The headline reconciles: source rows, duplicates combined, employees, and what
 * became of each one. Adding "12 rows" to "7 sent" would be mixing units, so the
 * arithmetic is spelled out instead.
 */
export function Results() {
  const [filter, setFilter] = useState<Filter>("all");

  const shown = RESULT_RECORDS.filter((record) => {
    if (filter === "all") return true;
    if (filter === "failed") return record.state === "failed";
    if (filter === "skipped") return record.state === "skipped";
    return record.state === "sent";
  });

  const failed = RESULT_RECORDS.filter((record) => record.state === "failed");

  return (
    <div className="space-y-6">
      <section className="card p-5 sm:p-6">
        <h2 className="font-display text-[20px] font-semibold">
          {RESULT_SUMMARY.sent} of {RESULT_SUMMARY.employees} employees reached the Demo HR system
        </h2>
        <p className="mt-2 text-[14.5px] leading-relaxed text-ink-muted">
          {RESULT_SUMMARY.sourceRows} rows across your files became{" "}
          {RESULT_SUMMARY.employees} employees after combining {RESULT_SUMMARY.merged}{" "}
          duplicate rows. {RESULT_SUMMARY.failed} was refused by the destination and{" "}
          {RESULT_SUMMARY.skipped} you chose to skip. Took{" "}
          {RESULT_SUMMARY.duration}.
        </p>

        <div className="mt-5 flex flex-wrap gap-2">
          <Count label="Sent" value={RESULT_SUMMARY.sent} tone="ok" onClick={() => setFilter("sent")} />
          <Count label="Refused" value={RESULT_SUMMARY.failed} tone="problem" onClick={() => setFilter("failed")} />
          <Count label="Skipped" value={RESULT_SUMMARY.skipped} tone="neutral" onClick={() => setFilter("skipped")} />
          <Count label="Values cleaned" value={RESULT_SUMMARY.cleaned} tone="neutral" />
        </div>
      </section>

      {failed.length > 0 && (
        <section className="rounded-lg border border-problem/30 bg-problem-soft p-5">
          <h3 className="text-[15.5px] font-semibold text-problem">
            {failed.length} record was not accepted
          </h3>
          {failed.map((record) => (
            <div key={record.employeeId} className="mt-2.5">
              <p className="text-[14px] font-medium">
                {record.name} · <span className="raw">{record.employeeId}</span>
              </p>
              {/* The destination's own reason, not a validation error from our side. */}
              <p className="mt-1 max-w-prose text-[13.5px] leading-relaxed text-ink-muted">
                {record.note}
              </p>
            </div>
          ))}
          <div className="mt-4 flex flex-wrap gap-2">
            <Button size="sm" variant="secondary">
              Try sending this again
            </Button>
            <Button size="sm" variant="quiet">
              Download the refused record
            </Button>
          </div>
          <p className="mt-2.5 text-[13px] text-ink-muted">
            Retrying only re-sends what failed. Records already accepted are never
            sent twice.
          </p>
        </section>
      )}

      <section>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-[15.5px] font-semibold">Every employee</h3>
          <div className="flex gap-1 rounded-md border border-line bg-surface p-0.5">
            {(["all", "sent", "failed", "skipped"] as Filter[]).map((option) => (
              <button
                key={option}
                onClick={() => setFilter(option)}
                aria-pressed={filter === option}
                className={cn(
                  "rounded px-2.5 py-1 text-[13px] font-medium capitalize transition-colors",
                  filter === option ? "bg-accent-soft text-accent-ink" : "text-ink-muted hover:text-ink",
                )}
              >
                {option === "failed" ? "refused" : option}
              </button>
            ))}
          </div>
        </div>

        {/* Only the table scrolls sideways on a phone, never the page. */}
        <div className="mt-3 overflow-x-auto rounded-lg border border-line">
          <table className="w-full border-collapse bg-surface text-left text-[13.5px]">
            <thead>
              <tr className="border-b border-line text-[12.5px] text-ink-muted">
                <Th>Employee</Th>
                <Th>Start date</Th>
                <Th>Result</Th>
                <Th>From</Th>
              </tr>
            </thead>
            <tbody>
              {shown.map((record) => (
                <tr key={record.employeeId} className="border-b border-line/70 align-top last:border-0">
                  <td className="px-3 py-2.5">
                    <p className="font-medium">{record.name}</p>
                    <p className="raw text-[12.5px] text-ink-muted">{record.employeeId}</p>
                  </td>
                  <td className="px-3 py-2.5 whitespace-nowrap">{record.startDate}</td>
                  <td className="px-3 py-2.5">
                    <Badge tone={STATE[record.state].tone}>{STATE[record.state].label}</Badge>
                    {record.note && (
                      <p className="mt-1 max-w-[34ch] text-[12.5px] leading-snug text-ink-muted">
                        {record.note}
                      </p>
                    )}
                  </td>
                  <td className="px-3 py-2.5 text-[12.5px] text-ink-muted">
                    {record.from.map((source) => (
                      <span key={source} className="block whitespace-nowrap">
                        {source}
                      </span>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="flex flex-wrap gap-2.5 border-t border-line pt-5">
        <Button variant="secondary">Download the migrated employees</Button>
        <Button variant="quiet">Download skipped and refused</Button>
        <Button variant="quiet">View every change</Button>
        <ButtonLink href="/app/new" variant="primary" className="ml-auto">
          Start another migration
        </ButtonLink>
      </div>
    </div>
  );
}

function Count({
  label,
  value,
  tone,
  onClick,
}: {
  label: string;
  value: number;
  tone: Tone;
  onClick?: () => void;
}) {
  const content = (
    <>
      <span className="text-[19px] font-semibold tabular-nums">{value}</span>
      <span className="text-[13px] text-ink-muted">{label}</span>
    </>
  );
  const base = cn(
    "flex items-baseline gap-2 rounded-md border px-3 py-2",
    tone === "ok" && "border-ok/25 bg-ok-soft",
    tone === "problem" && "border-problem/25 bg-problem-soft",
    tone === "neutral" && "border-line bg-sunken",
  );
  return onClick ? (
    <button onClick={onClick} className={cn(base, "transition-colors hover:border-line-strong")}>
      {content}
    </button>
  ) : (
    <div className={base}>{content}</div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th scope="col" className="px-3 py-2 font-medium whitespace-nowrap">{children}</th>;
}
