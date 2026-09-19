"use client";

import { useState } from "react";
import Link from "next/link";
import { Badge, Dot } from "@/components/ui/status";
import { Stages } from "./stages";
import { Activity } from "./activity";
import { Decision } from "./decision";
import { Results } from "./results";
import {
  ACTIVITY,
  DONE_STAGES,
  IN_FLIGHT_STAGES,
  QUESTIONS,
  RUNNING_STAGES,
  type Question,
} from "@/lib/sample";
import { cn } from "@/lib/utils";

/** Which moment of the journey this preview is showing. */
export type Moment = "working" | "review" | "done";

const MOMENTS: { id: Moment; label: string }[] = [
  { id: "working", label: "While it works" },
  { id: "review", label: "Needs a decision" },
  { id: "done", label: "Finished" },
];

export function RunView({ name, initial }: { name: string; initial: Moment }) {
  const [moment, setMoment] = useState<Moment>(initial);
  const [answered, setAnswered] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const open = QUESTIONS.filter((question) => !answered.includes(question.id));
  const current: Question | null = open[0] ?? null;

  const stages =
    moment === "working" ? IN_FLIGHT_STAGES : moment === "done" ? DONE_STAGES : RUNNING_STAGES;
  const visibleActivity = moment === "working" ? ACTIVITY.slice(0, 3) : ACTIVITY;

  function save() {
    if (!current) return;
    setSaving(true);
    // Stands in for the request. The real screen will show the server's verdict,
    // including refusing a correction that is still invalid.
    window.setTimeout(() => {
      setAnswered((done) => [...done, current.id]);
      setSaving(false);
    }, 450);
  }

  return (
    <div className="px-5 py-6 sm:px-8 sm:py-8">
      {/* Preview-only control, so the whole journey can be judged in one pass. */}
      <div className="mb-6 flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-line-strong bg-sunken px-3 py-2.5">
        <span className="text-[12.5px] font-medium text-ink-muted">
          Design preview — sample data, nothing is connected yet
        </span>
        <div className="ml-auto flex gap-1">
          {MOMENTS.map((option) => (
            <button
              key={option.id}
              onClick={() => {
                setMoment(option.id);
                setAnswered([]);
              }}
              aria-pressed={moment === option.id}
              className={cn(
                "rounded px-2.5 py-1 text-[12.5px] font-medium transition-colors",
                moment === option.id
                  ? "bg-surface text-ink shadow-[0_1px_2px_rgb(23_38_37/0.08)]"
                  : "text-ink-muted hover:text-ink",
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Link href="/app" className="text-[13px] text-ink-muted hover:text-ink">
            ← All migrations
          </Link>
          <h1 className="mt-1.5 font-display text-[25px] font-semibold">{name}</h1>
          <p className="mt-1.5 text-[13.5px] text-ink-muted">
            employees-legacy.csv, employees-hr-export.csv → Employee record → Demo HR system
          </p>
        </div>

        {moment === "working" ? (
          <Badge tone="working">
            <Dot tone="working" busy />
            Working
          </Badge>
        ) : moment === "review" ? (
          <Badge tone="attention">{open.length} waiting on you</Badge>
        ) : (
          <Badge tone="ok">Finished</Badge>
        )}
      </header>

      <div className="mt-7 rounded-lg border border-line bg-surface p-5">
        <Stages stages={stages} />
      </div>

      <div className="mt-7 grid gap-7 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-6">
          {moment === "working" && <Working />}

          {moment === "review" &&
            (current ? (
              <>
                <div>
                  <h2 className="font-display text-[18px] font-semibold">
                    {open.length === 1
                      ? "One decision before this can finish"
                      : `${open.length} decisions before this can finish`}
                  </h2>
                  <p className="mt-1 text-[13.5px] text-ink-muted">
                    Each one changes what gets migrated. Nothing is sent until they
                    are settled.
                  </p>
                </div>
                <Decision question={current} onSave={() => save()} saving={saving} />
                {open.length > 1 && (
                  <ol className="space-y-1.5">
                    <p className="text-[13px] font-medium text-ink-muted">Then:</p>
                    {open.slice(1).map((question) => (
                      <li key={question.id} className="flex gap-2 text-[13.5px] text-ink-muted">
                        <Dot tone="attention" />
                        {question.title}
                      </li>
                    ))}
                  </ol>
                )}
              </>
            ) : (
              <AllAnswered onShow={() => setMoment("done")} />
            ))}

          {moment === "done" && <Results />}
        </div>

        <aside className="space-y-6 lg:sticky lg:top-20 lg:self-start">
          <Activity lines={visibleActivity} live={moment === "working"} />
          {answered.length > 0 && moment === "review" && (
            <section>
              <h2 className="text-[15px] font-semibold">Your decisions</h2>
              <ul className="mt-2.5 space-y-2">
                {answered.map((id) => {
                  const question = QUESTIONS.find((q) => q.id === id);
                  return (
                    <li key={id} className="text-[13.5px] text-ink-muted">
                      <Dot tone="ok" /> {question?.title}
                    </li>
                  );
                })}
              </ul>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}

/** Mid-run: say what is happening now, without inventing a percentage. */
function Working() {
  return (
    <section className="card p-5 sm:p-6">
      <div className="flex items-center gap-2.5">
        <Dot tone="working" busy />
        <h2 className="font-display text-[18px] font-semibold">Matching your columns</h2>
      </div>
      <p className="mt-2 max-w-prose text-[14.5px] leading-relaxed text-ink-muted">
        Twelve of thirteen columns were recognised from their names. The last one
        is <span className="raw">Cost Centre Ref</span>, which no employee field
        matches — checking whether it belongs anywhere before moving on.
      </p>
      <p className="mt-3 text-[13px] text-ink-muted">
        Running 9 seconds. You can leave this page; the migration keeps its place
        and you can come back to it.
      </p>
    </section>
  );
}

function AllAnswered({ onShow }: { onShow: () => void }) {
  return (
    <section className="card p-6 text-center">
      <h2 className="font-display text-[18px] font-semibold">That was the last one</h2>
      <p className="mx-auto mt-2 max-w-sm text-[14px] leading-relaxed text-ink-muted">
        Sending the finished records to the Demo HR system now.
      </p>
      <button
        onClick={onShow}
        className="mt-4 text-[13.5px] font-medium text-accent underline-offset-2 hover:underline"
      >
        See the results
      </button>
    </section>
  );
}
