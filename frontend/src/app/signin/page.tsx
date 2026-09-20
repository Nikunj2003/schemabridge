"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Wordmark } from "@/components/brand/logo";
import { useWorkspace } from "@/components/auth/workspace-provider";

/** Choose a private Google-backed workspace or the explicitly shared guest one. */
export default function SignInPage() {
  const router = useRouter();
  const { configured, signInWithGoogle, switchToSharedWorkspace } = useWorkspace();

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
              onClick={() => void signInWithGoogle()}
              disabled={!configured}
              className="flex h-11 w-full items-center justify-center gap-3 rounded-md border border-line-strong bg-surface text-[14.5px] font-medium disabled:opacity-55"
            >
              <GoogleMark /> Continue with Google
            </button>
            {!configured && (
              <p className="text-center text-[12.5px] text-ink-muted">
                Google sign-in will be available after this deployment receives its Auth0 public settings.
              </p>
            )}
            <div className="my-1 h-px bg-line" />
            <button
              onClick={() => {
                switchToSharedWorkspace();
                router.push("/app");
              }}
              className="h-11 w-full rounded-md border border-line bg-sunken text-[14px] font-medium text-ink-muted hover:bg-surface"
            >
              Continue in shared anonymous workspace
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
