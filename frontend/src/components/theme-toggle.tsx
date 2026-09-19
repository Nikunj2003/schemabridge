"use client";

import { useSyncExternalStore } from "react";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";

const OPTIONS = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
] as const;

/** Light, dark or follow the device. The choice is remembered. */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  // The server cannot know the stored preference, so the control renders only
  // once the client has it — otherwise the wrong option looks selected. Read as
  // a hydration signal rather than set in an effect, which would cost an extra
  // render pass on every page.
  const hydrated = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );

  if (!hydrated) return <div className="h-8 w-[108px]" aria-hidden />;

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className="flex items-center gap-0.5 rounded-md border border-line bg-surface p-0.5"
    >
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          role="radio"
          aria-checked={theme === option.value}
          onClick={() => setTheme(option.value)}
          className={cn(
            "rounded px-2 py-1 text-[12px] font-medium transition-colors",
            theme === option.value ? "bg-accent-soft text-accent-ink" : "text-ink-muted hover:text-ink",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
