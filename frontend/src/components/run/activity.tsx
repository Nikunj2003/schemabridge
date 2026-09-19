import { ExecutionBasis } from "@/components/ui/execution-basis";
import type { ActivityEvent } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Recorded migration activity, newest first.
 *
 * Every line is an event the engine actually recorded, with its own reason and
 * the subsystem that produced it. Agent actor alone is not a model-use signal, so
 * each row uses the backend's explicit basis rather than guessing from its
 * wording — and the rows the model took part in carry an edge marker, so the call
 * site is findable while scrolling a long trail.
 */
export function Activity({ events }: { events: ActivityEvent[] }) {
  if (events.length === 0) {
    return (
      <p className="px-4 py-6 text-[13px] text-ink-subtle">
        Steps appear here as they happen.
      </p>
    );
  }

  return (
    <>
      <p className="border-b border-line bg-sunken px-4 py-2 text-[12px] text-ink-muted">
        Each step names what did the work: the <span className="font-medium text-accent-ink">LLM</span>,
        the rule engine, or you.
      </p>
      <ol className="divide-y divide-line">
        {[...events].reverse().map((event) => (
          <li
            key={event.seq}
            className={cn(
              "px-4 py-2.5",
              event.execution_basis === "model_assisted" &&
                "border-l-2 border-l-accent bg-accent-soft/35 pl-3.5",
            )}
          >
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
              <span className="raw shrink-0 text-[11.5px] text-ink-subtle tnum">{clock(event.at)}</span>
              <p className="min-w-0 text-[13px]">
                {event.action}
                {event.subject && <span className="text-ink-muted"> · {event.subject}</span>}
              </p>
              <ExecutionBasis basis={event.execution_basis} compact />
            </div>
            {event.reason && (
              <p className="mt-1 pl-[3.6rem] text-[12.5px] leading-snug text-ink-muted">
                {event.reason}
              </p>
            )}
            {(event.before || event.after) && (
              <p className="raw mt-0.5 pl-[3.6rem] text-[12px] text-ink-subtle">
                {event.before ?? "(blank)"} → {event.after ?? "(blank)"}
              </p>
            )}
          </li>
        ))}
      </ol>
    </>
  );
}

/** Timestamps show wall-clock time; the date is already the run's own. */
function clock(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "";
  return at.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}
