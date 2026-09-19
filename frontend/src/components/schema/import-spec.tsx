"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/field";
import { api, type ImportedSchema } from "@/lib/api";
import { cn } from "@/lib/utils";

const ACCEPTED = [".json", ".yaml", ".yml", ".txt"];

const EXAMPLE = `name: Customer
fields:
  - name: customerId
    label: Customer ID
    kind: identifier
    required: true
    is_identity: true
  - name: primaryEmail
    kind: email
    required: true
  - name: signedUp
    kind: date`;

/**
 * Handing over a spec file instead of building the schema by hand.
 *
 * The contract usually already exists — an API's JSON Schema, a data dictionary,
 * something a previous engagement wrote down. Retyping it is slow and is a chance
 * to introduce a discrepancy between what the tool checks and what the
 * destination actually wants.
 *
 * The result opens in the builder rather than being saved, because a spec cannot
 * express everything: JSON Schema has no way to say which field identifies a
 * record, so the import infers one and says so. Saving silently would make a
 * guess into the contract without anybody seeing it.
 */
export function ImportSpec({ onImported }: { onImported: (schema: ImportedSchema) => void }) {
  const [mode, setMode] = useState<"file" | "paste">("file");
  const [text, setText] = useState("");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const run = async (work: () => Promise<ImportedSchema>) => {
    setBusy(true);
    setError(null);
    try {
      onImported(await work());
    } catch (caught) {
      // The backend's message names the line and what was expected, so it is
      // more useful than anything this layer could write.
      setError(caught instanceof Error ? caught.message : "That spec could not be read.");
    } finally {
      setBusy(false);
    }
  };

  const takeFile = (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!ACCEPTED.includes(ext)) {
      setError(`${file.name} is not a .json or .yaml file.`);
      return;
    }
    void run(() => api.schemas.importFile(file));
  };

  return (
    <section className="panel px-4 py-4 sm:px-5">
      <h2 className="text-[15px] font-semibold">Already have a spec?</h2>
      <p className="mt-0.5 max-w-[62ch] text-[13px] text-ink-muted">
        A JSON Schema, a YAML field list, or a simple map of field to type. It
        opens in the builder so you can check what was read before saving.
      </p>

      <div className="mt-3 flex gap-1 rounded-md border border-line bg-sunken p-0.5">
        {(["file", "paste"] as const).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setMode(option)}
            aria-pressed={mode === option}
            className={cn(
              "flex-1 rounded px-3 py-1.5 text-[13px] font-medium transition-colors",
              mode === option
                ? "bg-surface text-ink shadow-[0_1px_2px_rgb(20_34_33/0.06)]"
                : "text-ink-muted hover:text-ink",
            )}
          >
            {option === "file" ? "Upload a file" : "Paste it"}
          </button>
        ))}
      </div>

      {mode === "file" ? (
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            takeFile(event.dataTransfer.files);
          }}
          className={cn(
            "mt-3 rounded-lg border border-dashed px-5 py-6 text-center transition-colors",
            dragging ? "border-accent bg-accent-soft" : "border-line-strong",
          )}
        >
          <p className="text-[13.5px] text-ink-muted">Drop a .json or .yaml file here</p>
          <Button size="sm" className="mt-2.5" disabled={busy} onClick={() => inputRef.current?.click()}>
            {busy ? "Reading…" : "Choose a spec file"}
          </Button>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED.join(",")}
            onChange={(event) => {
              takeFile(event.target.files);
              // Reset so the same file can be chosen twice.
              event.target.value = "";
            }}
            className="hidden"
          />
        </div>
      ) : (
        <div className="mt-3">
          <Textarea
            aria-label="Schema spec"
            rows={9}
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={EXAMPLE}
            className="[&_textarea]:raw"
          />
          <div className="mt-2 flex flex-wrap gap-2">
            <Button
              size="sm"
              disabled={busy || !text.trim()}
              onClick={() => void run(() => api.schemas.importText(text))}
            >
              {busy ? "Reading…" : "Read this spec"}
            </Button>
            <Button size="sm" variant="quiet" disabled={busy} onClick={() => setText(EXAMPLE)}>
              Use the example
            </Button>
          </div>
        </div>
      )}

      {error && (
        <p
          role="alert"
          className="mt-3 rounded-md border border-problem/30 bg-problem-soft px-3.5 py-2.5 text-[13px] text-problem"
        >
          {error}
        </p>
      )}
    </section>
  );
}
