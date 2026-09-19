import { Dot } from "@/components/ui/status";
import type { Stage } from "@/lib/sample";
import { cn } from "@/lib/utils";

/**
 * Where the migration has got to.
 *
 * Five named steps, each carrying what actually happened. This is the answer to
 * "what is it doing" — not a percentage counting toward an invented total.
 */
export function Stages({ stages }: { stages: Stage[] }) {
  return (
    <ol className="flex flex-col gap-0 sm:flex-row sm:items-start sm:gap-0">
      {stages.map((stage, index) => {
        const last = index === stages.length - 1;
        return (
          <li key={stage.id} className="flex flex-1 gap-3 sm:block">
            <div className="flex flex-col items-center sm:flex-row">
              <Mark stage={stage} />
              {/* The connector shows direction: down on a phone, across on desktop. */}
              {!last && (
                <span
                  className={cn(
                    "w-px flex-1 sm:h-px sm:w-full",
                    stage.state === "done" ? "bg-accent/40" : "bg-line",
                  )}
                />
              )}
            </div>

            <div className={cn("pb-6 sm:pt-3 sm:pb-0 sm:pr-4", last && "pb-0")}>
              <p
                className={cn(
                  "text-[14px] font-medium",
                  stage.state === "waiting" && "text-ink-subtle",
                  stage.state === "blocked" && "text-attention",
                )}
              >
                {stage.label}
              </p>
              {stage.detail && (
                <p className="mt-0.5 text-[13px] leading-snug text-ink-muted">{stage.detail}</p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function Mark({ stage }: { stage: Stage }) {
  if (stage.state === "done") {
    return (
      <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-accent text-white">
        <svg viewBox="0 0 16 16" className="size-3.5" aria-hidden>
          <path d="M3 8.5l3.5 3.5L13 4" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
        </svg>
        <span className="sr-only">Done</span>
      </span>
    );
  }

  if (stage.state === "active") {
    return (
      <span className="flex size-6 shrink-0 items-center justify-center rounded-full border-2 border-accent bg-surface">
        <Dot tone="working" busy />
        <span className="sr-only">Working</span>
      </span>
    );
  }

  if (stage.state === "blocked") {
    return (
      <span className="flex size-6 shrink-0 items-center justify-center rounded-full border-2 border-attention bg-attention-soft text-[13px] font-semibold text-attention">
        !<span className="sr-only">Waiting for you</span>
      </span>
    );
  }

  return (
    <span className="size-6 shrink-0 rounded-full border-2 border-line bg-surface">
      <span className="sr-only">Not started</span>
    </span>
  );
}
