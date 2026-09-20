"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/status";
import type { Decision as DecisionPayload } from "@/lib/api";
import type { PresentedQuestion } from "@/lib/present";
import { cn } from "@/lib/utils";

/**
 * One decision, with the evidence beside it.
 *
 * The question names the record, because "IDENTITY_CONFLICT" means nothing to
 * the person answering. The sources sit side by side so nobody has to open the
 * spreadsheet, and each option states what it would do.
 *
 * Choosing is two steps — select, then save. Migrating the wrong start date is
 * not recoverable by pressing undo, so a single stray keystroke must not commit
 * it. There is no confidence score: the agent stopped precisely because it could
 * not decide, so a recommendation here would be dishonest.
 */
export function Decision({
  question,
  onSave,
  saving,
  error,
  index,
  total,
}: {
  question: PresentedQuestion;
  onSave: (decision: DecisionPayload) => void;
  saving: boolean;
  /** A failed save belongs with the answer that needs to be retried. */
  error?: string | null;
  index: number;
  total: number;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  const [remember, setRemember] = useState(false);
  const typedRef = useRef<HTMLInputElement>(null);

  // A different question is a different decision: nothing carries over.
  const [ownerId, setOwnerId] = useState(question.id);
  if (ownerId !== question.id) {
    setOwnerId(question.id);
    setPicked(null);
    setTyped("");
    setRemember(false);
  }

  const needsTyping = picked !== null && picked === question.typedOption;
  useEffect(() => {
    if (needsTyping) typedRef.current?.focus();
  }, [needsTyping]);

  const ready = picked !== null && (!needsTyping || typed.trim().length > 0);

  const submit = () => {
    if (!picked) return;
    const option = question.options.find((o) => o.id === picked);
    if (!option) return;

    // The action tells the engine what kind of decision this is; it revalidates
    // either way, so a typed value is a proposal rather than an override.
    // `remember` is a pre-authorisation, not a second decision. It lets a rule
    // drawn from this answer apply to the rest of the run without interrupting the
    // person twice for one judgement; without it the rule is still drafted, it just
    // waits until the run is over.
    if (picked === question.typedOption) {
      onSave({ action: "correct", option_id: picked, value: typed.trim(), remember });
    } else if (picked.startsWith("exclude")) {
      onSave({ action: "exclude", option_id: picked, remember: false });
    } else {
      onSave({
        action: "approve",
        option_id: picked,
        value: option.value ?? null,
        remember,
      });
    }
  };

  const side = question.evidence.length > 1;

  return (
    <article className="panel overflow-hidden">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line bg-sunken px-5 py-3">
        <Badge tone="attention">Needs your judgment</Badge>
        <span className="text-[12.5px] text-ink-muted tnum">
          Question {index + 1} of {total}
        </span>
        {question.affected > 1 && (
          <span className="text-[12.5px] text-ink-muted">
            Affects {question.affected} records
          </span>
        )}
      </div>

      <div className="px-5 py-5 sm:px-6">
        <h2 className="font-display text-[20px] leading-snug">{question.title}</h2>
        {question.subject && (
          <p className="mt-1 text-[13px] text-ink-muted">{question.subject}</p>
        )}
        <p className="mt-3 max-w-[62ch] text-[14px] leading-relaxed text-ink-muted">
          {question.why}
        </p>

        {question.evidence.length > 0 && (
          <div className={cn("mt-5 grid gap-3", side ? "sm:grid-cols-2" : "sm:max-w-sm")}>
            {question.evidence.map((source, i) => (
              <div key={`${source.raw}-${i}`} className="rounded-md border border-line bg-sunken px-3.5 py-3">
                <p className="truncate text-[12px] text-ink-subtle">{source.label}</p>
                {source.reading ? (
                  <>
                    <p className="mt-1 text-[17px] font-semibold">{source.reading}</p>
                    <p className="raw mt-0.5 text-[12.5px] text-ink-muted">written as {source.raw}</p>
                  </>
                ) : (
                  <p className="raw mt-1 text-[16px] font-semibold break-all">{source.raw}</p>
                )}
              </div>
            ))}
          </div>
        )}

        <fieldset className="mt-6">
          <legend className="text-[13px] font-medium">Your answer</legend>
          <div className="mt-2.5 space-y-2">
            {question.options.map((option) => (
              <label
                key={option.id}
                className={cn(
                  "flex cursor-pointer gap-3 rounded-md border px-3.5 py-3 transition-colors",
                  picked === option.id
                    ? "border-accent bg-accent-soft"
                    : "border-line hover:border-line-strong hover:bg-sunken",
                )}
              >
                <input
                  type="radio"
                  name={`answer-${question.id}`}
                  checked={picked === option.id}
                  onChange={() => setPicked(option.id)}
                  className="mt-1 size-4 shrink-0 accent-[var(--accent)]"
                />
                <span className="min-w-0">
                  <span className="block text-[14px] font-medium">{option.label}</span>
                  {option.detail && (
                    <span className="mt-0.5 block text-[13px] text-ink-muted">{option.detail}</span>
                  )}
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        {needsTyping && (
          <div className="mt-4 sm:max-w-sm">
            <label htmlFor={`typed-${question.id}`} className="block text-[13px] font-medium">
              {question.fieldLabel ?? "New value"}
            </label>
            <input
              id={`typed-${question.id}`}
              ref={typedRef}
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              className="mt-1.5 h-9.5 w-full rounded-md border border-line-strong bg-surface px-3 text-[14px]"
            />
            <p className="mt-1.5 text-[12.5px] text-ink-muted">
              Checked before anything is sent. If it still does not pass, this
              question stays open.
            </p>
          </div>
        )}

        {ready && !picked?.startsWith("exclude") && (
          <label className="mt-5 flex cursor-pointer items-start gap-2.5 rounded-md border border-line bg-sunken/50 px-3.5 py-3">
            <input
              type="checkbox"
              checked={remember}
              onChange={(event) => setRemember(event.target.checked)}
              className="mt-0.5 size-4 shrink-0 accent-accent"
            />
            <span>
              <span className="block text-[13px] font-medium">
                Remember this for future migrations
              </span>
              <span className="mt-0.5 block text-[12.5px] text-ink-muted">
                A rule is drafted from your answer and checked against the schema. You
                see it before it is saved, and can turn it off at any time.
              </span>
            </span>
          </label>
        )}

        <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-line pt-4">
          <Button variant="primary" disabled={!ready || saving} onClick={submit}>
            {saving ? "Saving…" : "Save decision"}
          </Button>
          {!ready && (
            <span className="text-[13px] text-ink-subtle">
              {picked === null ? "Choose an answer to continue." : "Type a value to continue."}
            </span>
          )}
        </div>

        {error && (
          <p role="alert" className="mt-4 rounded-md border border-problem/30 bg-problem-soft px-3.5 py-2.5 text-[13px] text-problem">
            {error}
          </p>
        )}
      </div>
    </article>
  );
}
