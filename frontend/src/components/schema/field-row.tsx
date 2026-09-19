"use client";

import { useId, useState } from "react";
import { Checkbox, Input, Select } from "@/components/ui/field";
import type { FieldInput, ValueKind } from "@/lib/api";
import { KIND_DETAIL, KIND_LABEL, KINDS, suggestName } from "@/lib/schema";
import { cn } from "@/lib/utils";

/**
 * One field in the builder.
 *
 * Collapsed to a single line by default and expanded for the rest, because a
 * schema is read far more often than it is edited — twelve fields each showing
 * six controls is a wall nobody can scan. The collapsed line carries what
 * distinguishes one field from another: its label, its name, its kind, and the
 * flags that change how the engine treats it.
 */
export function FieldRow({
  field,
  index,
  total,
  error,
  dateFields,
  onChange,
  onRemove,
  onMove,
}: {
  field: FieldInput;
  index: number;
  total: number;
  error?: string;
  /** Other date fields, for the "must not precede" pairing. */
  dateFields: { name: string; label: string }[];
  onChange: (next: FieldInput) => void;
  onRemove: () => void;
  onMove: (to: number) => void;
}) {
  const [open, setOpen] = useState(!field.name);
  const panelId = useId();
  const set = <K extends keyof FieldInput>(key: K, value: FieldInput[K]) =>
    onChange({ ...field, [key]: value });

  return (
    <li className={cn("bg-surface", error && !open && "bg-problem-soft/40")}>
      <div className="flex items-start gap-1 px-2 py-2 sm:px-3">
        <Reorder index={index} total={total} onMove={onMove} label={field.label || field.name} />

        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          aria-controls={panelId}
          className="min-w-0 flex-1 rounded-md px-1.5 py-1 text-left hover:bg-sunken"
        >
          <span className="flex min-w-0 items-center gap-2">
            <Chevron open={open} />
            <span className="min-w-0 flex-1">
              <span className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span className="text-[13.5px] font-medium text-ink">
                  {field.label || field.name || "Untitled field"}
                </span>
                {field.name && (
                  <span className="raw text-[12px] text-ink-subtle">{field.name}</span>
                )}
              </span>
              <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px]">
                <span className="text-ink-muted">{KIND_LABEL[field.kind]}</span>
                {field.required && <Tag tone="accent">Required</Tag>}
                {field.is_identity && <Tag tone="accent">Identifies the record</Tag>}
                {field.is_unique && <Tag tone="plain">Must be unique</Tag>}
                {error && <Tag tone="problem">Needs attention</Tag>}
              </span>
            </span>
          </span>
        </button>

        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${field.label || field.name || "this field"}`}
          className="mt-1 shrink-0 rounded-md p-1.5 text-ink-subtle hover:bg-problem-soft hover:text-problem"
        >
          <svg
            viewBox="0 0 24 24"
            className="size-4"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.8}
            strokeLinecap="round"
            aria-hidden
          >
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>

      {open && (
        <div id={panelId} className="border-t border-line bg-sunken/40 px-3 py-3.5 sm:px-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label="Label"
              hint="what a person calls it"
              value={field.label}
              onChange={(event) => {
                const label = event.target.value;
                // The name follows the label only while it has not been set by
                // hand — retyping someone's deliberate name would be rude.
                const suggested = suggestName(label);
                const following = !field.name || field.name === suggestName(field.label);
                onChange({ ...field, label, name: following ? suggested : field.name });
              }}
              placeholder="Start date"
            />
            <Input
              label="Field name"
              hint="what the destination calls it"
              mono
              value={field.name}
              onChange={(event) => set("name", event.target.value)}
              placeholder="startDate"
              error={error}
            />
          </div>

          <Select
            label="What kind of value"
            className="mt-3"
            value={field.kind}
            onChange={(event) => {
              const kind = event.target.value as ValueKind;
              // Leaving a stale pairing behind would silently order two fields
              // that are no longer both dates.
              onChange({
                ...field,
                kind,
                not_before: kind === "date" ? field.not_before : null,
                enum_values: kind === "enum" ? field.enum_values : [],
              });
            }}
          >
            {KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {KIND_LABEL[kind]}
              </option>
            ))}
          </Select>
          <p className="mt-1.5 text-[12px] text-ink-muted">{KIND_DETAIL[field.kind]}</p>

          {field.kind === "enum" && (
            <>
              <Input
                label="Accepted values"
                hint="comma separated"
                className="mt-3"
                mono
                value={field.enum_values.join(", ")}
                onChange={(event) =>
                  set(
                    "enum_values",
                    event.target.value
                      .split(",")
                      .map((value) => value.trim())
                      .filter(Boolean),
                  )
                }
                placeholder="full_time, part_time, contract"
              />
              <ValueAliases
                enumValues={field.enum_values}
                aliases={field.value_aliases}
                onChange={(next) => set("value_aliases", next)}
              />
            </>
          )}

          {field.kind === "date" && dateFields.length > 0 && (
            <Select
              label="Must not come before"
              hint="optional"
              className="mt-3"
              value={field.not_before ?? ""}
              onChange={(event) => set("not_before", event.target.value || null)}
            >
              <option value="">No ordering rule</option>
              {dateFields.map((other) => (
                <option key={other.name} value={other.name}>
                  {other.label || other.name}
                </option>
              ))}
            </Select>
          )}

          <Input
            label="Description"
            hint="optional — shown to the AI when a header is unfamiliar"
            className="mt-3"
            value={field.description}
            onChange={(event) => set("description", event.target.value)}
            placeholder="Date employment began."
          />

          <fieldset className="mt-4 space-y-2.5 border-t border-line pt-3.5">
            <legend className="sr-only">How the engine treats this field</legend>
            <Checkbox
              label="Required"
              detail="A record without it cannot be delivered, and the run stops to ask."
              checked={field.required}
              onChange={(event) => set("required", event.target.checked)}
            />
            <Checkbox
              label="Identifies the record"
              detail="Rows sharing this value across files are treated as one record. Only one field can do this."
              checked={field.is_identity}
              onChange={(event) => set("is_identity", event.target.checked)}
            />
            <Checkbox
              label="Must be unique"
              detail="Two records sharing a value are flagged for you to look at, not merged."
              checked={field.is_unique}
              onChange={(event) => set("is_unique", event.target.checked)}
            />
          </fieldset>
        </div>
      )}
    </li>
  );
}

/**
 * Reordering by button rather than by drag.
 *
 * Field order is only presentation — it changes the column order in the tables,
 * nothing about the migration — and buttons work with a keyboard, a screen
 * reader and a touch screen, which a drag handle does not without considerably
 * more machinery than the payoff justifies.
 */
function Reorder({
  index,
  total,
  onMove,
  label,
}: {
  index: number;
  total: number;
  onMove: (to: number) => void;
  label: string;
}) {
  const name = label || `field ${index + 1}`;
  return (
    <div className="mt-0.5 flex shrink-0 flex-col">
      <button
        type="button"
        disabled={index === 0}
        onClick={() => onMove(index - 1)}
        aria-label={`Move ${name} up`}
        className="rounded p-0.5 text-ink-subtle hover:bg-sunken hover:text-ink disabled:opacity-25 disabled:hover:bg-transparent"
      >
        <Caret up />
      </button>
      <button
        type="button"
        disabled={index === total - 1}
        onClick={() => onMove(index + 1)}
        aria-label={`Move ${name} down`}
        className="rounded p-0.5 text-ink-subtle hover:bg-sunken hover:text-ink disabled:opacity-25 disabled:hover:bg-transparent"
      >
        <Caret />
      </button>
    </div>
  );
}

function Caret({ up = false }: { up?: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={cn("size-3.5", up && "rotate-180")}
      fill="none"
      stroke="currentColor"
      strokeWidth={2.2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={cn("size-3.5 shrink-0 text-ink-subtle transition-transform", open && "rotate-90")}
      fill="none"
      stroke="currentColor"
      strokeWidth={2.2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="m9 6 6 6-6 6" />
    </svg>
  );
}

function Tag({
  tone,
  children,
}: {
  tone: "accent" | "plain" | "problem";
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "rounded px-1.5 py-0.5 text-[11.5px] font-medium",
        tone === "accent" && "bg-accent-soft text-accent-ink",
        tone === "plain" && "bg-sunken text-ink-muted",
        tone === "problem" && "bg-problem-soft text-problem",
      )}
    >
      {children}
    </span>
  );
}


/**
 * Teaching the schema what the client's own spellings mean.
 *
 * Without this, a value the export writes as "Permanent" escalates on every
 * single row even though the answer is always the same — which is exactly the
 * kind of repeated non-decision that trains a reviewer to stop reading. Listing
 * it once turns a hundred questions into zero.
 *
 * Deliberately not fuzzy matching: deciding that "Seasonal Temp" means
 * "contract" is a business call, so an unlisted spelling still escalates.
 */
function ValueAliases({
  enumValues,
  aliases,
  onChange,
}: {
  enumValues: string[];
  aliases: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
}) {
  if (enumValues.length === 0) return null;

  // Grouped by the member they map onto, which is how someone thinks about them:
  // "what else counts as express?"
  const forMember = (member: string) =>
    Object.entries(aliases)
      .filter(([, target]) => target === member)
      .map(([spelling]) => spelling);

  const replace = (member: string, spellings: string[]) => {
    const next: Record<string, string> = {};
    // Keep other members' entries, drop this member's, then re-add.
    for (const [spelling, target] of Object.entries(aliases)) {
      if (target !== member) next[spelling] = target;
    }
    for (const spelling of spellings) {
      // Normalised the way the backend compares them, so what is typed here is
      // what will actually match.
      const key = spelling.toLowerCase().replace(/[\s_-]+/g, "");
      if (key && key !== member.toLowerCase().replace(/[\s_-]+/g, "")) next[key] = member;
    }
    onChange(next);
  };

  return (
    <fieldset className="mt-3">
      <legend className="text-[12.5px] font-medium text-ink">
        Other spellings <span className="font-normal text-ink-subtle">optional</span>
      </legend>
      <p className="mt-0.5 text-[12px] text-ink-muted">
        What else your export might call each value. Anything not listed is asked
        about rather than guessed.
      </p>
      <div className="mt-2 space-y-2">
        {enumValues.map((member) => (
          <div key={member} className="flex flex-wrap items-center gap-2">
            <span className="raw w-full shrink-0 text-[12px] text-ink-muted sm:w-28">
              {member}
            </span>
            <Input
              aria-label={`Other spellings for ${member}`}
              className="min-w-0 flex-1"
              mono
              value={forMember(member).join(", ")}
              onChange={(event) =>
                replace(
                  member,
                  event.target.value.split(",").map((value) => value.trim()),
                )
              }
              placeholder="permanent, fte, regular"
            />
          </div>
        ))}
      </div>
    </fieldset>
  );
}
