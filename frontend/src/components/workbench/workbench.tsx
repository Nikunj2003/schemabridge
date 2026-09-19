/**
 * The consultant's workspace.
 *
 * A workbench rather than a dashboard: dashboards are for monitoring, and this
 * is for doing. Most of the screen is a record of decisions the agent already
 * made; the part that needs attention is one queue, and how much is left should
 * be obvious without reading.
 */
"use client";

import { useMemo, useState } from "react";
import type { Decision, Run, TargetField } from "@/lib/api";
import { Activity } from "./activity";
import { IssueDetail } from "./issue-detail";
import { Queue } from "./queue";
import { Audit, Delivery, Mappings, Records } from "./tables";
import { useRun } from "./use-run";
import { Button } from "@/components/ui/button";
import { Dot, Pill, type Tone } from "@/components/ui/status";
import { PanelHeader } from "@/components/ui/panel";
import { cn } from "@/lib/utils";

type Tab = "review" | "mappings" | "records" | "delivery" | "audit";

const TABS: { id: Tab; label: string }[] = [
  { id: "review", label: "Review" },
  { id: "mappings", label: "Mappings" },
  { id: "records", label: "Records" },
  { id: "delivery", label: "Delivery" },
  { id: "audit", label: "Audit" },
];

function phaseTone(run: Run): Tone {
  if (run.phase === "blocked" || run.phase === "complete_with_failures") return "bad";
  if (run.paused) return "warn";
  if (run.phase === "complete") return "good";
  return "working";
}

export function Workbench({
  runId,
  initial,
  fields,
}: {
  runId: string;
  initial: Run | null;
  fields: TargetField[];
}) {
  const { run, error, busy, resolve, retry } = useRun(runId, initial);
  const [tab, setTab] = useState<Tab>("review");
  // Null means "follow the queue". An explicit id means the reviewer chose one.
  const [picked, setPicked] = useState<string | null>(null);

  // Open escalations first: that is what the reviewer is here for.
  const queue = useMemo(() => {
    if (!run) return [];
    const open = run.issues.filter((issue) => issue.resolution === null);
    const done = run.issues.filter((issue) => issue.resolution !== null);
    return [...open.filter((i) => i.blocking), ...open.filter((i) => !i.blocking), ...done];
  }, [run]);

  // Derived rather than stored: as the queue burns down the selection moves to
  // the next open item on its own, so the reviewer never has to hunt for it, and
  // a resolved item cannot stay selected.
  const selected = useMemo(() => {
    if (queue.length === 0) return null;
    const chosen = queue.find((issue) => issue.id === picked && issue.resolution === null);
    if (chosen) return chosen.id;
    return queue.find((issue) => issue.resolution === null)?.id ?? queue[0].id;
  }, [queue, picked]);

  if (!run) {
    return (
      <main className="flex h-dvh items-center justify-center">
        <p className="text-[13px] text-muted-foreground">
          {error ?? "Loading this migration…"}
        </p>
      </main>
    );
  }

  const issue = queue.find((candidate) => candidate.id === selected) ?? null;
  const waiting = run.paused;
  const running = run.runnable && !run.paused;
  const { counters } = run;

  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-card px-4">
        <span className="font-display text-[15px] font-semibold tracking-tight">SchemaBridge</span>
        <span className="hidden truncate text-[12px] text-muted-foreground sm:inline">
          {run.files.join(" · ")}
        </span>
        <div className="flex-1" />
        <Pill tone={phaseTone(run)}>
          <Dot tone={phaseTone(run)} pulse={running} />
          {run.phase_label}
        </Pill>
      </header>

      {error && (
        <div className="flex shrink-0 items-center gap-3 border-b border-destructive/25 bg-destructive/[0.06] px-4 py-2">
          <p className="flex-1 text-[12.5px] text-destructive">{error}</p>
          <Button size="sm" variant="outline" onClick={retry} disabled={busy}>
            Try again
          </Button>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        {/* Left rail: what needs a person, and what the agent has been doing. */}
        <aside className="flex w-[280px] shrink-0 flex-col border-r border-border md:w-[320px]">
          <div className="flex min-h-0 flex-1 flex-col">
            <PanelHeader title="Needs you" count={counters.awaiting_review} />
            <div className="min-h-0 flex-1 overflow-y-auto">
              <Queue issues={queue} selectedId={selected} onSelect={setPicked} />
            </div>
          </div>
          <div className="flex min-h-0 flex-1 flex-col border-t border-border">
            <PanelHeader title="Activity" />
            <div className="min-h-0 flex-1">
              <Activity events={run.events} waiting={waiting} running={running} />
            </div>
          </div>
        </aside>

        <main className="flex min-w-0 flex-1 flex-col">
          <nav className="flex h-10 shrink-0 items-center gap-0.5 border-b border-border px-3">
            {TABS.map((entry) => (
              <button
                key={entry.id}
                onClick={() => setTab(entry.id)}
                aria-current={tab === entry.id ? "page" : undefined}
                className={cn(
                  "rounded-md px-2.5 py-1 text-[12.5px] font-medium transition-colors",
                  tab === entry.id
                    ? "bg-secondary text-foreground"
                    : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground",
                )}
              >
                {entry.label}
                {entry.id === "review" && counters.awaiting_review > 0 && (
                  <span className="ml-1.5 text-primary">{counters.awaiting_review}</span>
                )}
              </button>
            ))}
          </nav>

          <div className="min-h-0 flex-1 overflow-hidden">
            {tab === "review" &&
              (issue ? (
                <IssueDetail
                  issue={issue}
                  busy={busy}
                  onResolve={(decision: Decision) => resolve({ [issue.id]: decision })}
                />
              ) : (
                <Done run={run} />
              ))}
            {tab === "mappings" && <Mappings mappings={run.mappings} />}
            {tab === "records" && <Records records={run.records} fields={fields} />}
            {tab === "delivery" && <Delivery records={run.records} />}
            {tab === "audit" && <Audit events={run.events} />}
          </div>
        </main>
      </div>

      {/* The numbers a consultant is asked about afterwards. */}
      <footer className="flex h-9 shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-t border-border bg-card px-4 text-[11.5px] text-muted-foreground">
        <Stat label="mapped" value={counters.auto_mapped} />
        <Stat label="records" value={counters.records} />
        {counters.merged > 0 && <Stat label="merged" value={counters.merged} />}
        {counters.repairs > 0 && <Stat label="cleaned" value={counters.repairs} />}
        <Stat label="delivered" value={counters.delivered} tone="good" />
        {counters.retrying > 0 && <Stat label="retrying" value={counters.retrying} tone="warn" />}
        {counters.failed > 0 && <Stat label="failed" value={counters.failed} tone="bad" />}
        {counters.excluded > 0 && <Stat label="left out" value={counters.excluded} />}
      </footer>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: Tone }) {
  return (
    <span className="whitespace-nowrap">
      <span
        className={cn(
          "font-medium",
          tone === "good" && "text-success",
          tone === "warn" && "text-warning",
          tone === "bad" && "text-destructive",
          !tone && "text-foreground",
        )}
      >
        {value}
      </span>{" "}
      {label}
    </span>
  );
}

/**
 * The review pane with nothing in it.
 *
 * An empty queue is the success state, so it says what happened rather than
 * looking like something failed to load.
 */
function Done({ run }: { run: Run }) {
  const { counters } = run;
  const finished = run.phase === "complete" || run.phase === "complete_with_failures";

  return (
    <div className="flex h-full items-center justify-center px-6">
      <div className="max-w-md text-center">
        <h2 className="text-[17px] font-semibold">
          {finished ? "Migration finished" : "Nothing needs you"}
        </h2>
        <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">
          {finished ? (
            <>
              {counters.delivered} of {counters.records} records reached the destination.
              {counters.failed > 0 && ` ${counters.failed} were not accepted — see Delivery.`}
              {counters.excluded > 0 && ` ${counters.excluded} were left out on purpose.`}
            </>
          ) : (
            <>
              The agent is working through {counters.records || counters.source_rows} records and
              handling everything it is confident about. It will stop here if it needs a decision.
            </>
          )}
        </p>
      </div>
    </div>
  );
}
