import { Skeleton } from "@/components/ui/skeleton";

/** Keeps the workbench chrome in place while an App Router segment resolves. */
export default function AppLoading() {
  return (
    <div className="mx-auto w-full max-w-[56rem] px-4 py-6 sm:px-8 sm:py-8" aria-busy="true">
      <span className="sr-only">Loading workspace…</span>
      <Skeleton className="h-7 w-48" />
      <Skeleton className="mt-3 h-4 max-w-[34rem]" />
      <div className="panel mt-7 space-y-4 px-5 py-5 sm:px-6">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    </div>
  );
}
