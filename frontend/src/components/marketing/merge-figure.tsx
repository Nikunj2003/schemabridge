/**
 * The product's claim, drawn.
 *
 * Two rows that disagree becoming one clean record, with the disagreement the
 * agent refused to guess at left visible. Real values from the sample fixtures,
 * so the illustration is not making a promise the engine does not keep.
 */
export function MergeFigure() {
  return (
    <figure className="panel overflow-hidden">
      <figcaption className="border-b border-line bg-sunken px-4 py-2.5 text-[12.5px] text-ink-muted">
        Two exports, one employee
      </figcaption>

      <div className="space-y-3 px-4 py-4">
        <Row
          file="employees-legacy.csv"
          cells={[
            ["emp_id", "E-1003"],
            ["emp_nm", "  Asha  Rao "],
            ["doj", "2 April 2026"],
          ]}
        />
        <Row
          file="employees-hr-export.csv"
          cells={[
            ["Employee Code", "E-1003"],
            ["Name", "Asha Rao"],
            ["Joining Date", "2024-11-30"],
          ]}
        />

        <div className="flex items-center gap-2 pt-1 text-[12.5px] text-ink-muted">
          <svg viewBox="0 0 24 24" className="size-4 shrink-0 text-accent" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
            <path d="M12 5v14M7 14l5 5 5-5" />
          </svg>
          Same person. Name tidied, columns matched, start dates in conflict.
        </div>

        <div className="rounded-md border border-line bg-sunken px-4 py-3">
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            <Field label="Employee ID" value="E-1003" />
            <Field label="Full name" value="Asha Rao" />
          </div>
          <div className="mt-3 rounded-md border border-attention/35 bg-attention-soft px-3 py-2.5">
            <p className="text-[12px] font-semibold text-attention">Start date — asked, not guessed</p>
            <p className="mt-0.5 text-[13px] text-ink">
              2 April 2026 or 30 November 2024?
            </p>
          </div>
        </div>
      </div>
    </figure>
  );
}

function Row({ file, cells }: { file: string; cells: [string, string][] }) {
  return (
    <div className="rounded-md border border-line px-3.5 py-2.5">
      <p className="text-[11.5px] text-ink-subtle">{file}</p>
      <div className="mt-1.5 flex flex-wrap gap-x-5 gap-y-1.5">
        {cells.map(([header, value]) => (
          <div key={header}>
            <p className="raw text-[11px] text-ink-subtle">{header}</p>
            <p className="raw text-[13px] whitespace-pre">{value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11.5px] text-ink-subtle">{label}</p>
      <p className="text-[13.5px] font-medium">{value}</p>
    </div>
  );
}
