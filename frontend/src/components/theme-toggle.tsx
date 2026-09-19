"use client";

import { useSyncExternalStore } from "react";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";

const OPTIONS = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
] as const;

/**
 * Light, dark or follow the device. The choice is remembered.
 *
 * Three labelled segments where there is room, a single cycling button where
 * there is not — 213px of header chrome is what pushed a phone into sideways
 * scrolling.
 */
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

  if (!hydrated) {
    return (
      <>
        <div className="size-8 sm:hidden" aria-hidden />
        <div className="hidden h-8 w-[152px] sm:block" aria-hidden />
      </>
    );
  }

  const current = OPTIONS.find((option) => option.value === theme) ?? OPTIONS[2];
  const next = OPTIONS[(OPTIONS.indexOf(current) + 1) % OPTIONS.length];

  return (
    <>
      <button
        onClick={() => setTheme(next.value)}
        title={`Theme: ${current.label}. Switch to ${next.label}.`}
        className="flex size-8 shrink-0 items-center justify-center rounded-md border border-line bg-surface text-ink-muted hover:text-ink sm:hidden"
      >
        <Glyph value={current.value} />
        <span className="sr-only">Theme: {current.label}. Switch to {next.label}.</span>
      </button>

      <div
        role="radiogroup"
        aria-label="Colour theme"
        className="hidden items-center gap-0.5 rounded-md border border-line bg-surface p-0.5 sm:flex"
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
    </>
  );
}

function Glyph({ value }: { value: (typeof OPTIONS)[number]["value"] }) {
  const common = {
    viewBox: "0 0 24 24",
    className: "size-4",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  if (value === "dark") {
    return (
      <svg {...common}>
        <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" />
      </svg>
    );
  }
  if (value === "light") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6l1.4 1.4m10 10 1.4 1.4m0-12.8-1.4 1.4m-10 10-1.4 1.4" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <rect x="3" y="4.5" width="18" height="12" rx="1.6" />
      <path d="M8 20h8" />
    </svg>
  );
}
