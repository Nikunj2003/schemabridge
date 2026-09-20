/**
 * Turning engine state into something a consultant can act on.
 *
 * The API speaks in issue types, dispositions and field names. This module is
 * the only place that translates those into the questions and sentences the UI
 * shows, so the wording is consistent and testable — and so nothing invents a
 * fact the backend did not report.
 */
import type {
  Counters,
  Issue,
  IssueOption,
  MigrationRecord,
  Run,
  TargetField,
} from "./api";

export type StageId = "read" | "match" | "check" | "send" | "done";
export type StageState = "waiting" | "active" | "done" | "blocked";

export interface Stage {
  id: StageId;
  label: string;
  state: StageState;
  detail?: string;
}

const STAGE_LABELS: Record<StageId, string> = {
  read: "Read files",
  match: "Match columns",
  check: "Clean & check",
  send: "Send records",
  done: "Results",
};

const ORDER: StageId[] = ["read", "match", "check", "send", "done"];

/** Which stage the run's phase corresponds to. */
function reachedIndex(run: Run): number {
  switch (run.phase) {
    case "ingested":
      return 1;
    case "analyzing":
      return 1;
    case "review":
      return 2;
    case "ready":
      return 3;
    case "delivering":
      return 3;
    case "complete":
    case "complete_with_failures":
      return 4;
    case "blocked":
      return 2;
  }
}

function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

/**
 * The five steps, each carrying what actually happened.
 *
 * Detail lines come from counters, never from a guess: if the engine has not
 * reported a number yet, the line is absent rather than zero.
 */
export function stagesFor(run: Run): Stage[] {
  const c = run.counters;
  const reached = reachedIndex(run);
  const finished = run.phase === "complete" || run.phase === "complete_with_failures";
  const waitingOnPerson = run.counters.awaiting_review > 0 && run.paused;

  const detail: Partial<Record<StageId, string>> = {};
  if (c.source_rows > 0) {
    detail.read = `${plural(c.source_rows, "row")} from ${plural(run.files.length, "file")}`;
  }
  if (c.auto_mapped + c.escalated > 0) {
    detail.match = `${c.auto_mapped} of ${c.auto_mapped + c.escalated} columns matched automatically`;
  }
  if (c.repairs > 0 || c.merged > 0) {
    const parts: string[] = [];
    if (c.merged > 0) parts.push(`combined ${plural(c.merged, "duplicate row")}`);
    if (c.repairs > 0) parts.push(`tidied ${plural(c.repairs, "value")}`);
    detail.check = sentenceCase(parts.join(", "));
  }
  if (c.delivered + c.failed > 0) {
    detail.send = `${c.delivered} of ${c.delivered + c.failed + c.retrying} sent`;
  }
  if (finished) {
    detail.done = `${plural(c.delivered, "record")} in the destination`;
  }

  return ORDER.map((id, index) => {
    let state: StageState = "waiting";
    if (index < reached) state = "done";
    else if (index === reached) {
      if (finished) state = "done";
      else if (waitingOnPerson || run.phase === "blocked") state = "blocked";
      else state = "active";
    }
    // The question count belongs on the stage that is actually stopped, which is
    // wherever the run paused — not always the cleanup step.
    const line =
      state === "blocked" && waitingOnPerson
        ? `${plural(c.awaiting_review, "question")} for you`
        : detail[id];
    return { id, label: STAGE_LABELS[id], state, detail: line };
  });
}

function sentenceCase(text: string): string {
  return text.length === 0 ? text : text[0].toUpperCase() + text.slice(1);
}

/** One line for the header: what is happening, right now, in a sentence. */
export function headline(run: Run): string {
  const c = run.counters;
  if (run.phase === "blocked") return run.blocked_reason ?? "This migration cannot continue.";
  if (c.awaiting_review > 0) {
    return c.awaiting_review === 1
      ? "One question needs your judgment"
      : `${c.awaiting_review} questions need your judgment`;
  }
  switch (run.phase) {
    case "ingested":
      return `Reading ${plural(run.files.length, "file")}`;
    case "analyzing":
      return "Working out which column means what";
    case "review":
      return "Reviewing what was found";
    case "ready":
      return `Getting ready to send ${plural(c.records, "record")}`;
    case "delivering":
      return `Sending ${c.delivered + 1} of ${plural(c.records - c.excluded, "record")}`;
    case "complete":
      return `${plural(c.delivered, "record")} sent to the destination`;
    case "complete_with_failures":
      return `${plural(c.delivered, "record")} sent, ${c.failed + c.excluded} did not go`;
  }
}

/* ------------------------------------------------------------------ */
/* Questions                                                          */
/* ------------------------------------------------------------------ */

export interface SourceEvidence {
  label: string;
  /** Exactly as the client wrote it. */
  raw: string;
  /** The same value written out, where a format could be misread. */
  reading?: string;
}

export interface PresentedQuestion {
  id: string;
  /** The business question, naming the employee where there is one. */
  title: string;
  subject: string | null;
  why: string;
  fieldLabel: string | null;
  evidence: SourceEvidence[];
  options: IssueOption[];
  /** Whether choosing this option requires the person to type a value. */
  typedOption: string | null;
  affected: number;
}

/**
 * The question a person can answer, built from the issue the engine raised.
 *
 * The title is derived from the issue type and subject, because
 * "VALIDATION_FAILED_TWICE" tells a consultant nothing. Everything factual —
 * the values, the reason, the options — comes straight from the API.
 */
export function presentQuestion(
  issue: Issue,
  records: MigrationRecord[],
  fields: TargetField[] = [],
): PresentedQuestion {
  const ids = new Set(issue.record_ids);
  const affected = records.filter((record) => ids.has(record.id));
  const who = describeWho(affected, fields);
  const field = issue.field_label;

  return {
    id: issue.id,
    title: titleFor(issue, who, field),
    subject: subjectLine(issue, affected, fields),
    why: issue.reason,
    fieldLabel: field,
    evidence: evidenceFor(issue, affected),
    options: issue.options,
    typedOption: issue.options.find((o) => o.id === "correct_value")?.id ?? null,
    affected: Math.max(issue.affected, affected.length),
  };
}

/**
 * How to name a record to a person.
 *
 * A name field where the schema has one, else its identifier — "Asha Rao" is
 * what a consultant recognises, and "rec:e-1003" is not. Driven by the schema
 * rather than by a hardcoded `fullName`, so a contract with no such field still
 * names its records by something meaningful.
 */
function nameOf(record: MigrationRecord, fields: TargetField[]): string | null {
  const naming = fields.find((field) => field.kind === "person_name");
  const value = naming ? record.values[naming.name] : null;
  return value || record.employee_id || null;
}

function describeWho(records: MigrationRecord[], fields: TargetField[]): string | null {
  if (records.length === 0) return null;
  const name = nameOf(records[0], fields);
  if (!name) return null;
  return records.length > 1 ? `${name} and ${records.length - 1} more` : name;
}

/** The line under the question: who or what, and where it came from. */
function subjectLine(
  issue: Issue,
  records: MigrationRecord[],
  fields: TargetField[],
): string | null {
  if (issue.column) {
    return issue.column_file ? `“${issue.column}” in ${issue.column_file}` : `“${issue.column}”`;
  }
  const record = records[0];
  if (!record) return null;
  const parts = [nameOf(record, fields), record.employee_id].filter(Boolean);
  const head = parts.join(" · ");
  return record.sources.length > 0 ? `${head} · from ${record.sources.join(", ")}` : head || null;
}

function titleFor(issue: Issue, who: string | null, field: string | null): string {
  const lowerField = (field ?? "value").toLowerCase();
  switch (issue.type) {
    case "IDENTITY_CONFLICT":
      return who
        ? `Which ${lowerField} is right for ${who}?`
        : `Two files disagree about the ${lowerField}`;
    case "AMBIGUOUS_DATE":
      return who ? `What date does this mean for ${who}?` : "What does this date mean?";
    case "DUPLICATE_EMAIL":
      return "Are these the same person?";
    case "VALIDATION_FAILED_TWICE":
      return field
        ? `${who ? `${who}'s ` : ""}${field.toLowerCase()} cannot be used as it is`
        : "A value could not be fixed";
    case "AMBIGUOUS_MAPPING":
      return issue.column
        ? `What does the “${issue.column}” column mean?`
        : "What does this column mean?";
    case "COMPETING_COLUMNS":
      return `Which column holds the ${lowerField}?`;
    case "REQUIRED_FIELD_UNMAPPED":
      return `Nothing in your files looks like ${field ?? "a required field"}`;
    case "UNSAFE_CLEANUP":
      return `Should this ${lowerField} be changed?`;
    case "DELIVERY_FAILED":
      return who ? `${who} was rejected by the destination` : "A record was rejected";
  }
}

/**
 * The values the decision is actually about.
 *
 * Dates are written out alongside what the file said, because `03/04/2026`
 * having two honest readings is the whole reason the engine stopped.
 */
function evidenceFor(issue: Issue, records: MigrationRecord[]): SourceEvidence[] {
  // A choice between concrete values: show each one as its own card.
  const valued = issue.options.filter((option) => option.value !== null);
  if (valued.length > 1) {
    // The engine reports the competing values but not which file each came from,
    // so only claim a source when there is exactly one per source to claim.
    const sources = records[0]?.sources ?? [];
    const aligned = sources.length === valued.length;
    return valued.map((option, index) => ({
      label: aligned ? sources[index] : "In your files",
      raw: option.value as string,
      reading: readable(option.value as string),
    }));
  }

  // A column: show its header and a value from it, so the meaning is visible.
  if (issue.column) {
    return [
      {
        label: issue.column_file ? `From ${issue.column_file}` : "From your file",
        raw: issue.current_value ?? issue.column,
        reading: issue.current_value ? readable(issue.current_value) : undefined,
      },
    ];
  }

  if (issue.current_value) {
    const record = records[0];
    return [
      {
        label: record?.sources[0] ?? "In your file",
        raw: issue.current_value,
        reading: readable(issue.current_value),
      },
    ];
  }

  return [];
}

/** A second rendering, only when the raw form could be misread. */
function readable(value: string): string | undefined {
  if (isIsoDate(value)) return writeDate(value);
  if (/^\s|\s$|\s{2,}/.test(value)) return value.replace(/\s+/g, " ").trim();
  return undefined;
}

function isIsoDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

/** 2026-04-02 → 2 April 2026. Never abbreviated: 2 Apr can still be misread. */
export function writeDate(iso: string): string {
  if (!isIsoDate(iso)) return iso;
  const [year, month, day] = iso.split("-").map(Number);
  const months = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];
  return `${day} ${months[month - 1]} ${year}`;
}

/* ------------------------------------------------------------------ */
/* Results                                                            */
/* ------------------------------------------------------------------ */

/**
 * The arithmetic, spelled out.
 *
 * Row counts and record counts are different units, so they are reconciled in
 * a sentence rather than added into one total.
 */
export function reconcile(c: Counters): string {
  if (c.merged > 0) {
    return `${plural(c.source_rows, "row")} across your files became ${plural(
      c.records,
      "record",
    )} after combining ${plural(c.merged, "duplicate row")}.`;
  }
  return `${plural(c.source_rows, "row")} across your files became ${plural(c.records, "record")}.`;
}

export const RECORD_STATE: Record<
  MigrationRecord["disposition"],
  { label: string; tone: "ok" | "attention" | "problem" | "neutral" | "working" }
> = {
  delivered: { label: "Sent", tone: "ok" },
  failed: { label: "Rejected", tone: "problem" },
  excluded: { label: "Left out", tone: "neutral" },
  retry_wait: { label: "Retrying", tone: "working" },
  delivering: { label: "Sending", tone: "working" },
  needs_review: { label: "Needs you", tone: "attention" },
  ready: { label: "Ready", tone: "neutral" },
  candidate: { label: "Checking", tone: "neutral" },
};

/** Bytes as a person reads them. 271 bytes is not "0 KB". */
export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
