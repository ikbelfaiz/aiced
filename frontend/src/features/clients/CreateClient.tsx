import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { DataEditor } from "../../components/DataEditor";
import { Dialog, StatePanel } from "../../components/ui";
import { workspaceApi } from "../../lib/workspace-api";

export function CreateClient({ close }: { close: () => void }) {
  const context = useQuery({
    queryKey: ["client-create-context"],
    queryFn: workspaceApi.createContext,
  });
  const navigate = useNavigate();
  const cache = useQueryClient();
  if (
    context.isPending ||
    context.isError ||
    !context.data?.organizations.length
  )
    return (
      <Dialog title="Créer un client AICED" onClose={close}>
        <StatePanel
          kind={
            context.isPending ? "loading" : context.isError ? "error" : "denied"
          }
          title={
            context.isPending
              ? "Chargement des organisations…"
              : context.isError
                ? "Organisations inaccessibles"
                : "Aucune organisation autorisée"
          }
          retry={context.isError ? () => void context.refetch() : undefined}
        />
      </Dialog>
    );
  return (
    <DataEditor
      title="Créer un client AICED"
      description="Identité locale AICED. Aucun rapprochement ni changement de données Carthago."
      fields={[
        {
          name: "organization_id",
          label: "Organisation",
          required: true,
          options: context.data.organizations.map((org) => ({
            value: org.id,
            label: org.name,
          })),
        },
        {
          name: "kind",
          label: "Type de personne",
          options: [
            { value: "physical", label: "Personne physique" },
            { value: "legal", label: "Personne morale" },
          ],
        },
        {
          name: "first_name",
          label: "Prénom (personne physique)",
          maxLength: 100,
        },
        { name: "last_name", label: "Nom (personne physique)", maxLength: 100 },
        {
          name: "legal_name",
          label: "Raison sociale (personne morale)",
          maxLength: 200,
        },
      ]}
      close={close}
      save={async (values) => {
        const identity =
          values.kind === "physical"
            ? { first_name: values.first_name, last_name: values.last_name }
            : { legal_name: values.legal_name };
        const result = await workspaceApi.create({
          organization_id: values.organization_id,
          kind: values.kind,
          ...identity,
        });
        await cache.invalidateQueries({ queryKey: ["clients"] });
        navigate(`/clients/${result.id}`);
      }}
    />
  );
}
