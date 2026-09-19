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

export interface ActivityEvent {
  seq: number;
  at: string;
  actor: "agent" | "reviewer" | "system";
  action: string;
  reason: string;
  subject: string | null;
  before: string | null;
  after: string | null;
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
  counters: Counters;
  mappings: Mapping[];
  issues: Issue[];
  records: MigrationRecord[];
  events: ActivityEvent[];
  latest_seq: number;
  blocked_reason: string | null;
}

export interface TargetField {
  name: string;
  label: string;
  description: string;
  required: boolean;
  kind: string;
  allowed_values: string[];
}

export interface SchemaInfo {
  fields: TargetField[];
  limits: Record<string, number>;
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

  usage: () => request<{ used: number; limit: number }>("/api/usage"),

  createRun: (files: File[]) => {
    const body = new FormData();
    for (const file of files) body.append("files", file);
    return request<Run>("/api/runs", { method: "POST", body });
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
