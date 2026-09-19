import { AppShell } from "@/components/app/shell";
import { ACCOUNT, USAGE } from "@/lib/account";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell account={ACCOUNT} usage={USAGE}>
      {children}
    </AppShell>
  );
}
