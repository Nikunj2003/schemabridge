"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Select, Textarea } from "@/components/ui/field";
import { api, type SchemaListing, type TargetSchema } from "@/lib/api";
import { fileSize } from "@/lib/present";
import { cn } from "@/lib/utils";

const ACCEPTED = [".csv", ".xlsx"];
const MAX_FILES = 4;

/** The special choice: derive a contract from the uploaded headers. */
const DETECT = "detected";

/** The special choice: a spec supplied for this run only, not saved. */
const SPEC = "spec";

/** The special choice: one of the account's own saved schemas, picked below. */
const SAVED = "saved";

/**
 * Starting a migration.
 *
 * Two questions, in the order they actually arise: what are you migrating, and
 * what shape does the destination want? The second has a sensible default, so
 * someone who does not care can ignore it — but it is visible, because the
 * previous build hid it entirely and left no way to migrate anything but
 * employees.
 */
export function NewMigration() {
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [listing, setListing] = useState<SchemaListing | null>(null);
  const [choice, setChoice] = useState<string | null>(null);
  const [saved, setSaved] = useState<string>("");
  const [spec, setSpec] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let live = true;
    void (async () => {
      try {
        const loaded = await api.schemas.list();
        if (!live) return;
        setListing(loaded);
        // Default to the built-in template rather than to nothing, so the
        // button is usable the moment a file is added.
        setChoice(loaded.builtin.schema_id);
      } catch {
        // Not fatal: omitting the schema uses the backend's own default.
        if (live) setListing(null);
      }
    })();
    return () => {
      live = false;
    };
  }, []);

  const add = (incoming: FileList | null) => {
    if (!incoming) return;
    setError(null);
    const accepted: File[] = [];
    const rejected: string[] = [];

    for (const file of Array.from(incoming)) {
      const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      if (!ACCEPTED.includes(ext)) rejected.push(`${file.name} is not a .csv or .xlsx file`);
      else accepted.push(file);
    }

    const room = MAX_FILES - files.length;
    const taken = accepted.slice(0, Math.max(0, room));
    // Silently dropping the rest is how someone ends up migrating half a dataset
    // without knowing it, so anything not taken is named.
    for (const file of accepted.slice(taken.length)) {
      rejected.push(`${file.name} was not added — at most ${MAX_FILES} files per migration`);
    }

    if (taken.length > 0) setFiles([...files, ...taken]);
    setNotice(rejected.length > 0 ? rejected.join(". ") : null);
  };

  const start = async () => {
    if (files.length === 0) return;
    setStarting(true);
    setError(null);
    try {
      const run = await api.createRun(
        files,
        choice === SPEC ? undefined : (choice === SAVED ? saved : (choice ?? undefined)),
        choice === SPEC ? spec : undefined,
      );
      router.push(`/app/migrations/${run.run_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The migration could not be started.");
      setStarting(false);
    }
  };

  const savedSchema: TargetSchema | null =
    listing?.schemas.find((schema) => schema.schema_id === saved) ?? null;

  // The schema whose required fields are worth naming below. Null for the two
  // choices whose shape is not known until the run starts.
  const chosen: TargetSchema | null =
    listing === null || choice === null || choice === DETECT || choice === SPEC
      ? null
      : choice === SAVED
        ? savedSchema
        : choice === listing.builtin.schema_id
          ? listing.builtin
          : null;

  return (
    <div className="mx-auto max-w-[52rem] px-4 py-6 sm:px-8 sm:py-8">
      <h1 className="font-display text-[24px]">New migration</h1>
      <p className="mt-1.5 max-w-[62ch] text-[14px] text-ink-muted">
        Add your exports and say what the destination expects. The agent works out
        which column means what — you do not map anything by hand.
      </p>

      <section className="mt-6">
        <h2 className="text-[15px] font-semibold">1. Your files</h2>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          CSV or Excel, up to {MAX_FILES} files. Use synthetic data only.
        </p>

        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            add(event.dataTransfer.files);
          }}
          className={cn(
            "mt-3 rounded-lg border border-dashed px-6 py-8 text-center transition-colors",
            dragging ? "border-accent bg-accent-soft" : "border-line-strong bg-surface",
          )}
        >
          <p className="text-[14px] text-ink-muted">Drag your exports here</p>
          <Button className="mt-3" onClick={() => inputRef.current?.click()}>
            Choose files
          </Button>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPTED.join(",")}
            onChange={(event) => {
              add(event.target.files);
              // Reset so choosing the same file twice still registers.
              event.target.value = "";
            }}
            className="hidden"
          />
        </div>

        {files.length > 0 && (
          <ul className="mt-3 divide-y divide-line overflow-hidden rounded-md border border-line bg-surface">
            {files.map((file, index) => (
              <li key={`${file.name}-${index}`} className="flex items-center gap-3 px-4 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13.5px] font-medium">{file.name}</p>
                  <p className="text-[12.5px] text-ink-muted tnum">{fileSize(file.size)}</p>
                </div>
                <button
                  onClick={() => setFiles(files.filter((_, i) => i !== index))}
                  className="shrink-0 rounded px-2 py-1 text-[13px] text-ink-muted hover:bg-sunken hover:text-ink"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}

        {notice && (
          <p
            role="status"
            className="mt-3 rounded-md border border-attention/30 bg-attention-soft px-4 py-2.5 text-[13px] text-attention"
          >
            {notice}
          </p>
        )}
      </section>

      <section className="mt-7">
        <h2 className="text-[15px] font-semibold">2. What the destination expects</h2>
        <p className="mt-0.5 max-w-[62ch] text-[13px] text-ink-muted">
          The contract your records are mapped onto and checked against.
        </p>

        {listing === null ? (
          <p className="panel mt-3 px-4 py-3 text-[13px] text-ink-muted">
            Saved schemas are unavailable, so this run will use the built-in
            employee shape.
          </p>
        ) : (
          <div className="mt-3 space-y-2">
            <SchemaOption
              id={listing.builtin.schema_id}
              chosen={choice}
              onChoose={setChoice}
              title={listing.builtin.name}
              note="Built in"
              detail={`${listing.builtin.fields.length} fields. A good default for employee data.`}
            />

            {/* One option for every saved schema rather than a radio each: the
                list grows per client, and twenty radios would bury the two
                choices that are not a saved schema. Absent entirely when there
                are none, so it is never an empty control. */}
            {listing.schemas.length > 0 && (
              <SchemaOption
                id={SAVED}
                chosen={choice}
                onChoose={(id) => {
                  setChoice(id);
                  // Selecting the group with nothing picked would leave the run
                  // with no schema, so default to the most recently changed.
                  if (!saved) setSaved(listing.schemas[0].schema_id);
                }}
                title="One of my schemas"
                note={`${listing.schemas.length} saved`}
                detail="A contract you built or imported here."
              >
                <Select
                  aria-label="Which of your schemas"
                  value={saved}
                  onChange={(event) => setSaved(event.target.value)}
                >
                  {listing.schemas.map((schema) => (
                    <option key={schema.schema_id} value={schema.schema_id}>
                      {schema.name} — {schema.fields.length} fields
                    </option>
                  ))}
                </Select>
                {savedSchema?.description && (
                  <p className="mt-2 text-[12.5px] text-ink-muted">
                    {savedSchema.description}
                  </p>
                )}
              </SchemaOption>
            )}

            <SchemaOption
              id={SPEC}
              chosen={choice}
              onChoose={setChoice}
              title="Paste a spec"
              detail="A JSON Schema or YAML field list, used for this run only. Save it from My schemas if you want to keep it."
            >
              <Textarea
                aria-label="Schema spec for this run"
                rows={6}
                className="mt-2.5 [&_textarea]:raw"
                value={spec}
                onChange={(event) => setSpec(event.target.value)}
                placeholder={"name: Customer\nfields:\n  - name: customerId\n    kind: identifier\n    required: true\n    is_identity: true"}
              />
            </SchemaOption>

            <SchemaOption
              id={DETECT}
              chosen={choice}
              onChoose={setChoice}
              title="Work it out from my files"
              detail="Builds a contract from your own headers. Nothing is marked required and no field identifies a record, so review it afterwards before relying on it."
            />

            <p className="pt-1 text-[12.5px] text-ink-muted">
              Need a different shape?{" "}
              <Link href="/app/schema/new" className="text-accent-ink underline">
                Build a schema
              </Link>
              .
            </p>
          </div>
        )}

        {chosen && chosen.fields.some((field) => field.required) && (
          <p className="mt-3 text-[12.5px] text-ink-muted">
            Every record needs{" "}
            {chosen.fields
              .filter((field) => field.required)
              .map((field) => field.label.toLowerCase())
              .join(", ")}
            . Anything else your files carry is matched where it fits and left out
            where it does not.
          </p>
        )}
      </section>

      <section className="mt-7">
        <h2 className="text-[15px] font-semibold">3. Where the records go</h2>
        <div className="panel mt-3 px-4 py-4">
          <p className="text-[13.5px] font-medium">Demo HR system</p>
          <p className="mt-0.5 text-[13px] text-ink-muted">
            A simulated destination inside this app. Nothing leaves it, and it
            enforces the schema you chose above.
          </p>
        </div>
      </section>

      {error && (
        <p
          role="alert"
          className="mt-5 rounded-md border border-problem/30 bg-problem-soft px-4 py-3 text-[13.5px] text-problem"
        >
          {error}
        </p>
      )}

      <div className="mt-7 border-t border-line pt-5">
        <Button
          variant="primary"
          size="lg"
          disabled={
            files.length === 0 ||
            starting ||
            (choice === SPEC && !spec.trim()) ||
            (choice === SAVED && !saved)
          }
          onClick={() => void start()}
        >
          {starting ? "Starting…" : "Start migration"}
        </Button>
        <p className="mt-2.5 max-w-[56ch] text-[13px] text-ink-muted">
          This lets the agent clean the records and send the valid ones to the
          demo destination on its own. It stops and asks you only when a choice
          would change what gets migrated.
        </p>
      </div>
    </div>
  );
}

function SchemaOption({
  id,
  chosen,
  onChoose,
  title,
  note,
  detail,
  children,
}: {
  id: string;
  chosen: string | null;
  onChoose: (id: string) => void;
  title: string;
  note?: string;
  detail: string;
  /** Revealed only when chosen, so an unselected option stays one line. */
  children?: React.ReactNode;
}) {
  const selected = chosen === id;
  return (
    <div
      className={cn(
        "rounded-md border transition-colors",
        selected ? "border-accent bg-accent-soft" : "border-line bg-surface hover:border-line-strong",
      )}
    >
      <label className="flex cursor-pointer gap-3 px-4 py-3">
        <input
          type="radio"
          name="schema"
          value={id}
          checked={selected}
          onChange={() => onChoose(id)}
          className="mt-1 size-4 shrink-0 accent-accent focus:outline-none focus:ring-2 focus:ring-accent/25"
        />
        <span className="min-w-0">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-[13.5px] font-medium">{title}</span>
            {note && <span className="text-[11.5px] text-ink-subtle">{note}</span>}
          </span>
          <span className="mt-0.5 block text-[12.5px] text-ink-muted">{detail}</span>
        </span>
      </label>
      {selected && children && <div className="px-4 pb-3.5">{children}</div>}
    </div>
  );
}
