"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input, Select, Textarea } from "@/components/ui/field";
import { api, type RuleInput, type RuleKind, type RuleView, type TargetSchema } from "@/lib/api";
import {
  CREATABLE_KINDS,
  DATE_ORDER_LABEL,
  KIND_HINT,
  KIND_LABEL,
  isValid,
  validateDraft,
} from "@/lib/rules";
import { RulePreviewPanel } from "@/components/rules/rule-preview";

/**
 * Writing or editing one rule.
 *
 * Follows the schema builder in the two things that matter. The version is captured
 * at mount and sent with the save, so two tabs cannot silently overwrite each other.
 * And there is no autosave: a half-typed header is a rule that would match nothing
 * or, worse, match the wrong column, and a migration must never pick one up
 * mid-edit.
 *
 * The form shows only the inputs the chosen kind actually uses. The alternative —
 * every field always visible, most of them ignored — invites someone to fill in a
 * canonical value on a header rule and wonder why it did nothing.
 */
export function RuleBuilder({
  source,
  ruleId,
  schemas,
}: {
  source: RuleView | null;
  ruleId: string | null;
  /** Every contract this person can migrate onto, built-in first. */
  schemas: TargetSchema[];
}) {
  const router = useRouter();
  // Chosen first, and never changed after saving: a rule names one contract's
  // field, so moving it to another schema is a different rule, not an edit.
  const [schemaId, setSchemaId] = useState(source?.schema_id ?? schemas[0]?.schema_id ?? "");
  const schema = schemas.find((candidate) => candidate.schema_id === schemaId) ?? null;
  const [kind, setKind] = useState<RuleKind>(source?.kind ?? "header_alias");
  const [header, setHeader] = useState(source?.header ?? "");
  const [fieldName, setFieldName] = useState(source?.field_name ?? "");
  const [value, setValue] = useState(source?.value ?? "");
  const [canonical, setCanonical] = useState(source?.canonical ?? "");
  const [dateOrder, setDateOrder] = useState(source?.date_order ?? "day_first");
  const [rationale, setRationale] = useState(source?.rationale ?? "");
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  // Captured at mount rather than at save, so the guard reflects what this page
  // was actually shown.
  const baseVersion = ruleId ? (source?.version ?? 1) : undefined;

  const draft: RuleInput = useMemo(
    () => ({
      kind,
      header: kind === "header_alias" || kind === "column_ignore" || kind === "date_order" ? header : "",
      field_name: kind === "column_ignore" ? "" : fieldName,
      value: kind === "value_alias" ? value : "",
      canonical: kind === "value_alias" ? canonical : "",
      ...(kind === "date_order" ? { date_order: dateOrder } : {}),
      rationale,
      schema_id: schemaId,
    }),
    [kind, header, fieldName, value, canonical, dateOrder, rationale, schemaId],
  );

  const problems = useMemo(() => validateDraft(draft), [draft]);
  const ready = isValid(problems);

  const enumField = schema?.fields.find((f) => f.name === fieldName && f.kind === "enum");

  const save = async () => {
    setSaving(true);
    setFailure(null);
    try {
      const payload: RuleInput = {
        ...draft,
        ...(baseVersion !== undefined ? { if_version: baseVersion } : {}),
      };
      if (ruleId) await api.rules.update(ruleId, payload);
      else await api.rules.create(payload);
      router.push("/app/rules");
    } catch (caught) {
      setFailure(caught instanceof Error ? caught.message : "The rule could not be saved.");
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-[56rem] px-4 py-6 sm:px-8 sm:py-8">
      <h1 className="font-display text-[24px]">{ruleId ? "Edit rule" : "New rule"}</h1>
      <p className="mt-1.5 max-w-[62ch] text-[14px] text-ink-muted">
        A rule answers one question the engine would otherwise ask. It matches exactly,
        on a header or a value, so you can see beforehand what it will and will not
        touch.
      </p>

      <div className="panel mt-6 px-5 py-5 sm:px-6">
        <Select
          label="Which schema does this rule apply to?"
          hint={
            ruleId
              ? "A rule belongs to one schema for its whole life. To use this logic on another schema, create a rule there."
              : "A rule only affects migrations onto this schema, so teaching one client's quirk never changes another's."
          }
          value={schemaId}
          disabled={ruleId !== null}
          onChange={(event) => {
            setSchemaId(event.target.value);
            // The field belonged to the previous schema and may not exist here.
            setFieldName("");
            setCanonical("");
          }}
        >
          {schemas.map((candidate) => (
            <option key={candidate.schema_id} value={candidate.schema_id}>
              {candidate.name}
              {candidate.schema_id === "builtin:employee" ? " (built in)" : ""}
            </option>
          ))}
        </Select>

        <div className="my-5 h-px bg-line" />

        <Select
          label="What should this rule decide?"
          hint={KIND_HINT[kind]}
          value={kind}
          onChange={(event) => setKind(event.target.value as RuleKind)}
        >
          {CREATABLE_KINDS.map((option) => (
            <option key={option} value={option}>
              {KIND_LABEL[option]}
            </option>
          ))}
        </Select>

        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          {(kind === "header_alias" || kind === "column_ignore") && (
            <Input
              label="Column header"
              hint="As the file writes it. Matching ignores case, spaces and punctuation."
              mono
              value={header}
              error={problems.fields.header}
              onChange={(event) => setHeader(event.target.value)}
            />
          )}

          {kind === "date_order" && (
            <>
              <Input
                label="Column header"
                hint="Leave blank to apply to every column feeding the field below."
                mono
                value={header}
                error={problems.fields.header}
                onChange={(event) => setHeader(event.target.value)}
              />
              <Select
                label="Which number comes first"
                value={dateOrder}
                error={problems.fields.date_order}
                onChange={(event) => setDateOrder(event.target.value as typeof dateOrder)}
              >
                {(["day_first", "month_first"] as const).map((option) => (
                  <option key={option} value={option}>
                    {DATE_ORDER_LABEL[option]}
                  </option>
                ))}
              </Select>
            </>
          )}

          {kind !== "column_ignore" && (
            <Select
              label="Target field"
              hint={
                kind === "date_order"
                  ? "Optional when a column is named above."
                  : "Which field in the schema this concerns."
              }
              value={fieldName}
              error={problems.fields.field_name}
              onChange={(event) => setFieldName(event.target.value)}
            >
              <option value="">Choose a field…</option>
              {(schema?.fields ?? [])
                .filter((field) => kind !== "value_alias" || field.kind === "enum")
                .map((field) => (
                  <option key={field.name} value={field.name}>
                    {field.label}
                  </option>
                ))}
            </Select>
          )}

          {kind === "value_alias" && (
            <>
              <Input
                label="Value as the source writes it"
                mono
                value={value}
                error={problems.fields.value}
                onChange={(event) => setValue(event.target.value)}
              />
              <Select
                label="Value it should become"
                hint="Only values the schema already permits, so a rule cannot write something validation would reject."
                value={canonical}
                error={problems.fields.canonical}
                onChange={(event) => setCanonical(event.target.value)}
              >
                <option value="">Choose a value…</option>
                {(enumField?.allowed_values ?? []).map((member: string) => (
                  <option key={member} value={member}>
                    {member}
                  </option>
                ))}
              </Select>
            </>
          )}
        </div>

        <Textarea
          label="Why this rule exists"
          hint="Shown wherever the rule appears, so whoever reads it later knows what it was for."
          className="mt-5"
          rows={2}
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
        />
      </div>

      <RulePreviewPanel draft={draft} ready={ready} />

      {failure && (
        <p
          role="alert"
          className="mt-4 rounded-md border border-problem/30 bg-problem-soft px-4 py-3 text-[13.5px] text-problem"
        >
          {failure}
        </p>
      )}

      <div className="mt-6 flex flex-wrap items-center gap-2.5 border-t border-line pt-5">
        <Button variant="primary" disabled={!ready || saving} onClick={() => void save()}>
          {saving ? "Saving…" : ruleId ? "Save rule" : "Create rule"}
        </Button>
        <Button variant="quiet" onClick={() => router.push("/app/rules")}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
