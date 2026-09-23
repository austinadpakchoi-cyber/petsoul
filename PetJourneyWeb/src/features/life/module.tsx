import type { CredentialDetail, CredentialSummary, JobRecord } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { defineModule } from "@/shared/modules/types";
import { LifeHubPage } from "./LifeHubPage";
import { CredentialPage } from "./CredentialPage";

export default defineModule({
  id: "life",
  routes: [
    { path: "life", element: <LifeHubPage /> },
    { path: "credentials/:credentialId", element: <CredentialPage /> },
  ],
  services: {
    life: {
      live: ({ api }) => ({
        jobs: (petId, signal) => api.request<JobRecord[]>("/jobs", { query: { pet_id: petId }, signal }),
        credentials: (petId, signal) => api.request<CredentialSummary[]>("/credentials", { query: { pet_id: petId }, signal }),
        credential: (credentialId, signal) => api.request<CredentialDetail>(`/credentials/${encodeURIComponent(credentialId)}`, { signal }),
      }),
      fixture: () => ({
        jobs: async () => { throw ApiError.capability("life.jobs", "演示模式没有真实工作记录。"); },
        credentials: async () => { throw ApiError.capability("life.credentials", "演示模式没有真实证件。"); },
        credential: async () => { throw ApiError.capability("life.credential", "演示模式没有真实证件详情。"); },
      }),
    },
  },
});
