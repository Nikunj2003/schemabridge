/**
 * The migration API, as the browser sees it.
 *
 * Types are written by hand rather than generated, so the shape the UI depends
 * on is explicit and a backend change that breaks it fails at compile time.
 */

export type RunPhase =
  | "ingested"
  | "analyzing"
  | "review"
  | "ready"
  | "delivering"
  | "complete"
  | "complete_with_failures"
  | "blocked";

export type Disposition =
  | "candidate"
  | "needs_review"
  | "ready"
  | "excluded"
  | "delivering"
  | "delivered"
  | "retry_wait"
  | "failed";

export type IssueType =
  | "AMBIGUOUS_MAPPING"
  | "COMPETING_COLUMNS"
  | "REQUIRED_FIELD_UNMAPPED"
  | "AMBIGUOUS_DATE"
  | "IDENTITY_CONFLICT"
  | "DUPLICATE_EMAIL"
  | "VALIDATION_FAILED_TWICE"
  | "UNSAFE_CLEANUP"
  | "DELIVERY_FAILED";

export interface IssueOption {
  id: string;
  label: string;
  detail: string;
  target: string | null;
  value: string | null;
}

export interface Resolution {
  action: "approve" | "correct" | "reject" | "exclude";
  option_id: string | null;
  value: string | null;
  note: string | null;
  at: string;
}

export interface Issue {
  id: string;
  type: IssueType;
  status: "open" | "resolved";
  reason: string;
  blocking: boolean;
  field: string | null;
  field_label: string | null;
  current_value: string | null;
  affected: number;
  /** Which records this issue is about, so the UI can name the employee. */
  record_ids: string[];
  /** The source column's own header, for issues raised about a column. */
  column: string | null;
  column_file: string | null;
  options: IssueOption[];
  errors: string[];
  resolution: Resolution | null;
}

export interface Mapping {
  column: string;
  file: string;
  target: string | null;
  target_label: string | null;
  outcome: "auto_mapped" | "escalated" | "excluded";
  basis: "exact_name" | "alias" | "model_assisted" | "human_correction" | "unmapped";
  evidence: string[];
  decided_by: "agent" | "reviewer" | "system";
}

export interface MigrationRecord {
  id: string;
  employee_id: string | null;
  values: Record<string, string | null>;
  disposition: Disposition;
  sources: string[];
  repairs: number;
  valid: boolean;
  errors: string[];
  exclusion_reason: string | null;
  target_id: string | null;
}

export type ExecutionBasis = "deterministic" | "model_assisted" | "human" | "unknown";

export interface ActivityEvent {
  seq: number;
  at: string;
  actor: "agent" | "reviewer" | "system";
  execution_basis: ExecutionBasis;
  action: string;
  reason: string;
  subject: string | null;
  before: string | null;
  after: string | null;
}

export interface MigrationUsage {
  used: number;
  limit: number;
  reset_at: string;
  scope: "anonymous_browser_session";
}

export interface Counters {
  source_rows: number;
  records: number;
  merged: number;
  auto_mapped: number;
  escalated: number;
  repairs: number;
  model_requests: number;
  delivered: number;
  failed: number;
  excluded: number;
  retrying: number;
  awaiting_review: number;
}

export interface Run {
  run_id: string;
  phase: RunPhase;
  phase_label: string;
  paused: boolean;
  runnable: boolean;
  active: boolean;
  files: string[];
  /** Which contract this run was validated against. */
  schema_name: string;
  schema_id: string;
  /** Its fields, so the record tables show the columns this run actually has. */
  schema_fields: TargetField[];
  counters: Counters;
  mappings: Mapping[];
  issues: Issue[];
  records: MigrationRecord[];
  events: ActivityEvent[];
  latest_seq: number;
  blocked_reason: string | null;
}

/** The six semantic kinds. Closed, because every cleanup rule keys off one. */
export type ValueKind = "identifier" | "person_name" | "email" | "date" | "text" | "enum";

export interface TargetField {
  name: string;
  label: string;
  description: string;
  required: boolean;
  kind: ValueKind;
  /** Keys the record on this field, so two files can describe one record. */
  is_identity: boolean;
  /** Two records sharing this value is worth a person's attention. */
  is_unique: boolean;
  allowed_values: string[];
  /**
   * Spellings accepted for each permitted value, so "Permanent" and "full-time"
   * can both canonicalise onto one member. Unlisted spellings escalate rather
   * than being guessed at.
   */
  value_aliases: Record<string, string>;
  /**
   * Header spellings that will match this field, derived by the backend.
   * Read-only: seeing that "doj" matches is what tells someone their export
   * will work without them having to try it.
   */
  spellings: string[];
  /** Names the field this one must not precede, for a date pair. */
  not_before?: string | null;
}

export interface TargetSchema {
  schema_id: string;
  name: string;
  description: string;
  version: number;
  /** The shipped template: usable as a starting point, not editable in place. */
  builtin: boolean;
  fields: TargetField[];
  updated_at?: string;
}

export interface SchemaInfo extends TargetSchema {
  limits: Record<string, number>;
}

/** A schema read from a spec, plus what the import had to infer. */
export interface ImportedSchema extends TargetSchema {
  /**
   * Things guessed rather than stated — JSON Schema cannot say which field
   * identifies a record. Shown to the user instead of being folded in silently.
   */
  assumptions: string[];
}

export interface SchemaListing {
  builtin: TargetSchema;
  schemas: TargetSchema[];
  limits: { max_fields: number; max_schemas: number };
}

/** A field as the builder submits it. Derived spellings are never sent back. */
export interface FieldInput {
  name: string;
  label: string;
  description: string;
  required: boolean;
  kind: ValueKind;
  is_identity: boolean;
  is_unique: boolean;
  enum_values: string[];
  value_aliases: Record<string, string>;
  not_before: string | null;
}

export interface SchemaInput {
  name: string;
  description: string;
  fields: FieldInput[];
  /** The version the editor read, so a concurrent save is refused not lost. */
  if_version?: number;
}

/** A decision the reviewer has made about one escalation. */
export interface Decision {
  action: "approve" | "correct" | "reject" | "exclude";
  option_id?: string | null;
  value?: string | null;
  note?: string | null;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Pull a usable message out of an error response. */
async function describeError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (detail?.message) return String(detail.message);
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  } catch {
    // Fall through to a status-based message.
  }
  if (response.status === 429) return "Too many migrations started today. Try again tomorrow.";
  if (response.status === 503) return "A required service is unavailable.";
  return `The request failed (${response.status}).`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    // Sessions live in an HttpOnly cookie, so it has to travel with the request.
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw new ApiError(await describeError(response), response.status);
  }
  return (await response.json()) as T;
}

export const api = {
  schema: () => request<SchemaInfo>("/api/schema"),

  /** Shared infrastructure model budget, not a visitor's migration allowance. */
  usage: () => request<{ used: number; limit: number }>("/api/usage"),

  /** Migration starts available to this anonymous browser session today. */
  migrationUsage: () => request<MigrationUsage>("/api/migration-usage"),

  /**
   * Start a migration.
   *
   * `schemaId` picks the contract: a saved schema's id, "detected" to derive one
   * from the uploaded headers, or omitted for the built-in template.
   * `schemaSpec` supplies a JSON or YAML spec inline, used for this run only.
   */
  createRun: (files: File[], schemaId?: string, schemaSpec?: string) => {
    const body = new FormData();
    for (const file of files) body.append("files", file);
    if (schemaId) body.append("schema_id", schemaId);
    if (schemaSpec) body.append("schema_spec", schemaSpec);
    return request<Run>("/api/runs", { method: "POST", body });
  },

  schemas: {
    list: () => request<SchemaListing>("/api/schemas"),

    read: (schemaId: string) => request<TargetSchema>(`/api/schemas/${schemaId}`),

    create: (schema: SchemaInput) =>
      request<TargetSchema>("/api/schemas", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(schema),
      }),

    /** Save changes. `if_version` must be the version the editor last read. */
    update: (schemaId: string, schema: SchemaInput) =>
      request<TargetSchema>(`/api/schemas/${schemaId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(schema),
      }),

    /**
     * Read a JSON or YAML spec into a schema without saving it.
     *
     * Not saved on purpose: the import may have had to guess an identity field,
     * so the result opens in the builder for review first.
     */
    importFile: (file: File) => {
      const body = new FormData();
      body.append("file", file);
      return request<ImportedSchema>("/api/schemas/import", { method: "POST", body });
    },

    importText: (text: string, name?: string) =>
      request<ImportedSchema>("/api/schemas/import/text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, name: name ?? null }),
      }),

    /** Where to download a schema as a YAML spec. */
    specUrl: (schemaId: string) => `/api/schemas/${schemaId}/spec`,

    remove: async (schemaId: string) => {
      const response = await fetch(`/api/schemas/${schemaId}`, {
        method: "DELETE",
        credentials: "same-origin",
      });
      // 204 carries no body, so this one cannot go through `request`.
      if (!response.ok) throw new ApiError(await describeError(response), response.status);
    },
  },

  /** Read state. Safe to poll; never changes anything. */
  readRun: (runId: string, since = 0) =>
    request<Run>(`/api/runs/${runId}?since=${since}`),

  /** Do the next piece of work. */
  advance: (runId: string) =>
    request<Run>(`/api/runs/${runId}/advance`, { method: "POST" }),

  /** Apply the reviewer's decisions and carry on. */
  resolve: (runId: string, decisions: Record<string, Decision>) =>
    request<Run>(`/api/runs/${runId}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(decisions),
    }),

  listRuns: () =>
    request<{ runs: { run_id: string; created_at: string; files: string[]; source_rows: number }[] }>(
      "/api/runs",
    ),
};
