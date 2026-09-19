import Link from "next/link";
import { Wordmark } from "@/components/brand/logo";

/**
 * Sign in.
 *
 * One way in, on its own page: Google through Auth0. No password fields, no
 * email capture, nothing to read past before deciding.
 */
export default function SignInPage() {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex h-14 shrink-0 items-center px-4 sm:px-8">
        <Link href="/">
          <Wordmark />
        </Link>
      </header>

      <main className="flex flex-1 items-center justify-center px-4 pb-16">
        <div className="w-full max-w-[24rem]">
          <h1 className="text-center font-display text-[25px]">Sign in to SchemaBridge</h1>
          <p className="mt-2 text-center text-[14px] text-ink-muted">
            Your migrations and decisions are saved to your account.
          </p>

          <div className="panel mt-7 px-5 py-6">
            {/* Wired to the NextAuth Auth0 route next; disabled rather than
                pretending to work. */}
            <button
              disabled
              className="flex h-11 w-full items-center justify-center gap-3 rounded-md border border-line-strong bg-surface text-[14.5px] font-medium disabled:opacity-55"
            >
              <GoogleMark />
              Continue with Google
            </button>

            <p className="mt-4 text-center text-[12.5px] text-ink-muted">
              Google sign-in is being connected. Until then the app runs without
              an account.
            </p>

            <Link
              href="/app"
              className="mt-4 block text-center text-[13.5px] font-medium text-accent underline-offset-4 hover:underline"
            >
              Continue without signing in
            </Link>
          </div>

          <p className="mt-5 text-center text-[12.5px] leading-relaxed text-ink-subtle">
            Synthetic data only. Uploads are deleted after 48 hours.
          </p>
        </div>
      </main>
    </div>
  );
}

/** Google's mark, in its own colours as their brand terms require. */
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
