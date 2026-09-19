import { cn } from "@/lib/utils";

/**
 * Status vocabulary.
 *
 * Every tone pairs with a word. Someone who cannot distinguish the hues must
 * still be able to tell "sent" from "needs attention".
 */
export type Tone = "neutral" | "working" | "ok" | "attention" | "problem";

const TONE: Record<Tone, string> = {
  neutral: "border-line-strong bg-sunken text-ink-muted",
  working: "border-accent/30 bg-accent-soft text-accent-ink",
  ok: "border-ok/25 bg-ok-soft text-ok",
  attention: "border-attention/30 bg-attention-soft text-attention",
  problem: "border-problem/25 bg-problem-soft text-problem",
};

const DOT: Record<Tone, string> = {
  neutral: "bg-ink-subtle",
  working: "bg-accent",
  ok: "bg-ok",
  attention: "bg-attention",
  problem: "bg-problem",
};

export function Badge({
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
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12.5px] font-medium",
        TONE[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Dot({ tone = "neutral", busy = false }: { tone?: Tone; busy?: boolean }) {
  return (
    <span className="relative inline-flex size-2 shrink-0" aria-hidden>
      {busy && (
        <span
          className={cn("absolute inline-flex size-full rounded-full opacity-50 motion-safe:animate-ping", DOT[tone])}
        />
      )}
      <span className={cn("relative inline-flex size-2 rounded-full", DOT[tone])} />
    </span>
  );
}
