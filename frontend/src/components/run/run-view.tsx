"use client";

import Link from "next/link";
import { useState } from "react";
import { Activity } from "@/components/run/activity";
import { Decision } from "@/components/run/decision";
import { Results } from "@/components/run/results";
import { Stages } from "@/components/run/stages";
import { ButtonLink } from "@/components/ui/button";
import { Badge } from "@/components/ui/status";
import { headline, presentQuestion, stagesFor } from "@/lib/present";
import { useRun } from "@/lib/use-run";

/**
 * One migration, whichever state it is in.
 *
 * The same page changes its own centre of gravity: live narration while work is
 * happening, a focused decision when the agent is stuck, results when it is
 * done. Navigation and run context stay put, so nobody loses their place when
 * the work changes.
 */
export function RunView({ runId }: { runId: string }) {
  const { run, error, saving, decide, activity, elapsed } = useRun(runId);
  const [showActivity, setShowActivity] = useState(false);

  if (error && !run) {
    return (
      <Frame>
        <div className="panel px-5 py-6">
          <h1 className="font-display text-[19px]">This migration could not be opened</h1>
          <p className="mt-1.5 text-[14px] text-ink-muted">{error}</p>
          <ButtonLink href="/app" className="mt-4">
            Back to migrations
          </ButtonLink>
        </div>
      </Frame>
    );
  }

  if (!run) {
    return (
      <Frame>
        <div className="panel px-5 py-6">
          <p className="text-[14px] text-ink-muted">Opening this migration…</p>
        </div>
      </Frame>
    );
  }

  const stages = stagesFor(run);
  const open = run.issues.filter((issue) => issue.status === "open" && issue.blocking);
  const answered = run.issues.filter((issue) => issue.status === "resolved");
  const finished = activity === "finished";

  return (
    <Frame>
      <header>
        <div className="flex flex-wrap items-center gap-2">
          <Link href="/app" className="text-[13px] text-ink-muted hover:text-ink">
            Migrations
          </Link>
          <span className="text-ink-subtle" aria-hidden>
            /
          </span>
          <span className="text-[13px] text-ink-muted">This migration</span>
        </div>

        <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="font-display text-[24px]">{headline(run)}</h1>
            <p className="mt-1 text-[13.5px] text-ink-muted">
              {run.files.join(" · ")} → Employee record → Demo HR system
            </p>
          </div>

          <div className="flex items-center gap-2">
            {activity === "working" && (
              <Badge tone="working">
                <span className="relative flex size-2" aria-hidden>
                  <span className="absolute size-full rounded-full bg-accent opacity-60 motion-safe:animate-ping" />
                  <span className="relative size-2 rounded-full bg-accent" />
                </span>
                Working · {formatElapsed(elapsed)}
              </Badge>
            )}
            {activity === "waiting" && <Badge tone="attention">Waiting for you</Badge>}
            {finished && <Badge tone={run.counters.failed > 0 ? "problem" : "ok"}>Finished</Badge>}
          </div>
        </div>
      </header>

      <section className="panel mt-5 px-5 py-4 sm:px-6">
        <Stages stages={stages} />
      </section>

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
          <Working run={run} elapsed={elapsed} />
        )}
      </div>

      <section className="panel mt-5 overflow-hidden">
        <button
          onClick={() => setShowActivity(!showActivity)}
          aria-expanded={showActivity}
          className="flex w-full items-center gap-2 px-5 py-3 text-left text-[13.5px] font-medium hover:bg-sunken"
        >
          Everything the agent did
          <span className="text-[12.5px] font-normal text-ink-muted tnum">
            {run.events.length} steps
          </span>
          <span className="ml-auto text-ink-subtle" aria-hidden>
            {showActivity ? "Hide" : "Show"}
          </span>
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
                {issue.resolution && (
                  <p className="mt-0.5 text-[12.5px] text-ink-muted">
                    You chose: {issue.resolution.value ?? issue.resolution.option_id ?? issue.resolution.action}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </Frame>
  );
}

/** The live view: what is happening now, with a real elapsed time. */
function Working({ run, elapsed }: { run: import("@/lib/api").Run; elapsed: number }) {
  const recent = [...run.events].reverse().slice(0, 4);
  return (
    <section className="panel px-5 py-5 sm:px-6">
      <div className="flex items-center gap-2.5">
        <span className="relative flex size-2.5" aria-hidden>
          <span className="absolute size-full rounded-full bg-accent opacity-60 motion-safe:animate-ping" />
          <span className="relative size-2.5 rounded-full bg-accent" />
        </span>
        <h2 className="text-[15px] font-semibold">{run.phase_label}</h2>
        <span className="ml-auto text-[12.5px] text-ink-muted tnum">{formatElapsed(elapsed)}</span>
      </div>

      <p className="mt-2 text-[13.5px] text-ink-muted">
        {/* No percentage: the work is model-assisted and its duration is unknown,
            so a bar filling to a made-up total would be a lie. */}
        This does not need you unless the agent finds something it cannot decide
        safely. You can leave and come back.
      </p>

      {recent.length > 0 && (
        <ul className="mt-4 space-y-1.5 border-t border-line pt-4">
          {recent.map((event) => (
            <li key={event.seq} className="text-[13px]">
              <span className="text-ink">{event.action}</span>
              {event.reason && <span className="text-ink-muted"> — {event.reason}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Frame({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto max-w-[62rem] px-4 py-6 sm:px-8 sm:py-8">{children}</div>;
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
}
