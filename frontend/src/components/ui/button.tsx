"use client";

import Link from "next/link";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "quiet" | "danger";
type Size = "sm" | "md" | "lg";

const VARIANT: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-accent-hover",
  secondary: "border border-line-strong bg-surface text-ink hover:bg-sunken",
  quiet: "text-ink-muted hover:bg-sunken hover:text-ink",
  danger: "border border-problem/35 bg-problem-soft text-problem hover:border-problem/60",
};

const SIZE: Record<Size, string> = {
  sm: "h-8 gap-1.5 rounded-md px-2.5 text-[13px]",
  md: "h-9.5 gap-2 rounded-md px-3.5 text-[14px]",
  lg: "h-11 gap-2 rounded-md px-5 text-[15px]",
};

const BASE =
  "inline-flex shrink-0 items-center justify-center font-medium transition-colors disabled:pointer-events-none disabled:opacity-45";

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }) {
  return <button className={cn(BASE, VARIANT[variant], SIZE[size], className)} {...props} />;
}

export function ButtonLink({
  href,
  variant = "secondary",
  size = "md",
  className,
  children,
  ...rest
}: {
  href: string;
  variant?: Variant;
  size?: Size;
  className?: string;
  children: React.ReactNode;
} & Omit<React.ComponentProps<typeof Link>, "href" | "className" | "children">) {
  return (
    <Link href={href} className={cn(BASE, VARIANT[variant], SIZE[size], className)} {...rest}>
      {children}
    </Link>
  );
}
