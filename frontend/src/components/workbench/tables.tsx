/**
 * The three record-keeping views: what the data became, where it went, and why.
 *
 * "See a clear record of everything it did" is a different job from resolving a
 * queue, so these live behind their own tabs rather than competing for the same
 * space.
 */
"use client";

import type { ActivityEvent, Mapping, MigrationRecord, TargetField } from "@/lib/api";
import { Pill, type Tone } from "@/components/ui/status";
import { cn } from "@/lib/utils";

const DISPOSITION_TONE: Record<MigrationRecord["disposition"], Tone> = {
  candidate: "neutral",
  needs_review: "warn",
  ready: "working",
  excluded: "neutral",
  delivering: "working",
  delivered: "good",
  retry_wait: "warn",
  failed: "bad",
};

const DISPOSITION_LABEL: Record<MigrationRecord["disposition"], string> = {
  candidate: "Pending",
  needs_review: "Needs you",
  ready: "Ready",
  excluded: "Left out",
  delivering: "Sending",
  delivered: "Delivered",
  retry_wait: "Retrying",
  failed: "Failed",
};

const BASIS_LABEL: Record<Mapping["basis"], string> = {
  exact_name: "Name matched",
  alias: "Known spelling",
  model_assisted: "Model suggested, checked",
  human_correction: "You chose",
  unmapped: "Not mapped",
};

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <th
      scope="col"
      className={cn(
        "sticky top-0 z-10 bg-card px-3 py-2 text-left text-[11px] font-semibold",
        "border-b border-border text-muted-foreground",
        className,
      )}
    >
      {children}
    </th>
  );
}

/** How each source column was interpreted, and on what grounds. */
export function Mappings({ mappings }: { mappings: Mapping[] }) {
  if (mappings.length === 0) {
    return <Empty>No columns read yet.</Empty>;
  }
  return (
    <div className="overflow-auto">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr>
            <Th>Source column</Th>
            <Th>File</Th>
            <Th>Becomes</Th>
            <Th>Why</Th>
          </tr>
        </thead>
        <tbody>
          {mappings.map((mapping) => (
            <tr key={`${mapping.file}:${mapping.column}`} className="border-b border-border/60">
              <td className="px-3 py-2 font-mono text-[12px]">{mapping.column}</td>
              <td className="px-3 py-2 text-muted-foreground">{mapping.file}</td>
              <td className="px-3 py-2">
                {mapping.target_label ? (
                  <span className="font-medium">{mapping.target_label}</span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </td>
              <td className="px-3 py-2 text-muted-foreground">
                {BASIS_LABEL[mapping.basis]}
                {mapping.evidence[0] && (
                  <span className="block text-[11px] opacity-80">{mapping.evidence[0]}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The unified dataset, with where each record came from. */
export function Records({
  records,
  fields,
}: {
  records: MigrationRecord[];
  fields: TargetField[];
}) {
  if (records.length === 0) {
    return <Empty>No records yet.</Empty>;
  }
  return (
    <div className="overflow-auto">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr>
            <Th>Status</Th>
            {fields.map((field) => (
              <Th key={field.name}>{field.label}</Th>
            ))}
            <Th>From</Th>
          </tr>
        </thead>
        <tbody>
          {records.map((record) => (
            <tr key={record.id} className="border-b border-border/60 align-top">
              <td className="px-3 py-2">
                <Pill tone={DISPOSITION_TONE[record.disposition]}>
                  {DISPOSITION_LABEL[record.disposition]}
                </Pill>
              </td>
              {fields.map((field) => (
                <td key={field.name} className="px-3 py-2">
                  {record.values[field.name] ?? (
                    <span className="text-muted-foreground/50">—</span>
                  )}
                </td>
              ))}
              <td className="px-3 py-2 text-[11px] text-muted-foreground">
                {/* Provenance: two sources here means the rows were merged. */}
                {record.sources.map((source) => (
                  <span key={source} className="block whitespace-nowrap">
                    {source}
                  </span>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Per-record delivery outcomes, as criterion 5 requires. */
export function Delivery({ records }: { records: MigrationRecord[] }) {
  const attempted = records.filter((record) =>
    ["delivered", "failed", "retry_wait", "delivering"].includes(record.disposition),
  );
  if (attempted.length === 0) {
    return <Empty>Nothing has been sent to the destination yet.</Empty>;
  }
  return (
    <div className="overflow-auto">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr>
            <Th>Employee</Th>
            <Th>Result</Th>
            <Th>Destination ID</Th>
            <Th>Detail</Th>
          </tr>
        </thead>
        <tbody>
          {attempted.map((record) => (
            <tr key={record.id} className="border-b border-border/60">
              <td className="px-3 py-2 font-mono text-[12px]">
                {record.employee_id ?? record.id}
              </td>
              <td className="px-3 py-2">
                <Pill tone={DISPOSITION_TONE[record.disposition]}>
                  {DISPOSITION_LABEL[record.disposition]}
                </Pill>
              </td>
              <td className="px-3 py-2 font-mono text-[11.5px] text-muted-foreground">
                {record.target_id ?? "—"}
              </td>
              <td className="px-3 py-2 text-[11.5px] text-muted-foreground">
                {record.errors[0] ?? record.exclusion_reason ?? ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Everything that happened, in order, with who did it and why. */
export function Audit({ events }: { events: ActivityEvent[] }) {
  if (events.length === 0) {
    return <Empty>Nothing recorded yet.</Empty>;
  }
  return (
    <div className="overflow-auto">
      <table className="w-full border-collapse text-[12.5px]">
        <thead>
          <tr>
            <Th className="w-16">Time</Th>
            <Th className="w-20">Who</Th>
            <Th>What</Th>
            <Th>Why</Th>
            <Th>Change</Th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <tr key={event.seq} className="border-b border-border/60 align-top">
              <td className="px-3 py-1.5 font-mono text-[11px] text-muted-foreground">
                {new Date(event.at).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                })}
              </td>
              <td className="px-3 py-1.5">
                <span
                  className={cn(
                    "text-[11px]",
                    event.actor === "reviewer" ? "text-primary" : "text-muted-foreground",
                  )}
                >
                  {event.actor === "reviewer" ? "You" : event.actor === "agent" ? "Agent" : "System"}
                </span>
              </td>
              <td className="px-3 py-1.5">
                <span className="font-medium">{event.action.replace(/_/g, " ")}</span>
                {event.subject && (
                  <span className="text-muted-foreground"> · {event.subject}</span>
                )}
              </td>
              <td className="px-3 py-1.5 text-muted-foreground">{event.reason}</td>
              <td className="px-3 py-1.5 font-mono text-[11px]">
                {event.before !== null && event.after !== null ? (
                  <>
                    <span className="text-muted-foreground line-through">{event.before}</span>
                    {" → "}
                    <span>{event.after}</span>
                  </>
                ) : (
                  <span className="text-muted-foreground/50">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="px-4 py-8 text-center text-[12.5px] text-muted-foreground">{children}</p>;
}
