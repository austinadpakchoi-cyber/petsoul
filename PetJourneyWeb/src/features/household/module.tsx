import type { HouseholdBrief, HouseholdDetail, HouseholdInvite, InviteCreated, InvitePreview, PetRelationship } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { defineModule } from "@/shared/modules/types";
import { JoinPage } from "./JoinPage";
import { HouseholdPage } from "./HouseholdPage";

export default defineModule({
  id: "household",
  bareRoutes: [{ path: "join", element: <JoinPage /> }],
  routes: [{ path: "households/manage", element: <HouseholdPage /> }],
  services: {
    households: {
      live: ({ api }) => ({
        list: () => api.request<HouseholdBrief[]>("/households"),
        detail: (householdId, signal) => api.request<HouseholdDetail>(`/households/${encodeURIComponent(householdId)}`, { signal }),
        updateSettings: (householdId, body) => api.request<HouseholdDetail>(`/households/${encodeURIComponent(householdId)}/settings`, { method: "PATCH", body }),
        invites: (householdId) => api.request<HouseholdInvite[]>(`/households/${encodeURIComponent(householdId)}/invites`),
        createInvite: (householdId, relationHint) => api.request<InviteCreated>(`/households/${encodeURIComponent(householdId)}/invites`, { method: "POST", body: { role: "caregiver", relation_hint: relationHint, ttl_hours: 72 } }),
        revokeInvite: (householdId, inviteId) => api.request<HouseholdInvite>(`/households/${encodeURIComponent(householdId)}/invites/${encodeURIComponent(inviteId)}`, { method: "DELETE" }),
        relationship: (petId) => api.request<PetRelationship>(`/pets/${encodeURIComponent(petId)}/relationship`),
        saveRelationship: (petId, body) => api.request<PetRelationship>(`/pets/${encodeURIComponent(petId)}/relationship`, { method: "PUT", body }),
        previewInvite: (token) => api.request<InvitePreview>("/invites/preview", { method: "POST", body: { token } }),
        acceptInvite: (token) => api.request<HouseholdDetail>("/invites/accept", { method: "POST", body: { token } }),
      }),
      fixture: () => ({
        list: async () => [],
        detail: async () => { throw ApiError.capability("households.detail", "演示模式没有真实家庭管理资料。"); },
        updateSettings: async () => { throw ApiError.capability("households.settings", "演示模式不能修改家庭设置。"); },
        invites: async () => [],
        createInvite: async () => { throw ApiError.capability("households.invites", "演示模式不能生成家庭邀请。"); },
        revokeInvite: async () => { throw ApiError.capability("households.invites", "演示模式不能撤销家庭邀请。"); },
        relationship: async () => { throw ApiError.capability("households.relationship", "演示模式没有真实称呼资料。"); },
        saveRelationship: async () => { throw ApiError.capability("households.relationship", "演示模式不能保存真实称呼。"); },
        previewInvite: async () => { throw ApiError.capability("households.invites", "演示模式没有真实家庭邀请。"); },
        acceptInvite: async () => { throw ApiError.capability("households.invites", "演示模式不能加入真实家庭。"); },
      }),
    },
  },
});
