import { Badge, type Tone } from "@/components/ui/status";
import { Button } from "@/components/ui/button";
import type { Run, TargetField } from "@/lib/api";
import { RECORD_STATE, reconcile, writeDate } from "@/lib/present";
import { displayFields } from "@/lib/schema";

/**
 * What ended up where.
 *
 * The columns come from the run's own schema rather than being written into the
 * markup, so a migration onto a contract that has nothing to do with employment
 * does not render a "Work email" column it has no values for. The headline says
 * "records" for the same reason.
 */
export function Results({ run }: { run: Run }) {
  const c = run.counters;
  const failed = run.records.filter((r) => r.disposition === "failed");

  // Six is where a table stops being scannable and starts being a spreadsheet;
  // the full values are always in the audit trail.
  const columns = displayFields(run.schema_fields).slice(0, 6);
  const identity = run.schema_fields.find((field) => field.is_identity);
  // Whatever best names a record to a person: a name field if the schema has
  // one, else its identifier.
  const naming = run.schema_fields.find((field) => field.kind === "person_name") ?? identity;

  return (
    <div className="space-y-5">
      <section className="panel px-5 py-5 sm:px-6">
        <h2 className="font-display text-[20px]">
          {c.delivered} of {c.records} records reached the destination
        </h2>
        <p className="mt-1.5 text-[14px] text-ink-muted">{reconcile(c)}</p>

        <dl className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Tally label="Sent" value={c.delivered} tone="ok" />
          <Tally label="Rejected" value={c.failed} tone={c.failed > 0 ? "problem" : "neutral"} />
          <Tally label="Left out" value={c.excluded} tone="neutral" />
          <Tally
            label="Retrying"
            value={c.retrying}
            tone={c.retrying > 0 ? "working" : "neutral"}
          />
        </dl>
      </section>

      {failed.length > 0 && (
        <section className="panel overflow-hidden">
          <div className="border-b border-line bg-problem-soft px-5 py-3">
            <h3 className="text-[14px] font-semibold text-problem">
              {failed.length === 1
                ? "One record needs attention"
                : `${failed.length} records need attention`}
            </h3>
            <p className="mt-0.5 text-[13px] text-ink-muted">
              The destination refused these. Its own reason is shown.
            </p>
          </div>
          <ul className="divide-y divide-line">
            {failed.map((record) => (
              <li key={record.id} className="px-5 py-3.5">
                <p className="text-[14px] font-medium">
                  {(naming ? record.values[naming.name] : null) ?? record.id}
                  {record.employee_id && (
                    <span className="raw ml-2 text-[12.5px] font-normal text-ink-muted">
                      {record.employee_id}
                    </span>
                  )}
                </p>
                {record.errors.map((message) => (
                  <p key={message} className="mt-1 text-[13px] text-problem">
                    {message}
                  </p>
                ))}
                <p className="mt-1 text-[12.5px] text-ink-subtle">
                  From {record.sources.join(", ")}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="panel overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3">
          <h3 className="text-[14px] font-semibold">Every record</h3>
          <span className="text-[12.5px] text-ink-subtle">mapped onto {run.schema_name}</span>
          <Button size="sm" className="ml-auto" disabled>
            Download cleaned data
          </Button>
        </div>

        {/* Only the table scrolls sideways, and it says so to a screen reader. */}
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Migrated records">
          <table className="w-full min-w-[46rem] border-collapse text-left">
            <thead>
              <tr className="border-b border-line text-[12px] text-ink-subtle">
                {columns.map((field) => (
                  <Th key={field.name}>{field.label}</Th>
                ))}
                <Th>Result</Th>
              </tr>
            </thead>
            <tbody>
              {run.records.map((record) => {
                const state = RECORD_STATE[record.disposition];
                return (
                  <tr key={record.id} className="border-b border-line last:border-0">
                    {columns.map((field) => (
                      <Td key={field.name} className={raw(field) ? "raw" : ""}>
                        {show(record.values[field.name], field)}
                      </Td>
                    ))}
                    <Td>
                      <Badge tone={state.tone}>{state.label}</Badge>
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

/** Codes and addresses are read character by character, so they get tabular type. */
function raw(field: TargetField): boolean {
  return field.kind === "identifier" || field.kind === "email";
}

function show(value: string | null | undefined, field: TargetField): string {
  if (value === null || value === undefined || value === "") return "—";
  // Dates are stored ISO and read badly that way.
  return field.kind === "date" ? writeDate(value) : value;
}

function Tally({ label, value, tone }: { label: string; value: number; tone: Tone }) {
  const colour =
    tone === "ok"
      ? "text-ok"
      : tone === "problem"
        ? "text-problem"
        : tone === "working"
          ? "text-accent"
          : "text-ink";
  return (
    <div className="rounded-md bg-sunken px-3.5 py-3">
      <dt className="text-[12.5px] text-ink-muted">{label}</dt>
      <dd className={`mt-0.5 font-display text-[22px] tnum ${colour}`}>{value}</dd>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th scope="col" className="px-5 py-2.5 font-medium">
      {children}
    </th>
  );
}

function Td({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <td className={`px-5 py-3 text-[13.5px] ${className}`}>{children}</td>;
}
