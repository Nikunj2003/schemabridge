/**
 * Driving and watching one migration.
 *
 * The browser advances the run and polls its state. That is a real constraint,
 * not a hidden one: the backend runs as serverless functions with no background
 * worker, so progress needs something to keep asking. State is durable, so
 * closing the tab pauses scheduling rather than losing work.
 *
 * Polling only runs while there is something to watch. A loop that keeps firing
 * against a finished run wastes the shared free-tier allowance for no benefit.
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api, type Decision, type Run } from "@/lib/api";

const POLL_MS = 1200;

export interface RunController {
  run: Run | null;
  error: string | null;
  busy: boolean;
  resolve: (decisions: Record<string, Decision>) => Promise<void>;
  retry: () => Promise<void>;
}

export function useRun(runId: string, initial: Run | null = null): RunController {
  const [run, setRun] = useState<Run | null>(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Guards against two advances overlapping, which would waste a step.
  const advancing = useRef(false);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const step = useCallback(async () => {
    if (advancing.current) return;
    advancing.current = true;
    try {
      const next = await api.advance(runId);
      if (alive.current) {
        setRun(next);
        setError(null);
      }
    } catch (cause) {
      if (alive.current) {
        setError(cause instanceof ApiError ? cause.message : "The migration could not continue.");
      }
    } finally {
      advancing.current = false;
    }
  }, [runId]);

  // Keep the run moving while it has work, and keep the view fresh while it
  // does not.
  useEffect(() => {
    if (!run) return;
    if (!run.runnable && !run.active) return;

    const timer = setTimeout(() => {
      if (run.runnable) {
        void step();
      } else {
        void api
          .readRun(runId)
          .then((next) => alive.current && setRun(next))
          .catch(() => undefined);
      }
    }, POLL_MS);
    return () => clearTimeout(timer);
  }, [run, runId, step]);

  const resolve = useCallback(
    async (decisions: Record<string, Decision>) => {
      setBusy(true);
      try {
        const next = await api.resolve(runId, decisions);
        if (alive.current) {
          setRun(next);
          setError(null);
        }
      } catch (cause) {
        if (alive.current) {
          setError(
            cause instanceof ApiError ? cause.message : "That decision could not be applied.",
          );
        }
      } finally {
        if (alive.current) setBusy(false);
      }
    },
    [runId],
  );

  const retry = useCallback(async () => {
    setBusy(true);
    await step();
    if (alive.current) setBusy(false);
  }, [step]);

  // First load, when the page did not arrive with state.
  useEffect(() => {
    if (run !== null) return;
    void api
      .readRun(runId)
      .then((next) => alive.current && setRun(next))
      .catch((cause) =>
        alive.current &&
        setError(cause instanceof ApiError ? cause.message : "That migration could not be loaded."),
      );
  }, [run, runId]);

  return { run, error, busy, resolve, retry };
}
