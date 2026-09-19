/**
 * Status indicators.
 *
 * Every status carries a word, not only a colour: a reviewer who cannot
 * distinguish red from green still has to be able to tell a delivered record
 * from a failed one.
 */
import { cn } from "@/lib/utils";

export type Tone = "neutral" | "working" | "good" | "warn" | "bad";

const TONES: Record<Tone, string> = {
  neutral: "text-muted-foreground bg-secondary border-border",
  working: "text-primary bg-primary/[0.08] border-primary/25",
  good: "text-success bg-success/[0.08] border-success/25",
  warn: "text-warning bg-warning/[0.10] border-warning/30",
  bad: "text-destructive bg-destructive/[0.08] border-destructive/25",
};

export function Pill({
  tone = "neutral",
  children,
  className,
}: {
  tone?: Tone;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5",
        "text-[11px] font-medium whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** A small dot, for a status that needs no word beside it. */
export function Dot({ tone = "neutral", pulse = false }: { tone?: Tone; pulse?: boolean }) {
  const fill: Record<Tone, string> = {
    neutral: "bg-muted-foreground/50",
    working: "bg-primary",
    good: "bg-success",
    warn: "bg-warning",
    bad: "bg-destructive",
  };
  return (
    <span className="relative inline-flex h-1.5 w-1.5 shrink-0">
      {pulse && (
        <span
          className={cn(
            "absolute inline-flex h-full w-full rounded-full opacity-60",
            fill[tone],
            "motion-safe:animate-ping",
          )}
        />
      )}
      <span className={cn("relative inline-flex h-1.5 w-1.5 rounded-full", fill[tone])} />
    </span>
  );
}
