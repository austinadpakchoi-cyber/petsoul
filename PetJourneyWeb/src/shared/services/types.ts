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
} from "@/shared/contracts";
import type { ApiClient } from "@/shared/api/client";
import type { DataMode } from "@/shared/config/env";

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
  settings(): Promise<SettingsView>;
  updateSettings(patch: SettingsUpdateInput): Promise<SettingsView>;
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
}

export interface LifeService {
  jobs(petId: string, signal?: AbortSignal): Promise<JobRecord[]>;
  credentials(petId: string, signal?: AbortSignal): Promise<CredentialSummary[]>;
  credential(credentialId: string, signal?: AbortSignal): Promise<CredentialDetail>;
}

/** 共同生活状态：家园权威快照（宠物唯一位置、守护、钱包摘要、欢迎细节）。 */
export interface WorldService {
  home(petId?: string | null, signal?: AbortSignal): Promise<HomeSnapshot>;
}

/** 到访：一次到访贯穿地图/店内/通讯/动态；推荐不等于到访。 */
export interface VisitService {
  visit(visitId: string): Promise<Visit>;
  act(visitId: string, body: VisitActionRequest, idempotencyKey: string): Promise<Visit>;
  /** 到店前改去寻味推荐的分店：行程版本 +1，旧推荐待复核。 */
  choose(visitId: string, body: VisitChoiceRequest, idempotencyKey: string): Promise<JourneyMapSnapshot>;
}

/** 统一物资与账本：钱包只从 HomeSnapshot.wallet 读取；这里是库存/收藏。 */
export interface EconomyService {
  collection(petId?: string | null, signal?: AbortSignal): Promise<CollectionItem[]>;
  /** 集市：仓库、杂货铺收购价、今天的居民订单（都是 NPC；玩家挂牌未开放）。 */
  market(): Promise<MarketView>;
  sell(itemKey: string, qty: number, idempotencyKey: string): Promise<MarketResult>;
  fulfill(orderId: string, idempotencyKey: string): Promise<MarketResult>;
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
}

export interface CommunicatorService {
  thread(petId: string): Promise<MessageThread>;
  send(petId: string, body: SendMessageRequest): Promise<MessageSummary>;
}

/**
 * 爪爪驾校（契约 0.3.0，规格 docs/contracts/DRIVING-SCHOOL-v1.md）：正式成绩只由服务端决定——
 * 科一科四服务端批改；科二科三上传操作记录、服务端复算。客户端不上报分数。
 */
export interface DrivingSchoolService {
  status(petId?: string | null, signal?: AbortSignal): Promise<DrivingSchoolStatus>;
  curriculum(): Promise<SchoolCurriculum>;
  enroll(): Promise<DrivingSchoolStatus>;
  createSession(body: SessionCreateRequest, idempotencyKey: string): Promise<SchoolSession>;
  session(sessionId: string): Promise<SchoolSession>;
  begin(sessionId: string): Promise<SchoolSession>;
  answer(sessionId: string, body: AnswerRequest): Promise<AnswerResult>;
  inputs(sessionId: string, body: InputChunk): Promise<InputResult>;
  pause(sessionId: string): Promise<SchoolSession>;
  submit(sessionId: string): Promise<SchoolSession>;
  abandon(sessionId: string, confirm: boolean): Promise<SchoolSession>;
  history(): Promise<SessionBrief[]>;
  ceremony(): Promise<CeremonyResult>;
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
