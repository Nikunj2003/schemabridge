import { EditRule } from "@/components/rules/edit-rule";

export default async function EditRulePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <EditRule ruleId={id} />;
}
