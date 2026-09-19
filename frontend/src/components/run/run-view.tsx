"use client";

import Link from "next/link";
import { useState } from "react";
import { Activity } from "@/components/run/activity";
import { Decision } from "@/components/run/decision";
import { Results } from "@/components/run/results";
import { Stages } from "@/components/run/stages";
import { ExecutionBasis } from "@/components/ui/execution-basis";
import { Skeleton } from "@/components/ui/skeleton";
import { ButtonLink } from "@/components/ui/button";
import { Badge } from "@/components/ui/status";
import { headline, presentQuestion, stagesFor } from "@/lib/present";
import { useRun } from "@/lib/use-run";

/**
 * One migration, whichever state it is in.
 *
 * The centre of gravity changes between live work, a focused review, and results,
 * while navigation and the recorded evidence stay in place.
 */
export function RunView({ runId }: { runId: string }) {
  const { run, error, refreshError, saving, decide, activity } = useRun(runId);
  const [showActivity, setShowActivity] = useState(false);

  if (error && !run) {
    return (
      <Frame>
        <div className="panel px-5 py-6">
          <h1 className="font-display text-[19px]">This migration could not be opened</h1>
          <p className="mt-1.5 text-[14px] text-ink-muted">{error}</p>
          <ButtonLink href="/app" className="mt-4">Back to migrations</ButtonLink>
        </div>
      </Frame>
    );
  }

  if (!run) return <RunSkeleton />;

  const stages = stagesFor(run);
  const open = run.issues.filter((issue) => issue.status === "open" && issue.blocking);
  const answered = run.issues.filter((issue) => issue.status === "resolved");
  const finished = activity === "finished";
  const latest = run.events.at(-1);

  return (
    <Frame>
      <header>
        <div className="flex flex-wrap items-center gap-2">
          <Link href="/app" className="text-[13px] text-ink-muted hover:text-ink">Migrations</Link>
          <span className="text-ink-subtle" aria-hidden>/</span>
          <span className="text-[13px] text-ink-muted">This migration</span>
        </div>

        <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="font-display text-[24px]">{headline(run)}</h1>
            <p className="mt-1 text-[13.5px] text-ink-muted">
              {run.files.join(" · ")} → {run.schema_name} → Demo destination
            </p>
          </div>

          <div className="flex items-center gap-2" aria-live="polite">
            {activity === "working" && (
              <Badge tone="working">
                <span className="relative flex size-2" aria-hidden>
                  <span className="absolute size-full rounded-full bg-accent opacity-60 motion-safe:animate-ping" />
                  <span className="relative size-2 rounded-full bg-accent" />
                </span>
                Working
              </Badge>
            )}
            {activity === "waiting" && <Badge tone="attention">Waiting for you</Badge>}
            {activity === "error" && run.phase === "blocked" && <Badge tone="problem">Blocked</Badge>}
            {finished && <Badge tone={run.counters.failed > 0 ? "problem" : "ok"}>Finished</Badge>}
          </div>
        </div>
      </header>

      <section className="panel mt-5 px-5 py-4 sm:px-6">
        <Stages stages={stages} />
      </section>

      {refreshError && (
        <p role="status" className="mt-4 rounded-md border border-attention/30 bg-attention-soft px-4 py-3 text-[13px] text-attention">
          {refreshError}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-4 rounded-md border border-problem/30 bg-problem-soft px-4 py-3 text-[13.5px] text-problem">
          {error}
        </p>
      )}

      <div className="mt-5">
        {finished ? (
          <Results run={run} />
        ) : open.length > 0 ? (
          <Decision
            question={presentQuestion(open[0], run.records, run.schema_fields)}
            onSave={(decision) => void decide(open[0].id, decision)}
            saving={saving}
            index={answered.length}
            total={answered.length + open.length}
          />
        ) : (
          <Working run={run} latest={latest} />
        )}
      </div>

      <section className="panel mt-5 overflow-hidden">
        <button
          onClick={() => setShowActivity(!showActivity)}
          aria-expanded={showActivity}
          className="flex w-full items-center gap-2 px-5 py-3 text-left text-[13.5px] font-medium hover:bg-sunken"
        >
          Everything the migration did
          <span className="text-[12.5px] font-normal text-ink-muted tnum">{run.events.length} steps</span>
          <span className="ml-auto text-ink-subtle" aria-hidden>{showActivity ? "Hide" : "Show"}</span>
        </button>
        {showActivity && (
          <div className="max-h-[22rem] scroll-area border-t border-line">
            <Activity events={run.events} />
          </div>
        )}
      </section>

      {answered.length > 0 && (
        <section className="mt-5">
          <h2 className="eyebrow">Already decided</h2>
          <ul className="mt-2 space-y-1.5">
            {answered.map((issue) => (
              <li key={issue.id} className="rounded-md border border-line bg-surface px-4 py-2.5">
                <p className="text-[13.5px]">{issue.reason}</p>
                {issue.resolution && <p className="mt-0.5 text-[12.5px] text-ink-muted">You chose: {issue.resolution.value ?? issue.resolution.option_id ?? issue.resolution.action}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </Frame>
  );
}

/** The live view only describes work that the server has committed. */
function Working({ run, latest }: { run: import("@/lib/api").Run; latest: import("@/lib/api").ActivityEvent | undefined }) {
  return (
    <section className="panel px-5 py-5 sm:px-6" aria-live="polite">
      <div className="flex items-center gap-2.5">
        {run.active ? (
          <span className="relative flex size-2.5" aria-hidden>
            <span className="absolute size-full rounded-full bg-accent opacity-60 motion-safe:animate-ping" />
            <span className="relative size-2.5 rounded-full bg-accent" />
          </span>
        ) : <span className="size-2.5 rounded-full bg-ink-subtle" aria-hidden />}
        <h2 className="text-[15px] font-semibold">{run.phase_label}</h2>
        {run.active && <span className="ml-auto text-[12.5px] text-ink-muted">Live updates</span>}
      </div>

      <p className="mt-2 text-[13.5px] text-ink-muted">
        {run.active
          ? "This does not need you unless the migration finds something it cannot decide safely."
          : "The migration is waiting for its next committed step."}
      </p>

      {latest ? (
        <div key={latest.seq} className="mt-4 border-t border-line pt-4 motion-safe:animate-[event-arrival_320ms_ease-out]">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[13px] font-medium">Latest recorded step</p>
            <ExecutionBasis basis={latest.execution_basis} compact />
          </div>
          <p className="mt-1 text-[13px] text-ink-muted">
            <span className="text-ink">{latest.action}</span>
            {latest.reason && <> — {latest.reason}</>}
          </p>
        </div>
      ) : (
        <p className="mt-4 border-t border-line pt-4 text-[13px] text-ink-muted">No completed step has been recorded yet.</p>
      )}
    </section>
  );
}

function RunSkeleton() {
  return (
    <Frame>
      <div aria-busy="true">
        <span className="sr-only">Opening migration…</span>
        <Skeleton className="h-3 w-28" />
        <Skeleton className="mt-3 h-7 w-[min(34rem,88%)]" />
        <Skeleton className="mt-2 h-4 w-[min(28rem,70%)]" />
        <div className="panel mt-5 grid gap-5 px-5 py-5 sm:grid-cols-5 sm:px-6">
          {[0, 1, 2, 3, 4].map((index) => <Skeleton key={index} className="h-10 w-full" />)}
        </div>
        <div className="panel mt-5 space-y-4 px-5 py-5 sm:px-6">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-[82%]" />
        </div>
      </div>
    </Frame>
  );
}

function Frame({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto max-w-[62rem] px-4 py-6 sm:px-8 sm:py-8">{children}</div>;
}
