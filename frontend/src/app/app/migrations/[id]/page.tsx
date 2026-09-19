import { RunView, type Moment } from "@/components/run/run-view";
import { HISTORY } from "@/lib/sample";

export default async function RunPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ preview?: string }>;
}) {
  const { id } = await params;
  const { preview } = await searchParams;

  const known = HISTORY.find((run) => run.id === id);
  const name = known?.name ?? "September employee import";

  // Which moment to open on. The real page will derive this from run state.
  const initial: Moment =
    preview === "running" ? "working" : preview === "done" ? "done" : known?.state === "done" ? "done" : "review";

  return <RunView name={name} initial={initial} />;
}
