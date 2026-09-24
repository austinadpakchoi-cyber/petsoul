import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { isApiError } from "@/shared/api/errors";

/**
 * 统一远端状态：4xx 与“能力未接入”不重试；网络/5xx 最多重试 2 次。
 * 会话过期/未登录（AUTH_REQUIRED / SESSION_EXPIRED）时重新读取会话，由入口守卫带回欢迎页，不停留在一堆报错里。
 * 跨模块失效规则登记在 queryKeys 与 docs/contracts/MODULE-MAP.md。
 */
export function createQueryClient(): QueryClient {
  let client: QueryClient;
  const onAuthError = (error: unknown, key?: readonly unknown[]) => {
    if (!isApiError(error) || !error.isAuth) return;
    if (key && key[0] === "identity" && key[1] === "session") return; // 会话查询自身不再触发，避免循环
    void client.invalidateQueries({ queryKey: ["identity", "session"] });
  };
  client = new QueryClient({
    queryCache: new QueryCache({ onError: (error, query) => onAuthError(error, query.queryKey) }),
    mutationCache: new MutationCache({ onError: (error) => onAuthError(error) }),
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        refetchOnWindowFocus: true,
        retry: (failureCount, error) => {
          if (isApiError(error) && (!error.retryable || error.isCapabilityUnavailable || error.isAuth)) return false;
          return failureCount < 2;
        },
      },
      mutations: { retry: false },
    },
  });
  return client;
}

/** 查询键唯一登记处：模块用这些键，写操作成功后按 MODULE-MAP 的失效规则 invalidate。 */
export const queryKeys = {
  meta: ["platform", "meta"] as const,
  basemap: (key: string) => ["platform", "basemap", key] as const,
  session: ["identity", "session"] as const,
  settings: ["identity", "settings"] as const,
  publicWorld: ["public", "world"] as const,
  publicResidents: ["public", "residents"] as const,
  publicPet: (petId: string) => ["public", "pet", petId] as const,
  publicPetPosts: (petId: string, cursor?: string) => ["public", "pet-posts", petId, cursor ?? "first"] as const,
  photoRequestsFor: (userId: string, petId: string) => ["pets", "photo-requests", userId, petId] as const,
  characterFor: (userId: string, petId: string) => ["pets", "character", userId, petId] as const,
  invitePreview: (token: string) => ["households", "invite-preview", token] as const,
  households: (userId: string) => ["households", "list", userId] as const,
  householdDetail: (userId: string, householdId: string) => ["households", "detail", userId, householdId] as const,
  householdInvites: (userId: string, householdId: string) => ["households", "invites", userId, householdId] as const,
  householdRelationship: (userId: string, petId: string) => ["households", "relationship", userId, petId] as const,
  jobsFor: (userId: string, petId: string) => ["life", "jobs", userId, petId] as const,
  // 2026-09-24 删掉 credentialsFor（["life","credentials",…]）：回忆页改读卡包的 `credentials` 前缀之后，
  // 全仓只剩这一行定义、零引用。**删比留安全**——留着的话，谁拿它去失效缓存都会
  // **静默地什么都不失效**（没有任何数据存在那个键下），而那种失败不报错。
  /** TA 在外面遇到的朋友（关系，不是位置）。 */
  friendsFor: (userId: string, petId: string) => ["social", "friends", userId, petId] as const,
  /** TA 的 DNA：只按宠物分键；保存时的 expected_version 是并发凭据，不进 key。 */
  dnaFor: (userId: string, petId: string) => ["pets", "dna", userId, petId] as const,
  /** 统一世界状态（W1）：按请求者分键（返回的是这个人家里的全部宠物）。 */
  worldStateFor: (userId: string) => ["world", "state", userId] as const,
  credentialFor: (userId: string, petId: string, credentialId: string) => ["life", "credential", userId, petId, credentialId] as const,
  crops: ["farm", "crops"] as const,
  neighbors: ["farm", "neighbors"] as const,
  neighborHome: (homeId: string) => ["farm", "neighbor-home", homeId] as const,
  destinations: ["transport", "destinations"] as const,
  destinationsFor: (userId: string, petId: string) => ["transport", "destinations", userId, petId] as const,
  journeyPlan: (petId: string, destinationKey: string) => ["transport", "plan", petId, destinationKey] as const,
  journeySuggestions: (userId: string, petId: string) => ["transport", "suggestions", userId, petId] as const,
  guidesFor: (userId: string, petId: string) => ["transport", "guides", userId, petId] as const,
  guide: (guideId: string) => ["transport", "guide", guideId] as const,
  home: ["world", "home"] as const,
  homeFor: (userId: string, petId: string) => ["world", "home", userId, petId] as const,
  homePlace: (petId: string) => ["world", "home-place", petId] as const,
  journeyMap: (petId: string, scenario?: string) => ["transport", "journey-map", petId, scenario ?? "default"] as const,
  leg: (legId: string) => ["transport", "leg", legId] as const,
  mediaSession: (sessionId: string) => ["companion-media", "session", sessionId] as const,
  visit: (visitId: string) => ["world", "visit", visitId] as const,
  foodPreference: (petId: string, subject: string) => ["food", "preference", petId, subject] as const,
  foodRecommendations: (key: string) => ["food", "recommendations", key] as const,
  foodRecommendation: (id: string) => ["food", "recommendation", id] as const,
  reception: (sessionId: string) => ["reception", "session", sessionId] as const,
  homeWelcome: (petId: string) => ["reception", "home-welcome", petId] as const,
  circleFeed: ["social", "feed"] as const,
  post: (postId: string) => ["social", "post", postId] as const,
  petPosts: (petId: string) => ["social", "pet-posts", petId] as const,
  petProfile: (petId: string) => ["social", "pet-profile", petId] as const,
  messages: (petId: string) => ["communicator", "messages", petId] as const,
  messagesFor: (userId: string, petId: string) => ["communicator", "messages", userId, petId] as const,
  collection: ["economy", "collection"] as const,
  collectionFor: (userId: string, petId: string) => ["economy", "collection", userId, petId] as const,
  adoption: ["pets", "adoption"] as const,
  drivingStatus: ["driving", "status"] as const,
  drivingStatusFor: (userId: string, petId: string) => ["driving", "status", userId, petId] as const,
  drivingCurriculum: ["driving", "curriculum"] as const,
  drivingSession: (sessionId: string) => ["driving", "session", sessionId] as const,
  drivingHistory: ["driving", "history"] as const,
  credentials: ["credentials", "list"] as const,
} as const;
