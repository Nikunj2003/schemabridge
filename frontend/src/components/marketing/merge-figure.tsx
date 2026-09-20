/**
 * The product's claim, drawn.
 *
 * Two rows that disagree becoming one clean record, with the disagreement the
 * agent refused to guess at left visible. Real values from the sample fixtures,
 * so the illustration is not making a promise the engine does not keep.
 *
 * The two source rows share one column grid. That is the whole point of the
 * figure — the reader is comparing the same three fields under different names,
 * and independently sized cells made that comparison impossible to see.
 */
export function MergeFigure() {
  return (
    <figure className="merge-figure panel overflow-hidden">
      <figcaption className="flex items-center justify-between gap-4 border-b border-line bg-sunken px-4 py-2.5 sm:px-5">
        <span className="text-[12.5px] font-medium text-ink">Two exports, one employee</span>
        <span className="text-[11px] text-ink-subtle">Before review</span>
      </figcaption>

      <div className="px-4 py-4 sm:px-5">
        <div className="space-y-2">
          <SourceRow
            file="employees-legacy.csv"
            cells={[
              { header: "emp_id", value: "E-1003" },
              { header: "emp_nm", value: "  Asha  Rao ", messy: true },
              { header: "doj", value: "2 April 2026" },
            ]}
          />
          <SourceRow
            file="employees-hr-export.csv"
            cells={[
              { header: "Employee Code", value: "E-1003" },
              { header: "Name", value: "Asha Rao" },
              { header: "Joining Date", value: "2024-11-30" },
            ]}
          />
        </div>

        <p className="flex items-center gap-2 py-3 text-[12px] leading-snug text-ink-muted">
          <svg viewBox="0 0 24 24" className="size-3.5 shrink-0 text-accent" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M12 5v14M6 13l6 6 6-6" />
          </svg>
          Name tidied, columns matched, start dates left for review.
        </p>

        <div className="rounded-md border border-line-strong bg-sunken px-3.5 py-3">
          <p className="eyebrow">Ready to send</p>
          <dl className="mt-2.5 grid grid-cols-[minmax(0,7rem)_minmax(0,1fr)] gap-x-4 gap-y-1.5">
            <Field label="Employee ID" value="E-1003" />
            <Field label="Full name" value="Asha Rao" />
          </dl>
          <div className="mt-3 rounded-md border border-attention/40 bg-attention-soft px-3 py-2.5">
            <p className="text-[11.5px] font-semibold text-attention">Start date needs a decision</p>
            <p className="mt-1 text-[12.5px] leading-snug text-ink">
              2 April 2026 or 30 November 2024?
            </p>
          </div>
        </div>
      </div>
    </figure>
  );
}

type Cell = { header: string; value: string; messy?: boolean };

/**
 * One source file's row.
 *
 * A fixed three-column grid, identical in both rows, so the reader's eye can
 * travel down from `emp_id` to `Employee Code` and see they are the same field.
 */
function SourceRow({ file, cells }: { file: string; cells: Cell[] }) {
  return (
    <div className="rounded-md border border-line bg-canvas px-3.5 py-2.5">
      <p className="raw text-[11px] text-ink-subtle">{file}</p>
      <div className="mt-2 grid grid-cols-[minmax(0,5rem)_minmax(0,1fr)_minmax(0,7rem)] gap-x-3">
        {cells.map(({ header, value, messy }) => (
          <div key={header} className="min-w-0">
            <p className="raw truncate text-[10px] uppercase tracking-wide text-ink-subtle">{header}</p>
            {/* The stray spacing is the point, so it is shown rather than
                collapsed: a marker makes it legible where `white-space: pre`
                alone just looked like a typesetting slip. */}
            <p className="raw mt-0.5 truncate text-[12px] text-ink">
              {messy ? <MessyValue value={value} /> : value}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Renders leading, doubled and trailing spaces visibly, as the engine sees them. */
function MessyValue({ value }: { value: string }) {
  return (
    <span className="whitespace-pre">
      {value.split(/( +)/).map((part, index) =>
        part.startsWith(" ") ? (
          <span key={index} className="rounded-[2px] bg-attention/20 text-attention">
            {part}
          </span>
        ) : (
          part
        ),
      )}
    </span>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-[11.5px] text-ink-subtle">{label}</dt>
      <dd className="text-[12.5px] font-medium text-ink">{value}</dd>
    </>
  );
}
