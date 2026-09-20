"use client";

import type { FieldInput } from "@/lib/api";

/**
 * What one record will look like at the destination.
 *
 * A field list says what the contract *is*; this says what it *produces*, which
 * is the thing a consultant is actually checking. Built with `JSON.stringify`
 * rather than assembled from strings, so a quote or a backslash in a value
 * cannot produce a preview that would not parse — showing invalid JSON as an
 * example of valid output would be worse than showing nothing.
 */
export function SchemaPreview({ fields }: { fields: FieldInput[] }) {
  const named = fields.filter((field) => field.name.trim());
  if (named.length === 0) return null;

  const sample: Record<string, unknown> = {};
  for (const field of named) sample[field.name.trim()] = example(field);

  return (
    <section className="mt-7">
      <h2 className="text-[15px] font-semibold">What gets sent</h2>
      <p className="mt-0.5 text-[13px] text-ink-muted">
        One record, as the destination will receive it. Optional fields with no
        value are left out rather than sent as null.
      </p>
      <pre
        className="raw mt-3 overflow-x-auto rounded-md border border-line bg-sunken px-4 py-3 text-[12.5px] leading-relaxed text-ink-muted"
        tabIndex={0}
        role="region"
        aria-label="Example record"
      >
        {JSON.stringify(sample, null, 2)}
      </pre>
    </section>
  );
}

/** A plausible value for a field, so the shape reads as real data. */
function example(field: FieldInput): string {
  switch (field.kind) {
    case "identifier":
      return "REC-1001";
    case "person_name":
      return "Priya Sharma";
    case "email":
      return "priya.sharma@example.com";
    case "date":
      return "2026-01-15";
    case "enum":
      return field.enum_values[0] ?? "";
    default:
      return field.label ? field.label.toLowerCase() : "text";
  }
}
