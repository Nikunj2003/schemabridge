"use client";

import { useEffect, useState } from "react";
import { SchemaBuilder } from "@/components/schema/builder";
import { api, type TargetSchema } from "@/lib/api";

/** Editing a saved schema. Loads it, then hands the draft to the builder. */
export function EditSchema({ schemaId }: { schemaId: string }) {
  const [schema, setSchema] = useState<TargetSchema | null>(null);
  const [limits, setLimits] = useState(40);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void (async () => {
      try {
        const [loaded, listing] = await Promise.all([
          api.schemas.read(schemaId),
          api.schemas.list(),
        ]);
        if (!live) return;
        setSchema(loaded);
        setLimits(listing.limits.max_fields);
      } catch (caught) {
        if (live) {
          setError(caught instanceof Error ? caught.message : "That schema could not be loaded.");
        }
      }
    })();
    return () => {
      live = false;
    };
  }, [schemaId]);

  if (error) {
    return (
      <div className="mx-auto max-w-[56rem] px-4 py-8 sm:px-8">
        <p
          role="alert"
          className="rounded-md border border-problem/30 bg-problem-soft px-4 py-3 text-[13.5px] text-problem"
        >
          {error}
        </p>
      </div>
    );
  }
  if (!schema) {
    return <p className="px-8 py-8 text-[13.5px] text-ink-muted">Loading…</p>;
  }
  // Keyed on the version so a reload after a save re-seeds the draft rather
  // than leaving the builder holding the previous revision's fields.
  return (
    <SchemaBuilder
      key={`${schema.schema_id}:${schema.version}`}
      source={schema}
      schemaId={schema.schema_id}
      maxFields={limits}
    />
  );
}
