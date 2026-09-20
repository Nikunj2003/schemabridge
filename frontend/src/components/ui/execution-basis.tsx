import type { ExecutionBasis } from "@/lib/api";
import { cn } from "@/lib/utils";

const CONTENT: Record<ExecutionBasis, { label: string; title: string; tone: string }> = {
  deterministic: {
    label: "Rule engine",
    title: "A deterministic rule did this: a header alias, a safe repair, a validation check or a delivery policy.",
    tone: "border-line bg-sunken text-ink-muted",
  },
  model_assisted: {
    label: "LLM",
    title: "A model request is part of this step. Anything the model suggests is verified against the schema before it is applied.",
    tone: "border-accent/30 bg-accent-soft text-accent-ink",
  },
  human: {
    label: "Your decision",
    title: "You answered this, and the engine did what you chose.",
    tone: "border-attention/30 bg-attention-soft text-attention",
  },
  unknown: {
    label: "Provenance unavailable",
    title: "This older recorded event does not contain execution provenance.",
    tone: "border-line bg-sunken text-ink-subtle",
  },
};

/**
 * Which subsystem did the work, in words as well as an icon.
 *
 * It names the actor rather than the verdict, because "where did the LLM run"
 * and "where did the rules run" is the question the audit has to answer. The
 * value comes from the backend's recorded basis, never from the event wording.
 */
export function ExecutionBasis({ basis, compact = false }: { basis: ExecutionBasis; compact?: boolean }) {
  const content = CONTENT[basis];
  return (
    <span
      title={content.title}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border font-medium",
        compact ? "px-1.5 py-0.5 text-[10.5px]" : "px-2 py-0.5 text-[11px]",
        content.tone,
      )}
    >
      <BasisIcon basis={basis} />
      {content.label}
    </span>
  );
}

function BasisIcon({ basis }: { basis: ExecutionBasis }) {
  const common = { viewBox: "0 0 16 16", className: "size-3 shrink-0", fill: "none", stroke: "currentColor", strokeWidth: 1.7, "aria-hidden": true };
  if (basis === "model_assisted") {
    return <svg {...common}><path d="M8 1.8l1.4 4.8L14.2 8l-4.8 1.4L8 14.2 6.6 9.4 1.8 8l4.8-1.4L8 1.8z" /></svg>;
  }
  if (basis === "human") {
    return <svg {...common}><circle cx="8" cy="5.25" r="2.25" /><path d="M3.5 14c.45-2.25 2.05-3.4 4.5-3.4s4.05 1.15 4.5 3.4" /></svg>;
  }
  if (basis === "unknown") {
    return <svg {...common}><circle cx="8" cy="8" r="5.75" /><path d="M6.8 6.2a1.4 1.4 0 0 1 2.75.42c0 1.3-1.55 1.35-1.55 2.55M8 11.85h.01" /></svg>;
  }
  return <svg {...common}><path d="M3 8.25l2.8 2.8L13 4.5" /></svg>;
}
