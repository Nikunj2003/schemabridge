/**
 * Buttons.
 *
 * Adapted from the author's codenex-ui project (MIT). See THIRD_PARTY_NOTICES.
 */
"use client";

import { cn } from "@/lib/utils";

type Variant = "primary" | "outline" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-primary text-primary-foreground hover:bg-primary/90 active:scale-[0.99] shadow-sm",
  outline:
    "border border-border bg-card text-foreground hover:bg-secondary hover:border-border",
  ghost: "text-muted-foreground hover:text-foreground hover:bg-secondary",
  danger:
    "border border-destructive/30 bg-destructive/5 text-destructive hover:bg-destructive/10",
};

const SIZES: Record<Size, string> = {
  sm: "h-7 px-2.5 text-[12px] gap-1.5 rounded-md",
  md: "h-9 px-3.5 text-[13px] gap-2 rounded-lg",
  lg: "h-11 px-5 text-[14px] gap-2 rounded-lg",
};

export function Button({
  variant = "outline",
  size = "md",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
}) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center font-medium transition-colors",
        "disabled:pointer-events-none disabled:opacity-50",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    />
  );
}
