/**
 * Turning rule data into sentences, and checking a draft before it is sent.
 *
 * The same split as `lib/schema.ts`: the backend stays the authority on what a
 * valid rule is, and this is a faster copy of the same test so a person is told
 * about a missing field while they are still typing rather than after a round trip.
 *
 * Wording lives here rather than in the components because a rule is described in
 * three places — the list, the editor, and the proposal a run offers — and three
 * descriptions of one kind that drift apart is how a feature stops being trusted.
 */
import type { DateOrder, Rule, RuleInput, RuleKind, RuleOrigin } from "./api";

/** What each kind decides, in the second person. */
export const KIND_LABEL: Record<RuleKind, string> = {
  header_alias: "Column means field",
  value_alias: "Value spelling",
  date_order: "Date reading",
  column_ignore: "Skip column",
  override: "Built-in rule turned off",
};

export const KIND_HINT: Record<RuleKind, string> = {
  header_alias:
    "A column header that should map to a target field. Use this when your exports name a field something the engine does not recognise.",
  value_alias:
    "A spelling of a permitted value. Use this when a source writes a value one way and the schema expects another.",
  date_order:
    "Which number comes first in dates like 03/04/2026. Only applies where both readings are real, so it never overrides a date that is already unambiguous.",
  column_ignore: "A column that carries nothing worth migrating, so it is left out without asking.",
  override: "A built-in rule you have turned off for your own migrations.",
};

export const ORIGIN_LABEL: Record<RuleOrigin, string> = {
  builtin: "Built in",
  handwritten: "Yours",
  learned: "Learned",
  override: "Turned off",
};

export const DATE_ORDER_LABEL: Record<DateOrder, string> = {
  day_first: "Day first (03/04 is 3 April)",
  month_first: "Month first (03/04 is 4 March)",
};

/** Kinds a person can create. An override is made by toggling a built-in rule. */
export const CREATABLE_KINDS: RuleKind[] = [
  "header_alias",
  "value_alias",
  "date_order",
  "column_ignore",
];

/**
 * One line saying what a rule does, with its own values in it.
 *
 * Built from the rule's fields rather than from a stored sentence, so a rule
 * cannot display one thing and do another.
 */
export function describeRule(rule: Rule, fieldLabel?: (name: string) => string): string {
  const label = (name: string) => fieldLabel?.(name) ?? name;
  switch (rule.kind) {
    case "header_alias":
      return `A column named “${rule.header}” is ${label(rule.field_name)}.`;
    case "value_alias":
      return `In ${label(rule.field_name)}, “${rule.value}” means “${rule.canonical}”.`;
    case "date_order":
      return rule.header
        ? `Dates in the “${rule.header}” column are ${rule.date_order === "day_first" ? "day first" : "month first"}.`
        : `Dates for ${label(rule.field_name)} are ${rule.date_order === "day_first" ? "day first" : "month first"}.`;
    case "column_ignore":
      return `A column named “${rule.header}” is left out of migrations.`;
    case "override":
      return "A built-in rule is turned off for your migrations.";
  }
}

export interface DraftProblems {
  /** Keyed by the input's own name, so the message sits on the field at fault. */
  fields: Record<string, string>;
  /** A problem with the rule as a whole. */
  rule: string | null;
}

export function isValid(problems: DraftProblems): boolean {
  return problems.rule === null && Object.keys(problems.fields).length === 0;
}

/**
 * Whether a draft carries what its kind needs.
 *
 * Mirrors the backend's own shape validator. Deliberately not a second opinion
 * about anything else: whether a field exists, whether a value belongs to an
 * enum, and whether a header is ambiguous are all judged server-side against the
 * schema, because only the server knows which schema a rule will run against.
 */
export function validateDraft(draft: RuleInput): DraftProblems {
  const fields: Record<string, string> = {};

  switch (draft.kind) {
    case "header_alias":
      if (!draft.header?.trim()) fields.header = "Name the column header this applies to.";
      if (!draft.field_name?.trim()) fields.field_name = "Choose the target field it means.";
      break;
    case "value_alias":
      if (!draft.field_name?.trim()) fields.field_name = "Choose the field this value belongs to.";
      if (!draft.value?.trim()) fields.value = "Give the spelling as the source writes it.";
      if (!draft.canonical?.trim()) fields.canonical = "Choose the value it should become.";
      break;
    case "date_order":
      if (!draft.date_order) fields.date_order = "Choose which number comes first.";
      if (!draft.header?.trim() && !draft.field_name?.trim()) {
        fields.header = "Name a column, or choose a field, for this to apply to.";
      }
      break;
    case "column_ignore":
      if (!draft.header?.trim()) fields.header = "Name the column header to leave out.";
      break;
    case "override":
      break;
  }

  return { fields, rule: null };
}

/**
 * The comparison key the backend stores, so the page previews what will match.
 *
 * Kept identical to `normalize_header` in the engine. A page that showed an
 * un-normalised header would promise a match the engine does not make.
 */
export function normalizeHeader(header: string): string {
  return header
    .replace(/﻿/g, "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}
