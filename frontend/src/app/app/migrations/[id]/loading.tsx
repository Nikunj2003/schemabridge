import { Skeleton } from "@/components/ui/skeleton";

/** A route-transition shell that matches the first migration snapshot. */
export default function MigrationLoading() {
  return (
    <div className="mx-auto max-w-[62rem] px-4 py-6 sm:px-8 sm:py-8" aria-busy="true">
      <span className="sr-only">Opening migration…</span>
      <Skeleton className="h-3 w-28" />
      <Skeleton className="mt-3 h-7 w-[min(34rem,88%)]" />
      <Skeleton className="mt-2 h-4 w-[min(28rem,70%)]" />
      <div className="panel mt-5 grid gap-5 px-5 py-5 sm:grid-cols-5 sm:px-6">
        {[0, 1, 2, 3, 4].map((index) => <Skeleton key={index} className="h-10 w-full" />)}
      </div>
      <div className="panel mt-5 space-y-4 px-5 py-5 sm:px-6">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-[82%]" />
      </div>
    </div>
  );
}
