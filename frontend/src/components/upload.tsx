/**
 * Starting a migration.
 *
 * One action, stated as what happens. The copy is deliberate: pressing this
 * authorises the agent to map, clean, and deliver — not to prepare something for
 * approval. Saying so here is what makes the absence of a later "confirm all"
 * step honest rather than surprising.
 */
"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const ACCEPT = ".csv,.xlsx";

export function Upload({ maxFiles }: { maxFiles: number }) {
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function accept(incoming: FileList | null) {
    if (!incoming) return;
    const chosen = Array.from(incoming).slice(0, maxFiles);
    setFiles(chosen);
    setError(null);
  }

  async function start() {
    if (files.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const run = await api.createRun(files);
      router.push(`/runs/${run.run_id}`);
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "The files could not be read.",
      );
      setBusy(false);
    }
  }

  return (
    <div className="w-full max-w-lg">
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        multiple
        className="sr-only"
        aria-label="Choose the client's exports"
        onChange={(event) => accept(event.target.files)}
      />

      {/* A button rather than a label: it is reachable by keyboard, announces
          itself, and does not depend on implicit label-to-input wiring for the
          one control the whole flow starts from. */}
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
          accept(event.dataTransfer.files);
        }}
        className={cn(
          "flex w-full cursor-pointer flex-col items-center justify-center rounded-xl",
          "border border-dashed px-6 py-10 text-center transition-colors",
          dragging ? "border-primary bg-primary/[0.04]" : "border-border hover:border-primary/40",
        )}
      >
        <span className="text-[14px] font-medium">Drop the client&rsquo;s exports here</span>
        <span className="mt-1.5 text-[12.5px] text-muted-foreground">
          CSV or Excel, up to {maxFiles} files. They can have different column names.
        </span>
      </button>

      {files.length > 0 && (
        <ul className="mt-3 space-y-1">
          {files.map((file) => (
            <li
              key={file.name}
              className="flex items-center gap-2 text-[12.5px] text-muted-foreground"
            >
              <span className="truncate text-foreground">{file.name}</span>
              <span className="shrink-0">{(file.size / 1024).toFixed(0)} KB</span>
            </li>
          ))}
        </ul>
      )}

      {error && (
        <p className="mt-3 text-[12.5px] text-destructive" role="alert">
          {error}
        </p>
      )}

      <div className="mt-5 flex items-center gap-3">
        <Button variant="primary" size="lg" onClick={start} disabled={busy || files.length === 0}>
          {busy ? "Reading the files…" : "Start the migration"}
        </Button>
        {files.length > 0 && !busy && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setFiles([]);
              if (inputRef.current) inputRef.current.value = "";
            }}
          >
            Clear
          </Button>
        )}
      </div>

      <p className="mt-3 text-[12px] leading-relaxed text-muted-foreground">
        The agent will work out the mapping, clean what it safely can, and send the
        records to the destination. It stops to ask you only when a decision needs
        judgement.
      </p>
    </div>
  );
}
