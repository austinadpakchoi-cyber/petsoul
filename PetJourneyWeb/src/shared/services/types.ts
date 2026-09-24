/**
 * 统一服务边界。页面只通过 useServices() 拿到这些接口；fixture/live 由注册表按模式选择，
 * 模块不自己决定“连不上就用假数据”。未提供 live 实现的服务在 live 模式下抛 CAPABILITY_UNAVAILABLE。
 */

import type {
  AdoptionCandidate,
  AdoptResult,
  AnswerRequest,
  AnswerResult,
  BasemapView,
  CareNote,
  CollectionItem,
  Comment,
  CommentPage,
  CommentRequestInput,
  CompanionCommandRequest,
  CompanionHeartbeatRequest,
  CompanionSession,
  CeremonyResult,
  CharacterRegenerateCommandInput,
  CharacterRegenerateResult,
  CharacterState,
  CropInfo,
  DestinationOption,
  DrivingSchoolStatus,
  EntryIntentRequest,
  FarmActionRequestInput,
  FarmActionResult,
  FoodFeedbackInput,
  FoodPreference,
  FoodRecommendation,
  FoodRecommendationList,
  FoodRecommendationRequestInput,
  FriendSummary,
  HabitatKind,
  HomePlaceView,
  HomeSnapshot,
  HomeWelcome,
  HouseholdBrief,
  HouseholdDetail,
  HouseholdInvite,
  HouseholdSettingsRequestInput,
  InviteCreated,
  InputChunk,
  InputResult,
  IntakeConfirmationRequest,
  IntakeConfirmationResult,
  InvitePreview,
  JobRecord,
  CredentialSummary,
  CredentialDetail,
  PetRelationship,
  PetRelationshipRequestInput,
  JourneyLeg,
  JourneyMapSnapshot,
  JourneySuggestion,
  MarketResult,
  MarketView,
  MemoryCorrectionRequestInput,
  MemoryCorrectionResult,
  MessageSummary,
  MessageThread,
  NeighborHomeSummary,
  NeighborHomeView,
  OnboardingState,
  Participation,
  PatrolResult,
  PetPrivateSummary,
  PetDNAInput,
  PetDNAView,
  PetSpecies,
  PetPublicProfile,
  PhotoRequestCommand,
  PhotoRequestResult,
  PhotoRequestView,
  Post,
  PostPage,
  PublicPetView,
  PublicResident,
  PublicWorld,
  PreferenceSubject,
  ReactionRequest,
  ReceptionSession,
  ReceptionStartRequest,
  ReceptionTurnRequest,
  SchoolCurriculum,
  SchoolSession,
  SendMessageRequest,
  SessionBrief,
  SessionCreateRequest,
  SessionState,
  SettingsUpdateInput,
  SettingsView,
  StealRequest,
  StealResult,
  TripPlanPreview,
  TravelGuide,
  Visit,
  VisitActionRequest,
  VisitChoiceRequest,
  WebMeta,
  WorldState,
} from "@/shared/contracts";
import type { ApiClient } from "@/shared/api/client";
import type { DataMode } from "@/shared/config/env";
import type { TravelWish } from "@/shared/contracts";

/** 地图范围（WGS-84）与容器尺寸（CSS 像素），用于请求真实底图。 */
export interface BasemapRequest {
  south: number;
  west: number;
  north: number;
  east: number;
  width: number;
  height: number;
}

export interface PlatformService {
  meta(): Promise<WebMeta>;
  /** 旅途地图的真实底图（服务端代理高德静态地图）；不可用时 available=false，由地图组件退回示意图。 */
  basemap(request: BasemapRequest): Promise<BasemapView>;
}

export interface SessionService {
  current(): Promise<SessionState>;
  register(username: string, password: string, displayName?: string, entry?: EntryIntentRequest | null): Promise<SessionState>;
  login(username: string, password: string): Promise<SessionState>;
  logout(): Promise<void>;
  /** 入住阶段：needs_companion → reception_optional → ready_to_move_in → active。 */
  onboarding(): Promise<OnboardingState>;
  /** 入住激活（与接待分开；不会自动出发）。public_posts 由主人明确选择。 */
  moveIn(publicPosts: boolean, habitat?: HabitatKind | null, petId?: string | null): Promise<OnboardingState>;
  /** 服务端当前家庭住处及当下真正开放的环境；不可据设计图列出可选片区。 */
  homePlace(petId?: string | null): Promise<HomePlaceView>;
  settings(petId?: string | null): Promise<SettingsView>;
  updateSettings(patch: SettingsUpdateInput, petId?: string | null): Promise<SettingsView>;
}

/** 家庭邀请沿唯一服务边界；访客可预览，接受必须有原始令牌与显式确认。 */
export interface HouseholdService {
  list(): Promise<HouseholdBrief[]>;
  detail(householdId: string, signal?: AbortSignal): Promise<HouseholdDetail>;
  updateSettings(householdId: string, body: HouseholdSettingsRequestInput): Promise<HouseholdDetail>;
  invites(householdId: string): Promise<HouseholdInvite[]>;
  createInvite(householdId: string, relationHint: string | null): Promise<InviteCreated>;
  revokeInvite(householdId: string, inviteId: string): Promise<HouseholdInvite>;
  relationship(petId: string): Promise<PetRelationship>;
  saveRelationship(petId: string, body: PetRelationshipRequestInput): Promise<PetRelationship>;
  previewInvite(token: string): Promise<InvitePreview>;
  acceptInvite(token: string): Promise<HouseholdDetail>;
  /** 管理员移除成员（DELETE /households/{id}/members/{user_id}，204）；立即生效。拒绝：409 last_admin、403 admin_required、404 member_not_found。 */ removeMember(householdId: string, userId: string): Promise<void>;
  /** 管理员调整成员角色（PUT …/members/{user_id}/role），返回最新家庭详情。拒绝：409 last_admin（最后一位管理员不能降级）、403 admin_required、404 member_not_found。 */ setMemberRole(householdId: string, userId: string, role: import("@/shared/contracts").HouseholdRole): Promise<HouseholdDetail>;
}

export interface LifeService {
  jobs(petId: string, signal?: AbortSignal): Promise<JobRecord[]>;
  credentials(petId: string, signal?: AbortSignal): Promise<CredentialSummary[]>;
  credential(credentialId: string, signal?: AbortSignal): Promise<CredentialDetail>;
}

/** 共同生活状态：家园权威快照（宠物唯一位置、守护、钱包摘要、欢迎细节）。 */
export interface WorldService {
  home(petId?: string | null, signal?: AbortSignal): Promise<HomeSnapshot>;
  /**
   * 统一世界状态（W1，纯读）：请求者家里每只宠物此刻在做什么、在哪（坐标 WGS-84，画到高德上要换 GCJ-02）。
   * position 无出处时整个为 null；pose 只给事实能确定的（作息接不上是 idle，不是 sleeping）；since/until 是“这一阶段”的起止。
   */
  state(petId?: string, signal?: AbortSignal): Promise<WorldState>;
}

/** 到访：一次到访贯穿地图/店内/通讯/动态；推荐不等于到访。 */
export interface VisitService {
  visit(visitId: string): Promise<Visit>;
  act(visitId: string, body: VisitActionRequest, idempotencyKey: string): Promise<Visit>;
  /** 到店前改去寻味推荐的分店：行程版本 +1，旧推荐待复核。 */
  choose(visitId: string, body: VisitChoiceRequest, idempotencyKey: string): Promise<JourneyMapSnapshot>;
  /** TRV-06：GET /travel/wish（合同 §23.4）——当前宠物的活动心愿；没有活动心愿时返回 200 + null，不包对象（I 已定）。 */
  travelWish(petId: string | null, signal?: AbortSignal): Promise<TravelWish | null>;
}

/** 统一物资与账本：钱包只从 HomeSnapshot.wallet 读取；这里是库存/收藏。 */
export interface EconomyService {
  collection(petId?: string | null, signal?: AbortSignal): Promise<CollectionItem[]>;
  /** 集市：仓库、杂货铺收购价、今天的居民订单（都是 NPC；玩家挂牌未开放）。 */
  market(petId?: string | null): Promise<MarketView>;
  sell(itemKey: string, qty: number, idempotencyKey: string, petId?: string | null): Promise<MarketResult>;
  fulfill(orderId: string, idempotencyKey: string, petId?: string | null): Promise<MarketResult>;
}

export interface FarmService {
  act(body: FarmActionRequestInput, idempotencyKey: string): Promise<FarmActionResult>;
  crops(): Promise<CropInfo[]>;
  neighbors(): Promise<NeighborHomeSummary[]>;
  neighborHome(homeId: string): Promise<NeighborHomeView>;
  steal(body: StealRequest, idempotencyKey: string): Promise<StealResult>;
  /** 宠物外出时主人巡院：短时守护，有冷却。 */
  patrol(): Promise<PatrolResult>;
}

export interface NewPetInput {
  name: string;
  species: PetSpecies;
  photo: File | Blob | null;
  /** Only for adding another pet to a verified household; the server checks admin role. */
  householdId?: string;
}

export interface PetsService {
  /** 主人主动拍摄：受理不等于任务排队或照片完成。 */
  requestPhoto(petId: string, body: PhotoRequestCommand, idempotencyKey: string): Promise<PhotoRequestResult>;
  /** 纯读列表；不触发任务。 */
  photoRequests(petId: string, signal?: AbortSignal): Promise<PhotoRequestView[]>;
  /** 仅 failed/unknown 由用户显式重画，响应 200 也可能只是原状态。 */
  retryPhoto(petId: string, requestId: string): Promise<PhotoRequestView[]>;
  /** 无需登录的星球入口与居民公开生活；正式模式只读服务端公开投影。 */
  publicWorld(): Promise<PublicWorld>;
  publicResidents(): Promise<PublicResident[]>;
  publicPet(petId: string): Promise<PublicPetView>;
  publicPetPosts(petId: string, cursor?: string): Promise<PostPage>;
  adoptionCandidates(): Promise<AdoptionCandidate[]>;
  adopt(candidateId: string, idempotencyKey: string): Promise<AdoptResult>;
  /** 上传自己的宠物：照片私有存储，只经鉴权接口访问。 */
  createOwn(input: NewPetInput, idempotencyKey: string): Promise<PetPrivateSummary>;
  publicProfile(petId: string): Promise<PetPublicProfile>;
  /** 专属世界形象：纯读，绝不触发生成（首次形象由有授权的上传自动排队）。 */
  character(petId: string, signal?: AbortSignal): Promise<CharacterState>;
  /** 可选的“调整形象”；幂等键走 Idempotency-Key 请求头（与其他写命令一致），同一次调整恢复时复用。 */
  regenerateCharacter(petId: string, body: CharacterRegenerateCommandInput, idempotencyKey: string): Promise<CharacterRegenerateResult>;
  /** 生成 / 重画证件照（CR-6C2B-IDPHOTO）：无请求体，幂等键走请求头。存量宠物不批量补，老宠物只能靠它拿到第一张。 */
  regenerateIdPhoto(petId: string, idempotencyKey: string): Promise<CharacterRegenerateResult>;
  /** TA 的 DNA（只给家人）：没保存过时是整理出的草稿（confirmed=false，页面提示“待你确认”）；behavior 是由原话整理出的倾向，每条带出处。 */
  dna(petId: string, signal?: AbortSignal): Promise<PetDNAView>;
  /**
   * 整体保存（即确认）。expectedVersion 是读到的全家共用版本号（写入时的并发凭据，不属于数据身份，不要放进 query key）；
   * 家人在这之后改过会 409（details.reason = dna_version_conflict，带 current_version），页面应重新读取再改。
   */
  saveDna(petId: string, body: PetDNAInput, expectedVersion: number | null): Promise<PetDNAView>;
  timeline(petId: string, signal?: AbortSignal): Promise<import("@/shared/contracts").TimelineItem[]>;
}

export interface ReceptionService {
  start(body: ReceptionStartRequest, idempotencyKey: string): Promise<ReceptionSession>;
  get(sessionId: string): Promise<ReceptionSession>;
  addTurn(sessionId: string, body: ReceptionTurnRequest, idempotencyKey: string): Promise<ReceptionSession>;
  skip(sessionId: string): Promise<ReceptionSession>;
  confirm(body: IntakeConfirmationRequest, idempotencyKey: string): Promise<IntakeConfirmationResult>;
  notes(petId: string): Promise<CareNote[]>;
  correct(noteId: string, body: MemoryCorrectionRequestInput, idempotencyKey: string): Promise<MemoryCorrectionResult>;
  homeWelcome(petId: string): Promise<HomeWelcome>;
}

export interface TransportQueryOptions {
  /** 仅 fixture 模式有效：选择演示场景。live 模式忽略。 */
  fixtureScenario?: string;
}

export interface TransportService {
  journeyMap(petId: string, options?: TransportQueryOptions): Promise<JourneyMapSnapshot>;
  /** 出发站：目的地、旅费、往返时长（真实经过时间）。 */
  destinations(petId?: string | null, signal?: AbortSignal): Promise<DestinationOption[]>;
  plan(destinationKey: string, petId?: string | null, signal?: AbortSignal): Promise<TripPlanPreview>;
  suggestions(petId?: string | null, signal?: AbortSignal): Promise<JourneySuggestion[]>;
  guides(petId?: string | null, signal?: AbortSignal): Promise<TravelGuide[]>;
  guide(guideId: string, signal?: AbortSignal): Promise<TravelGuide>;
  suggest(destinationKey: string, petId?: string | null): Promise<JourneySuggestion>;
  depart(destinationKey: string, idempotencyKey: string, petId?: string | null): Promise<JourneyMapSnapshot>;
  leg(legId: string, options?: TransportQueryOptions): Promise<JourneyLeg>;
  /** fixture 场景清单；live 返回空数组。 */
  fixtureScenarios(): Array<{ id: string; label: string }>;
}

export interface CompanionMediaService {
  session(sessionId: string): Promise<CompanionSession>;
  join(sessionId: string, deviceId: string): Promise<Participation>;
  command(sessionId: string, body: CompanionCommandRequest, idempotencyKey: string): Promise<CompanionSession>;
  heartbeat(sessionId: string, body: CompanionHeartbeatRequest): Promise<Participation>;
  leave(sessionId: string, deviceId: string): Promise<Participation>;
}

export interface FoodDiscoveryService {
  preference(petId: string, subject: PreferenceSubject, variant?: string): Promise<FoodPreference>;
  recommend(body: FoodRecommendationRequestInput, variant?: string): Promise<FoodRecommendationList>;
  recommendation(recommendationId: string): Promise<FoodRecommendation>;
  feedback(body: FoodFeedbackInput, idempotencyKey: string): Promise<FoodFeedbackInput>;
  savePreference(subject: PreferenceSubject, preference: FoodPreference, idempotencyKey: string): Promise<FoodPreference>;
  /** fixture 偏好组（清淡/浓郁）；live 返回空数组。 */
  fixtureVariants(): Array<{ id: string; label: string }>;
}

export interface SocialService {
  feed(cursor?: string): Promise<PostPage>;
  petPosts(petId: string, cursor?: string): Promise<PostPage>;
  post(postId: string): Promise<Post>;
  comments(postId: string, cursor?: string): Promise<CommentPage>;
  react(postId: string, body: ReactionRequest, idempotencyKey: string): Promise<Post>;
  comment(postId: string, body: CommentRequestInput, idempotencyKey: string): Promise<Comment>;
  removePost(postId: string): Promise<void>;
  removeComment(commentId: string): Promise<void>;
  follow(petId: string, follow: boolean): Promise<void>;
  /** 屏蔽某条动态或评论的作者（不暴露对方账号）。 */
  block(target: { post_id?: string; comment_id?: string }): Promise<void>;
  report(targetKind: "post" | "comment", targetId: string, reason: string): Promise<void>;
  /**
   * TA 在外面遇到的朋友（只给这只宠物的家人）：见过几次、多熟、最近在哪见过。
   * `last_place` 只说明“在哪见过”，**不是实时位置**——地图上不得据此画点，朋友的位置只来自世界状态接口（W1/W2）。
   */
  friends(petId: string, signal?: AbortSignal): Promise<FriendSummary[]>;
  /** 我的举报 GET /reports/mine（要登录）。类型用契约 MyReports；路由还没关联 response_model，取回后逐条校验（坏条目丢掉）；没装运营后台时是能力未接入。 */ myReports(signal?: AbortSignal): Promise<import("@/shared/contracts").MyReports>;
}

export interface CommunicatorService {
  thread(petId: string): Promise<MessageThread>;
  send(petId: string, body: SendMessageRequest): Promise<MessageSummary>;
  /** 平台公告 GET /announcements（登录与否都能读）。类型用契约 AnnouncementFeed；路由还没关联 response_model，取回后逐条校验（坏条目丢掉）；source = not_installed 是读不到，不是没有公告。 */ announcements(signal?: AbortSignal): Promise<import("@/shared/contracts").AnnouncementFeed>;
}

/**
 * 爪爪驾校（契约 0.3.0，规格 docs/contracts/DRIVING-SCHOOL-v1.md）：正式成绩只由服务端决定——
 * 科一科四服务端批改；科二科三上传操作记录、服务端复算。客户端不上报分数。
 */
export interface DrivingSchoolService {
  status(petId?: string | null, signal?: AbortSignal): Promise<DrivingSchoolStatus>;
  curriculum(): Promise<SchoolCurriculum>;
  enroll(petId?: string | null): Promise<DrivingSchoolStatus>;
  createSession(body: SessionCreateRequest, idempotencyKey: string, petId?: string | null): Promise<SchoolSession>;
  session(sessionId: string, petId?: string | null): Promise<SchoolSession>;
  begin(sessionId: string, petId?: string | null): Promise<SchoolSession>;
  answer(sessionId: string, body: AnswerRequest, petId?: string | null): Promise<AnswerResult>;
  inputs(sessionId: string, body: InputChunk, petId?: string | null): Promise<InputResult>;
  pause(sessionId: string, petId?: string | null): Promise<SchoolSession>;
  submit(sessionId: string, petId?: string | null): Promise<SchoolSession>;
  abandon(sessionId: string, confirm: boolean, petId?: string | null): Promise<SchoolSession>;
  history(petId?: string | null): Promise<SessionBrief[]>;
  ceremony(petId?: string | null): Promise<CeremonyResult>;
}

export interface ServiceMap {
  platform: PlatformService;
  session: SessionService;
  households: HouseholdService;
  life: LifeService;
  world: WorldService;
  visits: VisitService;
  economy: EconomyService;
  farm: FarmService;
  pets: PetsService;
  reception: ReceptionService;
  transport: TransportService;
  companionMedia: CompanionMediaService;
  food: FoodDiscoveryService;
  social: SocialService;
  communicator: CommunicatorService;
  driving: DrivingSchoolService;
}

export type ServiceKey = keyof ServiceMap;

export interface ServiceContext {
  mode: DataMode;
  api: ApiClient;
}

export type ServiceFactory<K extends ServiceKey> = (ctx: ServiceContext) => ServiceMap[K];

export type ServiceContributions = {
  [K in ServiceKey]?: { fixture?: ServiceFactory<K>; live?: ServiceFactory<K> };
};
