import { z } from "zod";
import { request, mutate, type Page } from "./api";

const profile = z.object({
  version: z.number(),
  notes: z.string(),
  email: z.string(),
  phone: z.string(),
  profession: z.string(),
  sector: z.string(),
});
export const workspaceSchema = z.object({
  is_prospect: z.boolean(),
  id: z.string(),
  organization_id: z.string(),
  display_name: z.string(),
  kind: z.enum(["physical", "legal"]),
  version: z.number(),
  origin: z.string(),
  relationship_manager: z.string().nullable(),
  created_at: z.string(),
  identity: z.record(z.string(), z.string()),
  crm: profile,
  permissions: z.record(z.string(), z.boolean()),
  provenance: z.object({
    identity_source: z.string(),
    crm_source: z.string(),
    synchronization: z.literal("not_connected"),
    last_local_source_as_of: z.string().nullable(),
  }),
  ownership: z.record(z.string(), z.string()),
});
export type Workspace = z.infer<typeof workspaceSchema>;
export type Activity = {
  id: string;
  version: number;
  kind?: string;
  subject?: string;
  notes: string;
  occurred_at?: string;
  title?: string;
  amount?: string | null;
  currency?: string;
  status?: string;
  due_date?: string | null;
};
export type ImportOrganization = {
  id: string;
  name: string;
  upload: boolean;
  approve: boolean;
  policy_manage: boolean;
};
export type Template = {
  sheet: string;
  headers: (string | null)[];
  candidate_keys: number[];
  version: number;
};
export type Batch = {
  template_version: number;
  data_scope: string;
  id: string;
  template: string;
  digest: string;
  source_as_of: string;
  snapshot_kind: string;
  date_format: string;
  status: string;
  created_at: string;
  uploaded_by_id: string;
  published_at: string | null;
  published_by_id: string | null;
  policy_id: string | null;
  fixed_configuration_version: number | null;
  total: number;
  rejected: number;
  published_rows: number;
};
export type Policy = {
  template_version: number;
  data_scope: string;
  id: string;
  template: string;
  key_column: number;
  date_format: string;
  rationale: string;
  created_by_id: string;
  approved_by_id: string | null;
  approved_at: string | null;
  revoked_at: string | null;
};
export type Staging = {
  id: string;
  number: number;
  cells: Record<string, string | number | boolean | null>;
  errors: string[];
  warnings: string[];
  normalized_dates: Record<string, string>;
};
const root = (org: string) => `/api/imports/${encodeURIComponent(org)}/`;
const client = (id: string) => `/api/clients/${encodeURIComponent(id)}/`;
export const workspaceApi = {
  get: async (id: string, signal?: AbortSignal) =>
    workspaceSchema.parse(await request(client(id) + "workspace/", { signal })),
  createContext: () =>
    request<{ organizations: { id: string; name: string }[] }>(
      "/api/clients/context/",
    ),
  create: (data: unknown) =>
    mutate<{ id: string }>("/api/clients/create/", data),
  edit: (id: string, section: string, data: unknown) =>
    mutate(client(id) + section + "/", data, "PATCH"),
  activities: (
    id: string,
    category: string,
    page: number,
    signal?: AbortSignal,
  ) =>
    request<Page<Activity>>(client(id) + category + `/?page=${page}`, {
      signal,
    }),
  saveActivity: (
    id: string,
    category: string,
    data: unknown,
    activityId?: string,
  ) =>
    mutate(
      client(id) +
        category +
        "/" +
        (activityId ? `${encodeURIComponent(activityId)}/` : ""),
      data,
      activityId ? "PATCH" : "POST",
    ),
  accounts: (id: string, page: number, signal?: AbortSignal) =>
    request<
      Page<{
        id: string;
        external_id: string;
        source: string;
        source_as_of: string;
        product_label: string;
      }>
    >(client(id) + `accounts/?page=${page}`, { signal }),
};
export const importApi = {
  syntheticJob: (organizationId: string, batchId: string) => request<{status: 'pending' | 'complete' | 'blocked'; processed: number; last_error: string}>(`/api/clients/synthetic-import-jobs/${encodeURIComponent(batchId)}/?organization_id=${encodeURIComponent(organizationId)}`),
  syncSyntheticPage: (organization_id: string, batch_id: string, offset: number) =>
    mutate<{ next_offset: number | null; processed: number }>("/api/clients/synthetic-import-sync/", { organization_id, batch_id, offset }),
  context: () =>
    request<{
      organizations: ImportOrganization[];
      templates: Record<string, Template>;
      mode: string;
    }>("/api/imports/context/"),
  batches: (org: string, page = 1) =>
    request<Page<Batch>>(root(org) + `batches/?page=${page}`),
  preview: (org: string, id: string, page = 1, rejected = false) =>
    request<
      Page<Staging> & {
        batch: Batch;
        headers: (string | null)[];
        history: { action: string; timestamp: string }[];
        legacy_rule_unique?: boolean;
        policy_match: {status: string; reason: string; policy: Policy | null; legacy_policies?: Policy[]; configuration?: Policy; detail_code?: string};
      }
    >(
      root(org) +
        `batches/${id}/?page=${page}&rejected=${rejected ? "1" : "0"}`,
    ),
  policies: (org: string, view = "all", page = 1) => request<Policy[]>(root(org) + `policies/?view=${view}&page=${page}`),
  policy: (org: string, data: unknown) => mutate<Policy>(root(org) + "policies/", data),
  approve: (org: string, id: string, revoke = false) =>
    mutate(root(org) + `policies/${id}/${revoke ? "revoke" : "approve"}/`),
  publish: (
    org: string,
    id: string,
    skip_rejected: boolean,
  ) =>
    mutate<Batch>(root(org) + `batches/${id}/publish/`, {
      skip_rejected,
    }),
  upload: async (
    org: string,
    file: File,
    template: string,
    source_as_of: string,
    snapshot_kind: string,
    date_format = "ISO",
    data_scope = "legacy",
  ) => {
    const csrf = await request<{ csrfToken: string }>("/api/auth/csrf/");
    return request<Batch>(
      root(org) +
        `upload/?${new URLSearchParams({ template, source_as_of, snapshot_kind, date_format, data_scope })}`,
      {
        method: "POST",
        headers: {
          "X-CSRFToken": csrf.csrfToken,
          "Content-Type": "application/octet-stream",
        },
        body: file,
      },
    );
  },
  rejectionUrl: (org: string, id: string) =>
    root(org) + `batches/${id}/rejections/`,
};
