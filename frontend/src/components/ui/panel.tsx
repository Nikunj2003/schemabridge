import { cn } from "@/lib/utils";

/** A bordered surface. The workbench is built from these. */
export function Panel({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("rounded-xl border border-border bg-card", className)}>{children}</div>
  );
}

/** A section heading inside a panel. */
export function PanelHeader({
  title,
  count,
  action,
}: {
  title: string;
  count?: number;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex h-10 items-center gap-2 border-b border-border px-3">
      <h2 className="text-[12px] font-semibold tracking-wide text-foreground">{title}</h2>
      {count !== undefined && count > 0 && (
        <span className="rounded-full bg-primary/10 px-1.5 py-px text-[11px] font-semibold text-primary">
          {count}
        </span>
      )}
      <div className="flex-1" />
      {action}
    </div>
  );
}
