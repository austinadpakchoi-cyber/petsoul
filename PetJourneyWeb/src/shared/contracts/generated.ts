/* eslint-disable */
// 由 scripts/gen_web_contract.py 从 PetJourneyBackend/app/schemas/web 生成，请勿手改。
// 修改契约：改 Python DTO → 运行 `npm run contract:gen` → 更新 WEB-CONTRACT 文档。

export const WEB_CONTRACT_VERSION = "0.4.5";
export const WEB_API_PREFIX = "/api/v1/web";

/** UTC ISO 8601，例如 2026-09-22T07:35:00Z */
export type IsoDateTime = string;
/** YYYY-MM-DD */
export type IsoDate = string;
/** 把有服务端默认值的字段变为可选：用于请求体。 */
export type WithOptional<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;

export type DataOrigin = "fixture" | "live";
export const DataOriginValues = ["fixture", "live"] as const;

export type WebErrorCode = "AUTH_REQUIRED" | "SESSION_EXPIRED" | "CSRF_FAILED" | "FORBIDDEN" | "NOT_FOUND" | "VALIDATION_FAILED" | "CONFLICT" | "VERSION_CONFLICT" | "IDEMPOTENCY_KEY_REQUIRED" | "IDEMPOTENCY_KEY_REUSED" | "IDEMPOTENCY_IN_PROGRESS" | "CAPABILITY_UNAVAILABLE" | "NOT_CONFIGURED" | "RATE_LIMITED" | "UPSTREAM_UNAVAILABLE" | "INTERNAL_ERROR" | "USERNAME_TAKEN" | "INVALID_CREDENTIALS" | "ADOPTION_TAKEN" | "PET_NOT_ACTIVATED" | "DRIVING_BLOCKS_VIDEO" | "CONTROL_LEASE_HELD" | "ITINERARY_CHANGED" | "DRAFT_EXPIRED" | "INSUFFICIENT_FUNDS" | "ALREADY_TRAVELING" | "FARM_GUARDED" | "ALREADY_HAS_COMPANION" | "MEDIA_REJECTED";
export const WebErrorCodeValues = ["AUTH_REQUIRED", "SESSION_EXPIRED", "CSRF_FAILED", "FORBIDDEN", "NOT_FOUND", "VALIDATION_FAILED", "CONFLICT", "VERSION_CONFLICT", "IDEMPOTENCY_KEY_REQUIRED", "IDEMPOTENCY_KEY_REUSED", "IDEMPOTENCY_IN_PROGRESS", "CAPABILITY_UNAVAILABLE", "NOT_CONFIGURED", "RATE_LIMITED", "UPSTREAM_UNAVAILABLE", "INTERNAL_ERROR", "USERNAME_TAKEN", "INVALID_CREDENTIALS", "ADOPTION_TAKEN", "PET_NOT_ACTIVATED", "DRIVING_BLOCKS_VIDEO", "CONTROL_LEASE_HELD", "ITINERARY_CHANGED", "DRAFT_EXPIRED", "INSUFFICIENT_FUNDS", "ALREADY_TRAVELING", "FARM_GUARDED", "ALREADY_HAS_COMPANION", "MEDIA_REJECTED"] as const;

export type CapabilityStatus = "available" | "not_implemented" | "not_configured" | "disabled";
export const CapabilityStatusValues = ["available", "not_implemented", "not_configured", "disabled"] as const;

export type AuthMethod = "web_password" | "apple_bearer";
export const AuthMethodValues = ["web_password", "apple_bearer"] as const;

export type CoordSystem = "wgs84" | "gcj02";
export const CoordSystemValues = ["wgs84", "gcj02"] as const;

export type OnboardingStep = "needs_companion" | "reception_optional" | "ready_to_move_in" | "active";
export const OnboardingStepValues = ["needs_companion", "reception_optional", "ready_to_move_in", "active"] as const;

export type HouseholdRole = "admin" | "caregiver";
export const HouseholdRoleValues = ["admin", "caregiver"] as const;

export type InviteStatus = "pending" | "accepted" | "revoked" | "expired";
export const InviteStatusValues = ["pending", "accepted", "revoked", "expired"] as const;

export type PetJoinStep = "reception_optional" | "ready_to_move_in" | "moved_in";
export const PetJoinStepValues = ["reception_optional", "ready_to_move_in", "moved_in"] as const;

export type EntryKind = "browse" | "own_pet" | "adopt" | "invite";
export const EntryKindValues = ["browse", "own_pet", "adopt", "invite"] as const;

export type PetSpecies = "dog" | "cat" | "parrot" | "rabbit" | "hamster" | "bird" | "other";
export const PetSpeciesValues = ["dog", "cat", "parrot", "rabbit", "hamster", "bird", "other"] as const;

export type PetOrigin = "own_pet" | "adopted_original" | "adopted_real_archive";
export const PetOriginValues = ["own_pet", "adopted_original", "adopted_real_archive"] as const;

export type PetPresence = "not_activated" | "at_home" | "in_transit" | "at_destination" | "visiting" | "returning" | "unknown";
export const PetPresenceValues = ["not_activated", "at_home", "in_transit", "at_destination", "visiting", "returning", "unknown"] as const;

export type ProfileVisibility = "public" | "followers" | "private";
export const ProfileVisibilityValues = ["public", "followers", "private"] as const;

export type AdoptionAvailability = "available" | "reserved" | "adopted";
export const AdoptionAvailabilityValues = ["available", "reserved", "adopted"] as const;

export type BehaviorPolarity = "positive" | "negative" | "averse" | "uncertain";
export const BehaviorPolarityValues = ["positive", "negative", "averse", "uncertain"] as const;

export type BehaviorTraitStatus = "applied" | "negated" | "outweighed" | "uncertain";
export const BehaviorTraitStatusValues = ["applied", "negated", "outweighed", "uncertain"] as const;

export type PetRhythm = "regular" | "night_owl" | "early_bird" | "sleepy";
export const PetRhythmValues = ["regular", "night_owl", "early_bird", "sleepy"] as const;

export type PetSociability = "social" | "steady" | "homebody";
export const PetSociabilityValues = ["social", "steady", "homebody"] as const;

export type PhotoScene = "home" | "train" | "flight_adventure";
export const PhotoSceneValues = ["home", "train", "flight_adventure"] as const;

export type PhotoNarrative = "daily_life" | "fictional_adventure";
export const PhotoNarrativeValues = ["daily_life", "fictional_adventure"] as const;

export type CharacterStatus = "absent" | "queued" | "running" | "ready" | "failed" | "unknown";
export const CharacterStatusValues = ["absent", "queued", "running", "ready", "failed", "unknown"] as const;

export type CharacterReason = "no_reference_photo" | "species_unsupported" | "provider_unavailable" | "not_configured" | "pet_has_no_household" | "generated_reference_only" | "reference_changed" | "budget_denied" | "unknown_result" | "transparency_not_requested" | "attempts_exhausted" | "daily_cap" | "rejected" | "timeout" | "unconfirmed" | "already_queued" | "not_png" | "undecodable" | "interlaced_unsupported" | "palette_unsupported" | "bit_depth_unsupported" | "no_alpha_channel" | "opaque_background" | "checkerboard_drawn" | "empty_subject" | "multiple_subjects" | "subject_cut_off" | "subject_too_large" | "subject_too_small" | "too_large_to_check" | "photo_not_to_bottom" | "photo_headroom_off" | "photo_head_cut_off" | "photo_too_small" | "photo_wrong_shape" | "photo_blank";
export const CharacterReasonValues = ["no_reference_photo", "species_unsupported", "provider_unavailable", "not_configured", "pet_has_no_household", "generated_reference_only", "reference_changed", "budget_denied", "unknown_result", "transparency_not_requested", "attempts_exhausted", "daily_cap", "rejected", "timeout", "unconfirmed", "already_queued", "not_png", "undecodable", "interlaced_unsupported", "palette_unsupported", "bit_depth_unsupported", "no_alpha_channel", "opaque_background", "checkerboard_drawn", "empty_subject", "multiple_subjects", "subject_cut_off", "subject_too_large", "subject_too_small", "too_large_to_check", "photo_not_to_bottom", "photo_headroom_off", "photo_head_cut_off", "photo_too_small", "photo_wrong_shape", "photo_blank"] as const;

export type CharacterPose = "neutral_full" | "sleeping" | "sunbathing" | "eating" | "walking" | "petted";
export const CharacterPoseValues = ["neutral_full", "sleeping", "sunbathing", "eating", "walking", "petted"] as const;

export type IdPhotoSource = "generated" | "companion_portrait";
export const IdPhotoSourceValues = ["generated", "companion_portrait"] as const;

export type HabitatKind = "seaside" | "grassland" | "desert" | "forest" | "lakeside" | "mountain" | "city" | "countryside";
export const HabitatKindValues = ["seaside", "grassland", "desert", "forest", "lakeside", "mountain", "city", "countryside"] as const;

export type GuardBasis = "pet_at_home" | "owner_patrol" | "none";
export const GuardBasisValues = ["pet_at_home", "owner_patrol", "none"] as const;

export type PlotStage = "empty" | "growing" | "ripe" | "harvested";
export const PlotStageValues = ["empty", "growing", "ripe", "harvested"] as const;

export type FarmActionKind = "plant" | "harvest" | "steal";
export const FarmActionKindValues = ["plant", "harvest", "steal"] as const;

export type WelcomeDetailKind = "owner_title" | "favorite_object" | "interaction_boundary";
export const WelcomeDetailKindValues = ["owner_title", "favorite_object", "interaction_boundary"] as const;

export type FarmWatch = "owner_patrol" | "pet_awake" | "pet_resting" | "nobody";
export const FarmWatchValues = ["owner_patrol", "pet_awake", "pet_resting", "nobody"] as const;

export type SuggestionStatus = "pending" | "accepted" | "passed" | "replaced";
export const SuggestionStatusValues = ["pending", "accepted", "passed", "replaced"] as const;

export type GuideStatus = "planned" | "in_progress" | "completed";
export const GuideStatusValues = ["planned", "in_progress", "completed"] as const;

export type PlaceProvider = "amap" | "google" | "fixture" | "world";
export const PlaceProviderValues = ["amap", "google", "fixture", "world"] as const;

export type VisitState = "planned" | "travelling" | "arrived" | "active" | "completed" | "cancelled";
export const VisitStateValues = ["planned", "travelling", "arrived", "active", "completed", "cancelled"] as const;

export type VenueTemplate = "cafe" | "restaurant" | "park" | "generic";
export const VenueTemplateValues = ["cafe", "restaurant", "park", "generic"] as const;

export type VisitActivityKind = "choose_seat" | "order_drink" | "take_photo" | "greet_resident";
export const VisitActivityKindValues = ["choose_seat", "order_drink", "take_photo", "greet_resident"] as const;

export type VisitActivityState = "available" | "in_progress" | "done" | "disabled";
export const VisitActivityStateValues = ["available", "in_progress", "done", "disabled"] as const;

export type JourneyLifecycle = "active" | "completed" | "cancelled";
export const JourneyLifecycleValues = ["active", "completed", "cancelled"] as const;

export type TransportMode = "flight" | "train" | "ferry" | "drive" | "transit" | "taxi" | "walk";
export const TransportModeValues = ["flight", "train", "ferry", "drive", "transit", "taxi", "walk"] as const;

export type TimeBasis = "verified_timetable" | "live_status" | "routed_estimate" | "demo_fixture";
export const TimeBasisValues = ["verified_timetable", "live_status", "routed_estimate", "demo_fixture"] as const;

export type LegTimeSource = "verified_timetable" | "operator_rule" | "routed_estimate" | "world_rule" | "demo_fixture";
export const LegTimeSourceValues = ["verified_timetable", "operator_rule", "routed_estimate", "world_rule", "demo_fixture"] as const;

export type DataFreshness = "verified" | "stale" | "unavailable";
export const DataFreshnessValues = ["verified", "stale", "unavailable"] as const;

export type PositionBasis = "simulated_route" | "schematic" | "live_vehicle";
export const PositionBasisValues = ["simulated_route", "schematic", "live_vehicle"] as const;

export type TravellerRole = "driver" | "passenger" | "walker";
export const TravellerRoleValues = ["driver", "passenger", "walker"] as const;

export type LegKind = "main" | "connection" | "wait" | "transfer";
export const LegKindValues = ["main", "connection", "wait", "transfer"] as const;

export type LegPhase = "scheduled" | "connecting" | "waiting" | "boarding" | "in_transit" | "arriving" | "arrived" | "cancelled";
export const LegPhaseValues = ["scheduled", "connecting", "waiting", "boarding", "in_transit", "arriving", "arrived", "cancelled"] as const;

export type NodeKind = "airport" | "station" | "port" | "road_point" | "place";
export const NodeKindValues = ["airport", "station", "port", "road_point", "place"] as const;

export type TravelActivityKind = "listening" | "watching" | "resting" | "window_gazing" | "dining" | "writing_postcard";
export const TravelActivityKindValues = ["listening", "watching", "resting", "window_gazing", "dining", "writing_postcard"] as const;

export type TravelActivityState = "active" | "paused" | "interrupted" | "ended";
export const TravelActivityStateValues = ["active", "paused", "interrupted", "ended"] as const;

export type ActivityBadgeKind = "music" | "tv";
export const ActivityBadgeKindValues = ["music", "tv"] as const;

export type MapEntryAction = "join" | "solo" | "open_leg_card";
export const MapEntryActionValues = ["join", "solo", "open_leg_card"] as const;

export type BasemapProvider = "amap";
export const BasemapProviderValues = ["amap"] as const;

export type BasemapUnavailableReason = "not_configured" | "outside_region" | "daily_cap" | "user_limit" | "upstream_error";
export const BasemapUnavailableReasonValues = ["not_configured", "outside_region", "daily_cap", "user_limit", "upstream_error"] as const;

export type MediaKind = "audio" | "video";
export const MediaKindValues = ["audio", "video"] as const;

export type MediaAvailability = "in_app_sync" | "external_link" | "unavailable";
export const MediaAvailabilityValues = ["in_app_sync", "external_link", "unavailable"] as const;

export type LicenseStatus = "self_generated_test" | "licensed" | "pending" | "unknown";
export const LicenseStatusValues = ["self_generated_test", "licensed", "pending", "unknown"] as const;

export type MediaSessionState = "playing" | "paused" | "ended" | "interrupted";
export const MediaSessionStateValues = ["playing", "paused", "ended", "interrupted"] as const;

export type ResumePolicy = "pet_continues" | "save_shared_progress" | "stop";
export const ResumePolicyValues = ["pet_continues", "save_shared_progress", "stop"] as const;

export type InterruptReason = "arrival" | "driving" | "content_unavailable" | "joint_pause";
export const InterruptReasonValues = ["arrival", "driving", "content_unavailable", "joint_pause"] as const;

export type ParticipationMode = "not_joined" | "joining" | "synced" | "solo" | "buffering" | "blocked" | "failed" | "left";
export const ParticipationModeValues = ["not_joined", "joining", "synced", "solo", "buffering", "blocked", "failed", "left"] as const;

export type CompanionCommandKind = "pause" | "resume" | "seek" | "restart";
export const CompanionCommandKindValues = ["pause", "resume", "seek", "restart"] as const;

export type FoodMode = "pet_virtual_explore" | "owner_real_dining";
export const FoodModeValues = ["pet_virtual_explore", "owner_real_dining"] as const;

export type PreferenceSubject = "pet" | "owner";
export const PreferenceSubjectValues = ["pet", "owner"] as const;

export type PreferenceSource = "explicit" | "reception_confirmed" | "feedback_derived" | "fixture";
export const PreferenceSourceValues = ["explicit", "reception_confirmed", "feedback_derived", "fixture"] as const;

export type DietaryRestrictionKind = "allergy" | "avoid" | "religious" | "other";
export const DietaryRestrictionKindValues = ["allergy", "avoid", "religious", "other"] as const;

export type EvidenceSourceKind = "map_poi" | "merchant_menu" | "licensed_review" | "owner_feedback" | "partner_note" | "fixture";
export const EvidenceSourceKindValues = ["map_poi", "merchant_menu", "licensed_review", "owner_feedback", "partner_note", "fixture"] as const;

export type EligibilityStatus = "eligible" | "needs_verification" | "excluded";
export const EligibilityStatusValues = ["eligible", "needs_verification", "excluded"] as const;

export type RecommendationGroup = "primary" | "alternative" | "explore" | "needs_verification";
export const RecommendationGroupValues = ["primary", "alternative", "explore", "needs_verification"] as const;

export type RecommendationFreshness = "fresh" | "needs_recheck" | "expired";
export const RecommendationFreshnessValues = ["fresh", "needs_recheck", "expired"] as const;

export type FoodDataStatus = "fixture" | "live_verified" | "live_partial";
export const FoodDataStatusValues = ["fixture", "live_verified", "live_partial"] as const;

export type FeedbackVerdict = "liked" | "neutral" | "disliked";
export const FeedbackVerdictValues = ["liked", "neutral", "disliked"] as const;

export type FeedbackVerification = "self_reported" | "verified";
export const FeedbackVerificationValues = ["self_reported", "verified"] as const;

export type ReceptionBranch = "own_pet" | "adopted";
export const ReceptionBranchValues = ["own_pet", "adopted"] as const;

export type ReceptionMode = "guided_notes" | "model_conversation";
export const ReceptionModeValues = ["guided_notes", "model_conversation"] as const;

export type ReceptionStatus = "active" | "awaiting_confirmation" | "skipped" | "completed" | "expired";
export const ReceptionStatusValues = ["active", "awaiting_confirmation", "skipped", "completed", "expired"] as const;

export type TurnSpeaker = "host" | "owner";
export const TurnSpeakerValues = ["host", "owner"] as const;

export type CandidateKind = "habit" | "shared_story" | "wish" | "letter" | "owner_private" | "inference";
export const CandidateKindValues = ["habit", "shared_story", "wish", "letter", "owner_private", "inference"] as const;

export type CandidateSubject = "pet" | "owner" | "relationship";
export const CandidateSubjectValues = ["pet", "owner", "relationship"] as const;

export type CandidateState = "unconfirmed" | "edited" | "confirmed" | "discarded";
export const CandidateStateValues = ["unconfirmed", "edited", "confirmed", "discarded"] as const;

export type CareNoteSlot = "owner_title" | "favorite_object" | "interaction_boundary" | "travel_mood" | "wish_place" | "other";
export const CareNoteSlotValues = ["owner_title", "favorite_object", "interaction_boundary", "travel_mood", "wish_place", "other"] as const;

export type SaveTarget = "give_to_pet" | "keep_here" | "do_not_save";
export const SaveTargetValues = ["give_to_pet", "keep_here", "do_not_save"] as const;

export type MemoryPurpose = "private_chat" | "home_interaction" | "travel_preference" | "food_preference_pet" | "public_story" | "media_generation";
export const MemoryPurposeValues = ["private_chat", "home_interaction", "travel_preference", "food_preference_pet", "public_story", "media_generation"] as const;

export type PersistState = "persisted" | "failed";
export const PersistStateValues = ["persisted", "failed"] as const;

export type MemoryCorrectionAction = "correct" | "revoke" | "erase";
export const MemoryCorrectionActionValues = ["correct", "revoke", "erase"] as const;

export type CleanupState = "usage_stopped" | "cleanup_pending" | "cleanup_done";
export const CleanupStateValues = ["usage_stopped", "cleanup_pending", "cleanup_done"] as const;

export type ActorKind = "pet" | "npc" | "owner";
export const ActorKindValues = ["pet", "npc", "owner"] as const;

export type PostVisibility = "public" | "followers" | "removed";
export const PostVisibilityValues = ["public", "followers", "removed"] as const;

export type MessageSender = "owner" | "pet";
export const MessageSenderValues = ["owner", "pet"] as const;

export type MessageDeliveryState = "sending" | "delivered" | "awaiting_reply" | "processing" | "failed";
export const MessageDeliveryStateValues = ["sending", "delivered", "awaiting_reply", "processing", "failed"] as const;

export type MessageComposer = "event" | "template" | "model";
export const MessageComposerValues = ["event", "template", "model"] as const;

export type MessageTopic = "morning" | "share" | "goodnight" | "thinking_of_you" | "news";
export const MessageTopicValues = ["morning", "share", "goodnight", "thinking_of_you", "news"] as const;

export type MessageChannel = "private" | "family";
export const MessageChannelValues = ["private", "family"] as const;

export type PhotoStatus = "processing" | "ready" | "failed" | "unknown";
export const PhotoStatusValues = ["processing", "ready", "failed", "unknown"] as const;

export type FriendKind = "pet" | "resident";
export const FriendKindValues = ["pet", "resident"] as const;

export type IntentChannel = "reception" | "communicator";
export const IntentChannelValues = ["reception", "communicator"] as const;

export type IntentLayerMode = "off" | "shadow" | "assist";
export const IntentLayerModeValues = ["off", "shadow", "assist"] as const;

export type IntentProvider = "rule" | "configured_llm" | "jev";
export const IntentProviderValues = ["rule", "configured_llm", "jev"] as const;

export type SignalKind = "share" | "ask" | "request" | "correct" | "refuse" | "revoke" | "missing" | "constraint" | "wish" | "privacy_limit" | "unclear";
export const SignalKindValues = ["share", "ask", "request", "correct", "refuse", "revoke", "missing", "constraint", "wish", "privacy_limit", "unclear"] as const;

export type SignalSubject = "owner" | "pet" | "place" | "journey" | "memory" | "photo" | "unknown";
export const SignalSubjectValues = ["owner", "pet", "place", "journey", "memory", "photo", "unknown"] as const;

export type TemporalScope = "past" | "ongoing" | "future_wish" | "hypothetical" | "current_command" | "unknown";
export const TemporalScopeValues = ["past", "ongoing", "future_wish", "hypothetical", "current_command", "unknown"] as const;

export type UsageLimit = "do_not_record" | "do_not_relay" | "do_not_publish";
export const UsageLimitValues = ["do_not_record", "do_not_relay", "do_not_publish"] as const;

export type ActionProposalKind = "none" | "clarify" | "offer_control" | "record_candidate" | "adjust_reply";
export const ActionProposalKindValues = ["none", "clarify", "offer_control", "record_candidate", "adjust_reply"] as const;

export type ActionOutcomeState = "proposed" | "needs_confirmation" | "blocked" | "executed" | "failed";
export const ActionOutcomeStateValues = ["proposed", "needs_confirmation", "blocked", "executed", "failed"] as const;

export type CredentialKind = "identity_card" | "bank_card" | "care_profile" | "passport" | "driver_license" | "boarding_pass" | "transport_ticket" | "hotel_key";
export const CredentialKindValues = ["identity_card", "bank_card", "care_profile", "passport", "driver_license", "boarding_pass", "transport_ticket", "hotel_key"] as const;

export type CredentialStatus = "not_obtained" | "in_progress" | "active" | "used" | "expired";
export const CredentialStatusValues = ["not_obtained", "in_progress", "active", "used", "expired"] as const;

export type SchoolSubject = "s1" | "s2" | "s3" | "s4";
export const SchoolSubjectValues = ["s1", "s2", "s3", "s4"] as const;

export type SchoolStage = "none" | "wish" | "enrolled" | "license_pending" | "licensed";
export const SchoolStageValues = ["none", "wish", "enrolled", "license_pending", "licensed"] as const;

export type SubjectState = "locked" | "available" | "in_exam" | "cooldown" | "passed";
export const SubjectStateValues = ["locked", "available", "in_exam", "cooldown", "passed"] as const;

export type SessionMode = "practice" | "formal";
export const SessionModeValues = ["practice", "formal"] as const;

export type AttemptKind = "first" | "retake";
export const AttemptKindValues = ["first", "retake"] as const;

export type SchoolSessionState = "preparing" | "running" | "settled" | "void";
export const SchoolSessionStateValues = ["preparing", "running", "settled", "void"] as const;

export type QuizKind = "choice" | "match" | "order";
export const QuizKindValues = ["choice", "match", "order"] as const;

export type EntryRoute = "browse" | "own_pet" | "adopt" | "invite";
export const EntryRouteValues = ["browse", "own_pet", "adopt", "invite"] as const;

export type ProviderState = "disabled" | "not_configured" | "configured" | "verified" | "failing";
export const ProviderStateValues = ["disabled", "not_configured", "configured", "verified", "failing"] as const;

export type MapProvider = "amap";
export const MapProviderValues = ["amap"] as const;

export type MapUnavailableReason = "not_configured";
export const MapUnavailableReasonValues = ["not_configured"] as const;

export type WorldRelation = "mine" | "household";
export const WorldRelationValues = ["mine", "household"] as const;

export type WorldActivityKind = "home" | "stroll" | "cafe" | "city_trip" | "drive_trip" | "job" | "trip";
export const WorldActivityKindValues = ["home", "stroll", "cafe", "city_trip", "drive_trip", "job", "trip"] as const;

export type WorldPhase = "home" | "going" | "there" | "returning" | "unknown";
export const WorldPhaseValues = ["home", "going", "there", "returning", "unknown"] as const;

export type WorldPositionBasis = "home_area" | "place" | "route" | "unknown";
export const WorldPositionBasisValues = ["home_area", "place", "route", "unknown"] as const;

export type WorldPose = "idle" | "sleeping" | "eating" | "sunbathing" | "walking" | "riding" | "cafe" | "working" | "exploring" | "unknown";
export const WorldPoseValues = ["idle", "sleeping", "eating", "sunbathing", "walking", "riding", "cafe", "working", "exploring", "unknown"] as const;

export type AnnouncementSeverity = "info" | "notice" | "maintenance";
export const AnnouncementSeverityValues = ["info", "notice", "maintenance"] as const;

export type AnnouncementSource = "live" | "not_installed";
export const AnnouncementSourceValues = ["live", "not_installed"] as const;

export type ReportStatus = "received" | "resolved";
export const ReportStatusValues = ["received", "resolved"] as const;

export type ReportOutcome = "received" | "content_removed" | "no_violation_found" | "content_restored";
export const ReportOutcomeValues = ["received", "content_removed", "no_violation_found", "content_restored"] as const;

export type TravelWaitingReason = "missing_funds" | "quota_denied" | "research_pending" | "research_unknown" | "research_failed" | "fact_stale" | "plan_stale" | "fact_unverified" | "fact_conflicting" | "weather_unsuitable" | "commitment_active" | "maintenance";
export const TravelWaitingReasonValues = ["missing_funds", "quota_denied", "research_pending", "research_unknown", "research_failed", "fact_stale", "plan_stale", "fact_unverified", "fact_conflicting", "weather_unsuitable", "commitment_active", "maintenance"] as const;

export type TravelWishStatus = "active" | "ready" | "linked" | "completed" | "cancelled";
export const TravelWishStatusValues = ["active", "ready", "linked", "completed", "cancelled"] as const;

export type TravelResearchStatus = "queued" | "running" | "ready" | "failed" | "unknown";
export const TravelResearchStatusValues = ["queued", "running", "ready", "failed", "unknown"] as const;

export type TravelStopRole = "main" | "suggested";
export const TravelStopRoleValues = ["main", "suggested"] as const;

export type TravelFactVerdict = "verified" | "unverified" | "stale" | "conflicting" | "rejected";
export const TravelFactVerdictValues = ["verified", "unverified", "stale", "conflicting", "rejected"] as const;

export type TravelJournalPhase = "plan" | "memory";
export const TravelJournalPhaseValues = ["plan", "memory"] as const;

export type TravelIdentityMode = "photo" | "none";
export const TravelIdentityModeValues = ["photo", "none"] as const;

export interface WebError {
  code: WebErrorCode;
  /** 可读说明；不含堆栈、SQL 或密钥 */
  message: string;
  request_id: string;
  retryable: boolean;
  details: Record<string, unknown> | null;
}
export type WebErrorInput = WithOptional<WebError, "retryable" | "details">;

export interface WebErrorEnvelope {
  error: WebError;
}
export type WebErrorEnvelopeInput = WebErrorEnvelope;

export interface Capability {
  /** 稳定能力键，例如 food.recommendations */
  key: string;
  status: CapabilityStatus;
  module: string;
  note: string | null;
}
export type CapabilityInput = WithOptional<Capability, "note">;

export interface WebMeta {
  api_prefix: string;
  contract_version: string;
  server_time: IsoDateTime;
  backend_version: string;
  data_origin: DataOrigin;
  auth_methods_available: AuthMethod[];
  capabilities: Capability[];
  applied_migrations: string[];
}
export type WebMetaInput = WithOptional<WebMeta, "api_prefix" | "contract_version" | "data_origin" | "auth_methods_available" | "capabilities" | "applied_migrations">;

/** 整数金额；currency 区分游戏币 travel_coin 与现实币种（HKD/CNY 等），两者不混算。 */
export interface MoneyAmount {
  amount_minor: number;
  currency: string;
}
export type MoneyAmountInput = MoneyAmount;

export interface LatLng {
  lat: number;
  lng: number;
}
export type LatLngInput = LatLng;

export interface OnboardingState {
  step: OnboardingStep;
  pet_id: string | null;
  home_id: string | null;
  reception_session_id: string | null;
  reception_skipped: boolean;
  home_activated_at: IsoDateTime | null;
  /** 伙伴来源；接待据此选择“自己的宠物/领养”分支 */
  pet_origin: PetOrigin | null;
  /** 你所在的家庭与各家的宠物（0.4.0：一个账号可以在多个家庭里照顾多只宠物） */
  households?: HouseholdBrief[];
  /** 注册时带来的入口（选中的伙伴 / 家庭邀请），等你确认；不会自动领养或加入 */
  entry?: EntryIntentView | null;
}
export type OnboardingStateInput = WithOptional<OnboardingState, "pet_id" | "home_id" | "reception_session_id" | "reception_skipped" | "home_activated_at" | "pet_origin" | "households" | "entry">;

export interface SessionUser {
  user_id: string;
  display_name: string | null;
  username: string | null;
  auth_method: AuthMethod;
}
export type SessionUserInput = WithOptional<SessionUser, "display_name" | "username">;

export interface SessionState {
  authenticated: boolean;
  user: SessionUser | null;
  csrf_required: boolean;
  expires_at: IsoDateTime | null;
  onboarding: OnboardingState | null;
}
export type SessionStateInput = WithOptional<SessionState, "user" | "csrf_required" | "expires_at" | "onboarding">;

export interface RegisterRequest {
  username: string;
  password: string;
  display_name: string | null;
  /** 从哪个入口来注册（0.4.0） */
  entry?: EntryIntentRequest | null;
}
export type RegisterRequestInput = WithOptional<RegisterRequest, "display_name" | "entry">;

export interface LoginRequest {
  username: string;
  password: string;
}
export type LoginRequestInput = LoginRequest;

/** 入住激活。public_posts：是否允许 TA 的旅行到访生成公开动态（默认不公开，由主人明确选择）。 */
export interface MoveInRequest {
  public_posts: boolean;
  /** 希望这个家在哪一类地方（只在家第一次入住时生效）；只能选当前开放的类型（见 /home/place） */
  habitat?: string | null;
  /** 住进来的是哪一只宠物（0.4.0；只照顾一只时可以省略） */
  pet_id?: string | null;
}
export type MoveInRequestInput = WithOptional<MoveInRequest, "public_posts" | "habitat" | "pet_id">;

export interface SettingsView {
  username: string | null;
  display_name: string | null;
  public_posts: boolean;
  profile_visibility: string;
  bio: string | null;
  intent_layer_mode: string;
  /** 开启时，由对话模型按已确认的叮嘱撰写：TA 给你的私信回复与主动来信、明信片上的话、攻略的措辞；家里第一位管理员的这项选择，还决定家庭频道的措辞、到站明信片上的话，以及运营开启自主决策时 TA 的思考用不用模型；运营开启自主决策时，你的叮嘱也会按用途交给模型参考。**默认开启**（2026-09-24 起），主人可随时关掉，关掉即撤回上述全部模型授权 */
  model_replies?: boolean;
  model_replies_available?: boolean;
  /** 对话模型服务商（披露用），未配置为空 */
  model_provider?: string | null;
  /** 主人开启后，冒险事件会请生图服务画一张插画；默认关闭 */
  generated_photos?: boolean;
  generated_photos_available?: boolean;
  image_provider?: string | null;
  /** 是否接收 TA 主动发来的消息（早安、分享、晚安等；每天最多 4 条，夜间不打扰） */
  pet_messages?: boolean;
  /** 主人所在时区（IANA 名称），安静时段按它计算 */
  timezone?: string;
}
export type SettingsViewInput = WithOptional<SettingsView, "username" | "display_name" | "bio" | "model_replies" | "model_replies_available" | "model_provider" | "generated_photos" | "generated_photos_available" | "image_provider" | "pet_messages" | "timezone">;

export interface SettingsUpdate {
  model_replies: boolean | null;
  generated_photos: boolean | null;
  pet_messages: boolean | null;
  /** IANA 时区名，例如 Asia/Hong_Kong；前端可取浏览器时区 */
  timezone: string | null;
  public_posts: boolean | null;
  profile_visibility: string | null;
  bio: string | null;
}
export type SettingsUpdateInput = WithOptional<SettingsUpdate, "model_replies" | "generated_photos" | "pet_messages" | "timezone" | "public_posts" | "profile_visibility" | "bio">;

export interface HouseholdPetBrief {
  pet_id: string;
  name: string;
  species: PetSpecies;
  photo_url: string | null;
  origin: PetOrigin;
  presence: PetPresence;
  join_step: PetJoinStep;
  joined_at: IsoDateTime;
  added_by_you: boolean;
}
export type HouseholdPetBriefInput = WithOptional<HouseholdPetBrief, "photo_url" | "added_by_you">;

export interface HouseholdBrief {
  household_id: string;
  name: string | null;
  home_id: string;
  /** 你在这个家庭里的角色 */
  role: HouseholdRole;
  home_activated: boolean;
  member_count: number;
  pets: HouseholdPetBrief[];
}
export type HouseholdBriefInput = WithOptional<HouseholdBrief, "name" | "pets">;

export interface HouseholdMember {
  user_id: string;
  display_name: string;
  role: HouseholdRole;
  joined_at: IsoDateTime;
  is_you: boolean;
}
export type HouseholdMemberInput = WithOptional<HouseholdMember, "is_you">;

export interface HouseholdSettings {
  name: string | null;
  /** 共同照顾者能否使用宠物的星球账户（出发旅费等） */
  caregivers_can_spend: boolean;
  /** 宠物自己的旅途照片是否生成写实照片（付费生图，由家庭管理员决定） */
  generated_photos: boolean;
  /** 宠物是否主动把生活里发生的事发到家庭频道 */
  pet_messages: boolean;
  /** 宠物的旅行到访是否生成公开动态 */
  public_posts: boolean;
}
export type HouseholdSettingsInput = WithOptional<HouseholdSettings, "name">;

export interface HouseholdDetail {
  household: HouseholdBrief;
  members: HouseholdMember[];
  settings: HouseholdSettings;
  /** view / care / spend / manage */
  your_permissions: string[];
  version: number;
}
export type HouseholdDetailInput = HouseholdDetail;

export interface HouseholdSettingsRequest {
  name: string | null;
  caregivers_can_spend: boolean | null;
  generated_photos: boolean | null;
  pet_messages: boolean | null;
  public_posts: boolean | null;
}
export type HouseholdSettingsRequestInput = WithOptional<HouseholdSettingsRequest, "name" | "caregivers_can_spend" | "generated_photos" | "pet_messages" | "public_posts">;

export interface MemberRoleRequest {
  role: HouseholdRole;
}
export type MemberRoleRequestInput = MemberRoleRequest;

export interface HouseholdInvite {
  invite_id: string;
  household_id: string;
  role: HouseholdRole;
  /** 邀请人写的称呼提示，例如“妈妈”；只是称呼，不带权限 */
  relation_hint: string | null;
  status: InviteStatus;
  created_at: IsoDateTime;
  expires_at: IsoDateTime;
  accepted_at: IsoDateTime | null;
}
export type HouseholdInviteInput = WithOptional<HouseholdInvite, "relation_hint" | "accepted_at">;

export interface InviteCreateRequest {
  role: HouseholdRole;
  relation_hint: string | null;
  ttl_hours: number;
}
export type InviteCreateRequestInput = WithOptional<InviteCreateRequest, "role" | "relation_hint" | "ttl_hours">;

export interface InviteCreated {
  invite: HouseholdInvite;
  /** 邀请令牌：只在创建时返回一次，服务端只保存摘要 */
  token: string;
  /** 前端的邀请直达路径，例如 /join?invite=<令牌> */
  join_path: string;
}
export type InviteCreatedInput = InviteCreated;

export interface InviteTokenRequest {
  token: string;
}
export type InviteTokenRequestInput = InviteTokenRequest;

/** 接受邀请前能看到的最少信息：家庭名、邀请人称呼、角色、宠物名字。不含私人资料。 */
export interface InvitePreview {
  invite_id: string;
  status: InviteStatus;
  role: HouseholdRole;
  relation_hint: string | null;
  expires_at: IsoDateTime;
  household_name: string | null;
  inviter_name: string;
  pet_names: string[];
  already_member: boolean;
}
export type InvitePreviewInput = WithOptional<InvitePreview, "relation_hint" | "household_name" | "pet_names" | "already_member">;

export interface PetRelationship {
  pet_id: string;
  /** TA 怎么称呼你（只属于你和 TA 之间） */
  owner_title: string | null;
  /** 你和 TA 的关系称呼；不影响权限 */
  relation_label: string | null;
  updated_at: IsoDateTime | null;
}
export type PetRelationshipInput = WithOptional<PetRelationship, "owner_title" | "relation_label" | "updated_at">;

export interface PetRelationshipRequest {
  owner_title: string | null;
  relation_label: string | null;
}
export type PetRelationshipRequestInput = WithOptional<PetRelationshipRequest, "owner_title" | "relation_label">;

/** 注册时带上的入口：先逛逛 / 接我的宠物入住 / 认识新伙伴（注册前选中的伙伴）/ 家庭邀请直达。只记下来，登录后由用户确认。 */
export interface EntryIntentRequest {
  kind: EntryKind;
  /** kind=adopt：注册前在访客页选中的待领养伙伴 */
  pet_id: string | null;
  /** kind=invite：邀请令牌（只用来找到邀请，不保存原文） */
  invite_token: string | null;
}
export type EntryIntentRequestInput = WithOptional<EntryIntentRequest, "pet_id" | "invite_token">;

export interface PendingAdoption {
  pet_id: string;
  name: string;
  species: PetSpecies;
  /** 重新校验后的可领养状态；已被别的家庭领养时为 false */
  available: boolean;
}
export type PendingAdoptionInput = PendingAdoption;

export interface EntryIntentView {
  kind: EntryKind;
  pending_adoption: PendingAdoption | null;
  pending_invite: InvitePreview | null;
  created_at: IsoDateTime;
}
export type EntryIntentViewInput = WithOptional<EntryIntentView, "pending_adoption" | "pending_invite">;

/** 给已有家庭添一只宠物（家庭管理员）。上传用 multipart 的 /pets（带 household_id 查询参数），领养用 /adoption/adopt。 */
export interface AddPetRequest {
  household_id: string;
}
export type AddPetRequestInput = AddPetRequest;

/** 只发给归属主人。owner_title 只在主人确认后出现，缺省不代表主人说过。 */
export interface PetPrivateSummary {
  pet_id: string;
  home_id: string | null;
  name: string;
  species: PetSpecies;
  photo_url: string | null;
  origin: PetOrigin;
  owner_title: string | null;
  presence: PetPresence;
  /** 照片是生成的写实证件照（没有主人上传的照片时）；页面应标注“AI 生成” */
  photo_generated?: boolean;
}
export type PetPrivateSummaryInput = WithOptional<PetPrivateSummary, "home_id" | "photo_url" | "owner_title" | "photo_generated">;

/** 公开主页投影：不含主人私密资料、接待原文或饮食限制。计数来自已执行动作。 */
export interface PetPublicProfile {
  pet_id: string;
  display_name: string;
  species: PetSpecies;
  avatar_url: string | null;
  bio: string | null;
  origin_label: string | null;
  visibility: ProfileVisibility;
  follower_count: number;
  post_count: number;
  /** 当前查看者的宠物是否已关注 TA */
  viewer_follows: boolean;
  /** 是否是查看者自己的宠物 */
  is_own: boolean;
  data_origin: DataOrigin;
}
export type PetPublicProfileInput = WithOptional<PetPublicProfile, "avatar_url" | "bio" | "origin_label" | "follower_count" | "post_count" | "viewer_follows" | "is_own">;

/** 领养卡：先讲名字/性格/梦想；真实背景可展开；来源未知保持未知。 */
export interface AdoptionCandidate {
  candidate_id: string;
  name: string;
  species: PetSpecies;
  personality: string;
  dream: string;
  origin: PetOrigin;
  /** 来源说明；未知则为 null，不编造 */
  source_note: string | null;
  background_available: boolean;
  availability: AdoptionAvailability;
  data_origin: DataOrigin;
  /** 已经在星球上生活的待领养居民的稳定 pet_id（领养后不变）；可用它看 TA 的公开生活 */
  pet_id?: string | null;
  /** 领养前住在哪（星球居民驿站·片区；世界规则提供食宿，不编造人类主人） */
  residence?: string | null;
  /** 从什么时候开始在星球上公开生活 */
  living_since?: IsoDateTime | null;
  /** TA 的形象照（公开路由，访客可看）；只在仍可领养时给，没有照片为 null。平台原创居民的形象是生成的原创设计，不是真实照片 */
  photo_url?: string | null;
}
export type AdoptionCandidateInput = WithOptional<AdoptionCandidate, "source_note" | "background_available" | "pet_id" | "residence" | "living_since" | "photo_url">;

/** 需 Idempotency-Key；服务端原子占用，两个家庭抢同一候选最多一个成功（409 ADOPTION_TAKEN）。 */
export interface AdoptRequest {
  candidate_id: string;
  /** 领养进已有的家庭（需要是这个家庭的管理员）；不给则新建家庭 */
  household_id?: string | null;
}
export type AdoptRequestInput = WithOptional<AdoptRequest, "household_id">;

export interface AdoptResult {
  pet_id: string;
  candidate_id: string;
  adopted_at: IsoDateTime;
}
export type AdoptResultInput = AdoptResult;

/** 宠物 DNA：主人描述、确认的性格与习惯。模型扮演宠物时读取；私密字段只用于私信，不进公开动态。 */
export interface PetDNA {
  /** TA 怎么称呼主人 */
  owner_title: string | null;
  /** 主人叫 TA 的小名 */
  nicknames: string[];
  /** 性格 */
  personality: string | null;
  /** 说话的样子，例如“慢吞吞、爱撒娇” */
  voice_style: string | null;
  /** 口头禅或常发出的声音 */
  catchphrase: string | null;
  favorite_foods: string[];
  favorite_places: string[];
  hobbies: string[];
  /** 小习惯 */
  habits: string[];
  /** 害怕的东西 */
  fears: string[];
  /** 和主人之间的小暗号、趣事；只在私信里使用 */
  shared_memories: string[];
}
export type PetDNAInput = WithOptional<PetDNA, "owner_title" | "nicknames" | "personality" | "voice_style" | "catchphrase" | "favorite_foods" | "favorite_places" | "hobbies" | "habits" | "fears" | "shared_memories">;

/** 一条原话出处：DNA 哪一栏、原话中的哪一小句（原样，不改写）、被怎样理解。 */
export interface BehaviorEvidence {
  /** personality / voice_style / catchphrase / habits / hobbies / favorite_places / favorite_foods / fears / dream / note（接待叮嘱） */
  field: string;
  /** 栏目中文名，例如“性格”“小习惯”“接待时的叮嘱” */
  field_label: string;
  /** 原话中的那一小句 */
  phrase: string;
  /** positive 肯定 / negative 被否定 / averse 讨厌或害怕 / uncertain 说不准 */
  polarity: BehaviorPolarity;
  /** 为什么这样理解，例如“‘不’否定了这个说法”“‘偶尔’：说法不确定，暂不归类” */
  note: string | null;
  /** 由别的说法反推（例如“不爱热闹”→ 偏安静），单独不足以归类 */
  implied: boolean;
}
export type BehaviorEvidenceInput = WithOptional<BehaviorEvidence, "note" | "implied">;

export interface BehaviorTrait {
  /** night_owl / early_bird / sleepy / social / homebody / curious / diligent / playful */
  key: string;
  label: string;
  /** applied 用上了 / negated 明确说不是 / outweighed 被更明确的相反说法盖过 / uncertain 说不准，暂不归类 */
  status: BehaviorTraitStatus;
  evidence: BehaviorEvidence[];
}
export type BehaviorTraitInput = WithOptional<BehaviorTrait, "evidence">;

export interface BehaviorPreference {
  /** job:<岗位> / route:local:stroll / route:local:cafe / route:local:city_trip / route:long */
  key: string;
  label: string;
  /** 选择时的倍数：>1 更愿意，<1 不太愿意，1 照常 */
  weight: number;
  evidence: BehaviorEvidence[];
  /** 来自性格的调整，例如“恋家：更爱在附近走走” */
  notes: string[];
}
export type BehaviorPreferenceInput = WithOptional<BehaviorPreference, "evidence" | "notes">;

/** 由 DNA 原话整理出的行为倾向（服务端确定性规则，不调用模型）；只给主人看。 */
export interface PetBehavior {
  rules_version: string;
  rhythm: PetRhythm;
  /** 入睡时间（TA 所在地当地时间，HH:MM） */
  sleep_start: string;
  /** 起床时间（HH:MM） */
  wake: string;
  sociability: PetSociability;
  curious: boolean;
  /** 一天最多自己出门几次 */
  outings_per_day: number;
  /** 一天主动找主人说话的次数 */
  chattiness: number;
  /** 学东西的快慢（驾考陪练与自学的倍数） */
  learn_rate: number;
  /** 一句话结论，例如“不爱熬夜：按平常作息（23:30 睡，07:30 起）” */
  summary: string[];
  /** 提到过的性格与作息特征（含被否定、被盖过和说不准的） */
  traits: BehaviorTrait[];
  /** 工作与路线倾向 */
  preferences: BehaviorPreference[];
  /** 提到了但说不准或前后矛盾、没有归类的原话 */
  unclassified: string[];
  /** 这次用到了哪些栏目 */
  sources: string[];
}
export type PetBehaviorInput = WithOptional<PetBehavior, "summary" | "traits" | "preferences" | "unclassified" | "sources">;

export interface PetDNAView {
  pet_id: string;
  dna: PetDNA;
  /** 主人是否已保存确认；未确认时为系统整理的草稿 */
  confirmed: boolean;
  /** 草稿来源：adoption_profile / owner_bio / reception_notes */
  draft_sources: string[];
  updated_at: IsoDateTime | null;
  /** 只用于私信、不进公开内容的字段 */
  private_fields: string[];
  /** 由这份 DNA 整理出的行为倾向与原话出处（0.2.5 追加） */
  behavior?: PetBehavior | null;
  /** 全家共用那部分 DNA 的版本号；保存时带 ?expected_version= 可防止无声覆盖家人的修改（冲突 409） */
  version?: number | null;
  /** 每位家人各自的一份（TA 怎么称呼你、你们之间的小暗号），别的家人看不到也不会被覆盖 */
  personal_fields?: string[];
  /** 共用部分最后一次是不是你改的 */
  updated_by_you?: boolean | null;
}
export type PetDNAViewInput = WithOptional<PetDNAView, "draft_sources" | "updated_at" | "private_fields" | "behavior" | "version" | "personal_fields" | "updated_by_you">;

/** 主人说「给我拍一张」。 */
export interface PhotoRequestCommand {
  scene: PhotoScene;
  /** flight_adventure 必须显式传 fictional_adventure；其余场景只接受 daily_life */
  narrative: PhotoNarrative;
}
export type PhotoRequestCommandInput = WithOptional<PhotoRequestCommand, "narrative">;

/** 受理结果。**不代表照片已经画好**，也不代表一定画得出来。 */
export interface PhotoRequestResult {
  /** 这次摄影请求的稳定标识，用它去只读查询里找结果、或发起重画 */
  request_id: string;
  /** 排上队的生图任务。为空的情况只有一种：这个环境没配生图供应商、或主人没开「生成照片」，于是命令受理了但没有排队。重复请求**不会**让它为空——那会原样返回第一次的任务号。 */
  task_id: string | null;
  scene: PhotoScene;
  narrative: PhotoNarrative;
  /** 真值表示这是主人选的虚构主题：不会写成真实出行、不扣旅费、不发勋章 */
  fictional: boolean;
  /** 按 TA **此刻所在城市**换算的拍摄时刻；途中用当前所在地，不是出发地 */
  captured_at: IsoDateTime;
  /** 这一刻 TA 在哪（家 / 车上 / 虚构主题的场景），只作展示 */
  place: string;
  city: string;
}
export type PhotoRequestResultInput = WithOptional<PhotoRequestResult, "task_id">;

/** 主人主动拍的那些照片，现在各是什么样。**纯读**：读它不会驱动任何任务，也不会发起任何调用。 */
export interface PhotoRequestView {
  request_id: string;
  task_id: string | null;
  scene: PhotoScene;
  narrative: PhotoNarrative;
  fictional: boolean;
  captured_at: IsoDateTime;
  place: string;
  city: string;
  /** processing＝还在画；ready＝画好了；failed＝确定没画成；**unknown＝结果还没确认**（可能已经发出、甚至已经计费），页面要显示成「还没确认」并给重画入口，不能写成「没画成」 */
  photo_status: PhotoStatus;
  /** 画好了才有；其余状态一律为空 */
  image_url: string | null;
  /** 能不能点「重画」：failed 与 unknown 可以，processing / ready 不行 */
  can_retry: boolean;
}
export type PhotoRequestViewInput = WithOptional<PhotoRequestView, "task_id" | "image_url">;

/** 非透明内容在画布里的实际边界（像素，左上原点）。 */
export interface ContentBox {
  left: number;
  top: number;
  right: number;
  bottom: number;
}
export type ContentBoxInput = ContentBox;

/** 落地点：角色"脚踩在哪里"，相对画布的归一化坐标。 */
export interface GroundAnchor {
  x: number;
  y: number;
  /** True＝从图像实测；False＝导演给的估计值 */
  measured: boolean;
}
export type GroundAnchorInput = WithOptional<GroundAnchor, "measured">;

/** 一张姿态图。URL **受权限保护**，不是公开静态资源。 */
export interface CharacterAsset {
  asset_id: string;
  pose: CharacterPose;
  /** 受权限保护的读取地址；越权读会被挡下，不是 CDN 直链 */
  url: string;
  /** 图片字节的 SHA-256；用于证明前端拿到的就是这一版 */
  content_sha256: string;
  /** 实际的图片 MIME，例如 image/png */
  content_type: string;
  width: number;
  height: number;
  content_box: ContentBox;
  anchor: GroundAnchor;
  /** 不透明像素占整张画布的比例。`has_alpha` 只说通道在不在，这个说主体有多大——接近 1 基本就是一张不透明的方图（背景没抠掉），接近 0 则可能主体被裁没了。 */
  opaque_ratio: number;
  /** 实际验证过的 alpha 通道可用性。**不得因为返回的是 PNG 就填 True**——PNG 可以完全不透明，当前 GPT 适配器也没有请求或验收透明背景。 */
  has_alpha: boolean;
}
export type CharacterAssetInput = CharacterAsset;

/** 一套已发布的角色资产。同一 `character_set_id` 内各姿态外貌必须一致。 */
export interface CharacterSet {
  character_set_id: string;
  pet_id: string;
  /** 同一只宠物的第几套；过期任务不得覆盖更高的 revision */
  revision: number;
  /** 生成时所用身份参考（原照）的版本。**换参考后旧结果不得发布**，靠这个比。 */
  reference_version: number;
  /** 画风版本；换风格要能解释形象为何变了 */
  style_version: string;
  assets: CharacterAsset[];
  published_at: IsoDateTime;
}
export type CharacterSetInput = CharacterSet;

/** 本次在建的那一套。它失败不影响 `active` 继续显示。 */
export interface CharacterCandidate {
  status: CharacterStatus;
  pose: CharacterPose;
  reference_version: number;
  style_version: string;
  queued_at: IsoDateTime;
  /** 未获授权、额度不足、供应商失败等**如实写原因**；不要把 unknown 的原因写成「没生成」。 */
  reason: string | null;
  /** 对应的后台任务；没有任务时为 null */
  task_id: string | null;
}
export type CharacterCandidateInput = WithOptional<CharacterCandidate, "reason" | "task_id">;

/** active 那一套里**一个额外姿态**的进度（批次二）。中性站姿不在这里——它的状态就是 `CharacterState.status`。 */
export interface CharacterPoseProgress {
  pose: CharacterPose;
  status: CharacterStatus;
  /** 没画成或作废的原因，码表同 `CharacterReason` */
  reason: string | null;
  /** 对应的后台任务 */
  task_id: string | null;
}
export type CharacterPoseProgressInput = WithOptional<CharacterPoseProgress, "reason" | "task_id">;

/** 每只宠物一张证件照（CR-6C2B-IDPHOTO）：护照、居民证、驾照等全部证件都用它。**不透明**，所以不是一种姿态。 */
export interface CharacterIdPhoto {
  /** 与角色同一口径；`unknown` 是可能已经发出、结果没确认，不得说成没画成 */
  status: CharacterStatus;
  /** `absent` 时为 null */
  source: IdPhotoSource | null;
  /** 证件用图（竖幅 3:4、浅蓝纯底）的受保护地址；没有生效的证件照时为 null */
  url: string | null;
  /** 地图头像：从证件照上方正方形缩成的 **256×256** 小图。**没有就是 null，不拿别的图冒充**（没照片的宠物那张基准照不是裁好的头像，也是 null） */
  avatar_url: string | null;
  width: number | null;
  height: number | null;
  /** 证件用图字节的 SHA-256 */
  content_sha256: string | null;
  /** 依据的是这只宠物的第几张参考照；换了照片才重画 */
  reference_version: number | null;
  revision: number | null;
  /** 没画成或作废的原因，码表同 `CharacterReason` */
  reason: string | null;
  task_id: string | null;
}
export type CharacterIdPhotoInput = WithOptional<CharacterIdPhoto, "source" | "url" | "avatar_url" | "width" | "height" | "content_sha256" | "reference_version" | "revision" | "reason" | "task_id">;

/** `GET /pets/{pet_id}/character` 的响应。**纯读，绝不触发生成。** */
export interface CharacterState {
  pet_id: string;
  /** 综合状态：有 candidate 时取它的，否则由 active 是否存在决定 */
  status: CharacterStatus;
  /** 当前生效的一套；从未成功过时为 null */
  active: CharacterSet | null;
  /** 本次在建的；空闲时为 null */
  candidate: CharacterCandidate | null;
  /** 是否允许发起「调整形象」。授权缺失、额度用尽、已有在建任务时为 False，**原因在 candidate.reason 或 blocked_reason 里给**。 */
  can_regenerate: boolean;
  /** can_regenerate 为 False 且没有 candidate 时，这里说明为什么 */
  blocked_reason: string | null;
  /** active 那一套里其余姿态的进度（批次二）。自动生成的开关默认关，关着时为空数组；已就绪的那几张同时出现在 `active.assets` 里 */
  poses?: CharacterPoseProgress[];
  /** 证件照（与形象不同，不透明、有底色）。没有时前端退回 `photo_url` */
  id_photo?: CharacterIdPhoto | null;
}
export type CharacterStateInput = WithOptional<CharacterState, "active" | "candidate" | "blocked_reason" | "poses" | "id_photo">;

/** 「调整形象」——**可选**操作。正常路径由上传成功自动触发，用户不必点这个。 */
export interface CharacterRegenerateCommand {
  /** **目前一律按整套重做**：先重画中性站姿，其余姿态（开关开着时）随新的一套重新生成——只重画某一个姿态会让它和同套的站姿不再是同一张参考（P 规范 §6-4）。本字段暂不区分取值 */
  pose: CharacterPose;
  /** 主人想调整的地方，可空 */
  note: string | null;
}
export type CharacterRegenerateCommandInput = WithOptional<CharacterRegenerateCommand, "pose" | "note">;

/** 发起结果。`accepted=False` 时 `reason` 必须能解释为什么没排上。 */
export interface CharacterRegenerateResult {
  accepted: boolean;
  status: CharacterStatus;
  task_id: string | null;
  reason: string | null;
}
export type CharacterRegenerateResultInput = WithOptional<CharacterRegenerateResult, "task_id" | "reason">;

export interface HomePlaceSummary {
  habitat: HabitatKind;
  /** 海边/草原/…… */
  habitat_label: string;
  city: string;
  /** 片区的说法，例如“环岛路附近的海边”；不是具体地址 */
  area_label: string;
  /** 展示用：城市·片区 */
  display: string;
  timezone: string;
  /** 主人是否选过；没选过时为默认（香港·中环） */
  chosen: boolean;
}
export type HomePlaceSummaryInput = HomePlaceSummary;

export interface HabitatOption {
  habitat: HabitatKind;
  label: string;
  /** 可能随机到的城市，例如“厦门、青岛” */
  examples: string[];
  /** 新家现在能不能选这一类（只开放真实交通与地点都已接通的片区；已有的家不受影响） */
  open?: boolean;
}
export type HabitatOptionInput = WithOptional<HabitatOption, "examples" | "open">;

export interface HomePlaceView {
  place: HomePlaceSummary;
  options: HabitatOption[];
  /** TA 在外面时不能搬家 */
  can_change: boolean;
}
export type HomePlaceViewInput = WithOptional<HomePlaceView, "options">;

/** 选一类地方；服务端在对应片区里随机一个，坐标已模糊处理。重复提交会重新随机。 */
export interface HomePlaceRequest {
  habitat: HabitatKind;
}
export type HomePlaceRequestInput = HomePlaceRequest;

export interface WalletSummary {
  /** 唯一游戏币口径 */
  currency: string;
  balance: number;
  updated_at: IsoDateTime | null;
}
export type WalletSummaryInput = WithOptional<WalletSummary, "currency" | "balance" | "updated_at">;

export interface GuardState {
  guarding: boolean;
  basis: GuardBasis;
  /** 主人巡院的守护截止时间（basis=owner_patrol 时） */
  until: IsoDateTime | null;
  /** 下一次可以巡院的时间；为空表示现在就可以 */
  next_patrol_at: IsoDateTime | null;
  /** 此刻在家、醒着、在守菜的宠物（多只一起守效果更好，但不是绝对防偷） */
  guarding_pets?: string[];
}
export type GuardStateInput = WithOptional<GuardState, "until" | "next_patrol_at" | "guarding_pets">;

/** 仓库里的可出售物资（收成、串门摘来的菜）。个人纪念与照片不在这里、不可交易。 */
export interface InventoryItem {
  item_key: string;
  label: string;
  qty: number;
  /** 杂货铺收购价（travel_coin/单位） */
  unit_price: number;
  tradable: boolean;
}
export type InventoryItemInput = WithOptional<InventoryItem, "tradable">;

export interface PlotSummary {
  plot_id: string;
  cycle_id: string | null;
  crop_key: string | null;
  crop_label: string | null;
  stage: PlotStage;
  ripe_at: IsoDateTime | null;
  /** 本批可偷总额（全体访客共享） */
  steal_total: number | null;
  steal_remaining: number | null;
}
export type PlotSummaryInput = WithOptional<PlotSummary, "cycle_id" | "crop_key" | "crop_label" | "ripe_at" | "steal_total" | "steal_remaining">;

/** 需 Idempotency-Key 请求头；同键同请求返回原结果。 */
export interface FarmActionRequest {
  home_id: string;
  plot_id: string;
  cycle_id: string | null;
  action: FarmActionKind;
  crop_key: string | null;
}
export type FarmActionRequestInput = WithOptional<FarmActionRequest, "cycle_id" | "crop_key">;

export interface FarmActionResult {
  plot: PlotSummary;
  wallet: WalletSummary;
  gained_items: string[];
}
export type FarmActionResultInput = WithOptional<FarmActionResult, "gained_items">;

export interface WelcomeDetail {
  kind: WelcomeDetailKind;
  text: string;
  note_id: string;
  note_version: number;
}
export type WelcomeDetailInput = WelcomeDetail;

/** 只由 MemoryProjection(home_interaction) 生成；未确认/owner_private 候选不会出现。 */
export interface HomeWelcome {
  pet_id: string;
  confirmation_id: string | null;
  projection_version: number;
  greeting: string;
  details: WelcomeDetail[];
}
export type HomeWelcomeInput = WithOptional<HomeWelcome, "confirmation_id" | "details">;

export interface UnreadSignals {
  messages: number;
  circle: number;
}
export type UnreadSignalsInput = WithOptional<UnreadSignals, "messages" | "circle">;

export interface JourneyBrief {
  journey_id: string;
  itinerary_version: number;
  headline: string;
  current_visit_id: string | null;
  current_leg_id: string | null;
}
export type JourneyBriefInput = WithOptional<JourneyBrief, "current_visit_id" | "current_leg_id">;

export interface HomeSnapshot {
  home_id: string;
  server_time: IsoDateTime;
  /** 快照版本，写操作后递增；客户端据此失效缓存 */
  version: number;
  pet: PetPrivateSummary;
  presence: PetPresence;
  guard: GuardState;
  wallet: WalletSummary;
  /** 仓库物资；卖给杂货铺或交居民订单才变成旅费 */
  pantry: InventoryItem[];
  plots: PlotSummary[];
  journey: JourneyBrief | null;
  welcome: HomeWelcome | null;
  unread: UnreadSignals;
  /** TA 的家在哪（城市·片区，不是具体地址） */
  place?: HomePlaceSummary | null;
  /** 尚未接入的能力键；前端据此显示未接入而非伪造数据 */
  missing_capabilities: string[];
  data_origin: DataOrigin;
  /** 这个家属于哪个家庭、你的角色、家里有几位成员 */
  household?: HouseholdBrief | null;
  /** 家里的全部宠物与各自此刻的状态；pet 字段是当前查看的那一只 */
  pets?: HouseholdPetBrief[];
  /** 当前查看的这只宠物有已经到期、后台还没结算到的事实：世界正在更新，工资与来信稍后出现（0.4.1） */
  catching_up?: boolean;
}
export type HomeSnapshotInput = WithOptional<HomeSnapshot, "pantry" | "plots" | "journey" | "welcome" | "unread" | "place" | "missing_capabilities" | "household" | "pets" | "catching_up">;

export interface CropInfo {
  crop_key: string;
  label: string;
  grow_seconds: number;
  yield_units: number;
  /** 每单位折算的 travel_coin */
  unit_value: number;
  /** 每一批作物全体访客合计最多可偷的单位数 */
  steal_total: number;
  /** 稀有作物：需要旅行带回的种子，种下时消耗一颗 */
  requires_seed: boolean;
}
export type CropInfoInput = WithOptional<CropInfo, "requires_seed">;

export interface NeighborPetBrief {
  pet_id: string;
  name: string;
  species: PetSpecies;
  avatar_url: string | null;
}
export type NeighborPetBriefInput = WithOptional<NeighborPetBrief, "avatar_url">;

export interface NeighborHomeSummary {
  home_id: string;
  pet: NeighborPetBrief;
  presence: PetPresence;
  /** 有人看着菜园（主人巡院或宠物在家）；宠物在家时仍可能偷到，只是几率低 */
  guarded: boolean;
  stealable_plots: number;
  /** 谁在看着菜园 */
  watch?: FarmWatch | null;
  data_origin: DataOrigin;
}
export type NeighborHomeSummaryInput = WithOptional<NeighborHomeSummary, "watch">;

export interface VisitorPlot {
  plot: PlotSummary;
  taken_by_me: boolean;
}
export type VisitorPlotInput = WithOptional<VisitorPlot, "taken_by_me">;

export interface NeighborHomeView {
  home_id: string;
  pet: NeighborPetBrief;
  presence: PetPresence;
  guarded: boolean;
  plots: VisitorPlot[];
  /** 谁在看着菜园 */
  watch?: FarmWatch | null;
  server_time: IsoDateTime;
  data_origin: DataOrigin;
}
export type NeighborHomeViewInput = WithOptional<NeighborHomeView, "plots" | "watch">;

/** 需 Idempotency-Key；同一批作物每位访客最多偷一次，全体合计不超过 steal_total。 */
export interface StealRequest {
  home_id: string;
  plot_id: string;
  cycle_id: string;
}
export type StealRequestInput = StealRequest;

/** 偷到的是物资（进自己的仓库），不是直接的游戏币。 */
export interface StealResult {
  home_id: string;
  plot: PlotSummary;
  gained_item_key: string;
  gained_units: number;
  message: string;
}
export type StealResultInput = StealResult;

export interface PatrolResult {
  guard: GuardState;
  message: string;
}
export type PatrolResultInput = PatrolResult;

/** 星球居民（公共 NPC，不是真实玩家）当天的收购订单；比杂货铺出价高，每单只能交一次。 */
export interface ResidentOrder {
  order_id: string;
  resident: string;
  item_key: string;
  item_label: string;
  qty: number;
  reward: number;
  /** 同样数量卖给杂货铺能得到的旅费，方便对比 */
  shop_value: number;
  fulfilled: boolean;
  can_fulfill: boolean;
  expires_at: IsoDateTime;
}
export type ResidentOrderInput = ResidentOrder;

export interface MarketView {
  pantry: InventoryItem[];
  wallet: WalletSummary;
  orders: ResidentOrder[];
  player_listing_enabled: boolean;
  player_listing_note: string;
  data_origin: DataOrigin;
}
export type MarketViewInput = WithOptional<MarketView, "pantry" | "orders" | "player_listing_enabled">;

/** 需 Idempotency-Key。 */
export interface SellRequest {
  item_key: string;
  qty: number;
}
export type SellRequestInput = SellRequest;

export interface MarketResult {
  wallet: WalletSummary;
  pantry: InventoryItem[];
  gained_coins: number;
  message: string;
}
export type MarketResultInput = WithOptional<MarketResult, "pantry">;

/** 主人给 TA 的出门建议（出发站上选一个地方）。TA 会认真考虑，但由 TA 自己决定去不去、什么时候去。 */
export interface SuggestRequest {
  destination_key: string;
}
export type SuggestRequestInput = SuggestRequest;

export interface JourneySuggestion {
  suggestion_id: string;
  destination_key: string;
  title: string;
  /** pending＝TA 还在考虑（出门一次没选它不算结束，24 小时内仍算数）；accepted＝TA 听了你的去了；passed＝考虑时间过了 TA 没去；replaced＝你改了建议 */
  status: SuggestionStatus;
  /** TA 最近一次出门时把这条建议一起想过的时刻（x-additive） */
  considered_at: IsoDateTime | null;
  created_at: IsoDateTime;
  decided_at: IsoDateTime | null;
}
export type JourneySuggestionInput = WithOptional<JourneySuggestion, "considered_at" | "decided_at">;

export interface TravelGuideStop {
  /** 核对到的真实名称；未核实时是 TA 写的名字 */
  name: string;
  /** TA 在攻略里写的叫法（手账图上用它） */
  label: string | null;
  /** 大概时段，例如“上午” */
  time: string | null;
  /** 为什么适合 TA */
  why: string | null;
  /** 给主人的实用提示；不确定的写“以现场为准” */
  tip: string | null;
  /** 是否用地图核对到了真实地点；未核实的不给地址 */
  verified: boolean;
  address: string | null;
  lat: number | null;
  lng: number | null;
  /** 地点资料来源，或“TA 听说的，未核实” */
  attribution: string | null;
  /** 核实过的地点：打开地图导航（高德，WGS-84 坐标） */
  nav_url?: string | null;
  /** 可复制的现实资料：名称与地址 */
  copy_text?: string | null;
}
export type TravelGuideStopInput = WithOptional<TravelGuideStop, "label" | "time" | "why" | "tip" | "address" | "lat" | "lng" | "attribution" | "nav_url" | "copy_text">;

/** TA 的攻略手账：出门前写的一日小攻略，主人也能照着走。 */
export interface TravelGuide {
  guide_id: string;
  journey_id: string;
  city: string;
  destination_title: string;
  title: string;
  summary: string | null;
  stops: TravelGuideStop[];
  owner_tips: string[];
  /** model＝TA 用自己的话写的（模型）；template＝模板 */
  composed_by: string;
  /** 写实手账图生成状态；没有开启“生成照片”时为空 */
  image_status: PhotoStatus | null;
  image_url: string | null;
  created_at: IsoDateTime;
  /** 这是 TA 的计划：planned 还没出发，in_progress 正在路上，completed 已经回来 */
  status?: GuideStatus | null;
  /** 实际到过的站点（已经发生的经历，与计划分开） */
  visited?: string[];
  /** 这趟花的星币（游戏内，从 TA 的银行卡出） */
  coin_budget?: number | null;
  /** 现实出行的花费说明（不用星币换算） */
  real_budget_note?: string | null;
  /** 整份攻略的纯文本（只含核实过的站点与地址、家人叮嘱与现实花费说明），可以直接复制给家人照着走 */
  copy_text?: string | null;
}
export type TravelGuideInput = WithOptional<TravelGuide, "summary" | "stops" | "owner_tips" | "image_status" | "image_url" | "status" | "visited" | "coin_budget" | "real_budget_note" | "copy_text">;

/** TA 的一份工作：岗位、地点、开始与结束时间、状态和工资（完成后才入账，按旅程只入一次）。 */
export interface JobRecord {
  journey_id: string;
  job_key: string;
  title: string;
  place: string | null;
  starts_at: IsoDateTime;
  ends_at: IsoDateTime;
  /** going 去上班的路上 / working 在干活 / done 干完了 */
  status: string;
  pay: number;
  /** 工资是否已经进了银行卡 */
  paid: boolean;
}
export type JobRecordInput = WithOptional<JobRecord, "place">;

/** 生活时间线：旅行、打工、证件、驾考、朋友、明信片……都来自已经发生的记录。 */
export interface TimelineItem {
  at: IsoDateTime;
  kind: string;
  title: string;
  detail: string | null;
  ref_id: string | null;
}
export type TimelineItemInput = WithOptional<TimelineItem, "detail" | "ref_id">;

/** 事实字段可缺省，不编造。place_id 带来源命名空间。 */
export interface Place {
  provider: PlaceProvider;
  place_id: string;
  name: string;
  address: string | null;
  lat: number;
  lng: number;
  coord_system: CoordSystem;
  category: string | null;
  source_updated_at: IsoDateTime | null;
  attribution: string | null;
  data_origin: DataOrigin;
}
export type PlaceInput = WithOptional<Place, "address" | "category" | "source_updated_at" | "attribution">;

export interface VisitActivity {
  activity_id: string;
  kind: VisitActivityKind;
  label: string;
  state: VisitActivityState;
  result_text: string | null;
}
export type VisitActivityInput = WithOptional<VisitActivity, "result_text">;

/** visit_id 由 Journey 服务在确认下一站时创建；推荐 ID 不等于 visit_id。 */
export interface Visit {
  visit_id: string;
  journey_id: string;
  pet_id: string;
  place: Place;
  state: VisitState;
  template: VenueTemplate;
  planned_arrival_utc: IsoDateTime | null;
  arrived_at: IsoDateTime | null;
  leaving_at: IsoDateTime | null;
  recommendation_id: string | null;
  activities: VisitActivity[];
  /** 店内为原创动物世界场景，不代表真实商家内饰 */
  interior_is_original: boolean;
  data_origin: DataOrigin;
}
export type VisitInput = WithOptional<Visit, "planned_arrival_utc" | "arrived_at" | "leaving_at" | "recommendation_id" | "activities" | "interior_is_original">;

/** 需 Idempotency-Key。 */
export interface VisitActionRequest {
  activity_id: string;
}
export type VisitActionRequestInput = VisitActionRequest;

/** 出发站选项。time_basis 标明时长依据；demo_fixture 表示演示线路（未接入真实路线/时刻表）。 */
export interface DestinationOption {
  destination_key: string;
  title: string;
  city: string;
  summary: string;
  /** 这趟的星币标价。**出发时从统一账本扣除，但持驾校借车券的首次自驾不扣**——所以「账本里没有这一行」有两种含义（用了券／本来免费），不要据此推断花了多少；实际扣没扣见行程的 fare_waived（m1701） */
  fee: number;
  /** 门到门往返总时长（真实经过时间，不压缩） */
  total_minutes: number;
  modes: string[];
  time_basis: string;
  /** 与主人确认过的愿望对应时的说明 */
  wish_match: string | null;
  affordable: boolean;
  /** 现在能不能去（现实资料拿不到时为 false，见 unavailable_reason） */
  available?: boolean;
  unavailable_reason?: string | null;
  /** 现实参考资料的来源说明（例如运营方船期与参考票价）；星币旅费与现实票价无关 */
  reference_note?: string | null;
}
export type DestinationOptionInput = WithOptional<DestinationOption, "modes" | "wish_match" | "available" | "unavailable_reason" | "reference_note">;

/** 现实参考票价（运营方公布，含来源）；与星币旅费无关，TA 在星球上的出行只花星币。 */
export interface ReferenceFare {
  currency: string;
  amount: number;
  fare_class: string;
  /** day_weekday / day_weekend_holiday / night */
  band: string;
  effective_from: string;
  note: string;
  source_url: string;
}
export type ReferenceFareInput = ReferenceFare;

export interface PlannedLegPreview {
  sequence: number;
  /** outbound / return */
  direction: string;
  kind: LegKind;
  mode: TransportMode;
  origin: TransportNode;
  destination: TransportNode;
  departs_at: IsoDateTime;
  arrives_at: IsoDateTime;
  time_basis: TimeBasis;
  time_source: LegTimeSource | null;
  source_label: string;
  /** 现实参考班次编号（已核验船期按服务日期落地） */
  reference_id: string | null;
  /** 动物世界承运人（出发时按参考班次分配稳定编号） */
  world_carrier: string | null;
  reference_fare: ReferenceFare | null;
}
export type PlannedLegPreviewInput = WithOptional<PlannedLegPreview, "time_source" | "reference_id" | "world_carrier" | "reference_fare">;

/** 出发前看一眼真实行程（0.4.0）：不扣钱、不生成行程、不分配编号；出门时间从开船时间反推。计划不是已发生的事。 */
export interface TripPlanPreview {
  destination_key: string;
  title: string;
  city: string;
  /** 星币旅费（世界内经济） */
  fee: number;
  leave_home_at: IsoDateTime;
  returns_home_at: IsoDateTime;
  stay_minutes: number;
  venue: Place;
  legs: PlannedLegPreview[];
  notes: string[];
  data_origin: DataOrigin;
}
export type TripPlanPreviewInput = WithOptional<TripPlanPreview, "notes">;

/** 需 Idempotency-Key；宠物必须在家、已入住，旅费足够。 */
export interface DepartRequest {
  destination_key: string;
}
export type DepartRequestInput = DepartRequest;

/** 到店前改选寻味推荐的分店：行程版本 +1，旧推荐待复核。需 Idempotency-Key。 */
export interface VisitChoiceRequest {
  recommendation_id: string;
  expected_itinerary_version: number;
}
export type VisitChoiceRequestInput = VisitChoiceRequest;

/** verified=False 表示示意节点（例如旧代码插值出的中转点），不得冒充真实枢纽。 */
export interface TransportNode {
  node_id: string;
  name: string;
  kind: NodeKind;
  /** IANA 时区，例如 Asia/Hong_Kong */
  timezone: string;
  lat: number | null;
  lng: number | null;
  verified: boolean;
}
export type TransportNodeInput = WithOptional<TransportNode, "lat" | "lng" | "verified">;

/** 现实参考：仅服务端核验与来源说明使用；主界面展示 WorldService。 */
export interface TransportReference {
  reference_id: string;
  provider: string;
  operating_instance_id: string;
  service_date: IsoDate;
  operator_name: string | null;
  marketing_codes: string[];
  origin: TransportNode;
  destination: TransportNode;
  scheduled_departure_utc: IsoDateTime | null;
  scheduled_arrival_utc: IsoDateTime | null;
  estimated_departure_utc: IsoDateTime | null;
  estimated_arrival_utc: IsoDateTime | null;
  actual_departure_utc: IsoDateTime | null;
  actual_arrival_utc: IsoDateTime | null;
  time_basis: TimeBasis;
  freshness: DataFreshness;
  source_url: string | null;
  fetched_at: IsoDateTime | null;
  verified_at: IsoDateTime | null;
  usage_scope: string | null;
}
export type TransportReferenceInput = WithOptional<TransportReference, "operator_name" | "marketing_codes" | "scheduled_departure_utc" | "scheduled_arrival_utc" | "estimated_departure_utc" | "estimated_arrival_utc" | "actual_departure_utc" | "actual_arrival_utc" | "source_url" | "fetched_at" | "verified_at" | "usage_scope">;

/** 发给客户端的最小来源说明，不含现实班次号作为主展示。 */
export interface TransportReferenceSummary {
  reference_id: string | null;
  time_basis: TimeBasis;
  freshness: DataFreshness;
  source_label: string;
  verified_at: IsoDateTime | null;
}
export type TransportReferenceSummaryInput = WithOptional<TransportReferenceSummary, "reference_id" | "verified_at">;

/** 动物世界承运身份：同一运营实例稳定映射（唯一约束 + mapping_version），刷新不换号。 */
export interface WorldService {
  world_service_id: string;
  carrier_name: string;
  service_code: string;
  mode: TransportMode;
  vehicle_style: string | null;
  reference_id: string | null;
  mapping_version: number;
}
export type WorldServiceInput = WithOptional<WorldService, "vehicle_style" | "reference_id" | "mapping_version">;

export interface LegTimes {
  origin_timezone: string;
  destination_timezone: string;
  planned_departure_utc: IsoDateTime;
  planned_arrival_utc: IsoDateTime;
  estimated_departure_utc: IsoDateTime | null;
  estimated_arrival_utc: IsoDateTime | null;
  actual_departure_utc: IsoDateTime | null;
  actual_arrival_utc: IsoDateTime | null;
}
export type LegTimesInput = WithOptional<LegTimes, "estimated_departure_utc" | "estimated_arrival_utc" | "actual_departure_utc" | "actual_arrival_utc">;

export interface JourneyLeg {
  leg_id: string;
  journey_id: string;
  sequence: number;
  kind: LegKind;
  mode: TransportMode;
  role: TravellerRole;
  world_service: WorldService | null;
  origin: TransportNode;
  destination: TransportNode;
  times: LegTimes;
  time_basis: TimeBasis;
  freshness: DataFreshness;
  position_basis: PositionBasis;
  phase: LegPhase;
  itinerary_version: number;
  /** 有几何才沿线呈现；仅节点时为示意 */
  route: LatLng[];
  reference: TransportReferenceSummary | null;
  rescheduled_reason: string | null;
  /** 这段时间的精确来源（见 LegTimeSource）；world_rule 的 time_basis 为 routed_estimate */
  time_source?: LegTimeSource | null;
}
export type JourneyLegInput = WithOptional<JourneyLeg, "world_service" | "route" | "reference" | "rescheduled_reason" | "time_source">;

/** 由服务器时间与已确认时间线计算；客户端只做平滑插值呈现，不决定到达。 */
export interface VehiclePosition {
  leg_id: string;
  lat: number;
  lng: number;
  heading_deg: number;
  progress: number;
  computed_at: IsoDateTime;
  position_basis: PositionBasis;
}
export type VehiclePositionInput = WithOptional<VehiclePosition, "heading_deg">;

export interface TravelActivity {
  activity_id: string;
  leg_id: string;
  kind: TravelActivityKind;
  state: TravelActivityState;
  starts_at: IsoDateTime;
  ends_at: IsoDateTime | null;
  media_session_id: string | null;
  interruptible: boolean;
  version: number;
}
export type TravelActivityInput = WithOptional<TravelActivity, "ends_at" | "media_session_id" | "interruptible" | "version">;

/** 地图车辆旁的音符/电视入口；badge 由实际 TravelActivity 决定，无活动则不下发。 */
export interface MapActivityEntry {
  entry_id: string;
  leg_id: string;
  activity_id: string;
  badge: ActivityBadgeKind;
  badge_state: TravelActivityState;
  media_session_id: string | null;
  label: string;
  actions: MapEntryAction[];
}
export type MapActivityEntryInput = WithOptional<MapActivityEntry, "media_session_id" | "actions">;

/** Journey → FoodDiscovery 的时间契约：门到门可行到达与可停留窗口，不只看落地时刻。 */
export interface PetArrivalContext {
  journey_id: string;
  itinerary_version: number;
  leg_id: string;
  city: string;
  destination_timezone: string;
  feasible_arrival_utc: IsoDateTime;
  stay_window_start_utc: IsoDateTime;
  stay_window_end_utc: IsoDateTime;
}
export type PetArrivalContextInput = PetArrivalContext;

export interface JourneyMapSnapshot {
  journey_id: string;
  pet_id: string;
  itinerary_version: number;
  /** active / completed / cancelled */
  lifecycle: string;
  destination_title: string | null;
  /** 宠物此刻在店里时才有值 */
  current_visit_id: string | null;
  /** 本次旅程的到访（出发即确定；到店前可按寻味推荐改选） */
  planned_visit_id: string | null;
  server_time: IsoDateTime;
  legs: JourneyLeg[];
  current_leg_id: string | null;
  vehicle: VehiclePosition | null;
  activities: TravelActivity[];
  activity_entries: MapActivityEntry[];
  arrival_context: PetArrivalContext | null;
  data_origin: DataOrigin;
  /** 有已经到期、后台还没结算到的事实（到站、收工、回家……）：位置照常按时间显示，工资与来信稍后出现；不是出错（0.4.1） */
  catching_up?: boolean;
}
export type JourneyMapSnapshotInput = WithOptional<JourneyMapSnapshot, "lifecycle" | "destination_title" | "current_visit_id" | "planned_visit_id" | "legs" | "current_leg_id" | "vehicle" | "activities" | "activity_entries" | "arrival_context" | "catching_up">;

/** 旅途地图的真实底图（服务端代理高德静态地图）。available=false 时前端退回示意地图，并说明原因。 */
export interface BasemapView {
  available: boolean;
  reason: BasemapUnavailableReason | null;
  provider: BasemapProvider | null;
  /** 同源图片地址（需登录），图片为 2 倍清晰度；图上自带供应商标志与审图号，不得遮挡或裁掉 */
  image_url: string | null;
  /** 图片中心（WGS-84）；叠加物按 WGS-84 做 Web Mercator 投影即可对齐 */
  center: LatLng | null;
  /** Web Mercator 缩放级别（256 像素瓦片） */
  zoom: number | null;
  /** 图片逻辑宽度（CSS 像素） */
  width: number | null;
  /** 图片逻辑高度（CSS 像素） */
  height: number | null;
  attribution: string | null;
  expires_at: IsoDateTime | null;
}
export type BasemapViewInput = WithOptional<BasemapView, "reason" | "provider" | "image_url" | "center" | "zoom" | "width" | "height" | "attribution" | "expires_at">;

export interface MediaLicense {
  status: LicenseStatus;
  allows_in_app_playback: boolean;
  allows_sync: boolean;
  public_release_allowed: boolean;
  regions: string[];
  expires_at: IsoDateTime | null;
  note: string | null;
}
export type MediaLicenseInput = WithOptional<MediaLicense, "public_release_allowed" | "regions" | "expires_at" | "note">;

export interface MediaAsset {
  media_id: string;
  kind: MediaKind;
  title: string;
  creator: string | null;
  /** 作品版本；版本不同不能标同步 */
  edition: string;
  duration_ms: number;
  src_url: string | null;
  poster_url: string | null;
  external_url: string | null;
  availability: MediaAvailability;
  license: MediaLicense;
  data_origin: DataOrigin;
}
export type MediaAssetInput = WithOptional<MediaAsset, "creator" | "src_url" | "poster_url" | "external_url">;

export interface MediaAnchor {
  position_ms: number;
  server_time: IsoDateTime;
  playback_rate: number;
}
export type MediaAnchorInput = WithOptional<MediaAnchor, "playback_rate">;

export interface ControlLease {
  holder_device_id: string | null;
  lease_expires_at: IsoDateTime | null;
}
export type ControlLeaseInput = WithOptional<ControlLease, "holder_device_id" | "lease_expires_at">;

export interface CompanionSession {
  session_id: string;
  activity_id: string;
  pet_id: string;
  media: MediaAsset;
  state: MediaSessionState;
  anchor: MediaAnchor;
  revision: number;
  resume_policy: ResumePolicy;
  control: ControlLease | null;
  saved_progress_ms: number | null;
  interrupt_reason: InterruptReason | null;
  /** 驾驶中为 false：服务端拒绝切换到视频 */
  video_allowed: boolean;
  data_origin: DataOrigin;
}
export type CompanionSessionInput = WithOptional<CompanionSession, "control" | "saved_progress_ms" | "interrupt_reason">;

/** 只有 synced 且在允许偏差内、心跳未过期才累计 counted_ms；页面停留不等于陪伴。 */
export interface Participation {
  session_id: string;
  device_id: string;
  mode: ParticipationMode;
  since: IsoDateTime;
  last_heartbeat_at: IsoDateTime | null;
  counted_ms: number;
}
export type ParticipationInput = WithOptional<Participation, "last_heartbeat_at" | "counted_ms">;

export interface CompanionJoinRequest {
  device_id: string;
  mode: ParticipationMode;
}
export type CompanionJoinRequestInput = WithOptional<CompanionJoinRequest, "mode">;

export interface CompanionLeaveRequest {
  device_id: string;
}
export type CompanionLeaveRequestInput = CompanionLeaveRequest;

/** 需 Idempotency-Key；session_revision 过期返回 409 VERSION_CONFLICT。 */
export interface CompanionCommandRequest {
  device_id: string;
  command: CompanionCommandKind;
  session_revision: number;
  position_ms: number | null;
}
export type CompanionCommandRequestInput = WithOptional<CompanionCommandRequest, "position_ms">;

export interface CompanionHeartbeatRequest {
  device_id: string;
  player_state: ParticipationMode;
  position_ms: number;
  media_edition: string;
  client_time: IsoDateTime;
}
export type CompanionHeartbeatRequestInput = CompanionHeartbeatRequest;

/** -2（很不喜欢）… 2（很喜欢）；null 表示未知，不等于中性。 */
export interface TasteVector {
  sweet: number | null;
  salty: number | null;
  spicy: number | null;
  oily: number | null;
  aromatic_spice: number | null;
  rich_broth: number | null;
  crispy: number | null;
}
export type TasteVectorInput = WithOptional<TasteVector, "sweet" | "salty" | "spicy" | "oily" | "aromatic_spice" | "rich_broth" | "crispy">;

export interface DietaryRestriction {
  kind: DietaryRestrictionKind;
  label: string;
  /** 恒为私密；公开/社交接口不得输出 */
  private: boolean;
}
export type DietaryRestrictionInput = WithOptional<DietaryRestriction, "private">;

export interface FoodPreference {
  preference_id: string;
  subject: PreferenceSubject;
  pet_id: string;
  version: number;
  /** 主人可读的偏好名，例如“清淡”“浓郁” */
  label: string;
  taste: TasteVector;
  budget: MoneyAmount | null;
  max_wait_minutes: number | null;
  party_size: number | null;
  restrictions: DietaryRestriction[];
  source: PreferenceSource;
  updated_at: IsoDateTime;
}
export type FoodPreferenceInput = WithOptional<FoodPreference, "budget" | "max_wait_minutes" | "party_size" | "restrictions">;

export interface SourceRating {
  provider: string;
  rating: number | null;
  /** 平台总评价数 */
  source_rating_count: number | null;
  /** 本系统实际取得并分析的样本数 */
  observed_sample_count: number;
  fetched_at: IsoDateTime | null;
}
export type SourceRatingInput = WithOptional<SourceRating, "rating" | "source_rating_count" | "observed_sample_count" | "fetched_at">;

/** branch_id 含来源命名空间（amap:/google:/fixture:）；总店证据不自动转移给分店。 */
export interface Branch {
  branch_id: string;
  name: string;
  brand: string | null;
  place: Place | null;
  ratings: SourceRating[];
}
export type BranchInput = WithOptional<Branch, "brand" | "place" | "ratings">;

export interface Dish {
  dish_id: string;
  branch_id: string;
  name: string;
  price: MoneyAmount | null;
  flavor_traits: string[];
}
export type DishInput = WithOptional<Dish, "price" | "flavor_traits">;

export interface EvidenceCitation {
  evidence_id: string;
  source_kind: EvidenceSourceKind;
  source_label: string;
  aspect: string;
  observation: string;
  observed_at: IsoDateTime | null;
  sample_count: number;
}
export type EvidenceCitationInput = WithOptional<EvidenceCitation, "observed_at" | "sample_count">;

export interface JudgementScores {
  quality: number | null;
  match: number | null;
  value: number | null;
  logistics: number | null;
  uncertainty: number | null;
}
export type JudgementScoresInput = WithOptional<JudgementScores, "quality" | "match" | "value" | "logistics" | "uncertainty">;

export interface DishSuggestion {
  dish: Dish;
  why: string;
  evidence: EvidenceCitation[];
}
export type DishSuggestionInput = WithOptional<DishSuggestion, "evidence">;

export interface RecommendationProvenance {
  generated_at: IsoDateTime;
  fact_version: string;
  preference_version: number;
  rule_version: string;
  data_status: FoodDataStatus;
  coverage_note: string;
}
export type RecommendationProvenanceInput = RecommendationProvenance;

/** 主人现实用餐：使用主人自己的日期/位置/时间，不套宠物行程。 */
export interface OwnerDiningContext {
  plan_date: IsoDate;
  meal_time_local: string;
  timezone: string;
  city: string;
  area: string | null;
}
export type OwnerDiningContextInput = WithOptional<OwnerDiningContext, "area">;

export interface FoodRecommendation {
  recommendation_id: string;
  mode: FoodMode;
  branch: Branch;
  dishes: DishSuggestion[];
  scores: JudgementScores;
  eligibility: EligibilityStatus;
  group: RecommendationGroup;
  rank: number | null;
  reasons: string[];
  not_suitable_when: string[];
  unknowns: string[];
  provenance: RecommendationProvenance;
  freshness: RecommendationFreshness;
  /** pet 模式绑定的行程版本；变化后 needs_recheck */
  itinerary_version: number | null;
  data_origin: DataOrigin;
}
export type FoodRecommendationInput = WithOptional<FoodRecommendation, "dishes" | "rank" | "reasons" | "not_suitable_when" | "unknowns" | "itinerary_version">;

export interface FoodRecommendationRequest {
  mode: FoodMode;
  pet_id: string;
  preference_id: string | null;
  pet_context: PetArrivalContext | null;
  owner_context: OwnerDiningContext | null;
  /** 确定性场景配置键，例如 special_trip / quick_bite */
  scene: string | null;
  max_results: number;
}
export type FoodRecommendationRequestInput = WithOptional<FoodRecommendationRequest, "preference_id" | "pet_context" | "owner_context" | "scene" | "max_results">;

export interface FoodRecommendationList {
  mode: FoodMode;
  preference: FoodPreference;
  items: FoodRecommendation[];
  /** 数量不足时如实说明，不强造三个 */
  shortfall_note: string | null;
  data_origin: DataOrigin;
}
export type FoodRecommendationListInput = WithOptional<FoodRecommendationList, "items" | "shortfall_note">;

/** 主人实际用餐反馈；不同于虚拟到访 visit_id，需 Idempotency-Key。 */
export interface FoodFeedback {
  feedback_id: string | null;
  recommendation_id: string;
  dish_ids: string[];
  verdict: FeedbackVerdict;
  reasons: string[];
  note: string | null;
  dined_on: IsoDate;
  verification: FeedbackVerification;
}
export type FoodFeedbackInput = WithOptional<FoodFeedback, "feedback_id" | "dish_ids" | "reasons" | "note" | "verification">;

/** 可配置的公共 NPC 接待角色；不是平台管理员，也不占专属领养池。 */
export interface ReceptionHost {
  host_id: string;
  display_name: string;
  role_label: string;
  avatar_url: string | null;
  is_ai: boolean;
  disclosure: string;
}
export type ReceptionHostInput = WithOptional<ReceptionHost, "avatar_url" | "is_ai">;

export interface ReceptionTurn {
  turn_id: string;
  seq: number;
  speaker: TurnSpeaker;
  text: string;
  created_at: IsoDateTime;
  /** 接待员这句话的来源：guided（固定引导）/ model（对话模型）；主人的话为空 */
  composed_by?: string | null;
}
export type ReceptionTurnInput = WithOptional<ReceptionTurn, "composed_by">;

export interface IntakeCandidate {
  candidate_id: string;
  kind: CandidateKind;
  subject: CandidateSubject;
  text: string;
  source_turn_id: string;
  /** 原话依据片段，主人可展开核对 */
  source_excerpt: string;
  needs_clarification: boolean;
  suggested_slot: CareNoteSlot | null;
  suggested_slot_value: string | null;
  state: CandidateState;
}
export type IntakeCandidateInput = WithOptional<IntakeCandidate, "needs_clarification" | "suggested_slot" | "suggested_slot_value">;

export interface ReceptionSession {
  session_id: string;
  pet_id: string;
  branch: ReceptionBranch;
  mode: ReceptionMode;
  status: ReceptionStatus;
  host: ReceptionHost;
  turns: ReceptionTurn[];
  candidates: IntakeCandidate[];
  draft_revision: number;
  draft_expires_at: IsoDateTime | null;
  data_origin: DataOrigin;
}
export type ReceptionSessionInput = WithOptional<ReceptionSession, "turns" | "candidates" | "draft_expires_at">;

/** 需 Idempotency-Key；同一宠物已有进行中的会话时返回该会话（继续草稿）。 */
export interface ReceptionStartRequest {
  pet_id: string;
  branch: ReceptionBranch;
  /** 主人选择让接待员用对话模型回应（会把本次接待中主人写的话发送给模型服务商）；不可用时退回引导便笺 */
  use_model?: boolean;
}
export type ReceptionStartRequestInput = WithOptional<ReceptionStartRequest, "use_model">;

/** 需 Idempotency-Key；expected_revision 过期返回 409 VERSION_CONFLICT。 */
export interface ReceptionTurnRequest {
  text: string;
  expected_revision: number;
}
export type ReceptionTurnRequestInput = ReceptionTurnRequest;

export interface CareNoteDecision {
  candidate_id: string;
  /** 主人编辑后的最终文字 */
  text: string;
  target: SaveTarget;
  purposes: MemoryPurpose[];
  slot: CareNoteSlot | null;
  slot_value: string | null;
}
export type CareNoteDecisionInput = WithOptional<CareNoteDecision, "purposes" | "slot" | "slot_value">;

/** 需 Idempotency-Key；draft_revision 与服务端不一致返回 409 VERSION_CONFLICT。 */
export interface IntakeConfirmationRequest {
  session_id: string;
  draft_revision: number;
  decisions: CareNoteDecision[];
}
export type IntakeConfirmationRequestInput = IntakeConfirmationRequest;

export interface CareNote {
  note_id: string;
  pet_id: string;
  kind: CandidateKind;
  subject: CandidateSubject;
  text: string;
  target: SaveTarget;
  purposes: MemoryPurpose[];
  slot: CareNoteSlot | null;
  slot_value: string | null;
  version: number;
  confirmed_at: IsoDateTime;
  supersedes_note_id: string | null;
  revoked_at: IsoDateTime | null;
}
export type CareNoteInput = WithOptional<CareNote, "purposes" | "slot" | "slot_value" | "supersedes_note_id" | "revoked_at">;

export interface MemoryGrant {
  grant_id: string;
  note_id: string;
  note_version: number;
  purpose: MemoryPurpose;
  granted_at: IsoDateTime;
  revoked_at: IsoDateTime | null;
}
export type MemoryGrantInput = WithOptional<MemoryGrant, "revoked_at">;

export interface IntakeConfirmationResult {
  confirmation_id: string;
  session_id: string;
  draft_revision: number;
  persist_state: PersistState;
  notes: CareNote[];
  grants: MemoryGrant[];
  onboarding: OnboardingState;
  data_origin: DataOrigin;
}
export type IntakeConfirmationResultInput = WithOptional<IntakeConfirmationResult, "notes" | "grants">;

export interface ProjectedNote {
  note_id: string;
  note_version: number;
  kind: CandidateKind;
  text: string;
  slot: CareNoteSlot | null;
  slot_value: string | null;
}
export type ProjectedNoteInput = WithOptional<ProjectedNote, "slot" | "slot_value">;

/** 按用途的最小投影；只读消费不扩大许可。 */
export interface MemoryProjection {
  pet_id: string;
  purpose: MemoryPurpose;
  items: ProjectedNote[];
  policy_version: string;
  generated_at: IsoDateTime;
}
export type MemoryProjectionInput = WithOptional<MemoryProjection, "items">;

/** 需 Idempotency-Key。先停止使用旧版本，再清理衍生物。 */
export interface MemoryCorrectionRequest {
  action: MemoryCorrectionAction;
  expected_version: number;
  new_text: string | null;
  /** 槽位值（如称呼）；不填则按新文字重新建议，无法确定时清空而不沿用旧值 */
  new_slot_value: string | null;
}
export type MemoryCorrectionRequestInput = WithOptional<MemoryCorrectionRequest, "new_text" | "new_slot_value">;

export interface MemoryCorrectionResult {
  note_id: string;
  new_note: CareNote | null;
  cleanup: CleanupState;
  affected_task_ids: string[];
}
export type MemoryCorrectionResultInput = WithOptional<MemoryCorrectionResult, "new_note" | "affected_task_ids">;

export interface ActorRef {
  actor_kind: ActorKind;
  actor_id: string;
  display_name: string;
  avatar_url: string | null;
  /** 真实账号家庭的宠物/主人为 true；NPC 恒为 false */
  is_real_household: boolean;
}
export type ActorRefInput = WithOptional<ActorRef, "avatar_url">;

export interface PostMedia {
  media_id: string;
  kind: string;
  url: string | null;
  alt: string | null;
  /** AI 生成图为 true；生成图不代表真实到店照片 */
  generated: boolean;
}
export type PostMediaInput = WithOptional<PostMedia, "url" | "alt">;

export interface Post {
  post_id: string;
  author: ActorRef;
  text: string;
  media: PostMedia[];
  /** 来源世界事件；普通动作不逐条发帖 */
  source_event_id: string;
  visit_id: string | null;
  visibility: PostVisibility;
  created_at: IsoDateTime;
  reaction_count: number;
  comment_count: number;
  viewer_reacted: boolean;
  data_origin: DataOrigin;
}
export type PostInput = WithOptional<Post, "media" | "visit_id" | "reaction_count" | "comment_count" | "viewer_reacted">;

export interface Comment {
  comment_id: string;
  post_id: string;
  actor: ActorRef;
  reply_to_comment_id: string | null;
  text: string;
  created_at: IsoDateTime;
  removed: boolean;
}
export type CommentInput = WithOptional<Comment, "reply_to_comment_id" | "removed">;

export interface PostPage {
  items: Post[];
  next_cursor: string | null;
}
export type PostPageInput = WithOptional<PostPage, "items" | "next_cursor">;

export interface CommentPage {
  items: Comment[];
  next_cursor: string | null;
}
export type CommentPageInput = WithOptional<CommentPage, "items" | "next_cursor">;

/** 需 Idempotency-Key；同一行动者对同一帖只计一次。 */
export interface ReactionRequest {
  as_actor: ActorKind;
}
export type ReactionRequestInput = ReactionRequest;

/** 需 Idempotency-Key。 */
export interface CommentRequest {
  as_actor: ActorKind;
  text: string;
  reply_to_comment_id: string | null;
}
export type CommentRequestInput = WithOptional<CommentRequest, "reply_to_comment_id">;

export interface FollowRequest {
  follow: boolean;
}
export type FollowRequestInput = WithOptional<FollowRequest, "follow">;

/** 屏蔽某条动态/评论的作者（不暴露对方账号 ID）。 */
export interface BlockRequest {
  post_id: string | null;
  comment_id: string | null;
}
export type BlockRequestInput = WithOptional<BlockRequest, "post_id" | "comment_id">;

export interface ReportRequest {
  target_kind: string;
  target_id: string;
  reason: string;
}
export type ReportRequestInput = ReportRequest;

export interface MessageSummary {
  message_id: string;
  client_message_id: string | null;
  sender: MessageSender;
  text: string;
  state: MessageDeliveryState;
  created_at: IsoDateTime;
  photo_url: string | null;
  /** 宠物消息的来源；主人消息为空 */
  composed_by?: MessageComposer | null;
  /** 附图（冒险插画）状态；无附图为空 */
  photo_status?: PhotoStatus | null;
  /** TA 主动发来的消息的话题 */
  topic?: MessageTopic | null;
  /** 主人消息等待回复时的说明，例如“TA 睡着啦，醒来会看到” */
  status_note?: string | null;
  /** 预计回复时间（等待中才有） */
  expected_reply_at?: IsoDateTime | null;
  /** 这条消息在哪个频道（0.4.0 家庭共同照顾） */
  channel?: MessageChannel;
  /** 由世界事件产生的来信指向那个事件（<journey_id>:<事件键>），同一事件全家只有一条；其他消息为空（0.4.1） */
  source_event_id?: string | null;
  /** TA 的这条回复针对的家人消息编号（0.4.1） */
  reply_to?: string | null;
}
export type MessageSummaryInput = WithOptional<MessageSummary, "client_message_id" | "photo_url" | "composed_by" | "photo_status" | "topic" | "status_note" | "expected_reply_at" | "channel" | "source_event_id" | "reply_to">;

export interface MessageThread {
  pet_id: string;
  items: MessageSummary[];
  next_cursor: string | null;
  data_origin: DataOrigin;
}
export type MessageThreadInput = WithOptional<MessageThread, "items" | "next_cursor">;

/** client_message_id 即幂等键（复用旧 communicator 的 (pet_id, client_message_id) 去重）。 */
export interface SendMessageRequest {
  client_message_id: string;
  text: string;
}
export type SendMessageRequestInput = SendMessageRequest;

export interface CollectionItem {
  item_id: string;
  kind: string;
  /** 可种植种子的作物键（kind=seed 时有值） */
  item_key: string | null;
  title: string;
  obtained_at: IsoDateTime;
  tradable: boolean;
  bound_to_pet: boolean;
  source_event_id: string | null;
  data_origin: DataOrigin;
  /** 明信片上 TA 写给主人的话 */
  note?: string | null;
  /** 明信片上的写实自拍（生成完成后才有；仅主人可读） */
  image_url?: string | null;
  /** 自拍生成状态；没有开启“生成照片”时为空 */
  image_status?: PhotoStatus | null;
  /** 寄出明信片的地方 */
  place?: string | null;
  city?: string | null;
}
export type CollectionItemInput = WithOptional<CollectionItem, "item_key" | "source_event_id" | "note" | "image_url" | "image_status" | "place" | "city">;

/** TA 在外面遇到的朋友：真实宠物（同一时间同一地点遇到）或星球居民（NPC，明确标注）。 */
export interface FriendSummary {
  friend_id: string;
  kind: FriendKind;
  name: string;
  species: string | null;
  meet_count: number;
  /** 初识 / 熟人 / 好朋友 */
  closeness: string;
  first_met_at: IsoDateTime;
  last_met_at: IsoDateTime;
  last_place: string | null;
}
export type FriendSummaryInput = WithOptional<FriendSummary, "species" | "last_place">;

/** 原文片段依据：start/end 为 Python 字符串（Unicode 码点）下标，必须能在对应消息原文中匹配。 */
export interface SpanRef {
  start: number;
  end: number;
  text: string;
  offset_unit: string;
}
export type SpanRefInput = WithOptional<SpanRef, "offset_unit">;

export interface IntentSignal {
  kind: SignalKind;
  subject: SignalSubject;
  target: string | null;
  temporal: TemporalScope;
  negated: boolean;
  quoted: boolean;
  span: SpanRef;
  usage_limits: UsageLimit[];
  /** judge（判断器）/ parser（解析步骤）；来源必须可区分 */
  source: string;
}
export type IntentSignalInput = WithOptional<IntentSignal, "target" | "negated" | "quoted" | "usage_limits">;

export interface DecisionEvidence {
  provider: IntentProvider;
  requested_model: string | null;
  /** 只有真实返回时才填写 */
  effective_model: string | null;
  rule_version: string;
  question_version: string | null;
  raw_probabilities: Record<string, number> | null;
  /** 输出分布集中度，不是正确率，也不是用户许可 */
  confidence: number | null;
  latency_ms: number;
  usage_note: string | null;
  error: string | null;
  degraded_reason: string | null;
}
export type DecisionEvidenceInput = WithOptional<DecisionEvidence, "requested_model" | "effective_model" | "question_version" | "raw_probabilities" | "confidence" | "usage_note" | "error" | "degraded_reason">;

/** 最小上下文：账号归属由服务端提供；不附全量私密记忆。 */
export interface IntentContext {
  request_id: string;
  message_id: string;
  channel: IntentChannel;
  language: string;
  recent_context: string[];
  candidate_targets: string[];
  state_version: string | null;
}
export type IntentContextInput = WithOptional<IntentContext, "language" | "recent_context" | "candidate_targets" | "state_version">;

export interface IntentAssessment {
  assessment_id: string;
  signals: IntentSignal[];
  unknown: boolean;
  needs_clarification: boolean;
  conflicts: string[];
  evidence: DecisionEvidence;
}
export type IntentAssessmentInput = WithOptional<IntentAssessment, "signals" | "unknown" | "needs_clarification" | "conflicts">;

export interface ActionProposal {
  proposal_id: string;
  kind: ActionProposalKind;
  target: string | null;
  expected_state_version: string | null;
  requires_confirmation: boolean;
  /** 领域校验结论（代码产生），例如 route_change_not_allowed_by_intent */
  domain_check: string | null;
  note: string | null;
}
export type ActionProposalInput = WithOptional<ActionProposal, "target" | "expected_state_version" | "requires_confirmation" | "domain_check" | "note">;

export interface ActionOutcome {
  proposal_id: string;
  state: ActionOutcomeState;
  operation_id: string | null;
  result_version: string | null;
  message: string | null;
}
export type ActionOutcomeInput = WithOptional<ActionOutcome, "operation_id" | "result_version" | "message">;

export interface CredentialLink {
  /** journey / leg / visit / exam / home */
  kind: string;
  ref_id: string;
  title: string;
  at: IsoDateTime | null;
}
export type CredentialLinkInput = WithOptional<CredentialLink, "at">;

export interface CredentialField {
  label: string;
  value: string;
}
export type CredentialFieldInput = CredentialField;

export interface CredentialSummary {
  /** 尚未获得时为空 */
  credential_id: string | null;
  kind: CredentialKind;
  /** 星球居民证 / 星球银行卡 / 照护档案 / 护照 / 爪爪驾驶证 / 登机牌 / 船票车票 / 酒店房卡 */
  label: string;
  status: CredentialStatus;
  /** 稳定唯一的证件编号；签发后不变 */
  number: string | null;
  /** 持久保存的签发时间；刷新不会变成“今天签发” */
  issued_at: IsoDateTime | null;
  title: string | null;
  /** 获得条件 */
  condition: string;
  /** 只给主人看（照护档案等），不进公开卡片 */
  private: boolean;
  /** 关联的经历 */
  links: CredentialLink[];
}
export type CredentialSummaryInput = WithOptional<CredentialSummary, "credential_id" | "number" | "issued_at" | "title" | "private" | "links">;

export interface LedgerEntry {
  tx_id: string;
  type: string;
  delta: number;
  reason: string;
  created_at: IsoDateTime;
  /** 这笔钱关联的业务：journey（旅费、工资、退款）/ order（集市订单）/ home（家园商店、欢迎礼）；其他为空 */
  ref_kind?: string | null;
  /** 关联业务的编号，例如工资与旅费对应的 journey_id（0.4.1） */
  ref_id?: string | null;
}
export type LedgerEntryInput = WithOptional<LedgerEntry, "ref_kind" | "ref_id">;

export interface PassportStamp {
  city: string;
  stamped_at: IsoDateTime;
  journey_id: string;
  title: string;
}
export type PassportStampInput = PassportStamp;

export interface CredentialDetail {
  summary: CredentialSummary;
  /** 卡面信息（服务端给出，前端只负责排版） */
  fields: CredentialField[];
  /** 星球银行卡：现有钱包余额（同一个账户，不另建余额） */
  balance: number | null;
  /** 星球银行卡：最近的收入与支出 */
  ledger: LedgerEntry[];
  /** 护照：到达后盖的纪念章 */
  stamps: PassportStamp[];
  /** 照护档案：主人确认过的习惯、安抚方式与叮嘱（私密） */
  care_notes: string[];
}
export type CredentialDetailInput = WithOptional<CredentialDetail, "fields" | "balance" | "ledger" | "stamps" | "care_notes">;

export interface SessionBrief {
  session_id: string;
  subject: SchoolSubject;
  mode: SessionMode;
  item: string | null;
  attempt_kind: AttemptKind | null;
  state: SchoolSessionState;
  passed: boolean | null;
  score: number | null;
  created_at: IsoDateTime;
  settled_at: IsoDateTime | null;
}
export type SessionBriefInput = WithOptional<SessionBrief, "item" | "attempt_kind" | "passed" | "score" | "settled_at">;

export interface SubjectStatus {
  subject: SchoolSubject;
  title: string;
  theme: string;
  /** quiz（科一、科四）/ drive（科二、科三） */
  kind: string;
  state: SubjectState;
  passed_at: IsoDateTime | null;
  passed_score: number | null;
  /** 旧版驾考已通过（此前自动答题的版本），不再需要考试 */
  legacy: boolean;
  /** 第几轮（冷却结束后开始新一轮） */
  round_no: number;
  /** 本轮已经用掉的正式考试次数（0—2） */
  attempts_used: number;
  /** 本轮还剩几次正式考试（首次＋补考共 2 次） */
  attempts_left: number;
  /** 下一次正式考试是首次还是补考 */
  next_attempt: AttemptKind | null;
  /** 冷却中时：可以再约考试的时间（服务器时间） */
  cooldown_until: IsoDateTime | null;
  /** 锁定时的原因，例如“先通过科目一” */
  unlock_hint: string | null;
  /** 这一科未结束的正式考局，回来可以接着考 */
  open_session_id: string | null;
  last_result: SessionBrief | null;
  practice_count: number;
}
export type SubjectStatusInput = WithOptional<SubjectStatus, "passed_at" | "passed_score" | "legacy" | "next_attempt" | "cooldown_until" | "unlock_hint" | "open_session_id" | "last_result" | "practice_count">;

export interface CoachInfo {
  name: string;
  line: string;
  intro: string;
}
export type CoachInfoInput = CoachInfo;

export interface DrivingSchoolStatus {
  stage: SchoolStage;
  /** TA 为什么想学开车 */
  wish_text: string | null;
  enrolled_at: IsoDateTime | null;
  coach: CoachInfo;
  subjects: SubjectStatus[];
  /** 未结束的正式考局（同一时间最多一场） */
  open_session: SessionBrief | null;
  license: CredentialSummary | null;
  /** 还有一张驾校借车券（第一次自驾免租车费） */
  voucher_available: boolean;
  /** 领证仪式已经做过 */
  ceremony_done: boolean;
  /** lively / steady / quiet：挑选 TA 台词的性格（来自 DNA 行为画像） */
  temperament: string;
  rules_version: string;
  server_time: IsoDateTime;
}
export type DrivingSchoolStatusInput = WithOptional<DrivingSchoolStatus, "wish_text" | "enrolled_at" | "open_session" | "license" | "voucher_available" | "ceremony_done">;

export interface LessonStep {
  title: string;
  body: string;
}
export type LessonStepInput = LessonStep;

export interface DeductionRule {
  label: string;
  points: number;
}
export type DeductionRuleInput = DeductionRule;

export interface ItemInfo {
  /** reverse_park / side_park / curve / route；练习另有 reverse_straight / reverse_turn */
  item: string;
  title: string;
  time_limit_s: number;
}
export type ItemInfoInput = ItemInfo;

export interface SubjectCurriculum {
  subject: SchoolSubject;
  title: string;
  theme: string;
  format: string;
  pass_rule: string;
  pass_score: number;
  duration: string;
  kind: string;
  lessons: LessonStep[];
  deductions: DeductionRule[];
  /** 红线：触发即自动制动、本次不通过（开考前必须展示） */
  red_lines: string[];
  /** 正式考试的项目（科二三项、科三一条路线） */
  items: ItemInfo[];
  practice_items: ItemInfo[];
}
export type SubjectCurriculumInput = WithOptional<SubjectCurriculum, "items" | "practice_items">;

export interface SchoolCurriculum {
  rules_version: string;
  coach: CoachInfo;
  subjects: SubjectCurriculum[];
  controls: string[];
  retake_rule: string[];
  cooldown_hours: number;
  /** 按性格（lively / steady / quiet）的台词：pass / fail / park / right / license */
  pet_lines: Record<string, Record<string, string>>;
  /** 判定事件与扣分的说明文字（line → 压线、red_light → 闯了红灯……），前端实时提示与成绩单共用 */
  reasons: Record<string, string>;
}
export type SchoolCurriculumInput = SchoolCurriculum;

export interface QuizOption {
  option_id: string;
  label: string;
}
export type QuizOptionInput = QuizOption;

export interface QuizTarget {
  target_id: string;
  label: string;
}
export type QuizTargetInput = QuizTarget;

/** 题目（不含答案）。match：把 options 放到 targets 上；order：把 options 排成正确顺序。 */
export interface QuizQuestionView {
  question_id: string;
  kind: QuizKind;
  /** 场景插画的键（前端按键绘制） */
  scene: string;
  topic_title: string;
  prompt: string;
  options: QuizOption[];
  targets: QuizTarget[];
  /** 科四：同一段情境的两个判断共用一个 group */
  group: string | null;
  group_title: string | null;
  story: string[];
}
export type QuizQuestionViewInput = WithOptional<QuizQuestionView, "targets" | "group" | "group_title" | "story">;

export interface QuizAnswer {
  choice: string | null;
  order: string[] | null;
  /** {target_id: option_id} */
  matches: Record<string, string> | null;
}
export type QuizAnswerInput = WithOptional<QuizAnswer, "choice" | "order" | "matches">;

export interface QuizFeedback {
  question_id: string;
  correct: boolean;
  correct_answer: QuizAnswer;
  explanation: string;
  pet_line: string;
}
export type QuizFeedbackInput = QuizFeedback;

export interface QuizProgress {
  questions: QuizQuestionView[];
  /** 已保存的作答（续考时恢复） */
  answers: Record<string, QuizAnswer>;
  /** 练习模式的即时讲解；正式模式交卷前为空 */
  feedback: Record<string, QuizFeedback>;
}
export type QuizProgressInput = WithOptional<QuizProgress, "answers" | "feedback">;

export interface InputEvent {
  /** tick（每秒 30 个），每一项从 0 开始 */
  t: number;
  /** s 转向目标 / t 油门 / b 刹车 / g 换挡 / k 转向灯 / c 出发前检查 / v 视频邀请 */
  c: string;
  v: number;
}
export type InputEventInput = InputEvent;

export interface SimEvent {
  t: number;
  /** line / cone / out_of_bounds / timeout / done / precheck_skipped / start_no_signal / stop_rolled / crosswalk / red_light / turn_no_signal / speeding / invite_shown / invite_opened */
  k: string;
  ref: string | null;
  /** 扣分 */
  p: number;
  /** 1＝红线或失败，本项立即结束 */
  f: number;
}
export type SimEventInput = WithOptional<SimEvent, "ref">;

export interface DriveItemProgress {
  item: string;
  title: string;
  /** 场地配置：车身、正切表、速度、线、锥桶、目标区、时限、路线检查点与装饰（渲染用） */
  course: Record<string, unknown>;
  /** pending / running / done / failed */
  status: string;
  committed_tick: number;
  /** 服务端已接受的操作（续考时本地重放恢复状态） */
  events: InputEvent[];
  /** 服务端复算出的判定事件 */
  sim_events: SimEvent[];
  /** 服务端复算到 committed_tick 时的模拟快照（用于对齐） */
  snapshot: Record<string, unknown> | null;
}
export type DriveItemProgressInput = WithOptional<DriveItemProgress, "events" | "sim_events" | "snapshot">;

export interface DriveProgress {
  items: DriveItemProgress[];
  current_item: number;
}
export type DriveProgressInput = DriveProgress;

export interface Deduction {
  kind: string;
  label: string;
  points: number;
  item: string | null;
  t: number | null;
  ref: string | null;
  question_id: string | null;
}
export type DeductionInput = WithOptional<Deduction, "item" | "t" | "ref" | "question_id">;

export interface QuestionReview {
  question_id: string;
  prompt: string;
  correct: boolean;
  your_answer: QuizAnswer | null;
  correct_answer: QuizAnswer;
  explanation: string;
}
export type QuestionReviewInput = WithOptional<QuestionReview, "your_answer">;

export interface ItemResult {
  item: string;
  title: string;
  status: string;
  deducted: number;
  ticks: number;
}
export type ItemResultInput = ItemResult;

export interface NextStep {
  /** passed / licensed / retake / cooldown / practice */
  kind: string;
  message: string;
  attempts_left: number | null;
  cooldown_until: IsoDateTime | null;
}
export type NextStepInput = WithOptional<NextStep, "attempts_left" | "cooldown_until">;

export interface SessionResult {
  passed: boolean;
  score: number;
  max_score: number;
  pass_score: number;
  deductions: Deduction[];
  /** 红线或失败原因（科二科三），例如超时、闯红灯、主动放弃 */
  fatal: Deduction | null;
  /** 科一科四：结算后才给出正确答案与讲解 */
  review: QuestionReview[];
  items: ItemResult[];
  pet_says: string;
  next: NextStep | null;
}
export type SessionResultInput = WithOptional<SessionResult, "deductions" | "fatal" | "review" | "items" | "next">;

export interface SchoolSession {
  session_id: string;
  subject: SchoolSubject;
  title: string;
  mode: SessionMode;
  item: string | null;
  attempt_kind: AttemptKind | null;
  round_no: number | null;
  state: SchoolSessionState;
  pass_score: number;
  created_at: IsoDateTime;
  begun_at: IsoDateTime | null;
  paused_at: IsoDateTime | null;
  settled_at: IsoDateTime | null;
  void_reason: string | null;
  quiz: QuizProgress | null;
  drive: DriveProgress | null;
  result: SessionResult | null;
}
export type SchoolSessionInput = WithOptional<SchoolSession, "item" | "attempt_kind" | "round_no" | "begun_at" | "paused_at" | "settled_at" | "void_reason" | "quiz" | "drive" | "result">;

export interface SessionCreateRequest {
  subject: SchoolSubject;
  mode: SessionMode;
  /** 练习单项（科二：reverse_straight / reverse_turn / reverse_park / side_park / curve）；不填为整科 */
  item: string | null;
}
export type SessionCreateRequestInput = WithOptional<SessionCreateRequest, "item">;

export interface AnswerRequest {
  question_id: string;
  answer: QuizAnswer;
}
export type AnswerRequestInput = AnswerRequest;

export interface AnswerResult {
  question_id: string;
  saved: boolean;
  answered: number;
  total: number;
  /** 只在练习模式返回 */
  feedback: QuizFeedback | null;
}
export type AnswerResultInput = WithOptional<AnswerResult, "feedback">;

export interface InputChunk {
  item_index: number;
  from_tick: number;
  upto_tick: number;
  events: InputEvent[];
}
export type InputChunkInput = WithOptional<InputChunk, "events">;

export interface InputResult {
  session_id: string;
  session_state: SchoolSessionState;
  item_index: number;
  current_item: number;
  item_status: string;
  committed_tick: number;
  new_events: SimEvent[];
  /** 这一场到目前为止的扣分合计（服务端复算） */
  deducted: number;
  snapshot: Record<string, unknown> | null;
  result: SessionResult | null;
}
export type InputResultInput = WithOptional<InputResult, "new_events" | "snapshot" | "result">;

export interface AbandonRequest {
  /** 必须为 true：放弃已经开始的正式考试，计为本次不通过 */
  confirm: boolean;
}
export type AbandonRequestInput = AbandonRequest;

export interface CeremonyResult {
  license: CredentialSummary;
  /** 领证合影（收藏） */
  memento: CollectionItem | null;
  /** 驾校借车券（第一次自驾免租车费；用掉后为空） */
  voucher: CollectionItem | null;
  pet_says: string;
  /** 这是第一次看仪式（再次打开只是回看） */
  first_time: boolean;
}
export type CeremonyResultInput = WithOptional<CeremonyResult, "memento" | "voucher">;

export interface PublicEntry {
  route: EntryRoute;
  label: string;
  needs_login: boolean;
  note: string | null;
}
export type PublicEntryInput = WithOptional<PublicEntry, "note">;

/** 一位还在星球上生活、可以领养的居民。住处是星球居民驿站（世界规则提供食宿，不是某位真实用户的家）。 */
export interface PublicResident {
  pet_id: string;
  candidate_id: string;
  name: string;
  species: PetSpecies;
  personality: string;
  dream: string;
  origin: PetOrigin;
  /** 来源说明；未知为 null，不编造 */
  source_note: string | null;
  /** 住在哪个驿站，例如“星球居民驿站·中环” */
  residence: string;
  city: string;
  living_since: IsoDateTime;
  /** 此刻在哪（按已发生的行程推算，访客读取不会推进世界） */
  presence: PetPresence;
  /** 此刻在做什么，例如“在驿站休息”“在去码头的路上” */
  doing: string;
  /** 正在到访的真实地点名（来自地图供应商的公开地点）；在驿站或路上时为空 */
  place_name: string | null;
  /** 最近的公开动态（最多 3 条） */
  recent_posts: Post[];
  /** TA 的照片（公开路由，访客可看）；没有照片为 null。与 `PublicPetView.profile.avatar_url` 同一个地址、同一条规则。平台原创居民的形象是生成的原创设计，不是真实照片 */
  avatar_url?: string | null;
}
export type PublicResidentInput = WithOptional<PublicResident, "source_note" | "place_name" | "recent_posts" | "avatar_url">;

export interface PublicPetView {
  profile: PetPublicProfile;
  /** 仍在驿站生活、可以领养时才有 */
  resident: PublicResident | null;
  adoptable: boolean;
  posts: Post[];
}
export type PublicPetViewInput = WithOptional<PublicPetView, "resident" | "adoptable" | "posts">;

export interface PublicWorld {
  server_time: IsoDateTime;
  entries: PublicEntry[];
  residents: PublicResident[];
  /** 全星球最近的公开动态 */
  recent_posts: Post[];
  living_residents: number;
  /** 这份内容最多缓存多久（访客页刷新不会每次都重算） */
  cache_seconds: number;
  data_origin: DataOrigin;
}
export type PublicWorldInput = WithOptional<PublicWorld, "recent_posts">;

export interface ProviderHealth {
  /** llm / amap / amap_static / google / image */
  provider: string;
  label: string;
  state: ProviderState;
  last_success_at: IsoDateTime | null;
  last_failure_at: IsoDateTime | null;
  /** 脱敏后的错误摘要 */
  last_error: string | null;
  calls_today: number;
  daily_cap: number | null;
}
export type ProviderHealthInput = WithOptional<ProviderHealth, "last_success_at" | "last_failure_at" | "last_error" | "calls_today" | "daily_cap">;

export interface WorldRunnerStatus {
  /** embedded（API 进程内）/ worker（独立任务进程）/ off */
  runner: string;
  interval_seconds: number;
  /** 这个 API 进程里的世界线程是否在跑 */
  running_here: boolean;
  /** 有没有进程持有有效租约（正在推进世界） */
  lease_alive: boolean;
  lease_holder_role: string | null;
  lease_pid: number | null;
  last_tick_at: IsoDateTime | null;
  last_ok_at: IsoDateTime | null;
  last_error: string | null;
  ticks: number;
  /** 最老一件已到期但还没登记的世界事实等了多少秒；持续变大说明这条线卡住了（0.4.1） */
  due_lag_seconds?: number | null;
}
export type WorldRunnerStatusInput = WithOptional<WorldRunnerStatus, "lease_holder_role" | "lease_pid" | "last_tick_at" | "last_ok_at" | "last_error" | "ticks" | "due_lag_seconds">;

export interface OutboxHealth {
  /** 世界事件下游：communicator / social / collection / credentials / guides / friends */
  consumer: string;
  pending: number;
  delivered: number;
  /** 重试用尽、需要人看的条数 */
  dead_letter: number;
  /** 最老一条待投递等了多少秒；持续变大说明这个下游卡住了 */
  oldest_pending_seconds: number | null;
}
export type OutboxHealthInput = WithOptional<OutboxHealth, "pending" | "delivered" | "dead_letter" | "oldest_pending_seconds">;

export interface RuntimeDueItem {
  /** 到期事项的引用，例如 journey:<旅程编号>、reply:<会话>；不含正文 */
  ref: string;
  /** journey / reply / cooldown / other */
  kind: string;
  due_at: IsoDateTime;
  /** 对家人的承诺（工钱、待回复）：不能被延期或丢弃 */
  commitment: boolean;
}
export type RuntimeDueItemInput = WithOptional<RuntimeDueItem, "commitment">;

/** 一只宠物此刻的运行详情（只给本机或管理令牌）：用来回答“TA 为什么这么安静”。 */
export interface PetRuntimeStatus {
  pet_id: string;
  as_of: IsoDateTime;
  realm_id: string;
  household_id: string | null;
  /** TA 此刻所在地的时区；认不出就是空，运行层会明确报不可用，不套用默认城市 */
  timezone: string | null;
  region_id: string | null;
  /** 家园 / 驿站 / 店铺 / 交通段的引用 */
  scene_ref: string | null;
  activity_kind: string;
  activity_ref: string | null;
  activity_ends_at: IsoDateTime | null;
  interruptible: boolean;
  /** 当地作息（入睡, 起床），来自 DNA 画像；未知为空 */
  sleep_window: string[];
  /** 语义版本代数：思考开始时记下，提交时再比一次 */
  versions: Record<string, number | null>;
  due_items: RuntimeDueItem[];
  next_check_at: IsoDateTime | null;
  /** 上一次决定时写下的「到这个时刻再重新考虑」。与 next_check_at 不是一回事：next_check_at 是**此刻**按当前事实算出来的下次查看时间，next_review_at 是**当时那次决定**留下的有效期（例如「先留在家，两小时后再看」）。两者都可能为空。 */
  next_review_at: IsoDateTime | null;
  /** 安静的原因：正常生活 / 暂无新决策 / 额度延期 / 依赖不可用 / 任务卡住 / 维护 */
  silence_reason: string | null;
  last_evaluated_at: IsoDateTime | null;
  last_decision_at: IsoDateTime | null;
  /** model / rule_fallback / rule */
  last_decision_by: string | null;
  maintenance: boolean;
  /** 按当前事实立刻评估一次心跳的结论（只读，不执行） */
  heartbeat_action: string | null;
  heartbeat_reasons: string[];
  /** 这只宠物的家庭是否同意把共用资料交给模型 */
  cognition_enabled: boolean;
  /** off / shadow / live */
  brain_mode: string;
}
export type PetRuntimeStatusInput = WithOptional<PetRuntimeStatus, "household_id" | "timezone" | "region_id" | "scene_ref" | "activity_ref" | "activity_ends_at" | "interruptible" | "sleep_window" | "versions" | "due_items" | "next_check_at" | "next_review_at" | "silence_reason" | "last_evaluated_at" | "last_decision_at" | "last_decision_by" | "maintenance" | "heartbeat_action" | "heartbeat_reasons" | "cognition_enabled">;

export interface FrontendHint {
  /** 前端应使用的数据模式：live 只走本后端；fixture 是演示数据，不连后端 */
  data_mode: string;
  api_base: string;
  /** vite dev/preview 的代理目标（PETSOUL_DEV_API_TARGET） */
  dev_proxy_target: string;
  note: string;
}
export type FrontendHintInput = FrontendHint;

export interface OpsStatus {
  /** dev / demo / real-local / staging / production（只是标签，不改变行为） */
  environment: string;
  server_time: IsoDateTime;
  backend_version: string;
  /** 正在使用的数据库文件（相对后端目录；目录外时为绝对路径） */
  database: string;
  media_dir: string;
  sqlite_wal: boolean;
  providers_enabled: boolean;
  providers: ProviderHealth[];
  world: WorldRunnerStatus;
  /** 认知线（可能调模型的表达与回复）：与世界线分开的线程和租约，卡住不影响到期结算（0.4.1） */
  cognition?: WorldRunnerStatus | null;
  applied_migrations: number;
  last_migration: string | null;
  capabilities: Capability[];
  frontend: FrontendHint;
  /** 后台任务：到期未领、领取中、租期已过仍在跑、用完次数、最老到期等待秒数（0.4.1） */
  tasks?: Record<string, number>;
  /** 世界事件各下游的投递情况（0.4.1） */
  outbox?: OutboxHealth[];
}
export type OpsStatusInput = WithOptional<OpsStatus, "cognition" | "last_migration" | "tasks" | "outbox">;

/** `GET /map/config` 的响应。未配置时 `available=false` 且 `js_key`/`service_host` 为空。 */
export interface MapConfig {
  provider: MapProvider;
  available: boolean;
  js_key: string | null;
  service_host: string | null;
  style: string;
  style_dark: string;
  overseas_tiles: boolean;
  unavailable_reason: MapUnavailableReason | null;
}
export type MapConfigInput = WithOptional<MapConfig, "provider" | "js_key" | "service_host" | "overseas_tiles" | "unavailable_reason">;

/** 家的模糊中心。**只给家庭成员**；非成员整个字段为 None，不是坐标置零。 */
export interface WorldHome {
  center: LatLng;
  precision_m: number;
  label: string;
}
export type WorldHomeInput = WorldHome;

export interface WorldJob {
  title: string;
  pay: number;
  paid: boolean;
}
export type WorldJobInput = WorldJob;

export interface WorldPlace {
  name: string;
  lat: number;
  lng: number;
  attribution: string | null;
}
export type WorldPlaceInput = WithOptional<WorldPlace, "attribution">;

/** 只在 going / returning 出现。`route` 用**出发时已缓存**的几何，没有就 `[]`——读时不调地图。 */
export interface WorldLeg {
  mode: string;
  route: LatLng[];
  departs_at: IsoDateTime | null;
  arrives_at: IsoDateTime | null;
}
export type WorldLegInput = WithOptional<WorldLeg, "route" | "departs_at" | "arrives_at">;

export interface WorldPosition {
  lat: number;
  lng: number;
  basis: WorldPositionBasis;
  precision_m: number;
}
export type WorldPositionInput = WorldPosition;

export interface WorldActivity {
  kind: WorldActivityKind;
  phase: WorldPhase;
  pose: WorldPose;
  title: string;
  doing: string | null;
  place: WorldPlace | null;
  since: IsoDateTime | null;
  until: IsoDateTime | null;
  job: WorldJob | null;
  journey_id: string | null;
  visit_id: string | null;
}
export type WorldActivityInput = WithOptional<WorldActivity, "doing" | "place" | "since" | "until" | "job" | "journey_id" | "visit_id">;

export interface WorldPetState {
  pet_id: string;
  name: string;
  species: string;
  avatar_url: string | null;
  relation: WorldRelation;
  home: WorldHome | null;
  activity: WorldActivity;
  leg: WorldLeg | null;
  position: WorldPosition | null;
  version: number;
}
export type WorldPetStateInput = WithOptional<WorldPetState, "avatar_url" | "home" | "leg" | "position" | "version">;

export interface WorldState {
  server_time: IsoDateTime;
  coord_system: string;
  cache_seconds: number;
  pets: WorldPetState[];
}
export type WorldStateInput = WithOptional<WorldState, "coord_system" | "cache_seconds" | "pets">;

export interface AnnouncementItem {
  item_id: string;
  slug: string;
  revision: number;
  title: string;
  body: string;
  severity: AnnouncementSeverity;
  link: string | null;
  image_asset_id: string | null;
  image_url: string | null;
  effective_at: IsoDateTime | null;
  expires_at: IsoDateTime | null;
}
export type AnnouncementItemInput = WithOptional<AnnouncementItem, "link" | "image_asset_id" | "image_url" | "effective_at" | "expires_at">;

export interface AnnouncementFeed {
  announcements: AnnouncementItem[];
  as_of: IsoDateTime;
  source: AnnouncementSource;
}
export type AnnouncementFeedInput = WithOptional<AnnouncementFeed, "announcements">;

export interface ReportOutcomeItem {
  report_id: string;
  target_kind: string;
  target_id: string;
  reason: string;
  created_at: IsoDateTime;
  status: ReportStatus;
  outcome: ReportOutcome;
  resolved_at: IsoDateTime | null;
  message: string;
}
export type ReportOutcomeItemInput = WithOptional<ReportOutcomeItem, "resolved_at">;

export interface MyReports {
  reports: ReportOutcomeItem[];
  note: string;
}
export type MyReportsInput = WithOptional<MyReports, "reports">;

/** TA 想去的一个地方。**「有心愿」不等于「可以出发」**（合同 §3）。 */
export interface TravelWishCandidate {
  destination_key: string;
  title: string;
  executable: boolean;
  blocked_by: TravelWaitingReason[];
}
export type TravelWishCandidateInput = WithOptional<TravelWishCandidate, "executable" | "blocked_by">;

/** 当前活动心愿（一只宠物同时只有一个 active 或 ready 的）。对应 A 的 `WishView`。 */
export interface TravelWish {
  wish_id: string;
  pet_id: string;
  wish_revision: number;
  status: TravelWishStatus;
  destination_key: string;
  destination_name: string;
  city: string;
  owner_reason: string;
  funds_goal: number | null;
  waiting_reasons: TravelWaitingReason[];
  research_state: TravelResearchStatus | null;
  research_round: number;
  plan_id: string | null;
  plan_revision: number | null;
  journey_id: string | null;
  reconsider_after: IsoDateTime | null;
  last_considered_at: IsoDateTime | null;
  plan_stale: boolean;
  target_coins: number | null;
  current_coins: number | null;
  candidates: TravelWishCandidate[];
}
export type TravelWishInput = WithOptional<TravelWish, "funds_goal" | "waiting_reasons" | "research_state" | "research_round" | "plan_id" | "plan_revision" | "journey_id" | "reconsider_after" | "last_considered_at" | "plan_stale" | "target_coins" | "current_coins" | "candidates">;

/** 一条来源。`url` 可空——只有机构名没有链接时也是合法来源。 */
export interface TravelSource {
  source_id: string;
  url: string | null;
  publisher: string | null;
  retrieved_at: IsoDateTime | null;
  published_at: IsoDateTime | null;
}
export type TravelSourceInput = WithOptional<TravelSource, "url" | "publisher" | "retrieved_at" | "published_at">;

/** 一条已核验（或已被判否）的事实。 */
export interface TravelFact {
  fact_id: string;
  category: string;
  subject: string;
  value: unknown;
  source_ids: string[];
  verification: string | null;
  conclusion: string | null;
  verdict: TravelFactVerdict;
  blocks_departure: boolean;
  retrieved_at: IsoDateTime | null;
  published_at: IsoDateTime | null;
  observed_at: IsoDateTime | null;
  valid_from: IsoDateTime | null;
  valid_until: IsoDateTime | null;
}
export type TravelFactInput = WithOptional<TravelFact, "value" | "source_ids" | "verification" | "conclusion" | "blocks_departure" | "retrieved_at" | "published_at" | "observed_at" | "valid_from" | "valid_until">;

/** 计划里的一个地点。 */
export interface TravelStop {
  station_id: string | null;
  name: string;
  role: TravelStopRole;
  why: string | null;
  tip: string | null;
  fact_ids: string[];
  verified: boolean;
  lat: number | null;
  lng: number | null;
  nav_url: string | null;
  visited_event_ids: string[];
}
export type TravelStopInput = WithOptional<TravelStop, "station_id" | "why" | "tip" | "fact_ids" | "verified" | "lat" | "lng" | "nav_url" | "visited_event_ids">;

/** 给主人的一条提醒，**和支持它的事实一一对应**——没有 `fact_ids` 的提醒不该出现（§18.4）。 */
export interface TravelOwnerTip {
  text: string;
  fact_ids: string[];
}
export type TravelOwnerTipInput = WithOptional<TravelOwnerTip, "fact_ids">;

/** 计划关联的那趟真实行程里，跟钱有关的部分。 */
export interface TravelJourneySummary {
  journey_id: string;
  fare: number;
  fare_waived: boolean;
}
export type TravelJourneySummaryInput = WithOptional<TravelJourneySummary, "fare" | "fare_waived">;

/** 一版计划（`web_travel_plans` 的一行，主键 `(plan_id, plan_revision)`）。**旧版都留着。** */
export interface TravelPlanRevision {
  plan_id: string;
  plan_revision: number;
  wish_id: string;
  wish_revision_at_build: number;
  pet_id: string;
  destination_key: string;
  operation_id: string | null;
  title: string;
  summary: string;
  rain_alternative: string | null;
  stops: TravelStop[];
  owner_tips: TravelOwnerTip[];
  preconditions: string[];
  sources: TravelSource[];
  facts: TravelFact[];
  valid_from: IsoDateTime | null;
  valid_until: IsoDateTime | null;
  journey: TravelJourneySummary | null;
  journals: TravelJournal[];
  created_at: IsoDateTime;
}
export type TravelPlanRevisionInput = WithOptional<TravelPlanRevision, "operation_id" | "rain_alternative" | "stops" | "owner_tips" | "preconditions" | "sources" | "facts" | "valid_from" | "valid_until" | "journey" | "journals">;

/** 一个心愿的计划全集。`current_revision` 指最新发布的那一版。 */
export interface TravelPlan {
  plan_id: string;
  wish_id: string;
  current_revision: number;
  revisions: TravelPlanRevision[];
}
export type TravelPlanInput = WithOptional<TravelPlan, "revisions">;

/** 一页手账（`web_travel_journals` 的一行，主键 `(journal_id, journal_revision)`）。 */
export interface TravelJournal {
  journal_id: string;
  journal_revision: number;
  plan_id: string;
  plan_revision: number;
  phase: TravelJournalPhase;
  title: string | null;
  summary: string | null;
  stations: TravelStop[];
  owner_tips: TravelOwnerTip[];
  rain_alternative: string | null;
  sources: TravelSource[];
  identity_mode: TravelIdentityMode;
  identity_note: string | null;
  template_revision: string | null;
  image_status: PhotoStatus | null;
  image_url: string | null;
  image_refused: string | null;
  redraw_ticket: string | null;
  event_ids: string[];
  created_at: IsoDateTime;
  updated_at: IsoDateTime | null;
}
export type TravelJournalInput = WithOptional<TravelJournal, "title" | "summary" | "stations" | "owner_tips" | "rain_alternative" | "sources" | "identity_mode" | "identity_note" | "template_revision" | "image_status" | "image_url" | "image_refused" | "redraw_ticket" | "event_ids" | "updated_at">;

export interface WebEndpoint {
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  path: string;
  auth: "public" | "optional" | "required";
  csrf: boolean;
  idempotency: boolean;
}

export const WEB_ENDPOINTS = {
  "adopt": { method: "POST", path: "/adoption/adopt", auth: "required", csrf: true, idempotency: true },
  "adoption_candidates": { method: "GET", path: "/adoption/candidates", auth: "required", csrf: false, idempotency: false },
  "announcements": { method: "GET", path: "/announcements", auth: "optional", csrf: false, idempotency: false },
  "public_asset": { method: "GET", path: "/assets/{asset_id}", auth: "public", csrf: false, idempotency: false },
  "login": { method: "POST", path: "/auth/login", auth: "public", csrf: false, idempotency: false },
  "logout": { method: "POST", path: "/auth/logout", auth: "optional", csrf: true, idempotency: false },
  "register": { method: "POST", path: "/auth/register", auth: "public", csrf: false, idempotency: false },
  "block": { method: "POST", path: "/blocks", auth: "required", csrf: true, idempotency: false },
  "correct_note": { method: "POST", path: "/care-notes/{note_id}/corrections", auth: "required", csrf: true, idempotency: true },
  "circle_feed": { method: "GET", path: "/circle/feed", auth: "required", csrf: false, idempotency: false },
  "list_collection": { method: "GET", path: "/collection", auth: "required", csrf: false, idempotency: false },
  "retry_collection_image": { method: "POST", path: "/collection/{pet_id}/items/{item_id}/retry-image", auth: "required", csrf: true, idempotency: false },
  "remove_comment": { method: "DELETE", path: "/comments/{comment_id}", auth: "required", csrf: true, idempotency: false },
  "list_messages": { method: "GET", path: "/communicator/{pet_id}/messages", auth: "required", csrf: false, idempotency: false },
  "send_message": { method: "POST", path: "/communicator/{pet_id}/messages", auth: "required", csrf: true, idempotency: false },
  "retry_photo": { method: "POST", path: "/communicator/{pet_id}/messages/{message_id}/retry-photo", auth: "required", csrf: true, idempotency: false },
  "list_credentials": { method: "GET", path: "/credentials", auth: "required", csrf: false, idempotency: false },
  "credential_detail": { method: "GET", path: "/credentials/{credential_id}", auth: "required", csrf: false, idempotency: false },
  "driving_status": { method: "GET", path: "/driving", auth: "required", csrf: false, idempotency: false },
  "ceremony": { method: "POST", path: "/driving/ceremony", auth: "required", csrf: true, idempotency: false },
  "driving_curriculum": { method: "GET", path: "/driving/curriculum", auth: "required", csrf: false, idempotency: false },
  "enroll": { method: "POST", path: "/driving/enroll", auth: "required", csrf: true, idempotency: false },
  "history": { method: "GET", path: "/driving/history", auth: "required", csrf: false, idempotency: false },
  "create_session": { method: "POST", path: "/driving/sessions", auth: "required", csrf: true, idempotency: true },
  "get_session": { method: "GET", path: "/driving/sessions/{session_id}", auth: "required", csrf: false, idempotency: false },
  "abandon": { method: "POST", path: "/driving/sessions/{session_id}/abandon", auth: "required", csrf: true, idempotency: false },
  "answer": { method: "PUT", path: "/driving/sessions/{session_id}/answers", auth: "required", csrf: true, idempotency: false },
  "begin": { method: "POST", path: "/driving/sessions/{session_id}/begin", auth: "required", csrf: true, idempotency: false },
  "inputs": { method: "POST", path: "/driving/sessions/{session_id}/inputs", auth: "required", csrf: true, idempotency: false },
  "pause": { method: "POST", path: "/driving/sessions/{session_id}/pause", auth: "required", csrf: true, idempotency: false },
  "submit": { method: "POST", path: "/driving/sessions/{session_id}/submit", auth: "required", csrf: true, idempotency: false },
  "farm_action": { method: "POST", path: "/farm/actions", auth: "required", csrf: true, idempotency: true },
  "crops": { method: "GET", path: "/farm/crops", auth: "required", csrf: false, idempotency: false },
  "patrol": { method: "POST", path: "/farm/patrol", auth: "required", csrf: true, idempotency: false },
  "steal": { method: "POST", path: "/farm/steal", auth: "required", csrf: true, idempotency: true },
  "submit_feedback": { method: "POST", path: "/food/feedback", auth: "required", csrf: true, idempotency: true },
  "get_food_preference": { method: "GET", path: "/food/preferences/{subject}", auth: "required", csrf: false, idempotency: false },
  "put_food_preference": { method: "PUT", path: "/food/preferences/{subject}", auth: "required", csrf: true, idempotency: true },
  "request_recommendations": { method: "POST", path: "/food/recommendations", auth: "required", csrf: true, idempotency: false },
  "get_recommendation": { method: "GET", path: "/food/recommendations/{recommendation_id}", auth: "required", csrf: false, idempotency: false },
  "friends": { method: "GET", path: "/friends", auth: "required", csrf: false, idempotency: false },
  "guides": { method: "GET", path: "/guides", auth: "required", csrf: false, idempotency: false },
  "guide": { method: "GET", path: "/guides/{guide_id}", auth: "required", csrf: false, idempotency: false },
  "retry_guide_image": { method: "POST", path: "/guides/{pet_id}/{guide_id}/retry-image", auth: "required", csrf: true, idempotency: false },
  "home_snapshot": { method: "GET", path: "/home", auth: "required", csrf: false, idempotency: false },
  "read_place": { method: "GET", path: "/home/place", auth: "required", csrf: false, idempotency: false },
  "choose_place": { method: "PUT", path: "/home/place", auth: "required", csrf: true, idempotency: false },
  "visit_home": { method: "GET", path: "/homes/{home_id}", auth: "required", csrf: false, idempotency: false },
  "my_households": { method: "GET", path: "/households", auth: "required", csrf: false, idempotency: false },
  "household_detail": { method: "GET", path: "/households/{household_id}", auth: "required", csrf: false, idempotency: false },
  "list_invites": { method: "GET", path: "/households/{household_id}/invites", auth: "required", csrf: false, idempotency: false },
  "create_invite": { method: "POST", path: "/households/{household_id}/invites", auth: "required", csrf: true, idempotency: false },
  "revoke_invite": { method: "DELETE", path: "/households/{household_id}/invites/{invite_id}", auth: "required", csrf: true, idempotency: false },
  "remove_member": { method: "DELETE", path: "/households/{household_id}/members/{user_id}", auth: "required", csrf: true, idempotency: false },
  "set_member_role": { method: "PUT", path: "/households/{household_id}/members/{user_id}/role", auth: "required", csrf: true, idempotency: false },
  "update_household_settings": { method: "PATCH", path: "/households/{household_id}/settings", auth: "required", csrf: true, idempotency: false },
  "accept_invite": { method: "POST", path: "/invites/accept", auth: "required", csrf: true, idempotency: false },
  "preview_invite": { method: "POST", path: "/invites/preview", auth: "optional", csrf: false, idempotency: false },
  "jobs": { method: "GET", path: "/jobs", auth: "required", csrf: false, idempotency: false },
  "depart": { method: "POST", path: "/journey/depart", auth: "required", csrf: true, idempotency: true },
  "destinations": { method: "GET", path: "/journey/destinations", auth: "required", csrf: false, idempotency: false },
  "journey_leg": { method: "GET", path: "/journey/legs/{leg_id}", auth: "required", csrf: false, idempotency: false },
  "journey_map": { method: "GET", path: "/journey/map", auth: "required", csrf: false, idempotency: false },
  "journey_plan": { method: "GET", path: "/journey/plan", auth: "required", csrf: false, idempotency: false },
  "suggest": { method: "POST", path: "/journey/suggest", auth: "required", csrf: true, idempotency: false },
  "suggestions": { method: "GET", path: "/journey/suggestions", auth: "required", csrf: false, idempotency: false },
  "basemap": { method: "GET", path: "/map/basemap", auth: "required", csrf: false, idempotency: false },
  "map_config": { method: "GET", path: "/map/config", auth: "public", csrf: false, idempotency: false },
  "market_view": { method: "GET", path: "/market", auth: "required", csrf: false, idempotency: false },
  "market_fulfill": { method: "POST", path: "/market/orders/{order_id}/fulfill", auth: "required", csrf: true, idempotency: true },
  "market_sell": { method: "POST", path: "/market/sell", auth: "required", csrf: true, idempotency: true },
  "basemap_image": { method: "GET", path: "/media/basemaps/{basemap_id}", auth: "required", csrf: false, idempotency: false },
  "character_media": { method: "GET", path: "/media/characters/{asset_id}", auth: "required", csrf: false, idempotency: false },
  "id_photo_media": { method: "GET", path: "/media/id-photos/{asset_id}", auth: "required", csrf: false, idempotency: false },
  "id_photo_avatar": { method: "GET", path: "/media/id-photos/{asset_id}/avatar", auth: "required", csrf: false, idempotency: false },
  "illustration": { method: "GET", path: "/media/illustrations/{illustration_id}", auth: "required", csrf: false, idempotency: false },
  "pet_photo": { method: "GET", path: "/media/pets/{pet_id}/photo", auth: "required", csrf: false, idempotency: false },
  "postcard": { method: "GET", path: "/media/postcards/{photo_id}", auth: "required", csrf: false, idempotency: false },
  "get_media_session": { method: "GET", path: "/media/sessions/{session_id}", auth: "required", csrf: false, idempotency: false },
  "command_media_session": { method: "POST", path: "/media/sessions/{session_id}/commands", auth: "required", csrf: true, idempotency: true },
  "heartbeat_media_session": { method: "POST", path: "/media/sessions/{session_id}/heartbeat", auth: "required", csrf: true, idempotency: false },
  "join_media_session": { method: "POST", path: "/media/sessions/{session_id}/join", auth: "required", csrf: true, idempotency: false },
  "leave_media_session": { method: "POST", path: "/media/sessions/{session_id}/leave", auth: "required", csrf: true, idempotency: false },
  "web_meta": { method: "GET", path: "/meta", auth: "public", csrf: false, idempotency: false },
  "neighbors": { method: "GET", path: "/neighbors", auth: "required", csrf: false, idempotency: false },
  "onboarding_state": { method: "GET", path: "/onboarding", auth: "required", csrf: false, idempotency: false },
  "move_in": { method: "POST", path: "/onboarding/move-in", auth: "required", csrf: true, idempotency: false },
  "pet_runtime": { method: "GET", path: "/ops/runtime/{pet_id}", auth: "public", csrf: false, idempotency: false },
  "ops_status": { method: "GET", path: "/ops/status", auth: "public", csrf: false, idempotency: false },
  "create_own_pet": { method: "POST", path: "/pets", auth: "required", csrf: true, idempotency: true },
  "list_care_notes": { method: "GET", path: "/pets/{pet_id}/care-notes", auth: "required", csrf: false, idempotency: false },
  "character_state": { method: "GET", path: "/pets/{pet_id}/character", auth: "required", csrf: false, idempotency: false },
  "character_regenerate": { method: "POST", path: "/pets/{pet_id}/character/regenerate", auth: "required", csrf: true, idempotency: true },
  "read_dna": { method: "GET", path: "/pets/{pet_id}/dna", auth: "required", csrf: false, idempotency: false },
  "save_dna": { method: "PUT", path: "/pets/{pet_id}/dna", auth: "required", csrf: true, idempotency: false },
  "follow": { method: "POST", path: "/pets/{pet_id}/follow", auth: "required", csrf: true, idempotency: false },
  "home_welcome": { method: "GET", path: "/pets/{pet_id}/home-welcome", auth: "required", csrf: false, idempotency: false },
  "id_photo_regenerate": { method: "POST", path: "/pets/{pet_id}/id-photo/regenerate", auth: "required", csrf: true, idempotency: true },
  "add_pet_photo": { method: "PUT", path: "/pets/{pet_id}/photo", auth: "required", csrf: true, idempotency: true },
  "photo_request": { method: "POST", path: "/pets/{pet_id}/photo-request", auth: "required", csrf: true, idempotency: true },
  "photo_requests": { method: "GET", path: "/pets/{pet_id}/photo-requests", auth: "required", csrf: false, idempotency: false },
  "retry_photo_request": { method: "POST", path: "/pets/{pet_id}/photo-requests/{request_id}/retry-image", auth: "required", csrf: true, idempotency: false },
  "pet_posts": { method: "GET", path: "/pets/{pet_id}/posts", auth: "required", csrf: false, idempotency: false },
  "pet_public_profile": { method: "GET", path: "/pets/{pet_id}/profile", auth: "required", csrf: false, idempotency: false },
  "read_relationship": { method: "GET", path: "/pets/{pet_id}/relationship", auth: "required", csrf: false, idempotency: false },
  "save_relationship": { method: "PUT", path: "/pets/{pet_id}/relationship", auth: "required", csrf: true, idempotency: false },
  "remove_post": { method: "DELETE", path: "/posts/{post_id}", auth: "required", csrf: true, idempotency: false },
  "get_post": { method: "GET", path: "/posts/{post_id}", auth: "required", csrf: false, idempotency: false },
  "post_comments": { method: "GET", path: "/posts/{post_id}/comments", auth: "required", csrf: false, idempotency: false },
  "comment": { method: "POST", path: "/posts/{post_id}/comments", auth: "required", csrf: true, idempotency: true },
  "react": { method: "POST", path: "/posts/{post_id}/reactions", auth: "required", csrf: true, idempotency: true },
  "public_pet_photo": { method: "GET", path: "/public/media/pets/{pet_id}/photo", auth: "public", csrf: false, idempotency: false },
  "public_postcard": { method: "GET", path: "/public/media/postcards/{photo_id}", auth: "public", csrf: false, idempotency: false },
  "public_pet": { method: "GET", path: "/public/pets/{pet_id}", auth: "public", csrf: false, idempotency: false },
  "public_pet_posts": { method: "GET", path: "/public/pets/{pet_id}/posts", auth: "public", csrf: false, idempotency: false },
  "public_residents": { method: "GET", path: "/public/residents", auth: "public", csrf: false, idempotency: false },
  "public_world": { method: "GET", path: "/public/world", auth: "public", csrf: false, idempotency: false },
  "confirm_notes": { method: "POST", path: "/reception/confirmations", auth: "required", csrf: true, idempotency: true },
  "start_reception": { method: "POST", path: "/reception/sessions", auth: "required", csrf: true, idempotency: true },
  "get_reception": { method: "GET", path: "/reception/sessions/{session_id}", auth: "required", csrf: false, idempotency: false },
  "skip_reception": { method: "POST", path: "/reception/sessions/{session_id}/skip", auth: "required", csrf: true, idempotency: false },
  "add_turn": { method: "POST", path: "/reception/sessions/{session_id}/turns", auth: "required", csrf: true, idempotency: true },
  "report": { method: "POST", path: "/reports", auth: "required", csrf: true, idempotency: false },
  "my_reports": { method: "GET", path: "/reports/mine", auth: "required", csrf: false, idempotency: false },
  "read_session": { method: "GET", path: "/session", auth: "optional", csrf: false, idempotency: false },
  "read_settings": { method: "GET", path: "/settings", auth: "required", csrf: false, idempotency: false },
  "update_settings": { method: "PATCH", path: "/settings", auth: "required", csrf: true, idempotency: false },
  "life_timeline": { method: "GET", path: "/timeline", auth: "required", csrf: false, idempotency: false },
  "read_plan": { method: "GET", path: "/travel/plans/{plan_id}", auth: "required", csrf: false, idempotency: false },
  "read_wish": { method: "GET", path: "/travel/wish", auth: "required", csrf: false, idempotency: false },
  "get_visit": { method: "GET", path: "/visits/{visit_id}", auth: "required", csrf: false, idempotency: false },
  "visit_action": { method: "POST", path: "/visits/{visit_id}/actions", auth: "required", csrf: true, idempotency: true },
  "visit_choice": { method: "POST", path: "/visits/{visit_id}/choice", auth: "required", csrf: true, idempotency: true },
  "world_state": { method: "GET", path: "/world/state", auth: "required", csrf: false, idempotency: false },
} as const satisfies Record<string, WebEndpoint>;
export type WebEndpointName = keyof typeof WEB_ENDPOINTS;
