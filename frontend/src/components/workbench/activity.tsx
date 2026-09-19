/**
 * What the agent has been doing.
 *
 * Every line is a committed decision with its reason — never a spinner standing
 * in for work, and never a percentage counting toward an invented total. When
 * the run is waiting on a person the feed says so and stops, because a feed that
 * keeps animating while nothing happens teaches people to ignore it.
 */
"use client";

import { useEffect, useRef } from "react";
import type { ActivityEvent } from "@/lib/api";
import { Dot, type Tone } from "@/components/ui/status";
import { cn } from "@/lib/utils";

/** How each kind of event reads at a glance. */
function toneFor(action: string): Tone {
  if (action.includes("failed") || action.includes("rejected")) return "bad";
  if (action.includes("escalated") || action.includes("retry") || action.includes("unavailable"))
    return "warn";
  if (action.includes("succeeded") || action.includes("applied") || action.includes("repaired"))
    return "good";
  if (action.includes("attempted") || action.includes("summary")) return "neutral";
  return "working";
}

function label(event: ActivityEvent): string {
  const words = event.action.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function Activity({
  events,
  waiting,
  running,
}: {
  events: ActivityEvent[];
  waiting: boolean;
  running: boolean;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  const count = events.length;

  // Follow the feed as work happens, but not while the reviewer is reading a
  // paused run — yanking the scroll position then would be hostile.
  useEffect(() => {
    if (running) endRef.current?.scrollIntoView({ block: "end" });
  }, [count, running]);

  return (
    <div className="flex h-full flex-col">
      <ol className="flex-1 overflow-y-auto px-3 py-2">
        {events.length === 0 && (
          <li className="px-1 py-4 text-[12px] text-muted-foreground">
            Nothing yet.
          </li>
        )}
        {events.map((event) => (
          <li key={event.seq} className="group flex gap-2.5 py-1.5">
            <span className="mt-[7px]">
              <Dot tone={toneFor(event.action)} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[12px] leading-snug">
                <span className="font-medium">{label(event)}</span>
                {event.subject && (
                  <span className="text-muted-foreground"> · {event.subject}</span>
                )}
                {event.actor === "reviewer" && (
                  <span className="ml-1.5 text-[10px] text-primary">you</span>
                )}
              </p>
              <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">
                {event.reason}
              </p>
              {event.before !== null && event.after !== null && (
                <p className="mt-0.5 font-mono text-[10.5px] text-muted-foreground/80">
                  <span className="line-through opacity-60">{event.before}</span>
                  {" → "}
                  <span className="text-foreground">{event.after}</span>
                </p>
              )}
            </div>
          </li>
        ))}
        <div ref={endRef} />
      </ol>

      <div
        className={cn(
          "flex h-8 shrink-0 items-center gap-2 border-t border-border px-3",
          "text-[11px] text-muted-foreground",
        )}
      >
        {running ? (
          <>
            <Dot tone="working" pulse />
            Working
          </>
        ) : waiting ? (
          <>
            <Dot tone="warn" />
            Waiting for you
          </>
        ) : (
          <>
            <Dot tone="neutral" />
            Idle
          </>
        )}
      </div>
    </div>
  );
}
