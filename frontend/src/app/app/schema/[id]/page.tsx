import { EditSchema } from "@/components/schema/edit-schema";

export default async function EditSchemaPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <EditSchema schemaId={id} />;
}
