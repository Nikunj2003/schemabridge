"use client";

import { type AppState, Auth0Provider, useAuth0 } from "@auth0/auth0-react";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { configureAccessTokenProvider, resetWorkspace } from "@/lib/api";

/**
 * Which workspace the browser is acting as.
 *
 * `authenticated` is a private, Google-backed workspace. `anonymous` is one
 * workspace shared by every guest, so its migrations, schemas, rules and audit
 * are deliberately visible to all of them.
 */
type WorkspaceMode = "anonymous" | "authenticated";

type WorkspaceContextValue = {
  mode: WorkspaceMode;
  /** Whether this deployment has Auth0's public settings, so sign-in can work. */
  configured: boolean;
  isLoading: boolean;
  displayName: string;
  signInWithGoogle: () => Promise<void>;
  signOut: () => void;
  switchToSharedWorkspace: () => void;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

const domain = process.env.NEXT_PUBLIC_AUTH0_DOMAIN;
const clientId = process.env.NEXT_PUBLIC_AUTH0_CLIENT_ID;
const audience = process.env.NEXT_PUBLIC_AUTH0_AUDIENCE;

const GUEST_LABEL = "Shared anonymous workspace";

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  // Without the public settings there is nothing to sign in against, so the app
  // runs as a guest rather than showing a button that cannot work.
  if (!domain || !clientId || !audience) {
    return <GuestWorkspaceProvider>{children}</GuestWorkspaceProvider>;
  }
  return (
    <Auth0Provider
      domain={domain}
      clientId={clientId}
      authorizationParams={{
        audience,
        scope: "openid profile email migrations:read migrations:write",
        redirect_uri: typeof window === "undefined" ? undefined : window.location.origin,
      }}
      useRefreshTokens
      // Persisted, so a reload or a returning visit does not silently drop the
      // session — with `memory` the person appeared signed out after any refresh.
      // The stored refresh token is rotating and therefore single-use, which is
      // what makes this an acceptable trade for a token in browser storage.
      cacheLocation="localstorage"
      onRedirectCallback={(state?: AppState) => {
        // A client-side navigation, not a full page load: `location.replace`
        // reloaded the whole app, which is why the landing page flashed for a
        // second before /app appeared. `history.replaceState` is not enough
        // either — it moves the address bar without telling the router.
        redirectTo(returnTarget(state?.returnTo));
      }}
    >
      <ConfiguredWorkspaceProvider>{children}</ConfiguredWorkspaceProvider>
    </Auth0Provider>
  );
}

/**
 * How to navigate after the callback, installed by the subtree that has the
 * router. A module-level handle rather than a hook, because `onRedirectCallback`
 * is a prop of the provider itself and so sits outside any component that could
 * call `useRouter`.
 */
let navigate: ((path: string) => void) | null = null;

function redirectTo(path: string) {
  if (navigate) {
    navigate(path);
    return;
  }
  // Before the router is available, a hard navigation is still correct.
  window.location.replace(path);
}

/** Where to land after Google returns.
 *
 * Only a same-origin path is honoured: `returnTo` survives a round trip through
 * the identity provider, so treating it as a URL would be an open redirect.
 * Signing in from the sign-in page itself has to go on to the app rather than
 * back to the page whose job is already done.
 */
function returnTarget(returnTo?: string): string {
  if (!returnTo || !returnTo.startsWith("/") || returnTo.startsWith("//")) return "/app";
  return returnTo === "/signin" || returnTo === "/" ? "/app" : returnTo;
}

function GuestWorkspaceProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    configureAccessTokenProvider(null);
    // These are inlined at build time, so a deployment built before they were
    // set has no way to sign anyone in. Saying so in the console turns a dead
    // button into a diagnosable one.
    if (process.env.NODE_ENV !== "test") {
      console.warn(
        "Auth0 is not configured in this build: NEXT_PUBLIC_AUTH0_DOMAIN, " +
          "NEXT_PUBLIC_AUTH0_CLIENT_ID and NEXT_PUBLIC_AUTH0_AUDIENCE must be " +
          "present at build time. Running in the shared guest workspace.",
      );
    }
  }, []);
  const value = useMemo<WorkspaceContextValue>(
    () => ({
      mode: "anonymous",
      configured: false,
      isLoading: false,
      displayName: GUEST_LABEL,
      signInWithGoogle: async () => undefined,
      signOut: () => undefined,
      switchToSharedWorkspace: () => undefined,
    }),
    [],
  );
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

function ConfiguredWorkspaceProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    navigate = (path: string) => router.replace(path);
    return () => {
      navigate = null;
    };
  }, [router]);

  const { error, isAuthenticated, isLoading, user, loginWithRedirect, logout, getAccessTokenSilently } =
    useAuth0();
  /**
   * Set when a signed-in person deliberately chooses the shared workspace.
   *
   * The mode is derived from this and Auth0's own state rather than mirrored into
   * state by an effect, so there is one source of truth for which workspace the
   * API client is speaking to.
   */
  const [preferGuest, setPreferGuest] = useState(false);
  const mode: WorkspaceMode = isAuthenticated && !preferGuest ? "authenticated" : "anonymous";

  /**
   * Whether to hold the page back rather than render a route.
   *
   * `isLoading` covers the whole handoff: the SDK runs `handleRedirectCallback`
   * and `onRedirectCallback` inside its initialisation, so it stays true from the
   * moment Google returns until the redirect to /app has been issued. That is
   * what stops the landing page painting at the callback URL, and it also means
   * no page renders before its workspace is known.
   *
   * Deliberately not derived from the `code` and `state` parameters. Reading
   * `window.location` during render was the bug that stranded this on
   * "Signing you in…" — React never re-evaluated it, so once the redirect
   * stripped the parameters the gate stayed shut until a manual refresh — and
   * `useSearchParams` cannot be used this high in the tree without forcing every
   * page out of static prerendering.
   *
   * A failed handoff clears it too, because the SDK finishes loading and reports
   * the failure through `error` rather than staying in flight.
   */
  const awaitingWorkspace = isLoading;

  useEffect(() => {
    // Nothing may be fetched until Auth0 has finished restoring the session.
    // Declaring "no token" too early would send the first request to the shared
    // guest workspace and show its runs under a private account.
    if (isLoading) {
      resetWorkspace();
      return;
    }
    // The API client attaches a bearer token only in personal mode; guest
    // requests deliberately carry none, which is what selects the shared
    // workspace server-side.
    configureAccessTokenProvider(
      mode === "authenticated" ? async () => getAccessTokenSilently() : null,
    );
  }, [getAccessTokenSilently, isLoading, mode]);

  const value = useMemo<WorkspaceContextValue>(
    () => ({
      mode,
      configured: true,
      isLoading,
      displayName:
        mode === "authenticated" && user
          ? user.name || user.email || "Signed-in workspace"
          : GUEST_LABEL,
      signInWithGoogle: async () => {
        setPreferGuest(false);
        await loginWithRedirect({
          // Where they were, unless that is the sign-in page itself.
          appState: { returnTo: returnTarget(pathname) },
          // Names the connection, so Universal Login goes straight to Google
          // rather than offering it among other options.
          authorizationParams: { connection: "google-oauth2" },
        });
      },
      signOut: () => {
        setPreferGuest(false);
        logout({ logoutParams: { returnTo: window.location.origin } });
      },
      switchToSharedWorkspace: () => setPreferGuest(true),
    }),
    [isLoading, loginWithRedirect, logout, mode, pathname, user],
  );
  return (
    <WorkspaceContext.Provider value={value}>
      {awaitingWorkspace ? <SigningIn error={error} /> : children}
    </WorkspaceContext.Provider>
  );
}

/** Shown only while the sign-in handoff completes, in place of any real page. */
function SigningIn({ error }: { error?: Error }) {
  if (error) {
    return (
      <div className="flex min-h-dvh items-center justify-center px-6 bg-canvas" role="alert">
        <div className="max-w-[26rem] text-center">
          <p className="text-[14.5px] font-medium">Sign-in did not complete</p>
          <p className="mt-1.5 text-[13.5px] text-ink-muted">{error.message}</p>
          <a
            href="/signin"
            className="mt-4 inline-block text-[13.5px] font-medium text-accent underline-offset-4 hover:underline"
          >
            Try again
          </a>
        </div>
      </div>
    );
  }
  return (
    <div className="flex min-h-dvh items-center justify-center bg-canvas" role="status">
      <p className="text-[14px] text-ink-muted">Signing you in…</p>
    </div>
  );
}

export function useWorkspace(): WorkspaceContextValue {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace must be used inside WorkspaceProvider.");
  return value;
}
