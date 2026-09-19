/**
 * Target schemas, as the builder and the run screens need them.
 *
 * The backend is the authority on what a schema is and which header spellings
 * match it. This module holds only what the browser needs on top: the wording
 * for each value kind, the presets that make building a schema quick, and the
 * validation that lets the builder object before a request is sent.
 */
import type { FieldInput, TargetField, TargetSchema, ValueKind } from "./api";

/** Each kind in the words a consultant would use, not the type code. */
export const KIND_LABEL: Record<ValueKind, string> = {
  identifier: "Code or ID",
  person_name: "Person's name",
  email: "Email address",
  date: "Calendar date",
  text: "Free text",
  enum: "One of a fixed set",
};

/** What choosing a kind actually changes, so the choice is not a guess. */
export const KIND_DETAIL: Record<ValueKind, string> = {
  identifier:
    "Kept exactly as written, so leading zeros and prefixes survive. Never treated as a number.",
  person_name: "Only trimmed. Capitalisation is left alone, because “McDonald” is not “Mcdonald”.",
  email: "Checked for a usable address. The domain is lowercased; the part before @ is not.",
  date: "Read into a calendar date. An ambiguous one like 03/04/2026 is asked about, never guessed.",
  text: "Trimmed, otherwise untouched. Accepts anything.",
  enum: "Only the values you list are accepted. Other spellings you name are mapped onto them.",
};

export const KINDS: ValueKind[] = [
  "identifier",
  "person_name",
  "email",
  "date",
  "text",
  "enum",
];

/**
 * Field shapes people reach for first.
 *
 * Quick-add rather than a template, because the second field someone adds is
 * usually one of these and typing four inputs for it is friction with no
 * purpose. Everything remains editable afterwards.
 */
export const PRESETS: { label: string; field: Omit<FieldInput, "not_before"> }[] = [
  {
    label: "ID",
    field: {
      name: "recordId",
      label: "Record ID",
      description: "Identifies one record.",
      kind: "identifier",
      required: true,
      is_identity: true,
      is_unique: false,
      enum_values: [],
      value_aliases: {},
    },
  },
  {
    label: "Name",
    field: {
      name: "fullName",
      label: "Full name",
      description: "",
      kind: "person_name",
      required: false,
      is_identity: false,
      is_unique: false,
      enum_values: [],
      value_aliases: {},
    },
  },
  {
    label: "Email",
    field: {
      name: "email",
      label: "Email",
      description: "",
      kind: "email",
      required: false,
      is_identity: false,
      is_unique: true,
      enum_values: [],
      value_aliases: {},
    },
  },
  {
    label: "Date",
    field: {
      name: "date",
      label: "Date",
      description: "",
      kind: "date",
      required: false,
      is_identity: false,
      is_unique: false,
      enum_values: [],
      value_aliases: {},
    },
  },
  {
    label: "Text",
    field: {
      name: "field",
      label: "Field",
      description: "",
      kind: "text",
      required: false,
      is_identity: false,
      is_unique: false,
      enum_values: [],
      value_aliases: {},
    },
  },
];

export function blankField(): FieldInput {
  return {
    name: "",
    label: "",
    description: "",
    kind: "text",
    required: false,
    is_identity: false,
    is_unique: false,
    enum_values: [],
    value_aliases: {},
    not_before: null,
  };
}

/** Turn a saved schema into something the builder can edit. */
export function toInputs(schema: TargetSchema): FieldInput[] {
  return schema.fields.map((field) => ({
    name: field.name,
    label: field.label,
    description: field.description,
    kind: field.kind,
    required: field.required,
    is_identity: field.is_identity,
    is_unique: field.is_unique,
    enum_values: [...field.allowed_values],
    value_aliases: { ...field.value_aliases },
    not_before: field.not_before ?? null,
  }));
}

/**
 * A label turned into a field name.
 *
 * Suggested as someone types a label, never enforced: the destination decides
 * what its fields are called, and overriding a name the user typed on purpose
 * would be worse than leaving a slightly odd suggestion.
 */
export function suggestName(label: string): string {
  const words = label
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .split(/[^A-Za-z0-9]+/)
    .filter(Boolean);
  if (words.length === 0) return "";
  const [head, ...rest] = words;
  const camel =
    head.toLowerCase() + rest.map((w) => w[0].toUpperCase() + w.slice(1).toLowerCase()).join("");
  // A name cannot start with a digit.
  return /^[0-9]/.test(camel) ? `field${camel}` : camel.slice(0, 64);
}

const NAME_PATTERN = /^[A-Za-z][A-Za-z0-9_]{0,63}$/;

export interface SchemaProblems {
  /** Keyed by field index, so the message sits on the row that caused it. */
  fields: Record<number, string>;
  /** Wrong with the schema as a whole rather than with one field. */
  schema: string | null;
}

/**
 * What is wrong with a draft, checked here so the builder can object
 * immediately rather than after a round trip.
 *
 * These mirror the backend's own rules, which remain the authority — this is a
 * faster copy of them, not a replacement. Anything this misses is still caught
 * on save and shown.
 */
export function validate(name: string, fields: FieldInput[]): SchemaProblems {
  const problems: Record<number, string> = {};
  const counts = new Map<string, number>();
  for (const field of fields) {
    const key = field.name.trim();
    if (key) counts.set(key, (counts.get(key) ?? 0) + 1);
  }

  fields.forEach((field, index) => {
    const fieldName = field.name.trim();
    if (!fieldName) {
      problems[index] = "Give this field a name.";
    } else if (!NAME_PATTERN.test(fieldName)) {
      problems[index] =
        "Start with a letter and use only letters, digits and underscores.";
    } else if ((counts.get(fieldName) ?? 0) > 1) {
      problems[index] = `Another field is already called ${fieldName}.`;
    } else if (field.kind === "enum" && field.enum_values.length === 0) {
      problems[index] = "List the values this field accepts.";
    }
  });

  let schema: string | null = null;
  if (!name.trim()) {
    schema = "Give the schema a name.";
  } else if (fields.length === 0) {
    schema = "Add at least one field.";
  } else {
    const identities = fields.filter((field) => field.is_identity);
    if (identities.length > 1) {
      schema = `Only one field can identify a record. ${identities
        .map((field) => field.label || field.name)
        .join(" and ")} are both marked.`;
    }
  }

  return { fields: problems, schema };
}

export function isValid(problems: SchemaProblems): boolean {
  return problems.schema === null && Object.keys(problems.fields).length === 0;
}

/** Columns for the record tables: the identity field first, then the rest. */
export function displayFields(fields: TargetField[]): TargetField[] {
  const identity = fields.filter((field) => field.is_identity);
  const rest = fields.filter((field) => !field.is_identity);
  return [...identity, ...rest];
}
