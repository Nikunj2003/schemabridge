"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/status";
import { Button, ButtonLink } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type RuleListing, type RuleView, type TargetSchema } from "@/lib/api";
import { KIND_LABEL, ORIGIN_LABEL, describeRule } from "@/lib/rules";

/**
 * Everything the engine knows, and where each piece came from.
 *
 * Three sections in a deliberate order: what the engine learned from you, what you
 * wrote yourself, and what it shipped knowing. The learned section is first because
 * it is the one a person has a reason to check — a rule drafted from a decision is
 * the only kind they did not author word for word.
 *
 * Built-in rules are listed but not editable, and the honest reason is shown rather
 * than hidden: they come from code, so there is nothing to edit. What a person can
 * do is turn one off for themselves, which is a different and reversible act.
 */
export function RulesList() {
  const [listing, setListing] = useState<RuleListing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [showBuiltin, setShowBuiltin] = useState(false);
  const [schemas, setSchemas] = useState<TargetSchema[]>([]);
  // Which contract's rules are on screen. A rule only ever affects migrations onto
  // one schema, so showing them all at once would answer the wrong question: what a
  // person needs to know is what applies to the run they are about to start.
  const [schemaId, setSchemaId] = useState<string>("");

  const load = useCallback(async () => {
    try {
      setListing(await api.rules.list(schemaId));
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Rules could not be loaded.");
    }
  }, [schemaId]);

  useEffect(() => {
    let live = true;
    void (async () => {
      const listed = await api.schemas.list().catch(() => null);
      if (!live) return;
      if (listed) {
        const all = [listed.builtin, ...listed.schemas];
        setSchemas(all);
        setSchemaId(all[0]?.schema_id ?? "");
      }
    })();
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    if (!schemaId) return;
    let live = true;
    void (async () => {
      const loaded = await api.rules.list(schemaId).catch(() => null);
      if (!live) return;
      if (loaded) setListing(loaded);
      else setError("Rules could not be loaded.");
    })();
    return () => {
      live = false;
    };
  }, [schemaId]);

  const act = async (id: string, work: () => Promise<unknown>, failure: string) => {
    setBusy(id);
    try {
      await work();
      setConfirming(null);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : failure);
    } finally {
      setBusy(null);
    }
  };

  // The API already scopes `mine` to the chosen schema, so these are exactly the
  // rules in force for a run against it.
  const learned = listing?.mine.filter((rule) => rule.origin === "learned") ?? [];
  const written = listing?.mine.filter((rule) => rule.origin === "handwritten") ?? [];
  const overrides = listing?.mine.filter((rule) => rule.origin === "override") ?? [];
  const current = schemas.find((candidate) => candidate.schema_id === schemaId);

  return (
    <div className="mx-auto max-w-[56rem] px-4 py-6 sm:px-8 sm:py-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-[24px]">Rules</h1>
          <p className="mt-1.5 max-w-[62ch] text-[14px] text-ink-muted">
            A rule is a decision the engine no longer has to ask you about. Every
            question you answer can become one, so the second migration of the same
            export asks less than the first — and costs less, because a rule needs no
            model request.
          </p>
        </div>
        <ButtonLink href="/app/rules/new" variant="primary">
          New rule
        </ButtonLink>
      </div>

      {schemas.length > 1 && (
        <div
          role="tablist"
          aria-label="Schema"
          className="mt-5 flex flex-wrap gap-1.5 border-b border-line pb-3"
        >
          {schemas.map((candidate) => (
            <button
              key={candidate.schema_id}
              role="tab"
              aria-selected={candidate.schema_id === schemaId}
              onClick={() => {
                setSchemaId(candidate.schema_id);
                setListing(null);
                setShowBuiltin(false);
              }}
              className={
                candidate.schema_id === schemaId
                  ? "rounded-md bg-accent-soft px-3 py-1.5 text-[13px] font-medium text-accent-ink"
                  : "rounded-md px-3 py-1.5 text-[13px] text-ink-muted hover:bg-sunken"
              }
            >
              {candidate.name}
            </button>
          ))}
        </div>
      )}

      {current && (
        <p className="mt-4 rounded-md border border-line bg-sunken/50 px-4 py-2.5 text-[12.5px] text-ink-muted">
          Showing the rules that apply when migrating onto{" "}
          <span className="font-medium text-ink">{current.name}</span>. A rule never
          affects a migration onto a different schema.
        </p>
      )}

      {error && (
        <p
          role="alert"
          className="mt-5 rounded-md border border-problem/30 bg-problem-soft px-4 py-3 text-[13.5px] text-problem"
        >
          {error}
        </p>
      )}

      {listing === null && !error && <RulesSkeleton />}

      {listing && (
        <>
          <section className="mt-7">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="eyebrow">Learned from your decisions</h2>
              <span className="text-[12px] text-ink-subtle tnum">
                {listing.mine.length} of {listing.limits.max_rules}
              </span>
            </div>
            {learned.length === 0 ? (
              <div className="panel mt-2.5 px-5 py-8 text-center">
                <p className="text-[14px] font-medium">Nothing learned yet</p>
                <p className="mx-auto mt-1 max-w-[48ch] text-[13px] text-ink-muted">
                  When a migration asks you something that would recur, it offers to
                  remember your answer as a rule. Approve one and it appears here.
                </p>
              </div>
            ) : (
              <ul className="panel mt-2.5 divide-y divide-line overflow-hidden">
                {learned.map((rule) => (
                  <RuleRow
                    key={rule.rule_id}
                    rule={rule}
                    busy={busy === rule.rule_id}
                    confirming={confirming === rule.rule_id}
                    onConfirm={() => setConfirming(rule.rule_id)}
                    onCancel={() => setConfirming(null)}
                    onToggle={() =>
                      void act(
                        rule.rule_id,
                        () => api.rules.toggle(rule.rule_id, !rule.enabled),
                        "The rule could not be changed.",
                      )
                    }
                    onRemove={() =>
                      void act(
                        rule.rule_id,
                        () => api.rules.remove(rule.rule_id),
                        "The rule could not be deleted.",
                      )
                    }
                  />
                ))}
              </ul>
            )}
          </section>

          <section className="mt-7">
            <h2 className="eyebrow">Written by you</h2>
            {written.length === 0 ? (
              <p className="panel mt-2.5 px-5 py-5 text-[13px] text-ink-muted">
                None yet. A rule you write by hand behaves exactly like a learned one;
                the only difference is who drafted it.
              </p>
            ) : (
              <ul className="panel mt-2.5 divide-y divide-line overflow-hidden">
                {written.map((rule) => (
                  <RuleRow
                    key={rule.rule_id}
                    rule={rule}
                    busy={busy === rule.rule_id}
                    confirming={confirming === rule.rule_id}
                    onConfirm={() => setConfirming(rule.rule_id)}
                    onCancel={() => setConfirming(null)}
                    onToggle={() =>
                      void act(
                        rule.rule_id,
                        () => api.rules.toggle(rule.rule_id, !rule.enabled),
                        "The rule could not be changed.",
                      )
                    }
                    onRemove={() =>
                      void act(
                        rule.rule_id,
                        () => api.rules.remove(rule.rule_id),
                        "The rule could not be deleted.",
                      )
                    }
                  />
                ))}
              </ul>
            )}
          </section>

          {overrides.length > 0 && (
            <section className="mt-7">
              <h2 className="eyebrow">Built-in rules you turned off</h2>
              <ul className="panel mt-2.5 divide-y divide-line overflow-hidden">
                {overrides.map((rule) => (
                  <li
                    key={rule.rule_id}
                    className="flex flex-wrap items-center gap-3 px-4 py-3 text-[13px]"
                  >
                    <span className="raw text-ink-muted">{rule.targets_rule_id}</span>
                    <Button
                      size="sm"
                      variant="quiet"
                      className="ml-auto"
                      disabled={busy === rule.rule_id}
                      onClick={() =>
                        void act(
                          rule.rule_id,
                          () => api.rules.toggle(rule.rule_id, false),
                          "The rule could not be restored.",
                        )
                      }
                    >
                      Turn back on
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="mt-7">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="eyebrow">Built in</h2>
              <span className="text-[12px] text-ink-subtle tnum">{listing.builtin.length}</span>
            </div>
            <p className="mt-1.5 max-w-[62ch] text-[13px] text-ink-muted">
              These come from the engine itself, so there is nothing to edit — but you
              can turn one off if it is wrong for your data. Headers that two fields
              both claim are deliberately absent: those are what make a column
              ambiguous, and a rule settling one would remove a question you want.
            </p>
            {showBuiltin ? (
              <ul className="panel mt-2.5 max-h-[28rem] divide-y divide-line overflow-hidden scroll-area">
                {listing.builtin.map((rule) => (
                  <li key={rule.rule_id} className="flex flex-wrap items-center gap-2.5 px-4 py-2.5">
                    <Badge tone="neutral">{KIND_LABEL[rule.kind]}</Badge>
                    <span className="min-w-0 flex-1 text-[13px]">{describeRule(rule)}</span>
                    <Button
                      size="sm"
                      variant="quiet"
                      disabled={busy === rule.rule_id}
                      onClick={() =>
                        void act(
                          rule.rule_id,
                          () => api.rules.toggle(rule.rule_id, false, schemaId),
                          "The rule could not be turned off.",
                        )
                      }
                    >
                      Turn off
                    </Button>
                  </li>
                ))}
              </ul>
            ) : (
              <Button variant="secondary" className="mt-3" onClick={() => setShowBuiltin(true)}>
                Show {listing.builtin.length} built-in rules
              </Button>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function RuleRow({
  rule,
  busy,
  confirming,
  onConfirm,
  onCancel,
  onToggle,
  onRemove,
}: {
  rule: RuleView;
  busy: boolean;
  confirming: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  onToggle: () => void;
  onRemove: () => void;
}) {
  return (
    <li className="px-4 py-3">
      <div className="flex flex-wrap items-center gap-2.5">
        <Badge tone={rule.origin === "learned" ? "working" : "neutral"}>
          {ORIGIN_LABEL[rule.origin]}
        </Badge>
        <span className="text-[12px] text-ink-subtle">{KIND_LABEL[rule.kind]}</span>
        {!rule.enabled && <Badge tone="attention">Off</Badge>}
        {rule.hits > 0 && (
          <span className="text-[12px] text-ink-subtle tnum" title="Times this rule has answered">
            {rule.hits} {rule.hits === 1 ? "use" : "uses"}
          </span>
        )}
      </div>

      <p className="mt-1.5 text-[13.5px]">{describeRule(rule)}</p>
      {rule.rationale && <p className="mt-0.5 text-[12.5px] text-ink-muted">{rule.rationale}</p>}
      {rule.provenance && rule.provenance.decision && (
        <p className="mt-0.5 text-[12px] text-ink-subtle">
          From a question you answered with “{rule.provenance.decision}”.
        </p>
      )}

      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        <ButtonLink href={`/app/rules/${rule.rule_id}`} size="sm" variant="secondary">
          Edit
        </ButtonLink>
        <Button size="sm" variant="quiet" disabled={busy} onClick={onToggle}>
          {rule.enabled ? "Turn off" : "Turn on"}
        </Button>
        {confirming ? (
          <span className="ml-auto flex items-center gap-2">
            <span className="text-[12.5px] text-ink-muted">Delete this rule?</span>
            <Button size="sm" variant="danger" disabled={busy} onClick={onRemove}>
              {busy ? "Deleting…" : "Delete"}
            </Button>
            <Button size="sm" variant="quiet" onClick={onCancel}>
              Keep
            </Button>
          </span>
        ) : (
          <Button size="sm" variant="quiet" className="ml-auto" onClick={onConfirm}>
            Delete
          </Button>
        )}
      </div>
    </li>
  );
}

function RulesSkeleton() {
  return (
    <div className="mt-7" aria-busy="true">
      <span className="sr-only">Loading rules…</span>
      <Skeleton className="h-3 w-40" />
      <div className="panel mt-2.5 divide-y divide-line overflow-hidden">
        {[0, 1, 2].map((index) => (
          <div key={index} className="space-y-2 px-4 py-3.5">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="h-4 w-[70%]" />
          </div>
        ))}
      </div>
    </div>
  );
}
