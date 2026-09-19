"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type Decision, type Run } from "./api";

/**
 * Driving one migration from the browser.
 *
 * Observation only reads committed checkpoint state, while execution advances at
 * most one bounded graph call at a time. Keeping them separate lets the screen
 * update between real workflow nodes without inventing a percentage or duration.
 */
export type Activity = "idle" | "working" | "waiting" | "finished" | "error";

export function useRun(runId: string) {
  const [run, setRun] = useState<Run | null>(null);
  // A run failure belongs to the page; a failed review save belongs to the
  // review dialog, where the person can correct and retry it.
  const [error, setError] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Refs gate concurrent effects without causing a render. `lastSeq` is both the
  // API event cursor and a safeguard against an older overlapping response
  // replacing a newer full run snapshot.
  const advancing = useRef(false);
  const alive = useRef(true);
  const lastSeq = useRef(0);

  useEffect(() => {
    return () => {
      alive.current = false;
    };
  }, []);

  const absorb = useCallback((next: Run) => {
    if (!alive.current) return;
    setRun((previous) => {
      if (previous && next.latest_seq < previous.latest_seq) return previous;
      const seen = new Set(previous?.events.map((event) => event.seq) ?? []);
      const events = [
        ...(previous?.events ?? []),
        ...next.events.filter((event) => !seen.has(event.seq)),
      ];
      return { ...next, events };
    });
    lastSeq.current = Math.max(lastSeq.current, next.latest_seq);
    setRefreshError(null);
  }, []);

  /** Observation remains independent from an in-flight bounded execution call. */
  useEffect(() => {
    alive.current = true;
    lastSeq.current = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const look = async () => {
      try {
        absorb(await api.readRun(runId, lastSeq.current));
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 404) {
          setError("This migration no longer exists.");
          return;
        }
        if (alive.current) {
          setRefreshError("Connection interrupted. Trying again…");
        }
      }
      if (alive.current) timer = setTimeout(look, 1200);
    };

    void look();
    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [runId, absorb]);

  /** Execution is bounded and never overlaps another advance from this page. */
  useEffect(() => {
    if (!run || advancing.current || !run.runnable || run.paused) return;

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

  const decide = useCallback(
    async (issueId: string, decision: Decision) => {
      setSaving(true);
      setDecisionError(null);
      try {
        absorb(await api.resolve(runId, { [issueId]: decision }));
        return true;
      } catch (caught) {
        setDecisionError(caught instanceof Error ? caught.message : "That decision could not be saved.");
        return false;
      } finally {
        setSaving(false);
      }
    },
    [runId, absorb],
  );

  const activity: Activity = !run
    ? "idle"
    : run.phase === "complete" || run.phase === "complete_with_failures"
      ? "finished"
      : run.phase === "blocked" || error
        ? "error"
        : run.counters.awaiting_review > 0 || run.paused
          ? "waiting"
          : run.active
            ? "working"
            : "idle";

  return { run, error, decisionError, refreshError, saving, decide, activity };
}
