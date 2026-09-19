import { Workbench } from "@/components/workbench/workbench";
import { TARGET_FIELDS } from "@/lib/target-fields";

/**
 * One migration.
 *
 * The workbench loads its own state, so this page renders immediately and the
 * run appears as it is fetched — the alternative would block the whole view on a
 * round trip that the polling loop is about to make anyway.
 */
export default async function RunPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  return <Workbench runId={runId} initial={null} fields={TARGET_FIELDS} />;
}
