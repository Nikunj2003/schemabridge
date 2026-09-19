"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/status";
import type { Question } from "@/lib/sample";
import { cn } from "@/lib/utils";

/**
 * One decision, with the evidence beside it.
 *
 * The question names the employee, because "IDENTITY_CONFLICT" means nothing to
 * the person answering. Both sources sit side by side so nobody has to open the
 * spreadsheet, and each option says what it would do.
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
}: {
  question: Question;
  onSave: (choiceId: string, typed?: string) => void;
  saving: boolean;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  const typedRef = useRef<HTMLInputElement>(null);

  // A different question is a different decision: nothing carries over.
  const [ownerId, setOwnerId] = useState(question.id);
  if (ownerId !== question.id) {
    setOwnerId(question.id);
    setPicked(null);
    setTyped("");
  }

  const needsTyping = picked !== null && question.choices.find((c) => c.id === picked)?.label.startsWith("Type");
  useEffect(() => {
    if (needsTyping) typedRef.current?.focus();
  }, [needsTyping]);

  const ready = picked !== null && (!needsTyping || typed.trim().length > 0);

  return (
    <article className="card overflow-hidden">
      <div className="border-b border-line px-5 py-4 sm:px-6">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="attention">Needs your judgment</Badge>
          {question.affected > 1 && (
            <span className="text-[13px] text-ink-muted">
              Affects {question.affected} employees
            </span>
          )}
        </div>

        <h2 className="mt-3 font-display text-[21px] leading-snug font-semibold">
          {question.title}
        </h2>
        <p className="mt-1 text-[13.5px] text-ink-muted">{question.subject}</p>
      </div>

      <div className="space-y-6 px-5 py-5 sm:px-6">
        <p className="max-w-prose text-[14.5px] leading-relaxed text-ink-muted">
          {question.why}
        </p>

        {/* The evidence. Side by side when there are two sources to compare. */}
        <div
          className={cn(
            "grid gap-3",
            question.sources.length > 1 ? "sm:grid-cols-2" : "sm:max-w-sm",
          )}
        >
          {question.sources.map((source) => (
            <div key={`${source.file}-${source.row}`} className="rounded-lg border border-line bg-sunken p-3.5">
              <p className="text-[12.5px] text-ink-subtle">
                {source.file} · row {source.row}
              </p>
              {source.reading ? (
                <>
                  <p className="mt-1.5 text-[17px] font-semibold">{source.reading}</p>
                  <p className="raw mt-0.5 text-[12.5px] text-ink-muted">written as {source.raw}</p>
                </>
              ) : (
                <p className="raw mt-1.5 text-[17px] font-semibold break-all">{source.raw}</p>
              )}
            </div>
          ))}
        </div>

        <fieldset>
          <legend className="text-[13.5px] font-medium">Your answer</legend>
          <div className="mt-2.5 space-y-2">
            {question.choices.map((choice) => (
              <label
                key={choice.id}
                className={cn(
                  "flex cursor-pointer gap-3 rounded-lg border p-3 transition-colors",
                  picked === choice.id
                    ? "border-accent bg-accent-soft"
                    : "border-line hover:border-line-strong hover:bg-sunken",
                )}
              >
                <input
                  type="radio"
                  name={`answer-${question.id}`}
                  checked={picked === choice.id}
                  onChange={() => setPicked(choice.id)}
                  className="mt-1 size-4 shrink-0 accent-[var(--accent)]"
                />
                <span className="min-w-0">
                  <span className="block text-[14.5px] font-medium">{choice.label}</span>
                  <span className="mt-0.5 block text-[13px] text-ink-muted">{choice.consequence}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        {needsTyping && (
          <div className="sm:max-w-sm">
            <label htmlFor={`typed-${question.id}`} className="block text-[13.5px] font-medium">
              {question.field}
            </label>
            <input
              id={`typed-${question.id}`}
              ref={typedRef}
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              placeholder="name@example.com"
              className="mt-1.5 h-10 w-full rounded-md border border-line-strong bg-surface px-3 text-[14px]"
            />
            <p className="mt-1.5 text-[13px] text-ink-muted">
              Checked before anything is sent. If it still does not work, this
              question stays open.
            </p>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
          <Button
            variant="primary"
            disabled={!ready || saving}
            onClick={() => picked && onSave(picked, typed.trim() || undefined)}
          >
            {saving ? "Saving…" : "Save decision"}
          </Button>
          <button className="text-[13.5px] text-ink-muted underline-offset-2 hover:text-ink hover:underline">
            Why am I being asked this?
          </button>
        </div>
      </div>
    </article>
  );
}
