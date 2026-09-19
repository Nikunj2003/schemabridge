"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type Decision, type Run } from "./api";

/**
 * Driving one migration from the browser.
 *
 * Two independent loops, deliberately:
 *
 *  - **Observation** polls `GET /runs/:id`, which never mutates. It keeps
 *    running while an advance request is still in flight, which is the only way
 *    stages can appear *during* long work rather than all at once at the end.
 *  - **Execution** calls `POST advance` one bounded step at a time, and only
 *    when the run has work left and no request is already out.
 *
 * Collapsing these into one response-driven timer is what made the previous
 * build look frozen: nothing could be observed while the thing being observed
 * was holding the only request.
 */
export type Activity = "idle" | "working" | "waiting" | "finished" | "error";

export function useRun(runId: string) {
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [startedAt] = useState(() => Date.now());
  const [elapsed, setElapsed] = useState(0);

  // Refs, not state: these gate effects and must not cause re-renders.
  const advancing = useRef(false);
  const alive = useRef(true);
  const lastSeq = useRef(0);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const absorb = useCallback((next: Run) => {
    if (!alive.current) return;
    // Events arrive as a delta; anything else is a full snapshot.
    lastSeq.current = Math.max(lastSeq.current, next.latest_seq);
    setRun((previous) => {
      if (!previous) return next;
      const seen = new Set(previous.events.map((event) => event.seq));
      const merged = [...previous.events, ...next.events.filter((e) => !seen.has(e.seq))];
      return { ...next, events: merged };
    });
    setError(null);
  }, []);

  /** Observation. Independent of whether work is in flight. */
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;

    const look = async () => {
      try {
        absorb(await api.readRun(runId, lastSeq.current));
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 404) {
          setError("This migration no longer exists.");
          return;
        }
        // A single failed poll is not worth alarming anyone about; the next one
        // will either succeed or the advance call will report the real problem.
      }
      if (alive.current) timer = setTimeout(look, 1200);
    };

    void look();
    return () => clearTimeout(timer);
  }, [runId, absorb]);

  /** Execution. One bounded step at a time, never overlapping. */
  useEffect(() => {
    if (!run || advancing.current) return;
    if (!run.runnable || run.paused) return;

    advancing.current = true;
    void (async () => {
      try {
        absorb(await api.advance(runId));
      } catch (caught) {
        if (alive.current) {
          setError(caught instanceof Error ? caught.message : "The migration could not continue.");
        }
      } finally {
        advancing.current = false;
      }
    })();
  }, [run, runId, absorb]);

  /** Elapsed time, shown instead of a fabricated percentage. */
  useEffect(() => {
    const finished = run?.phase === "complete" || run?.phase === "complete_with_failures";
    if (finished) return;
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [run?.phase, startedAt]);

  const decide = useCallback(
    async (issueId: string, decision: Decision) => {
      setSaving(true);
      try {
        absorb(await api.resolve(runId, { [issueId]: decision }));
        return true;
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "That decision could not be saved.");
        return false;
      } finally {
        setSaving(false);
      }
    },
    [runId, absorb],
  );

  const activity: Activity = !run
    ? "idle"
    : error
      ? "error"
      : run.phase === "complete" || run.phase === "complete_with_failures"
        ? "finished"
        : run.counters.awaiting_review > 0
          ? "waiting"
          : "working";

  return { run, error, saving, decide, activity, elapsed };
}
