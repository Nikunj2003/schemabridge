import type { Stage } from "@/lib/present";
import { cn } from "@/lib/utils";

/**
 * Where the migration has got to.
 *
 * Five named steps carrying what actually happened, because "what is it doing"
 * is answered by a stage and a fact, not by a percentage counting toward an
 * invented total.
 */
export function Stages({ stages }: { stages: Stage[] }) {
  return (
    <ol className="grid gap-0 sm:grid-flow-col sm:auto-cols-fr">
      {stages.map((stage, index) => {
        const last = index === stages.length - 1;
        return (
          <li key={stage.id} className="flex gap-3 sm:block sm:min-w-0">
            <div className="flex flex-col items-center sm:flex-row">
              <Mark stage={stage} />
              {!last && (
                <span
                  className={cn(
                    "w-px flex-1 sm:h-px sm:w-full",
                    stage.state === "done" ? "bg-accent/45" : "bg-line",
                  )}
                />
              )}
            </div>

            <div className={cn("min-w-0 pb-5 sm:pt-2.5 sm:pb-0 sm:pr-5", last && "pb-0")}>
              <p
                className={cn(
                  "text-[13.5px] font-medium",
                  stage.state === "waiting" && "text-ink-subtle",
                  stage.state === "blocked" && "text-attention",
                )}
              >
                {stage.label}
              </p>
              {stage.detail && (
                <p className="mt-0.5 text-[12.5px] leading-snug text-ink-muted">{stage.detail}</p>
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
      <span className="flex size-5.5 shrink-0 items-center justify-center rounded-full bg-accent text-white">
        <svg viewBox="0 0 16 16" className="size-3" aria-hidden>
          <path d="M3 8.5l3.5 3.5L13 4" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
        </svg>
        <span className="sr-only">Done.</span>
      </span>
    );
  }

  if (stage.state === "active") {
    return (
      <span className="flex size-5.5 shrink-0 items-center justify-center rounded-full border-2 border-accent bg-surface">
        <span className="relative flex size-2">
          <span className="absolute size-full rounded-full bg-accent opacity-60 motion-safe:animate-ping" />
          <span className="relative size-2 rounded-full bg-accent" />
        </span>
        <span className="sr-only">Working now.</span>
      </span>
    );
  }

  if (stage.state === "blocked") {
    return (
      <span className="flex size-5.5 shrink-0 items-center justify-center rounded-full border-2 border-attention bg-attention-soft text-[12px] font-bold text-attention">
        !<span className="sr-only">Waiting for you.</span>
      </span>
    );
  }

  return (
    <span className="size-5.5 shrink-0 rounded-full border-2 border-line bg-surface">
      <span className="sr-only">Not started.</span>
    </span>
  );
}
