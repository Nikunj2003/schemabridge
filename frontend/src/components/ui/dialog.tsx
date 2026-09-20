"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function focusableElements(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (element) => !element.hasAttribute("hidden") && element.getAttribute("aria-hidden") !== "true",
  );
}

/**
 * A small modal primitive for consequential, blocking work.
 *
 * It keeps keyboard focus inside while open, returns focus to the control that
 * opened it, and treats Escape and the visible close control as the same exit.
 */
export function Dialog({
  open,
  onOpenChange,
  title,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: ReactNode;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;

    returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const frame = window.requestAnimationFrame(() => {
      const dialog = dialogRef.current;
      if (!dialog) return;
      const [first] = focusableElements(dialog);
      (first ?? dialog).focus();
    });

    return () => {
      window.cancelAnimationFrame(frame);
      returnFocusRef.current?.focus();
      returnFocusRef.current = null;
    };
  }, [open]);

  if (!open) return null;

  const close = () => onOpenChange(false);

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/35 p-0 backdrop-blur-[1px] sm:items-center sm:p-6">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            close();
            return;
          }
          if (event.key !== "Tab") return;

          const dialog = dialogRef.current;
          if (!dialog) return;
          const elements = focusableElements(dialog);
          if (elements.length === 0) {
            event.preventDefault();
            dialog.focus();
            return;
          }

          const first = elements[0];
          const last = elements.at(-1);
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
          }
        }}
        className="max-h-[calc(100dvh-1rem)] w-full overflow-hidden rounded-t-lg border border-line bg-surface shadow-pop sm:max-h-[min(46rem,calc(100dvh-3rem))] sm:max-w-[52rem] sm:rounded-lg"
      >
        <div className="flex items-center justify-between gap-4 border-b border-line bg-sunken px-5 py-3 sm:px-6">
          <h2 id={titleId} className="text-[15px] font-semibold">{title}</h2>
          {/* Named after the dialog it closes: "Close review dialog" was hardcoded
              here and became wrong as soon as a second dialog reused this. */}
          <Button variant="quiet" size="sm" onClick={close} aria-label={`Close ${title.toLowerCase()}`}>
            Close
          </Button>
        </div>
        <div className="max-h-[calc(100dvh-5rem)] scroll-area sm:max-h-[calc(min(46rem,100dvh-3rem)-3.5rem)]">
          {children}
        </div>
      </div>
    </div>,
    document.body,
  );
}
