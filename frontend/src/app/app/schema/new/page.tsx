import { Suspense } from "react";
import { NewSchema } from "@/components/schema/new-schema";

export default function NewSchemaPage() {
  return (
    // `?from=` is read on the client, so this page cannot be prerendered without
    // a boundary to fall back to while the search params resolve.
    <Suspense fallback={<p className="px-8 py-8 text-[13.5px] text-ink-muted">Loading…</p>}>
      <NewSchema />
    </Suspense>
  );
}
