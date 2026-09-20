"use client";

import { useRef, useSyncExternalStore } from "react";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";

const OPTIONS = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "Use device setting" },
] as const;

type ThemeOption = (typeof OPTIONS)[number];

/** A remembered colour preference with radio semantics on larger screens. */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const radioRefs = useRef<(HTMLButtonElement | null)[]>([]);
  // The server cannot know the stored preference. Keep the pre-hydration shape
  // stable so an option never appears selected before the client takes over.
  const hydrated = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );

  if (!hydrated) {
    return (
      <>
        <div className="size-8 sm:hidden" aria-hidden />
        <div className="hidden h-10 w-[112px] sm:block" aria-hidden />
      </>
    );
  }

  const currentIndex = Math.max(0, OPTIONS.findIndex((option) => option.value === theme));
  const current = OPTIONS[currentIndex];
  const next = OPTIONS[(currentIndex + 1) % OPTIONS.length];

  const choose = (index: number, focus = false) => {
    setTheme(OPTIONS[index].value);
    if (focus) radioRefs.current[index]?.focus();
  };

  const handleRadioKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      nextIndex = (index + 1) % OPTIONS.length;
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      nextIndex = (index - 1 + OPTIONS.length) % OPTIONS.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = OPTIONS.length - 1;
    }

    if (nextIndex !== null) {
      event.preventDefault();
      choose(nextIndex, true);
    }
  };

  return (
    <>
      <button
        type="button"
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
        className="theme-picker hidden items-center sm:flex"
      >
        {OPTIONS.map((option, index) => {
          const selected = index === currentIndex;
          return (
            <button
              key={option.value}
              ref={(element) => {
                radioRefs.current[index] = element;
              }}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-label={option.label}
              tabIndex={selected ? 0 : -1}
              title={option.label}
              onClick={() => choose(index)}
              onKeyDown={(event) => handleRadioKeyDown(event, index)}
              className={cn(
                "theme-picker-cell flex size-10 items-center justify-center text-ink-muted transition-colors",
                selected ? "theme-picker-cell-selected text-accent-ink" : "hover:text-ink",
              )}
            >
              <Glyph value={option.value} />
              <span className="sr-only">{option.label}</span>
            </button>
          );
        })}
      </div>
    </>
  );
}

function Glyph({ value }: { value: ThemeOption["value"] }) {
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
