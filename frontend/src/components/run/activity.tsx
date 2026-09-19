import type { ActivityEvent } from "@/lib/api";

/**
 * What the agent did, newest last.
 *
 * Every line is an event the engine actually recorded, with its own reason. This
 * is the audit trail, so it is never summarised into something friendlier than
 * what happened.
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
    <ol className="divide-y divide-line">
      {[...events].reverse().map((event) => (
        <li key={event.seq} className="px-4 py-2.5">
          <div className="flex items-baseline gap-2">
            <span className="raw shrink-0 text-[11.5px] text-ink-subtle tnum">{clock(event.at)}</span>
            <p className="min-w-0 text-[13px]">
              {event.action}
              {event.subject && <span className="text-ink-muted"> · {event.subject}</span>}
            </p>
          </div>
          {event.reason && (
            <p className="mt-0.5 pl-[3.6rem] text-[12.5px] leading-snug text-ink-muted">
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
  );
}

/** Timestamps show wall-clock time; the date is already the run's own. */
function clock(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "";
  return at.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}
