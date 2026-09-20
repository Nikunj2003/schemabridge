"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Badge } from "@/components/ui/status";
import { Button, ButtonLink } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type RuleListing, type RuleView, type TargetSchema } from "@/lib/api";
import { KIND_LABEL, ORIGIN_LABEL, describeRule, normalizeHeader } from "@/lib/rules";
import { cn } from "@/lib/utils";

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

  /**
   * Run one action and fold its result back into the row it belongs to.
   *
   * Deliberately not a refetch. Re-reading the whole listing to reflect one
   * toggle threw away 193 rendered rows and the reader's scroll position, which
   * read as a page reload for what is a one-field change. The endpoint returns the
   * updated rule, so the row it describes is replaced and nothing else moves.
   *
   * A delete has no updated row to return, so that one does reload — there is no
   * way to represent a removal by patching a row.
   */
  const act = async (
    id: string,
    work: () => Promise<RuleView | void>,
    failure: string,
    { reload = false, overridden }: { reload?: boolean; overridden?: boolean } = {},
  ) => {
    setBusy(id);
    setError(null);
    try {
      const updated = await work();
      setConfirming(null);
      if (reload || !updated) {
        await load();
        return;
      }
      setListing((current) => (current ? patchRule(current, id, updated, overridden) : current));
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
                        { reload: true },
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
                        { reload: true },
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
                          { reload: true },
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

          <BuiltinRules
            rules={listing.builtin}
            busy={busy}
            onToggle={(rule) =>
              void act(
                rule.rule_id,
                // `enabled` on the request means "should this shipped rule apply",
                // so turning it back on sends true and clearing the override follows.
                () => api.rules.toggle(rule.rule_id, rule.overridden, schemaId),
                rule.overridden
                  ? "The rule could not be turned back on."
                  : "The rule could not be turned off.",
                { overridden: !rule.overridden },
              )
            }
          />
        </>
      )}
    </div>
  );
}

/**
 * Fold one action's result back into the listing, leaving every other row alone.
 *
 * A shipped rule is a special case worth spelling out. Toggling one does not change
 * that rule — it cannot, it comes from code — it creates or clears an *override*,
 * which is a different rule with its own id. So the shipped row is marked
 * `overridden` rather than replaced with what the endpoint returned; replacing it
 * turned a header alias into "a built-in rule is turned off", which is both wrong
 * and impossible to undo from the row.
 */
function patchRule(
  listing: RuleListing,
  ruleId: string,
  updated: RuleView,
  overridden?: boolean,
): RuleListing {
  if (ruleId.startsWith("builtin:")) {
    return {
      ...listing,
      builtin: listing.builtin.map((rule) =>
        rule.rule_id === ruleId ? { ...rule, overridden: overridden ?? true } : rule,
      ),
    };
  }
  const swap = (rule: RuleView) => (rule.rule_id === ruleId ? { ...rule, ...updated } : rule);
  return { ...listing, builtin: listing.builtin.map(swap), mine: listing.mine.map(swap) };
}

/** How many shipped rules to render before the reader asks for more. */
const BUILTIN_PAGE = 30;

/**
 * The rules the engine ships with.
 *
 * Nearly two hundred of them, which is why this is not a plain list. Rendering all
 * of them at once was visibly slow, and the reason is boring: each row carries a
 * badge, a generated sentence and a button, so the cost is in the node count rather
 * than in anything that can be optimised away. So the list renders a page at a time
 * and grows on request.
 *
 * The search box matters more than the paging. Nobody scrolls two hundred rules
 * looking for one; they know the header they care about. Filtering is on the same
 * normalised form the engine matches on, so what the box finds is what would fire.
 */
function BuiltinRules({
  rules,
  busy,
  onToggle,
}: {
  rules: RuleView[];
  busy: string | null;
  onToggle: (rule: RuleView) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [shown, setShown] = useState(BUILTIN_PAGE);
  const listRef = useRef<HTMLUListElement>(null);
  // The reader's own scroll position, tracked continuously.
  //
  // It cannot be read in the click handler: the browser scrolls this container to
  // the top before React's handler runs, so `scrollTop` there is already 0. That
  // cost three wrong fixes before the probe showed it, so the offset is captured as
  // the reader scrolls and a jump to 0 is never believed.
  const keptScroll = useRef(0);
  const restoring = useRef(false);

  // Disabling the button under the pointer takes focus off it, and the browser
  // answers by scrolling this container back to the top. The row updates in place
  // and the node is never remounted, so the only thing lost is the offset — which is
  // enough to make a correct in-place update feel like a page reload.
  //
  // Captured in the click handler rather than in an effect: by the time an effect
  // runs the browser has already scrolled, so there is nothing left to remember.
  // A layout effect, so the offset is put back in the same frame the browser
  // cleared it and the list never visibly jumps. `useEffect` runs after paint, which
  // showed as a flick to the top and back.
  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list || !restoring.current || keptScroll.current === 0) return;
    list.scrollTop = keptScroll.current;
    if (list.scrollTop === keptScroll.current) restoring.current = false;
  });

  const matching = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return rules;
    return rules.filter(
      (rule) =>
        rule.header.includes(normalizeHeader(needle)) ||
        rule.field_name.toLowerCase().includes(needle) ||
        rule.value.includes(normalizeHeader(needle)) ||
        rule.canonical.toLowerCase().includes(needle),
    );
  }, [rules, query]);

  const visible = matching.slice(0, shown);
  const disabledCount = rules.filter((rule) => rule.overridden).length;

  return (
    <section className="mt-7">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="eyebrow">Built in</h2>
        <span className="text-[12px] text-ink-subtle tnum">
          {disabledCount > 0 ? `${disabledCount} of ${rules.length} off` : rules.length}
        </span>
      </div>
      <p className="mt-1.5 max-w-[62ch] text-[13px] text-ink-muted">
        These come from the engine itself, so there is nothing to edit — but you can
        turn one off if it is wrong for your data. Headers that two fields both claim
        are deliberately absent: those are what make a column ambiguous, and a rule
        settling one would remove a question you want.
      </p>

      {!open ? (
        <Button variant="secondary" className="mt-3" onClick={() => setOpen(true)}>
          Show {rules.length} built-in rules
        </Button>
      ) : (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-2.5">
            <Input
              aria-label="Search built-in rules"
              placeholder="Search a header or field…"
              value={query}
              className="min-w-[16rem] flex-1"
              onChange={(event) => {
                setQuery(event.target.value);
                setShown(BUILTIN_PAGE);
              }}
            />
            <Button variant="quiet" onClick={() => setOpen(false)}>
              Hide
            </Button>
          </div>

          {matching.length === 0 ? (
            <p className="panel mt-2.5 px-5 py-6 text-center text-[13px] text-ink-muted">
              No built-in rule matches “{query.trim()}”. If your files use that
              spelling, it is exactly what a rule of your own is for.
            </p>
          ) : (
            <>
              {/* Height-capped and scrollable: `overflow-hidden` here previously
                  clipped the list instead of letting it scroll, so the rules past
                  the fold were unreachable. */}
              <ul
                ref={listRef}
                className="panel scroll-area mt-2.5 max-h-[28rem] divide-y divide-line"
                onScroll={(event) => {
                  const top = event.currentTarget.scrollTop;
                  // A jump to the very top during a toggle is the browser, not the
                  // reader: it happens because the focused button is disabled.
                  // Believing it is what loses the position.
                  if (restoring.current && top === 0) return;
                  keptScroll.current = top;
                }}
              >
                {visible.map((rule) => (
                  <li
                    key={rule.rule_id}
                    className="flex flex-wrap items-center gap-2.5 px-4 py-2.5"
                  >
                    <Badge tone="neutral">{KIND_LABEL[rule.kind]}</Badge>
                    <span
                      className={cn(
                        "min-w-0 flex-1 text-[13px]",
                        rule.overridden && "text-ink-subtle line-through",
                      )}
                    >
                      {describeRule(rule)}
                    </span>
                    {rule.overridden && <Badge tone="attention">Off</Badge>}
                    <Button
                      size="sm"
                      variant="quiet"
                      disabled={busy === rule.rule_id}
                      onClick={() => {
                        // Remembered here because the browser scrolls this
                        // container to the top the moment the button is disabled,
                        // and by then the real offset is gone.
                        restoring.current = true;
                        onToggle(rule);
                      }}
                    >
                      {busy === rule.rule_id
                        ? "Saving…"
                        : rule.overridden
                          ? "Turn back on"
                          : "Turn off"}
                    </Button>
                  </li>
                ))}
              </ul>

              {visible.length < matching.length && (
                <Button
                  variant="quiet"
                  className="mt-2.5"
                  onClick={() => setShown((current) => current + BUILTIN_PAGE)}
                >
                  Show {Math.min(BUILTIN_PAGE, matching.length - visible.length)} more
                  {query.trim() ? ` of ${matching.length} matching` : ` of ${rules.length}`}
                </Button>
              )}
            </>
          )}
        </>
      )}
    </section>
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
