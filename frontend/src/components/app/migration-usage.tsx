"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, type MigrationUsage } from "@/lib/api";

type MigrationUsageContextValue = {
  usage: MigrationUsage | null;
  error: string | null;
  refresh: () => Promise<MigrationUsage | null>;
};

const MigrationUsageContext = createContext<MigrationUsageContextValue | null>(null);

/** Server-authoritative migration allowance for this anonymous browser session. */
export function MigrationUsageProvider({ children }: { children: React.ReactNode }) {
  const [usage, setUsage] = useState<MigrationUsage | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await api.migrationUsage();
      setUsage(next);
      setError(null);
      return next;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Migration allowance is unavailable.");
      return null;
    }
  }, []);

  useEffect(() => {
    // Schedule after the provider has committed; React's lint rule correctly
    // rejects a synchronous state update from an effect body.
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  const value = useMemo(() => ({ usage, error, refresh }), [usage, error, refresh]);
  return <MigrationUsageContext.Provider value={value}>{children}</MigrationUsageContext.Provider>;
}

export function useMigrationUsage(): MigrationUsageContextValue {
  const value = useContext(MigrationUsageContext);
  if (!value) throw new Error("useMigrationUsage must be used inside MigrationUsageProvider.");
  return value;
}
