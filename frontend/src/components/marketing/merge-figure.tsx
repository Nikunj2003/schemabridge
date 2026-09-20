/**
 * The product's claim, drawn.
 *
 * Two rows that disagree becoming one clean record, with the disagreement the
 * agent refused to guess at left visible. Real values from the sample fixtures,
 * so the illustration is not making a promise the engine does not keep.
 */
export function MergeFigure() {
  return (
    <figure className="merge-figure panel overflow-hidden">
      <figcaption className="flex items-center justify-between gap-4 border-b border-line bg-sunken px-4 py-3">
        <span className="text-[13px] font-medium text-ink">Two exports, one employee</span>
        <span className="text-[11px] text-ink-subtle">Before review</span>
      </figcaption>

      <div className="space-y-3.5 px-4 py-4 sm:px-5 sm:py-5">
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

        <div className="merge-figure-bridge flex items-center gap-2.5 py-1 text-[12.5px] leading-snug text-ink-muted">
          <svg viewBox="0 0 24 24" className="size-4 shrink-0 text-accent" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
            <path d="M12 4v15M7 14l5 5 5-5" />
          </svg>
          Name tidied, columns matched, start dates left for review.
        </div>

        <div className="rounded-md border border-line bg-sunken px-4 py-3.5">
          <p className="text-[11px] font-medium text-ink-subtle">Ready to send</p>
          <div className="mt-2 flex flex-wrap gap-x-7 gap-y-2">
            <Field label="Employee ID" value="E-1003" />
            <Field label="Full name" value="Asha Rao" />
          </div>
          <div className="mt-3.5 rounded-md border border-attention/35 bg-attention-soft px-3 py-2.5">
            <p className="text-[12px] font-semibold text-attention">Start date needs a decision</p>
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
    <div className="rounded-md border border-line bg-surface px-3.5 py-3">
      <p className="text-[11.5px] text-ink-subtle">{file}</p>
      <div className="mt-2 flex flex-wrap gap-x-5 gap-y-2">
        {cells.map(([header, value]) => (
          <div key={header}>
            <p className="raw text-[10.5px] text-ink-subtle">{header}</p>
            <p className="raw text-[12.5px] whitespace-pre text-ink">{value}</p>
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
