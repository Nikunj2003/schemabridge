import { MigrationUsageProvider } from "@/components/app/migration-usage";
import { AppShell } from "@/components/app/shell";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <MigrationUsageProvider>
      <AppShell>{children}</AppShell>
    </MigrationUsageProvider>
  );
}
