/**
 * The queue of things needing a person.
 *
 * Kept deliberately terse: each row is a glanceable summary, and the detail
 * lives in the pane beside it. The count at the top is the number that matters
 * to a consultant — how much is left before this migration is done.
 */
"use client";

import type { Issue } from "@/lib/api";
import { Dot } from "@/components/ui/status";
import { cn } from "@/lib/utils";

const SUMMARIES: Record<Issue["type"], string> = {
  AMBIGUOUS_MAPPING: "Unclear field",
  COMPETING_COLUMNS: "Two columns compete",
  REQUIRED_FIELD_UNMAPPED: "Missing field",
  AMBIGUOUS_DATE: "Unclear date",
  IDENTITY_CONFLICT: "Sources disagree",
  DUPLICATE_EMAIL: "Shared email",
  VALIDATION_FAILED_TWICE: "Invalid record",
  UNSAFE_CLEANUP: "Value needs checking",
  DELIVERY_FAILED: "Not accepted",
};

export function Queue({
  issues,
  selectedId,
  onSelect,
}: {
  issues: Issue[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (issues.length === 0) {
    return (
      <div className="px-3 py-5 text-[12px] leading-relaxed text-muted-foreground">
        Nothing needs you. The agent handled everything it was confident about.
      </div>
    );
  }

  return (
    <ul className="overflow-y-auto py-1">
      {issues.map((issue) => {
        const selected = issue.id === selectedId;
        const done = issue.resolution !== null;
        return (
          <li key={issue.id}>
            <button
              onClick={() => onSelect(issue.id)}
              aria-current={selected ? "true" : undefined}
              className={cn(
                "relative flex w-full items-start gap-2.5 px-3 py-2 text-left transition-colors",
                selected ? "bg-secondary" : "hover:bg-secondary/50",
                selected &&
                  "before:absolute before:left-0 before:top-1/2 before:h-5 before:w-[3px] before:-translate-y-1/2 before:rounded-r-full before:bg-primary",
              )}
            >
              <span className="mt-[6px]">
                <Dot tone={done ? "good" : issue.blocking ? "warn" : "neutral"} />
              </span>
              <span className="min-w-0 flex-1">
                <span
                  className={cn(
                    "block truncate text-[12.5px] font-medium",
                    done && "text-muted-foreground line-through",
                  )}
                >
                  {SUMMARIES[issue.type]}
                </span>
                <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                  {issue.field_label ?? issue.current_value ?? issue.reason}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
