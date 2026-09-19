"use client";

import { useId } from "react";
import { cn } from "@/lib/utils";

/**
 * Form controls.
 *
 * Every one is label-bound rather than placeholder-labelled: a placeholder
 * disappears the moment someone types, so a half-filled form stops saying what
 * its own fields are. Errors are tied to the control with `aria-describedby` so
 * a screen reader reaches the reason, not just the invalid state.
 */

const CONTROL =
  "w-full rounded-md border bg-surface px-2.5 py-1.5 text-[13.5px] text-ink " +
  "transition-colors placeholder:text-ink-subtle " +
  "focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25 " +
  "disabled:cursor-not-allowed disabled:bg-sunken disabled:text-ink-muted";

function border(invalid: boolean | undefined) {
  return invalid ? "border-problem/60" : "border-line-strong";
}

export function Label({
  htmlFor,
  children,
  hint,
  className,
}: {
  htmlFor?: string;
  children: React.ReactNode;
  hint?: string;
  className?: string;
}) {
  return (
    <label htmlFor={htmlFor} className={cn("block text-[12.5px] font-medium text-ink", className)}>
      {children}
      {hint && <span className="ml-1.5 font-normal text-ink-subtle">{hint}</span>}
    </label>
  );
}

export function Input({
  label,
  hint,
  error,
  className,
  mono,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  hint?: string;
  error?: string;
  /** For values that are code — a field name is read character by character. */
  mono?: boolean;
}) {
  const generated = useId();
  const id = props.id ?? generated;
  const errorId = `${id}-error`;
  return (
    <div className={className}>
      {label && (
        <Label htmlFor={id} hint={hint} className="mb-1">
          {label}
        </Label>
      )}
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        className={cn(CONTROL, border(!!error), mono && "raw")}
        {...props}
      />
      {error && (
        <p id={errorId} className="mt-1 text-[12px] text-problem">
          {error}
        </p>
      )}
    </div>
  );
}

export function Textarea({
  label,
  hint,
  error,
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label?: string;
  hint?: string;
  error?: string;
}) {
  const generated = useId();
  const id = props.id ?? generated;
  const errorId = `${id}-error`;
  return (
    <div className={className}>
      {label && (
        <Label htmlFor={id} hint={hint} className="mb-1">
          {label}
        </Label>
      )}
      <textarea
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        className={cn(CONTROL, border(!!error), "resize-y")}
        {...props}
      />
      {error && (
        <p id={errorId} className="mt-1 text-[12px] text-problem">
          {error}
        </p>
      )}
    </div>
  );
}

export function Select({
  label,
  hint,
  error,
  className,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & {
  label?: string;
  hint?: string;
  error?: string;
}) {
  const generated = useId();
  const id = props.id ?? generated;
  return (
    <div className={className}>
      {label && (
        <Label htmlFor={id} hint={hint} className="mb-1">
          {label}
        </Label>
      )}
      <div className="relative">
        <select
          id={id}
          aria-invalid={error ? true : undefined}
          // A native select, deliberately: it gets the platform's own picker on
          // a phone, which beats anything reimplemented with divs.
          className={cn(CONTROL, border(!!error), "appearance-none pr-8")}
          {...props}
        >
          {children}
        </select>
        <svg
          viewBox="0 0 24 24"
          className="pointer-events-none absolute right-2.5 top-1/2 size-3.5 -translate-y-1/2 text-ink-subtle"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </div>
      {error && <p className="mt-1 text-[12px] text-problem">{error}</p>}
    </div>
  );
}

export function Checkbox({
  label,
  detail,
  className,
  ...props
}: Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> & {
  label: string;
  detail?: string;
}) {
  const generated = useId();
  const id = props.id ?? generated;
  return (
    <div className={cn("flex gap-2.5", className)}>
      <input
        id={id}
        type="checkbox"
        className={cn(
          "mt-0.5 size-4 shrink-0 cursor-pointer rounded border-line-strong text-accent",
          "accent-accent focus:outline-none focus:ring-2 focus:ring-accent/25",
          "disabled:cursor-not-allowed disabled:opacity-50",
        )}
        {...props}
      />
      <div className="min-w-0">
        <label htmlFor={id} className="block cursor-pointer text-[13px] font-medium text-ink">
          {label}
        </label>
        {detail && <p className="mt-0.5 text-[12px] text-ink-muted">{detail}</p>}
      </div>
    </div>
  );
}
