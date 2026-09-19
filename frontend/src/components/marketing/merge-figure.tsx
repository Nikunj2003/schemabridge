/**
 * The hero figure: two disagreeing source rows becoming one clean record, with
 * the one decision a person has to make left visible.
 *
 * This is the product in a picture. It is a static illustration, labelled as an
 * example — not a live run and not an invented metric.
 */
export function MergeFigure() {
  return (
    <figure className="card overflow-hidden">
      <figcaption className="flex items-center justify-between border-b border-line px-4 py-2.5 text-[12.5px] text-ink-muted">
        <span>An example, not a live migration</span>
        <span className="raw">2 files → 1 employee</span>
      </figcaption>

      <div className="space-y-3 p-4">
        <SourceRow
          file="employees-legacy.csv"
          cells={[
            ["emp_id", "E-1003"],
            ["emp_nm", "  Asha Rao "],
            ["doj", "2 April 2026"],
          ]}
        />
        <SourceRow
          file="employees-hr-export.csv"
          cells={[
            ["Employee Number", "E-1003"],
            ["Full Name", "Asha Rao"],
            ["Joining Date", "2024-11-30"],
          ]}
        />

        <div className="flex items-center gap-2 pl-1 text-[13px] text-ink-muted">
          <svg viewBox="0 0 16 16" className="size-4 shrink-0 text-accent" aria-hidden>
            <path d="M8 2v12M4 10l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
          Same person, two spellings, two different start dates
        </div>

        <div className="rounded-lg border border-accent/30 bg-accent-soft p-4">
          <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
            <Resolved label="Employee ID" value="E-1003" note="kept as written" />
            <Resolved label="Full name" value="Asha Rao" note="spaces trimmed" />
            <Resolved label="Work email" value="asha.rao@example.com" note="domain lowercased" />
            <div>
              <p className="text-[12.5px] text-accent-ink/80">Start date</p>
              <p className="mt-0.5 flex items-center gap-2 text-[14px] font-medium">
                <span className="text-attention">Needs your answer</span>
              </p>
              <p className="mt-0.5 text-[12.5px] text-ink-muted">
                2 April 2026 or 30 November 2024?
              </p>
            </div>
          </div>
        </div>
      </div>
    </figure>
  );
}

function SourceRow({ file, cells }: { file: string; cells: [string, string][] }) {
  return (
    <div className="rounded-lg border border-line bg-sunken px-3 py-2.5">
      <p className="text-[12px] text-ink-subtle">{file}</p>
      <div className="mt-1.5 flex flex-wrap gap-x-5 gap-y-1">
        {cells.map(([header, value]) => (
          <span key={header} className="text-[13px]">
            <span className="text-ink-subtle">{header}</span>{" "}
            <span className="raw text-ink">{value}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function Resolved({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div>
      <p className="text-[12.5px] text-accent-ink/80">{label}</p>
      <p className="mt-0.5 text-[14px] font-medium">{value}</p>
      <p className="mt-0.5 text-[12.5px] text-ink-muted">{note}</p>
    </div>
  );
}
