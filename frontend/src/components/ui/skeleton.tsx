import { cn } from "@/lib/utils";

/**
 * A quiet placeholder for content whose shape is known before its data arrives.
 *
 * The shape is decorative; the surrounding region supplies the loading message
 * and aria-busy state. Motion is opt-in through motion-safe, so the global
 * reduced-motion preference makes this a stable surface.
 */
export function Skeleton({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "block rounded-md bg-sunken motion-safe:animate-[skeleton-pulse_1.6s_ease-in-out_infinite]",
        className,
      )}
    />
  );
}

/** A layout-matched starting point for the schema editor and its route fallback. */
export function SchemaBuilderSkeleton() {
  return (
    <div className="mx-auto max-w-[56rem] px-4 py-6 sm:px-8 sm:py-8" aria-busy="true">
      <span className="sr-only">Loading schema editor…</span>
      <Skeleton className="h-7 w-40" />
      <Skeleton className="mt-3 h-4 max-w-[38rem]" />
      <div className="panel mt-7 px-5 py-5 sm:px-6">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="mt-3 h-10 w-full" />
        <Skeleton className="mt-5 h-4 w-20" />
        <Skeleton className="mt-3 h-10 w-full" />
      </div>
      <div className="mt-5 space-y-3">
        {[0, 1, 2].map((index) => (
          <div key={index} className="panel flex items-center gap-4 px-5 py-4">
            <Skeleton className="size-5 rounded-full" />
            <Skeleton className="h-4 w-40" />
            <Skeleton className="ml-auto h-7 w-16" />
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * The rule editor's own shape.
 *
 * Laid out to match what replaces it — one panel of controls, then the preview
 * panel — so the page does not visibly reflow the moment the schema arrives.
 */
export function RulesBuilderSkeleton() {
  return (
    <div className="mx-auto max-w-[56rem] px-4 py-6 sm:px-8 sm:py-8" aria-busy="true">
      <span className="sr-only">Loading rule editor…</span>
      <Skeleton className="h-7 w-32" />
      <Skeleton className="mt-3 h-4 max-w-[36rem]" />
      <div className="panel mt-6 px-5 py-5 sm:px-6">
        <Skeleton className="h-4 w-44" />
        <Skeleton className="mt-3 h-10 w-full" />
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
        <Skeleton className="mt-5 h-16 w-full" />
      </div>
      <div className="panel mt-5 px-5 py-5 sm:px-6">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="mt-3 h-4 max-w-[34rem]" />
        <Skeleton className="mt-4 h-9 w-32" />
      </div>
    </div>
  );
}
