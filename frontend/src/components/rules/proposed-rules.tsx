"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/status";
import { api, type ProposedRule } from "@/lib/api";
import { KIND_LABEL, describeRule } from "@/lib/rules";

/**
 * Rules this migration learned, offered once it is over.
 *
 * Placed here rather than mid-run because a mapping rule cannot help the run that
 * produced it: columns are matched before any record exists, so the only thing an
 * interruption would buy is an interruption. What it buys instead is the next run.
 *
 * Nothing is saved until a proposal is approved, and declining leaves no trace —
 * so the honest framing is an offer, not a confirmation. The card renders nothing
 * at all when there is nothing to offer, since an empty "no suggestions" panel
 * teaches people to stop reading this area.
 */
export function ProposedRules({
  runId,
  schemaName,
  asked,
}: {
  runId: string;
  schemaName: string;
  /** Whether the reviewer decided anything, so a silent card is not the answer. */
  asked: boolean;
}) {
  const [proposals, setProposals] = useState<ProposedRule[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [accepted, setAccepted] = useState<Set<string>>(new Set());
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void (async () => {
      const result = await api.rules.proposed(runId).catch(() => null);
      if (!live) return;
      if (result) setProposals(result.proposals);
      setLoaded(true);
    })();
    return () => {
      live = false;
    };
  }, [runId]);

  const accept = async (proposal: ProposedRule) => {
    setBusy(proposal.proposal_id);
    setError(null);
    try {
      await api.rules.accept(runId, proposal.proposal_id);
      setAccepted((current) => new Set(current).add(proposal.proposal_id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The rule could not be saved.");
    } finally {
      setBusy(null);
    }
  };

  const open = proposals.filter((proposal) => !dismissed.has(proposal.proposal_id));

  // A decision was made and no rule came of it. Saying so is the point: the audit
  // shows the model being asked, and a card that simply vanished left the reader to
  // conclude something had broken. Silence is only correct when nothing was asked.
  if (open.length === 0) {
    if (!asked || !loaded) return null;
    return (
      <section className="panel mt-5 px-5 py-4">
        <h2 className="text-[14px] font-medium">Nothing worth remembering</h2>
        <p className="mt-1 max-w-[64ch] text-[12.5px] text-ink-muted">
          Your decisions here were about this file rather than a pattern that would
          recur, so no rule was drafted. The audit below says which, and why, for each
          one. Nothing was saved.
        </p>
      </section>
    );
  }

  const savedCount = open.filter((p) => accepted.has(p.proposal_id)).length;

  return (
    <section className="panel mt-5 overflow-hidden">
      <div className="border-b border-line bg-sunken px-5 py-3">
        <h2 className="text-[14px] font-medium">Worth remembering</h2>
        <p className="mt-0.5 max-w-[64ch] text-[12.5px] text-ink-muted">
          {savedCount > 0
            ? `${savedCount} saved to ${schemaName}. Next time this export arrives, ${savedCount === 1 ? "that question is" : "those questions are"} not asked and no model request is spent on it.`
            : `Your answers below would recur on the next export. Keep any of them and they join the rules for ${schemaName} — affecting migrations onto that schema and no other.`}
        </p>
      </div>

      {error && (
        <p
          role="alert"
          className="border-b border-line bg-problem-soft px-5 py-2.5 text-[13px] text-problem"
        >
          {error}
        </p>
      )}

      <ul className="divide-y divide-line">
        {open.map((proposal) => {
          const saved = accepted.has(proposal.proposal_id);
          return (
            <li key={proposal.proposal_id} className="px-5 py-3.5">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={saved ? "ok" : "working"}>{saved ? "Saved" : "Suggested"}</Badge>
                <span className="text-[12px] text-ink-subtle">
                  {KIND_LABEL[proposal.rule.kind]}
                </span>
                {proposal.scope === "value" && !saved && (
                  <span className="text-[12px] text-ink-subtle">
                    · would also apply to the rest of this migration
                  </span>
                )}
              </div>

              <p className="mt-1.5 text-[13.5px]">{describeRule(proposal.rule)}</p>
              {proposal.rationale && (
                <p className="mt-0.5 text-[12.5px] text-ink-muted">{proposal.rationale}</p>
              )}
              {proposal.provenance.decision && (
                <p className="mt-0.5 text-[12px] text-ink-subtle">
                  Drawn from your answer: “{proposal.provenance.decision}”.
                </p>
              )}

              {!saved && (
                <div className="mt-2.5 flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    variant="primary"
                    disabled={busy === proposal.proposal_id}
                    onClick={() => void accept(proposal)}
                  >
                    {busy === proposal.proposal_id ? "Saving…" : "Keep this rule"}
                  </Button>
                  <Button
                    size="sm"
                    variant="quiet"
                    onClick={() =>
                      setDismissed((current) => new Set(current).add(proposal.proposal_id))
                    }
                  >
                    No thanks
                  </Button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
