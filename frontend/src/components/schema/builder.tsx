"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { FieldRow } from "@/components/schema/field-row";
import { SchemaPreview } from "@/components/schema/preview";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/field";
import { api, type FieldInput, type TargetSchema } from "@/lib/api";
import { PRESETS, blankField, isValid, toInputs, validate } from "@/lib/schema";

/**
 * Building a target schema field by field.
 *
 * The whole draft is edited locally and saved in one request. Autosaving a
 * half-typed field name would mean a run could pick up a schema mid-edit, and the
 * version guard exists precisely so a save is a deliberate act that can be
 * refused if someone else got there first.
 *
 * Copying the built-in template rather than editing it is what "editable by
 * copy" means in practice: `source` seeds the draft, and `schemaId` decides
 * whether saving creates or replaces.
 */
export function SchemaBuilder({
  source,
  schemaId,
  maxFields,
  assumptions = [],
}: {
  /** The schema to start from: one being edited, or a template being copied. */
  source: TargetSchema | null;
  /** Set when editing a saved schema. Null when creating one. */
  schemaId: string | null;
  maxFields: number;
  /**
   * What an import had to infer rather than read. Shown so a guess is visible as
   * a guess — a spec cannot say which field identifies a record, and getting that
   * wrong merges or splits records.
   */
  assumptions?: string[];
}) {
  const router = useRouter();
  const [name, setName] = useState(
    source ? (schemaId ? source.name : `${source.name} (copy)`) : "",
  );
  const [description, setDescription] = useState(source?.description ?? "");
  const [fields, setFields] = useState<FieldInput[]>(source ? toInputs(source) : []);
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  // The version read when the editor opened. Sent on save so a schema changed
  // somewhere else is refused rather than overwritten.
  const baseVersion = schemaId ? (source?.version ?? 1) : undefined;

  const problems = useMemo(() => validate(name, fields), [name, fields]);
  const ready = isValid(problems);

  const dateFieldsFor = (index: number) =>
    fields
      .filter((field, other) => other !== index && field.kind === "date" && field.name)
      .map((field) => ({ name: field.name, label: field.label }));

  const update = (index: number, next: FieldInput) =>
    setFields(fields.map((field, other) => (other === index ? next : field)));

  const move = (from: number, to: number) => {
    if (to < 0 || to >= fields.length) return;
    const next = [...fields];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    setFields(next);
  };

  const add = (field: FieldInput) => {
    if (fields.length >= maxFields) return;
    // A preset's name collides the second time it is used, so number it rather
    // than adding a field the draft will immediately call invalid.
    const taken = new Set(fields.map((existing) => existing.name));
    let name_ = field.name;
    for (let suffix = 2; taken.has(name_); suffix += 1) name_ = `${field.name}${suffix}`;
    // Only one field can identify a record, so a second ID preset does not claim it.
    const claimed = fields.some((existing) => existing.is_identity);
    setFields([
      ...fields,
      { ...field, name: name_, is_identity: field.is_identity && !claimed },
    ]);
  };

  const save = async () => {
    setSaving(true);
    setFailure(null);
    const payload = {
      name: name.trim(),
      description: description.trim(),
      fields: fields.map((field) => ({ ...field, name: field.name.trim() })),
      ...(baseVersion !== undefined ? { if_version: baseVersion } : {}),
    };
    try {
      const saved = schemaId
        ? await api.schemas.update(schemaId, payload)
        : await api.schemas.create(payload);
      router.push(`/app/schema/${saved.schema_id}`);
    } catch (caught) {
      setFailure(caught instanceof Error ? caught.message : "The schema could not be saved.");
      setSaving(false);
    }
  };

  const full = fields.length >= maxFields;

  return (
    <div className="mx-auto max-w-[56rem] px-4 py-6 sm:px-8 sm:py-8">
      <h1 className="font-display text-[24px]">
        {schemaId ? "Edit schema" : source ? "Copy schema" : "New schema"}
      </h1>
      <p className="mt-1.5 max-w-[62ch] text-[14px] text-ink-muted">
        Describe what the destination expects. The agent matches your columns onto
        these fields, whatever your export calls them.
      </p>

      {assumptions.length > 0 && (
        <div className="mt-5 rounded-md border border-attention/30 bg-attention-soft px-4 py-3">
          <p className="text-[13px] font-medium text-attention">
            Read from your spec, with some things filled in
          </p>
          <ul className="mt-1.5 space-y-1">
            {assumptions.map((note) => (
              <li key={note} className="text-[12.5px] text-attention">
                {note}
              </li>
            ))}
          </ul>
        </div>
      )}

      <section className="panel mt-6 px-4 py-4 sm:px-5">
        <Input
          label="Schema name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Employee"
        />
        <Textarea
          label="Description"
          hint="optional"
          className="mt-3"
          rows={2}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="What this contract is for, and which client expects it."
        />
      </section>

      <section className="mt-7">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-[15px] font-semibold">Fields</h2>
          <p className="text-[12.5px] text-ink-muted tnum">
            {fields.length} of {maxFields}
          </p>
        </div>

        {fields.length === 0 ? (
          <div className="panel mt-3 px-5 py-8 text-center">
            <p className="text-[14px] font-medium">No fields yet</p>
            <p className="mx-auto mt-1 max-w-[42ch] text-[13px] text-ink-muted">
              Add the fields your destination expects. Start from a common shape
              below, or add a blank one and fill it in.
            </p>
          </div>
        ) : (
          <ul className="panel mt-3 divide-y divide-line overflow-hidden">
            {fields.map((field, index) => (
              <FieldRow
                key={index}
                field={field}
                index={index}
                total={fields.length}
                error={problems.fields[index]}
                dateFields={dateFieldsFor(index)}
                onChange={(next) => update(index, next)}
                onRemove={() => setFields(fields.filter((_, other) => other !== index))}
                onMove={(to) => move(index, to)}
              />
            ))}
          </ul>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button size="sm" disabled={full} onClick={() => add(blankField())}>
            + Add field
          </Button>
          <span className="text-[12.5px] text-ink-subtle">or start from</span>
          {PRESETS.map((preset) => (
            <Button
              key={preset.label}
              size="sm"
              variant="quiet"
              disabled={full}
              onClick={() => add({ ...preset.field, not_before: null })}
            >
              {preset.label}
            </Button>
          ))}
        </div>
        {full && (
          <p className="mt-2 text-[12.5px] text-ink-muted">
            That is the most fields a schema can have.
          </p>
        )}
      </section>

      <SchemaPreview fields={fields} />

      {problems.schema && (
        <p
          role="status"
          className="mt-6 rounded-md border border-attention/30 bg-attention-soft px-4 py-2.5 text-[13px] text-attention"
        >
          {problems.schema}
        </p>
      )}

      {failure && (
        <p
          role="alert"
          className="mt-4 rounded-md border border-problem/30 bg-problem-soft px-4 py-3 text-[13.5px] text-problem"
        >
          {failure}
        </p>
      )}

      <div className="mt-7 flex flex-wrap items-center gap-2.5 border-t border-line pt-5">
        <Button variant="primary" size="lg" disabled={!ready || saving} onClick={() => void save()}>
          {saving ? "Saving…" : schemaId ? "Save changes" : "Save schema"}
        </Button>
        <Button size="lg" variant="quiet" onClick={() => router.back()}>
          Cancel
        </Button>
        {schemaId && (
          // A saved schema can be handed to version control or another
          // engagement. Only once saved: exporting a half-typed draft would
          // produce a spec that does not describe anything.
          <a
            href={api.schemas.specUrl(schemaId)}
            download
            className="ml-auto text-[13px] text-accent-ink underline"
          >
            Download as YAML
          </a>
        )}
      </div>
    </div>
  );
}
