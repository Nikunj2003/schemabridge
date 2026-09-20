import { cn } from "@/lib/utils";

/**
 * The one alignment rule for workspace pages.
 *
 * Page-specific inner measures can still constrain prose or forms, but headings,
 * loading shells, and primary panels all start on the same responsive frame.
 */
export function ContentFrame({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mx-auto w-full max-w-[62rem] px-4 py-6 sm:px-6 sm:py-8 lg:px-8", className)}>
      {children}
    </div>
  );
}
