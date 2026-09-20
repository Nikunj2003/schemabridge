/**
 * The mark: two source streams converging into one.
 *
 * It is the product's whole claim in one glyph, which is why it is drawn rather
 * than set as an initial in a rounded square.
 */
export function Logo({ className = "size-7" }: { className?: string }) {
  return (
    <span
      className={`inline-flex ${className} shrink-0 items-center justify-center rounded-md bg-accent text-white`}
      aria-hidden
    >
      <svg viewBox="0 0 24 24" className="size-[68%]" fill="none" stroke="currentColor">
        <path d="M4 6h5c4 0 3 6 7 6h4" strokeWidth="2" strokeLinecap="round" />
        <path d="M4 18h5c4 0 3-6 7-6h4" strokeWidth="2" strokeLinecap="round" />
        <circle cx="19.5" cy="12" r="2" fill="currentColor" stroke="none" />
      </svg>
    </span>
  );
}

export function Wordmark({ withMark = true }: { withMark?: boolean }) {
  return (
    <span className="flex items-center gap-2">
      {withMark && <Logo className="size-7" />}
      <span className="font-display text-[17px] font-semibold tracking-tight">
        Schema<span className="text-accent">Bridge</span>
      </span>
    </span>
  );
}
