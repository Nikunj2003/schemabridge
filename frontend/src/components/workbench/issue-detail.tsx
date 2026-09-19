/**
 * One escalation, with everything needed to settle it.
 *
 * The brief asks for enough context to resolve a case "in one glance", which
 * rules out a drill-down. So this shows, in reading order: what the agent is
 * asking, where the data came from, what it looks like, why the agent would not
 * decide alone, and the available answers.
 *
 * There is no confidence score. A consultant cannot act on "0.87", and showing
 * one invites treating an arbitrary threshold as a probability. The reason the
 * agent stopped is the honest version of the same information.
 *
 * The options are also given equal visual weight on purpose. Styling one as the
 * obvious answer produces rubber-stamping: the reviewer stops reading and clicks
 * the big button. Since the agent escalated precisely because it could not pick,
 * presenting a favourite here would be dishonest as well as unhelpful.
 */
"use client";

import { useEffect, useRef, useState } from "react";
import type { Decision, Issue } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/status";
import { cn } from "@/lib/utils";

/** What the agent is asking about, in the consultant's words. */
const QUESTIONS: Record<Issue["type"], string> = {
  AMBIGUOUS_MAPPING: "Which field is this?",
  COMPETING_COLUMNS: "Which column should we use?",
  REQUIRED_FIELD_UNMAPPED: "Where does this field come from?",
  AMBIGUOUS_DATE: "Which date is this?",
  IDENTITY_CONFLICT: "Which value is right?",
  DUPLICATE_EMAIL: "Are these the same person?",
  VALIDATION_FAILED_TWICE: "This record needs fixing",
  UNSAFE_CLEANUP: "This value needs checking",
  DELIVERY_FAILED: "This record was not accepted",
};

export function IssueDetail({
  issue,
  onResolve,
  busy,
}: {
  issue: Issue;
  onResolve: (decision: Decision) => void;
  busy: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  // Tracking which issue the local state belongs to lets it reset during render
  // rather than in an effect, which would cost an extra render pass every time
  // the reviewer moves to the next case.
  const [draft, setDraft] = useState({ issueId: issue.id, typed: "", showInput: false });
  const current = draft.issueId === issue.id ? draft : { issueId: issue.id, typed: "", showInput: false };
  const { typed, showInput } = current;
  const setTyped = (value: string) => setDraft({ ...current, typed: value });
  const setShowInput = (value: boolean) => setDraft({ ...current, showInput: value });

  useEffect(() => {
    if (showInput) inputRef.current?.focus();
  }, [showInput]);

  // Number keys pick an option, so a queue of several can be cleared quickly
  // without reaching for the mouse. Ignored while typing a value.
  const resolved = issue.resolution !== null;
  const choices = issue.options.filter((option) => option.id !== "ignore");
  useEffect(() => {
    if (resolved || busy || showInput) return;
    function onKey(event: KeyboardEvent) {
      const index = Number(event.key) - 1;
      if (Number.isNaN(index) || index < 0 || index >= choices.length) return;
      const target = event.target as HTMLElement | null;
      if (target?.tagName === "INPUT" || target?.tagName === "TEXTAREA") return;
      event.preventDefault();
      const option = choices[index];
      onResolve({ action: "correct", option_id: option.id, value: option.value });
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [choices, busy, showInput, resolved, onResolve]);

  const ignore = issue.options.find((option) => option.id === "ignore");
  const excludes = issue.options.filter((option) => option.id.startsWith("exclude:"));
  const canType = issue.type === "VALIDATION_FAILED_TWICE" || issue.field !== null;

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto px-6 py-5">
        <div className="mx-auto max-w-2xl">
          <div className="flex items-center gap-2">
            <Pill tone={issue.blocking ? "warn" : "neutral"}>
              {issue.blocking ? "Needs an answer" : "Optional"}
            </Pill>
            {issue.affected > 1 && (
              <span className="text-[12px] text-muted-foreground">
                {issue.affected} records affected
              </span>
            )}
            {resolved && <Pill tone="good">Resolved</Pill>}
          </div>

          <h1 className="mt-3 text-[22px] leading-snug font-semibold">
            {QUESTIONS[issue.type]}
          </h1>

          {/* Why the agent stopped, in plain language. This is the substitute
              for a confidence number, and it is the most important text here. */}
          <p className="mt-3 text-[14px] leading-relaxed text-muted-foreground">
            {issue.reason}
          </p>

          {issue.current_value && (
            <div className="mt-5">
              <h2 className="text-[12px] font-medium text-muted-foreground">
                {issue.field_label
                  ? `What the sources say for ${issue.field_label.toLowerCase()}`
                  : "The value in question"}
              </h2>
              <p className="mt-1 font-mono text-[14px] break-all">{issue.current_value}</p>
            </div>
          )}

          {issue.errors.length > 0 && (
            <ul className="mt-4 space-y-1.5 border-l-2 border-destructive/30 pl-3">
              {issue.errors.map((error) => (
                <li key={error} className="text-[13px] text-destructive">
                  {error}
                </li>
              ))}
            </ul>
          )}

          {resolved && issue.resolution && (
            <p className="mt-5 text-[13px] text-muted-foreground">
              You chose{" "}
              <span className="text-foreground">
                {issue.resolution.value ?? issue.resolution.option_id ?? issue.resolution.action}
              </span>
              {issue.resolution.note ? ` — ${issue.resolution.note}` : "."}
            </p>
          )}
        </div>
      </div>

      {!resolved && (
        <div className="border-t border-border bg-card px-6 py-4">
          <div className="mx-auto max-w-2xl space-y-2">
            {/* The real answers, each labelled with what it does rather than
                with an abstraction like "approve". */}
            {/* Each answer states what it would mean, so the choice is made on
                consequence rather than on which button looks recommended. Equal
                weight on purpose: the agent escalated because it could not pick,
                so highlighting a favourite here would be dishonest. */}
            <div className="grid gap-2 sm:grid-cols-2">
              {choices.map((option, index) => (
                <button
                  key={option.id}
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    onResolve({
                      action: "correct",
                      option_id: option.id,
                      value: option.value,
                    })
                  }
                  className={cn(
                    "group rounded-lg border border-border bg-card px-3 py-2.5 text-left",
                    "transition-colors hover:border-primary/50 hover:bg-secondary/60",
                    "focus-visible:border-primary disabled:pointer-events-none disabled:opacity-50",
                  )}
                >
                  <span className="flex items-center gap-2">
                    <span className="text-[13px] font-medium">{option.label}</span>
                    {index < 9 && (
                      <kbd className="ml-auto rounded border border-border px-1 text-[10px] text-muted-foreground">
                        {index + 1}
                      </kbd>
                    )}
                  </span>
                  {option.detail && (
                    <span className="mt-0.5 block text-[11.5px] leading-snug text-muted-foreground">
                      {option.detail}
                    </span>
                  )}
                </button>
              ))}
            </div>

            {canType && !showInput && (
              <button
                className="text-[12px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                onClick={() => setShowInput(true)}
                disabled={busy}
              >
                Type a different value
              </button>
            )}

            {showInput && (
              <form
                className="flex gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (typed.trim()) {
                    onResolve({ action: "correct", value: typed.trim() });
                  }
                }}
              >
                <input
                  ref={inputRef}
                  value={typed}
                  onChange={(event) => setTyped(event.target.value)}
                  placeholder={
                    issue.field_label ? `New ${issue.field_label.toLowerCase()}` : "New value"
                  }
                  className={cn(
                    "h-9 flex-1 rounded-lg border border-input bg-background px-3",
                    "text-[13px] placeholder:text-muted-foreground/60",
                  )}
                />
                <Button type="submit" variant="primary" disabled={busy || !typed.trim()}>
                  Use this
                </Button>
              </form>
            )}

            {/* Rejecting always states its consequence, so nobody clicks it
                expecting the record to be fixed. */}
            <div className="flex flex-wrap items-center gap-2 pt-1">
              {excludes.map((option) => (
                <Button
                  key={option.id}
                  variant="ghost"
                  size="sm"
                  disabled={busy}
                  onClick={() =>
                    onResolve({
                      action: "exclude",
                      option_id: option.id,
                      note: option.detail,
                    })
                  }
                >
                  {option.label}
                </Button>
              ))}
              {ignore && (
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={busy}
                  title={ignore.detail}
                  onClick={() => onResolve({ action: "reject", option_id: ignore.id })}
                >
                  {ignore.label}
                </Button>
              )}
              {!ignore && excludes.length === 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={busy}
                  onClick={() =>
                    onResolve({
                      action: "exclude",
                      note: "Left out of this migration.",
                    })
                  }
                >
                  Leave this record out
                </Button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
