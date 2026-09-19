import { TARGET_FIELDS } from "@/lib/target-fields";

/**
 * The destination contract.
 *
 * A consultant's first question is "what does it want from my file?", and the
 * answer being buried in the backend is why the previous build felt opaque.
 */
export default function SchemaPage() {
  return (
    <div className="mx-auto max-w-[52rem] px-4 py-6 sm:px-8 sm:py-8">
      <h1 className="font-display text-[24px]">My schema</h1>
      <p className="mt-1.5 max-w-[60ch] text-[14px] text-ink-muted">
        Every migration maps onto this employee record. You do not configure it
        per run — the agent matches your columns onto these fields, whatever they
        are called in your export.
      </p>

      <div className="panel mt-6 overflow-hidden">
        <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Destination fields">
          <table className="w-full min-w-[34rem] border-collapse text-left">
            <thead>
              <tr className="border-b border-line text-[12px] text-ink-subtle">
                <th scope="col" className="px-5 py-2.5 font-medium">Field</th>
                <th scope="col" className="px-5 py-2.5 font-medium">Needed</th>
                <th scope="col" className="px-5 py-2.5 font-medium">What it holds</th>
              </tr>
            </thead>
            <tbody>
              {TARGET_FIELDS.map((field) => (
                <tr key={field.name} className="border-b border-line last:border-0">
                  <td className="px-5 py-3">
                    <p className="text-[13.5px] font-medium">{field.label}</p>
                    <p className="raw mt-0.5 text-[12px] text-ink-subtle">{field.name}</p>
                  </td>
                  <td className="px-5 py-3 text-[13px]">
                    {field.required ? (
                      <span className="text-ink">Always</span>
                    ) : (
                      <span className="text-ink-muted">Optional</span>
                    )}
                  </td>
                  <td className="px-5 py-3 text-[13px] text-ink-muted">{KIND[field.kind] ?? field.kind}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <p className="mt-5 max-w-[60ch] text-[13px] text-ink-muted">
        Columns that match nothing here are left out rather than guessed at, and
        the run records which ones and why.
      </p>
    </div>
  );
}

/** Field kinds in words, not type codes. */
const KIND: Record<string, string> = {
  identifier: "A code that identifies one employee",
  person_name: "A person's full name",
  email: "A working email address",
  date: "A calendar date",
  text: "Free text",
  enum: "One of a fixed set of values",
};
