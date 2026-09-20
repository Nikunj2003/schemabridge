"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Wordmark } from "@/components/brand/logo";
import { useWorkspace } from "@/components/auth/workspace-provider";

/** Choose a private Google-backed workspace or the explicitly shared guest one. */
export default function SignInPage() {
  const router = useRouter();
  const { configured, signInWithGoogle, switchToSharedWorkspace } = useWorkspace();
  /**
   * Which choice is in flight.
   *
   * Neither button acknowledged a click. Measured on the deployed app, the guest
   * path takes ~0.7s to reach /app and Google ~1.0s before the browser leaves —
   * the SDK fetches OIDC metadata first — and for that whole second the page
   * looked unresponsive, so people press again. Naming the pending choice also
   * makes the second press a no-op rather than a second redirect.
   */
  const [pending, setPending] = useState<"google" | "guest" | null>(null);

  useEffect(() => {
    // Warm the destination. Both choices land in /app, and nothing on this page
    // links there, so without this the route's chunk is fetched only once the
    // button is pressed — which was most of the delay, not just an unacknowledged
    // click. Cheap and idempotent; failure only costs the head start.
    router.prefetch("/app");
  }, [router]);

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex h-14 shrink-0 items-center px-4 sm:px-8">
        <Link href="/"><Wordmark /></Link>
      </header>
      <main className="flex flex-1 items-center justify-center px-4 pb-16">
        <div className="w-full max-w-[24rem]">
          <h1 className="text-center font-display text-[25px]">Choose your workspace</h1>
          <p className="mt-2 text-center text-[14px] text-ink-muted">
            Google sign-in keeps your migrations private for seven days.
          </p>
          <div className="panel mt-7 space-y-3 px-5 py-6">
            <button
              onClick={() => {
                if (pending) return;
                setPending("google");
                // If the redirect fails the page stays put, so the button has to
                // become pressable again rather than stay stuck on "Redirecting".
                void signInWithGoogle().catch(() => setPending(null));
              }}
              disabled={!configured || pending !== null}
              aria-busy={pending === "google"}
              className="flex h-11 w-full items-center justify-center gap-3 rounded-md border border-line-strong bg-surface text-[14.5px] font-medium transition-colors hover:bg-sunken active:bg-sunken disabled:cursor-not-allowed disabled:opacity-55 disabled:hover:bg-surface"
            >
              {pending === "google" ? (
                <>
                  <Spinner /> Redirecting to Google…
                </>
              ) : (
                <>
                  <GoogleMark /> Continue with Google
                </>
              )}
            </button>
            {!configured && (
              <p className="text-center text-[12.5px] text-ink-muted">
                Google sign-in will be available after this deployment receives its Auth0 public settings.
              </p>
            )}
            <div className="my-1 h-px bg-line" />
            <button
              onClick={() => {
                if (pending) return;
                setPending("guest");
                switchToSharedWorkspace();
                router.push("/app");
              }}
              disabled={pending !== null}
              aria-busy={pending === "guest"}
              className="flex h-11 w-full items-center justify-center gap-2 rounded-md border border-line bg-sunken text-[14px] font-medium text-ink-muted transition-colors hover:bg-surface hover:text-ink active:bg-surface disabled:cursor-not-allowed disabled:opacity-60"
            >
              {pending === "guest" ? (
                <>
                  <Spinner /> Opening the shared workspace…
                </>
              ) : (
                "Continue in shared anonymous workspace"
              )}
            </button>
            <p className="text-center text-[12.5px] leading-relaxed text-ink-muted">
              Anonymous migrations, records, rules, and audit entries are visible to everyone using this shared workspace and are deleted after two days.
            </p>
          </div>
          <p className="mt-5 text-center text-[12.5px] leading-relaxed text-ink-subtle">
            Synthetic data only. Never upload credentials or secrets.
          </p>
        </div>
      </main>
    </div>
  );
}

/** A quiet indeterminate spinner, so a pending click is visibly pending. */
function Spinner() {
  return (
    <svg viewBox="0 0 24 24" className="size-4 shrink-0 animate-spin" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" opacity="0.25" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  );
}

function GoogleMark() {
  return (
    <svg viewBox="0 0 18 18" className="size-[18px] shrink-0" aria-hidden>
      <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92a8.78 8.78 0 0 0 2.68-6.62z" />
      <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.81.54-1.84.86-3.04.86a5.4 5.4 0 0 1-5.07-3.73H.96v2.33A9 9 0 0 0 9 18z" />
      <path fill="#FBBC05" d="M3.93 10.69a5.4 5.4 0 0 1 0-3.38V4.98H.96a9 9 0 0 0 0 8.04l2.97-2.33z" />
      <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.59A9 9 0 0 0 .96 4.98L3.93 7.3A5.4 5.4 0 0 1 9 3.58z" />
    </svg>
  );
}
