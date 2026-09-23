/**
 * 宠物与专属领养模块：建立伙伴（上传自己的宠物 / 原子独占领养）、公开主页读取。
 * live：照片以 multipart 上传，服务端校验格式与大小、剥离元数据、私有存储。
 * fixture：演示候选池；不上传照片（明确提示），不创建真实归属。
 */
import type { AdoptionCandidate, AdoptResult, PetPrivateSummary, PetPublicProfile, PhotoRequestResult, PhotoRequestView, PostPage, PublicPetView, PublicResident, PublicWorld } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { defineModule } from "@/shared/modules/types";
import { fixtureAdopt, fixtureCandidates } from "@/fixtures/adoption";
import { fixturePublicProfile } from "@/fixtures/social";
import { delay } from "@/fixtures/world";
import { AddCompanionPage, AdoptPage, OnboardingPage } from "./pages";
import { PendingEntryPage } from "./PendingEntryPage";
import { PublicPetPage, PublicWorldPage } from "./PublicWorldPage";
import { PhotoRequestsPage } from "./PhotoRequestsPage";

function fixtureResidents(): PublicResident[] {
  return fixtureCandidates().filter((candidate) => candidate.availability === "available").map((candidate) => ({
    pet_id: candidate.pet_id ?? `fx-resident-${candidate.candidate_id}`,
    candidate_id: candidate.candidate_id,
    name: candidate.name,
    species: candidate.species,
    personality: candidate.personality,
    dream: candidate.dream,
    origin: candidate.origin,
    source_note: candidate.source_note,
    residence: "演示居民驿站",
    city: "演示星球",
    living_since: "2026-09-22T00:00:00Z",
    presence: "at_home",
    doing: "在演示驿站休息",
    place_name: null,
    recent_posts: [],
  }));
}

export default defineModule({
  id: "pets",
  routes: [{ path: "pets/new", element: <AddCompanionPage /> }, { path: "photos", element: <PhotoRequestsPage /> }],
  bareRoutes: [
    { path: "onboarding", element: <OnboardingPage /> },
    { path: "onboarding/choice", element: <PendingEntryPage /> },
    { path: "adopt", element: <AdoptPage /> },
    { path: "world", element: <PublicWorldPage /> },
    { path: "world/residents/:petId", element: <PublicPetPage /> },
  ],
  services: {
    pets: {
      fixture: () => ({
        requestPhoto: async () => { throw ApiError.capability("pets.photo-request", "演示模式不能申请真实照片。"); },
        photoRequests: async () => { throw ApiError.capability("pets.photo-requests", "演示模式没有真实照片列表。"); },
        retryPhoto: async () => { throw ApiError.capability("pets.retry-photo", "演示模式不能重画真实照片。"); },
        publicWorld: async () => delay<PublicWorld>({
          server_time: "2026-09-22T00:00:00Z",
          entries: [
            { route: "browse", label: "先逛逛", needs_login: false, note: "演示公开世界" },
            { route: "own_pet", label: "带我的宠物来", needs_login: true, note: "演示模式不创建账号" },
            { route: "adopt", label: "认识新伙伴", needs_login: true, note: "演示居民" },
          ],
          residents: fixtureResidents(), recent_posts: [], living_residents: fixtureResidents().length, cache_seconds: 30, data_origin: "fixture",
        }),
        publicResidents: async () => delay(fixtureResidents()),
        publicPet: async (petId) => {
          const resident = fixtureResidents().find((item) => item.pet_id === petId);
          if (!resident) throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有找到这位居民。" });
          const view: PublicPetView = {
            profile: { pet_id: resident.pet_id, display_name: resident.name, species: resident.species, avatar_url: null, bio: resident.personality, origin_label: resident.source_note, visibility: "public", follower_count: 0, post_count: 0, viewer_follows: false, is_own: false, data_origin: "fixture" },
            resident, adoptable: true, posts: [],
          };
          return delay(view);
        },
        publicPetPosts: async () => delay<PostPage>({ items: [], next_cursor: null }),
        adoptionCandidates: () => delay(fixtureCandidates()),
        adopt: async (id, key) => delay(fixtureAdopt(id, key)),
        createOwn: async () => {
          throw ApiError.capability("pets.create_own", "演示模式不上传照片，也不创建真实宠物。");
        },
        publicProfile: async (petId) => {
          const profile = fixturePublicProfile(petId);
          if (!profile) throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有找到这只宠物的公开主页。" });
          return delay(profile);
        },
      }),
      live: ({ api }) => ({
        requestPhoto: (petId, body, key) => api.request<PhotoRequestResult>(`/pets/${encodeURIComponent(petId)}/photo-request`, { method: "POST", body, idempotencyKey: key }),
        photoRequests: (petId, signal) => api.request<PhotoRequestView[]>(`/pets/${encodeURIComponent(petId)}/photo-requests`, { signal }),
        retryPhoto: (petId, requestId) => api.request<PhotoRequestView[]>(`/pets/${encodeURIComponent(petId)}/photo-requests/${encodeURIComponent(requestId)}/retry-image`, { method: "POST" }),
        publicWorld: () => api.request<PublicWorld>("/public/world"),
        publicResidents: () => api.request<PublicResident[]>("/public/residents"),
        publicPet: (petId) => api.request<PublicPetView>(`/public/pets/${encodeURIComponent(petId)}`),
        publicPetPosts: (petId, cursor) => api.request<PostPage>(`/public/pets/${encodeURIComponent(petId)}/posts`, { query: { cursor } }),
        adoptionCandidates: () => api.request<AdoptionCandidate[]>("/adoption/candidates"),
        adopt: (id, key) => api.request<AdoptResult>("/adoption/adopt", { method: "POST", body: { candidate_id: id }, idempotencyKey: key }),
        createOwn: (input, key) => {
          const form = new FormData();
          form.set("name", input.name);
          form.set("species", input.species);
          if (input.photo) form.set("photo", input.photo);
          if (input.householdId) form.set("household_id", input.householdId);
          return api.request<PetPrivateSummary>("/pets", { method: "POST", body: form, idempotencyKey: key, timeoutMs: 30_000 });
        },
        publicProfile: (petId) => api.request<PetPublicProfile>(`/pets/${encodeURIComponent(petId)}/profile`),
      }),
    },
  },
});
