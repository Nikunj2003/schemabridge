"use client";

import { useId } from "react";
import { cn } from "@/lib/utils";

/** A labelled text input. The label is always real, never a placeholder. */
export function Field({
  label,
  hint,
  error,
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  error?: string;
}) {
  const id = useId();
  const describedBy = [hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(" ");

  return (
    <div className={className}>
      <label htmlFor={id} className="block text-[13.5px] font-medium">
        {label}
      </label>
      {hint && (
        <p id={`${id}-hint`} className="mt-0.5 text-[13px] text-ink-muted">
          {hint}
        </p>
      )}
      <input
        id={id}
        aria-describedby={describedBy || undefined}
        aria-invalid={error ? true : undefined}
        className={cn(
          "mt-1.5 h-10 w-full rounded-md border bg-surface px-3 text-[14px]",
          "placeholder:text-ink-subtle",
          error ? "border-problem" : "border-line-strong",
        )}
        {...props}
      />
      {error && (
        <p id={`${id}-error`} role="alert" className="mt-1.5 text-[13px] text-problem">
          {error}
        </p>
      )}
    </div>
  );
}
