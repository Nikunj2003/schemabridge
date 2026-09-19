"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { cn } from "@/lib/utils";

const MAX_FILES = 3;

/** Bytes as a person reads them. 271 bytes is not "0 KB". */
function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function NewMigration() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState("");
  const [dragging, setDragging] = useState(false);
  const [tooMany, setTooMany] = useState<string | null>(null);

  function addFiles(incoming: FileList | null) {
    if (!incoming) return;
    const merged = [...files, ...Array.from(incoming)];
    // Say what was dropped rather than silently discarding the extras.
    if (merged.length > MAX_FILES) {
      setTooMany(
        `You can use up to ${MAX_FILES} files. The first ${MAX_FILES} are kept — remove one to swap it.`,
      );
    } else {
      setTooMany(null);
    }
    setFiles(merged.slice(0, MAX_FILES));
  }

  return (
    <div className="mx-auto max-w-2xl px-5 py-8 sm:px-8 sm:py-10">
      <h1 className="font-display text-[26px] font-semibold">New migration</h1>
      <p className="mt-1.5 text-[14.5px] text-ink-muted">
        Add the exports. SchemaBridge works out the columns — you do not map
        anything by hand.
      </p>

      <div className="mt-8 space-y-7">
        <Field
          label="Name this migration"
          hint="So you can find it later. Optional."
          placeholder="September employee import"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />

        <div>
          <p className="text-[13.5px] font-medium">Employee exports</p>
          <p className="mt-0.5 text-[13px] text-ink-muted">
            CSV or Excel, up to {MAX_FILES} files and 2 MB together. Different
            column names are fine.
          </p>

          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".csv,.xlsx"
            className="sr-only"
            aria-label="Choose employee exports"
            onChange={(event) => addFiles(event.target.files)}
          />

          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              addFiles(event.dataTransfer.files);
            }}
            className={cn(
              "mt-3 flex w-full flex-col items-center gap-1 rounded-lg border border-dashed px-6 py-8 transition-colors",
              dragging ? "border-accent bg-accent-soft" : "border-line-strong hover:border-accent/50",
            )}
          >
            <span className="text-[14.5px] font-medium">Drop files here, or choose them</span>
            <span className="text-[13px] text-ink-muted">
              No spreadsheet to hand? Start from a sample instead.
            </span>
          </button>

          {tooMany && (
            <p role="alert" className="mt-2 text-[13px] text-attention">
              {tooMany}
            </p>
          )}

          {files.length > 0 && (
            <ul className="mt-3 divide-y divide-line overflow-hidden rounded-lg border border-line">
              {files.map((file, index) => (
                <li key={`${file.name}-${index}`} className="flex items-center gap-3 bg-surface px-3 py-2.5">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[14px]">{file.name}</p>
                    <p className="text-[12.5px] text-ink-muted">{fileSize(file.size)}</p>
                  </div>
                  <Button
                    size="sm"
                    variant="quiet"
                    onClick={() => setFiles(files.filter((_, at) => at !== index))}
                  >
                    Remove
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-lg border border-line bg-sunken p-4">
          <p className="text-[13.5px] font-medium">Where the records go</p>
          <p className="mt-1 text-[13.5px] text-ink-muted">
            Into the <strong className="font-medium text-ink">Employee</strong> record —
            ID, name, work email, start date, and optionally end date, department
            and employment type — then sent to the{" "}
            <strong className="font-medium text-ink">Demo HR system</strong>, a
            stand-in so nothing reaches a real one.
          </p>
        </div>

        <div>
          <Button
            variant="primary"
            size="lg"
            disabled={files.length === 0}
            onClick={() => router.push("/app/migrations/mig-4821?preview=running")}
          >
            Start migration
          </Button>
          <p className="mt-2.5 text-[13px] leading-relaxed text-ink-muted">
            This lets SchemaBridge match the columns, make the fixes it can prove
            are safe, and send the finished records — pausing only for decisions
            that need you. There is no second approval step for records it is sure
            about.
          </p>
        </div>
      </div>
    </div>
  );
}
