"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { fileSize } from "@/lib/present";
import { TARGET_FIELDS } from "@/lib/target-fields";
import { cn } from "@/lib/utils";

const ACCEPTED = [".csv", ".xlsx"];
const MAX_FILES = 4;

/**
 * Starting a migration.
 *
 * Not a mapping wizard: the destination is fixed and the whole point is that
 * the agent works out the columns. So this asks for files and states plainly
 * what pressing the button authorises.
 */
export function NewMigration() {
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

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
      const run = await api.createRun(files);
      router.push(`/app/migrations/${run.run_id}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The migration could not be started.");
      setStarting(false);
    }
  };

  const required = TARGET_FIELDS.filter((field) => field.required);

  return (
    <div className="mx-auto max-w-[52rem] px-4 py-6 sm:px-8 sm:py-8">
      <h1 className="font-display text-[24px]">New migration</h1>
      <p className="mt-1.5 text-[14px] text-ink-muted">
        Add your employee exports. The agent works out which column means what —
        you do not map anything by hand.
      </p>

      <section className="mt-6">
        <h2 className="text-[14px] font-semibold">Your files</h2>
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
          <p role="status" className="mt-3 rounded-md border border-attention/30 bg-attention-soft px-4 py-2.5 text-[13px] text-attention">
            {notice}
          </p>
        )}
      </section>

      <section className="mt-7">
        <h2 className="text-[14px] font-semibold">Where the records go</h2>
        <div className="panel mt-3 px-4 py-4">
          <p className="text-[13.5px] font-medium">Demo HR system</p>
          <p className="mt-0.5 text-[13px] text-ink-muted">
            A simulated destination inside this app. Nothing leaves it.
          </p>
          <p className="mt-3 text-[12.5px] text-ink-muted">
            Every employee needs {required.map((f) => f.label.toLowerCase()).join(", ")}.
            Anything else your files carry is matched where it fits and left out
            where it does not.
          </p>
        </div>
      </section>

      {error && (
        <p role="alert" className="mt-5 rounded-md border border-problem/30 bg-problem-soft px-4 py-3 text-[13.5px] text-problem">
          {error}
        </p>
      )}

      <div className="mt-7 border-t border-line pt-5">
        <Button variant="primary" size="lg" disabled={files.length === 0 || starting} onClick={() => void start()}>
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
