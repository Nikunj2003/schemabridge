import { Suspense } from "react";
import { NewSchema } from "@/components/schema/new-schema";
import { SchemaBuilderSkeleton } from "@/components/ui/skeleton";

export default function NewSchemaPage() {
  return (
    // `?from=` is read on the client, so this page cannot be prerendered without
    // a boundary to fall back to while the search params resolve.
    <Suspense fallback={<SchemaBuilderSkeleton />}>
      <NewSchema />
    </Suspense>
  );
}
