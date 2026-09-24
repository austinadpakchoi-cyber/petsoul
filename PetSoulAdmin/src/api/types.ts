/**
 * 管理端响应的前端类型。
 *
 * 如实说明：这一份是**手写**的，不是从后端契约生成的——`/api/v1/admin` 目前不进
 * `scripts/gen_web_contract.py` 的生成范围（那份只覆盖玩家侧 `/api/v1/web`）。
 * 已在窗口日志里作为跨窗口请求记给 I：要么把管理端 DTO 纳入生成器，要么单独出一份管理端契约。
 * 在那之前，改后端字段要同步改这里。
 */

export interface StaffView {
  staff_id: string;
  username: string;
  display_name: string;
  status: "active" | "disabled";
  mfa_enabled: boolean;
  roles: string[];
  version: number;
  created_at: string;
  last_login_at: string | null;
  permissions: string[];
  write_permissions: string[];
}

export interface SessionView {
  staff: StaffView;
  expires_at: string;
  mfa_satisfied: boolean;
  mfa_enrollment_required: boolean;
  environment: string;
  admin_version: string;
}

export interface MetricView {
  key: string;
  label: string;
  value: number | null;
  available: boolean;
  source: string;
  window: string | null;
  note: string | null;
}

export interface SwitchView {
  key: string;
  state: string;
  reason: string | null;
  version: number;
  changed_at: string | null;
  changed_by: string | null;
}

export interface OverviewView {
  environment: {
    environment: string;
    backend_version: string;
    server_time: string;
    database: string;
    providers_enabled: boolean;
    world_runner: string;
    world_tick_seconds: number;
    brain_mode: string;
  };
  metrics: MetricView[];
  attention: MetricView[];
  runtime: {
    lanes: Record<string, { runner: string; running_here: boolean; lease_alive: boolean; last_tick_at: string | null; last_error: string | null; ticks: number;
                            state?: string }>;
    tasks: Record<string, unknown>;
    outbox: Record<string, unknown>;
    due_lag_seconds: number | null;
  };
  switches: SwitchView[];
  read_only_note: string;
}

export interface UserHit {
  user_id: string;
  username: string | null;
  display_name: string | null;
  account_status: "active" | "frozen";
  created_at: string | null;
  household_count: number;
  pet_count: number;
  matched_on: string;
}

export interface PetBrief {
  pet_id: string;
  name: string;
  species: string;
  origin: string | null;
  household_id: string | null;
  home_activated: boolean;
}

export interface SearchView {
  query: string;
  users: UserHit[];
  pets: { pet_id: string; name: string; species: string; household_id: string | null }[];
  note: string;
}

export interface AuditEntry {
  audit_id: string;
  occurred_at: string;
  actor_staff_id: string | null;
  actor_username: string | null;
  action: string;
  permission: string | null;
  target_kind: string | null;
  target_id: string | null;
  reason: string | null;
  status: string;
  outcome: string | null;
  operation_id: string | null;
  request_id: string | null;
  changes: Record<string, unknown> | null;
}

export interface UserDetailView {
  user: UserHit;
  prefs: { model_replies: boolean; generated_photos: boolean; pet_messages: boolean; timezone: string; last_active_at: string | null };
  sessions: { session_id: string; created_at: string; expires_at: string; revoked_at: string | null }[];
  households: {
    household_id: string;
    name: string | null;
    role: string;
    member_status: string;
    created_at: string | null;
    members: { user_id: string; role: string; status: string; display_name: string | null; username: string | null }[];
    pets: PetBrief[];
  }[];
  freeze: { status: string; reason: string | null; changed_at: string | null; changed_by: string | null; version: number } | null;
  recent_admin_actions: AuditEntry[];
  homes?: { home_id: string; household_id: string; activated_at: string | null }[];
  redaction_note: string;
}

export interface Reservation {
  operation_id: string;
  provider: string;
  purpose: string;
  status: string;
  outcome: string | null;
  reserved_units: number;
  actual_units: number | null;
  /** 与额度计数器同一口径的计入用量：released（确定没发出）为 0，在途为 null。展示看它，不看 actual_units。 */
  counted_units: number | null;
  provider_request_id: string | null;
  created_at: string;
  settled_at: string | null;
}

export interface PhotoAttemptView {
  illustration_id: string;
  pet_id: string;
  status: "processing" | "ready" | "failed";
  task_id: string;
  task_status: string | null;
  attempts: number | null;
  max_attempts: number | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
  provider: string | null;
  model: string | null;
  reservations: Reservation[];
  call_state: "ready" | "processing" | "failed" | "unknown";
  recoverable: boolean;
  retry_ticket?: string;
  /** 最近一次错误的一句人话；认不出来为 null（照原样显示原始错误串）。 */
  error_label?: string | null;
  /** 这张图在玩家那一侧用在哪里；null＝这个库查不了，[]＝没找到。 */
  surfaces?: { kind: string; item_kind?: string; ref: string; city: string | null; at: string | null }[] | null;
}

export interface DiagnosisView {
  pet_id: string;
  as_of: string;
  available: boolean;
  unavailable_reason: string | null;
  headline: string;
  detail: string;
  silence_reason: string | null;
  silence_kind: string | null;
  activity: { kind: string; ref: string | null; ends_at: string | null; interruptible: boolean };
  place: { realm_id: string | null; household_id: string | null; timezone: string | null; region_id: string | null; scene_ref: string | null; sleep_window: string[] };
  heartbeat: { action: string; reason_codes: string[]; next_check_at: string | null; next_review_at: string | null; last_decision_at: string | null; last_decision_by: string | null; maintenance: boolean };
  versions: Record<string, number | null>;
  due_items: { ref: string; kind: string; due_at: string; commitment: boolean }[];
  consent: Record<string, unknown>;
  journey: { journey_id: string; title: string; city: string; lifecycle: string; lifecycle_label?: string | null; departed_at: string | null; completes_at: string | null;
             recent_events: { event_key: string; kind: string; label?: string | null; occurred_at: string }[];
             legs?: JourneyLegView[] | null; visits?: JourneyVisitView[] | null } | null;
  photos: PhotoAttemptView[];
  world_runner: Record<string, { running_here: boolean; lease_alive: boolean; last_error: string | null; ticks: number }>;
  pet: PetBrief | null;
  owner_user_id: string | null;
  read_only_note: string;
  place_label?: string | null;
  reasons?: { code: string; label: string | null }[];
  consent_rows?: { key: string; label: string | null; value: unknown }[];
}

export interface ReportRow {
  report_id: string;
  reporter_user_id: string;
  target_kind: string;
  target_id: string;
  reason: string;
  created_at: string;
  handled: boolean;
  target: { kind: string; text?: string; visibility?: string; removed_at?: string | null; note?: string } | null;
  actions: { decision: string; reason: string; staff_id: string; created_at: string }[];
  /** 当前认领（过期的不算）；只回名字与「是不是我」，不回员工号。 */
  claim: { username: string | null; claimed_at: string; expires_at: string; mine: boolean } | null;
  /** 举报人与被举报人之间的关系（只给计数与是否拉黑）；查不到被举报的人时为 null。 */
  context?: ReportContext | null;
  reporter_name?: PersonName | null;
}

export interface PersonName { username: string | null; display_name: string | null }

export interface ReportContext {
  author_user_id: string;
  author_name: PersonName | null;
  reporter_blocked_author: boolean;
  author_blocked_reporter: boolean;
  reports_against_author: number;
  author_removed: number;
  reporter_filed: number;
  same_person: boolean;
}

export type ContentType = "announcement" | "adventure" | "crop" | "job" | "resident" | "destination";

export interface ContentTypeInfo {
  content_type: ContentType;
  label: string;
  kind: "standalone" | "overlay" | "table";
  consumer: string;
  /** 玩家侧读取它的接口路径（技术细节，只在「显示技术代码」时显示）。 */
  consumer_api?: string;
  publishable: string[];
  blocked: string[];
}

export interface ContentSource {
  slug: string;
  /** 中文名（冒险标题、作物名、岗位名、地点名、居民名与物种）；下拉框显示它，内部键只在技术代码里。 */
  name?: string;
  builtin: Record<string, unknown>;
  identity?: { name: string; species: string };
}

export interface ContentItem {
  item_id: string;
  content_type: ContentType;
  slug: string;
  title: string;
  status: "draft" | "published" | "withdrawn";
  live_revision: number | null;
  draft_revision: number | null;
  version: number;
  effective_at: string | null;
  expires_at: string | null;
  created_at: string;
  created_by: string;
  updated_at: string;
  updated_by: string;
}

export interface ValidationIssue {
  field: string;
  message: string;
}

export interface ContentDetailView {
  item: ContentItem;
  revisions: { revision: number; body: Record<string, unknown>; body_hash: string; note: string | null; source_revision: number | null; created_at: string; created_by: string }[];
  publications: { publication_id: string; revision: number; action: string; effective_at: string; expires_at: string | null; reason: string; staff_id: string; diff_summary: string | null; created_at: string }[];
  validation: ValidationIssue[];
  live_body: Record<string, unknown> | null;
}

export interface PreviewView {
  item: ContentItem;
  revision: number;
  body: Record<string, unknown>;
  rendered: Record<string, unknown>;
  consumer_api?: string | null;
  issues: ValidationIssue[];
  publishable: boolean;
}

export interface UsageView {
  accounting_window: string;
  unit: string;
  /** estimated_cost：按币种分开的估算（字符串，避免浮点）；没有适用价格就是 null，不是 0。 */
  lines: { provider: string; purpose: string; used_units: number; inflight_units: number; estimated_cost: CurrencyCosts | null;
           billed_cost: number | null; currency: string | null; cost_state: CostState; unpriced_units: number | null }[];
  reservations_by_status: Record<string, number>;
  reservations_all_time_by_status: Record<string, number>;
  unsettled: { operation_id: string; provider: string; purpose: string; status: string; actual_units: number | null; counted_units: number | null; reserved_units: number; accounting_window: string; created_at: string }[];
  by_provider_purpose: { provider: string; purpose: string; status: string; calls: number; units: number | null }[];
  provider_health: Record<string, Record<string, unknown>>;
  price_table_configured: boolean;
  window_note: string;
  cost_note: string;
  counted_note: string;
}

export interface LedgerView {
  currency: string;
  separation_note: string;
  reason_note?: string;
  /** reason＝玩家在银行卡上看到的说明。admin_compensation：可以冲正的后台补偿；reversed_by / reversal_of：冲正关系。 */
  transactions: { tx_id: string; pet_id: string; type: string; idempotency_key: string; travel_coin: number; reason: string; operator: string;
                  source: string; status: string; created_at: string; admin_compensation?: boolean; reversed_by?: string | null;
                  reversal_of?: string | null }[];
  wallets: { pet_id: string; travel_coin: number; updated_at: string | null }[];
}

/** 单笔补偿的影响预览：与提交走同一套校验（宠物不存在 404、金额越界 422）。 */
export interface GrantPreview {
  pet_id: string;
  pet_name: string;
  caregiver_user_id: string | null;
  caregiver_frozen: boolean;
  balance_before: number;
  amount: number;
  balance_after: number;
  currency: string;
  max_amount: number;
  player_view: PlayerView;
  effects: string[];
}

/** 玩家在星球银行卡上会看到的那一行（账本的 reason 就是它；员工的内部原因不在这里）。 */
export interface PlayerView {
  where: string;
  delta: number;
  type: string;
  reason: string;
}

export interface GrantResult {
  pet_id: string;
  amount: number;
  applied: boolean;
  replayed: boolean;
  balance: number;
  currency: string;
  ledger_key: string;
  player_view: PlayerView;
  note: string;
}

export interface ReversalPreview {
  original: { tx_id: string; pet_id: string; amount: number; reason: string; internal_reason: string | null; operator: string;
              handled_by: string[]; source: string; created_at: string; reversed_by: { tx_id: string; created_at: string; operator: string } | null };
  pet_name: string | null;
  balance_before: number;
  balance_after: number | null;
  enough_balance: boolean;
  reversible: boolean;
  refusal: { reason: string; message: string } | null;
  player_view: PlayerView;
  effects: string[];
}

export interface ReversalResult {
  reversal: { tx_id: string; ledger_key: string; amount: number; original_tx_id: string };
  pet_id: string;
  balance: number;
  player_view: PlayerView;
  note: string;
  replayed: boolean;
}

/** 单只宠物的平台调用账（单位：调用次数）。与星币账是两本账，权限也分开。 */
export interface PetCallsView {
  pet_id: string;
  subject_scope: string;
  unit: string;
  accounting_window: string;
  counters_today: { scope_key: string; used_units: number; inflight_units: number }[];
  reservations_by_status: Record<string, number>;
  reservations: {
    operation_id: string; provider: string; purpose: string; status: string; outcome: string | null;
    reserved_units: number; actual_units: number | null; counted_units: number | null; accounting_window: string;
    created_at: string; settled_at: string | null;
    estimated_cost: string | null; cost_currency?: string | null; price_id?: string | null;
    billed_cost: number | null; cost_state: CostState;
  }[];
  price_table_configured: boolean;
  scope_note: string;
  cost_note: string;
  counted_note: string;
}

/** 费用状态：没有有效价格 / 没有适用价格 / 没有计入用量 / 在途 / 已估算 / 部分未定价 / 未确认的估算。 */
export type CostState = "unknown_no_price_table" | "unknown_no_price" | "not_counted" | "in_flight"
  | "estimated" | "partial" | "unconfirmed_estimate";

/** 按币种分开的金额。人民币与美元各算各的，不相加、不换算；与星币无关。 */
export type CurrencyCosts = Record<string, { estimated: string; unconfirmed: string }>;

export interface PriceRow {
  price_id: string;
  provider: string;
  purpose: string;
  currency: string;
  unit_price: string;
  unit_price_micros: number;
  unit: "call_unit";
  effective_from: string;
  source_note: string;
  model_note: string | null;
  status: "active" | "retired";
  created_by: string;
  created_at: string;
  retired_by: string | null;
  retired_at: string | null;
  retired_reason: string | null;
}

export interface PricesView {
  prices: PriceRow[];
  observed_scopes: { provider: string; purpose: string; calls: number; first_at: string | null; last_at: string | null }[];
  currencies: string[];
  can_manage: boolean;
  unit_note: string;
  billed_note: string;
  history_note: string;
}

export interface CostEstimateLine {
  provider: string;
  purpose: string;
  calls: number;
  in_flight_calls: number;
  not_counted_calls: number;
  counted_units: number;
  priced_units: number;
  unpriced_units: number;
  price_ids: string[];
  by_currency: CurrencyCosts;
  complete: boolean;
}

export interface CostEstimateView {
  window: { from: string; to: string; days: number; basis: string };
  price_table_configured: boolean;
  currencies: Record<string, { estimated: string; unconfirmed: string; estimated_micros: number; unconfirmed_micros: number }>;
  lines: CostEstimateLine[];
  unpriced_units: number;
  billed: null;
  notes: Record<string, string>;
}

export interface EconomyFinding {
  kind: "balance_mismatch" | "ledger_without_wallet" | "negative_balance" | "entry_inconsistent" | "chain_gap"
    | "repeated_admin_compensation";
  severity: "error" | "warn" | "review";
  pet_id: string;
  pet_name: string | null;
  title: string;
  rule: string;
  details: Record<string, unknown>;
}

export interface EconomyChecksView {
  as_of: string;
  checked_pets: number;
  checked_entries: number;
  unchained_entries: number;
  non_committed_entries: Record<string, number>;
  counts: Record<string, number>;
  pets_with_errors: number;
  findings: EconomyFinding[];
  rules: Record<string, string>;
  note: string;
  scale_note: string;
}

export interface UserLedgerSummary {
  user_id: string;
  sections: { economy: boolean; calls: boolean };
  pets: {
    pet_id: string;
    name: string;
    economy?: { balance: number | null; entries: number; last_entry_at: string | null; admin_compensations: number;
                admin_compensated_coins: number };
    calls?: { reservations_by_status: Record<string, number>; counted_units: number; estimated_cost: CurrencyCosts | null;
              unpriced_units: number | null; cost_state: CostState };
  }[];
  notes: Record<string, string>;
}

export interface BatchCapability {
  enabled: boolean;
  max_recipients: number | null;
  max_coins_per_pet: number | null;
  max_total_coins: number | null;
  note: string;
}

export interface BatchRecipientPreview {
  pet_id: string;
  name: string | null;
  eligible: boolean;
  reason: string | null;
  balance_before: number | null;
  balance_after: number | null;
}

export interface BatchPreview {
  recipients: BatchRecipientPreview[];
  amount_per_pet: number;
  eligible_count: number;
  skipped_count: number;
  total_amount: number;
  currency: string;
  effects: string[];
  player_view: PlayerView;
  limits: BatchCapability;
}

export interface BatchSummary {
  batch_id: string;
  title: string;
  reason: string;
  amount_per_pet: number;
  recipient_count: number;
  total_amount: number;
  status: "pending_approval" | "approved" | "rejected" | "executed" | "failed";
  version: number;
  submitted_by: string;
  submitted_at: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
  executed_by: string | null;
  executed_at: string | null;
  applied_count: number | null;
  skipped_count: number | null;
  applied_amount: number | null;
  player_note: string;
}

export interface BatchDetail {
  batch: BatchSummary;
  items: { pet_id: string; amount: number; status: string; outcome: string | null; ledger_key: string | null }[];
}

export interface AssetView {
  asset_id: string;
  filename: string;
  content_type: string;
  byte_size: number;
  sha256: string;
  width: number | null;
  height: number | null;
  has_thumbnail: boolean;
  thumb_note: string | null;
  source: string;
  source_note: string;
  license: string | null;
  usage_scope: "public" | "internal";
  status: "active" | "retired";
  version: number;
  uploaded_by: string;
  uploaded_at: string;
  retired_at: string | null;
  retired_reason: string | null;
}

export interface AssetListView {
  assets: AssetView[];
  sources: string[];
  usage_scopes: string[];
  rules: string[];
}

// ---- 第七批：宠物的东西、家里的东西、系统运行（都只读，不含正文）----
export interface PetBelongingsView {
  pet_id: string;
  collection: { counts: Record<string, number>;
                items: { item_id: string; kind: string; city: string | null; image_status: string | null; obtained_at: string | null;
                         consumed_at: string | null; tradable: boolean }[] } | null;
  credentials: { kind: string; title: string | null; number_tail: string | null; issued_at: string | null }[] | null;
  passport: { count: number; recent: { city: string | null; title: string | null; stamped_at: string | null }[] } | null;
  driving: { stage: string | null; note?: string; enrolled_at?: string | null; theory_passed_at?: string | null; licensed_at?: string | null;
             needs_practice?: boolean; last_study_at?: string | null;
             exams?: { part: string; attempt_no: number; score: number | null; max_score: number | null; passed: boolean; taken_at: string | null }[] } | null;
  messages: { by_sender: Record<string, { count: number; last_at: string | null }>; photos: Record<string, number>;
              replies: { due_at: string | null; reason: string | null; outcome: string | null; overdue: boolean; created_at: string | null }[] } | null;
  character: { active: { set_id: string; revision: number; published_at: string | null } | null;
               takes: { pose: string; state: string; reason: string | null; task_id: string | null; revision: number; updated_at: string | null }[];
               id_photo?: { active: { revision: number; published_at: string | null } | null;
                            takes: { revision: number; state: string; reason: string | null; task_id: string | null; updated_at: string | null }[] } | null } | null;
  friends?: { friend_id: string; friend_kind: string; friend_name: string | null; meet_count: number; first_met_at: string | null;
              last_met_at: string | null; last_place: string | null }[] | null;
  school?: { subjects: { subject: string; title: string | null; round_no: number | null; fails_in_round: number | null;
                         cooldown_until: string | null; passed_at: string | null; passed_score: number | null; practice_count: number }[];
             sessions: { subject: string; title: string | null; mode: string; state: string; passed: boolean | null; score: number | null;
                         created_at: string | null; settled_at: string | null }[];
             notes: { count: number; delivered: number } | null; practice_rounds: number | null } | null;
  media?: { count: number; recent: { session_id: string; state: string; updated_at: string | null; devices: number; modes: string[];
                                     minutes: number }[] } | null;
  food?: { preferences: Record<string, number>; recommendations: Record<string, number>; feedback: number | null } | null;
  privacy_note: string;
}

export interface HomeView {
  home_id: string;
  household_id: string | null;
  created_at: string | null;
  activated_at: string | null;
  pets: { pet_id: string; name: string }[];
  pantry: { stock: { item_key: string; item_label: string | null; qty: number; updated_at: string | null }[];
            moves: { item_key: string; item_label: string | null; delta: number; reason: string | null; actor_user_id: string | null;
                     pet_id: string | null; created_at: string | null }[] } | null;
  pantry_note?: string;
  orders?: { order_id: string; day: string; slot: number; resident: string | null; item_key: string; item_label: string | null;
             qty: number; reward: number; fulfilled_at: string | null }[] | null;
  people?: Record<string, PersonName>;
  farm: { plots: { slot: number; crop_key: string | null; crop_label: string | null; state: string; planted_at: string | null;
                   ripe_at: string | null; stolen_units: number; harvested_at: string | null }[];
          patrol: { started_at: string | null; until: string | null; active: boolean } | null } | null;
  steals: { from_this_home: { thief_user_id: string; thief_household_id: string | null; units: number; created_at: string | null }[];
            by_this_household: { victim_home_id: string; thief_user_id: string; units: number; created_at: string | null }[] } | null;
  note: string;
}

export interface SystemView {
  as_of: string;
  environment: OverviewView["environment"];
  outbox: { consumers: { consumer: string; pending: number; delivered: number; dead_letter?: number; other: number; oldest_pending_at: string | null }[];
            pending_total: number; dead_total?: number;
            dead?: { consumer: string; kind: string; attempts: number; last_error: string | null; created_at: string | null }[];
            failing: { consumer: string; kind: string; attempts: number; next_attempt_at: string | null; last_error: string | null; created_at: string | null }[] } | null;
  /** 按运行配置，执行者该不该在跑（runner=off 或每轮间隔 ≤ 0 时为 false）。 */
  world_configured?: boolean;
  workers: { name: string; role: string | null; holder: string | null; host: string | null; pid: number | null; started_at: string | null;
             heartbeat_at: string | null; expires_at: string | null; alive: boolean; last_tick_at: string | null; last_ok_at: string | null;
             last_error: string | null; ticks: number;
             /** 按配置判：configured_off（按配置关着，不是故障）/ healthy / lost（应该在跑但心跳过期或没登记）。 */
             state?: string; registered?: boolean }[] | null;
  tasks: { counts: { kind: string; status: string; count: number }[];
           overdue: { kind: string; count: number; oldest_run_after: string | null }[];
           recent_failures: { kind: string; last_error: string | null; attempts: number; max_attempts: number; updated_at: string | null }[] } | null;
  migrations: { count: number; latest: { migration_id: string; module: string | null; description: string | null; applied_at: string | null }[] } | null;
  providers: { provider: string; last_success_at: string | null; last_failure_at: string | null; last_error: string | null; updated_at: string | null }[] | null;
  switches: { key: string; state: string; reason: string | null; changed_at: string | null; changed_by: string | null }[];
  backups: { available: boolean; note: string };
}

// ---- 第八批：旅程逐段、社交、待领养居民 ----
export interface JourneyLegView {
  leg_id: string; sequence: number; direction: string; kind: string; mode: string; role: string;
  from: string | null; to: string | null; starts_at: string | null; ends_at: string | null;
  time_basis: string; freshness: string; position_basis: string;
}

export interface JourneyVisitView {
  visit_id: string; place: string | null; category: string | null; template: string;
  starts_at: string | null; ends_at: string | null; activities: { kind: string; label: string | null; state: string }[];
}

export interface UserSocialView {
  user_id: string;
  posts: { by_visibility: Record<string, number>;
           recent: { post_id: string; author_pet_id: string; visibility: string; excerpt: string | null; created_at: string | null;
                     removed_at: string | null; reported: boolean }[] } | null;
  comments: { total: number; removed: number;
              recent: { comment_id: string; post_id: string; actor_kind: string; excerpt: string | null; created_at: string | null;
                        removed_at: string | null; reported: boolean }[] } | null;
  blocks: { blocked: { user_id: string; name: PersonName | null; created_at: string | null }[];
            blocked_by: { user_id: string; name: PersonName | null; created_at: string | null }[] } | null;
  follows: { following: { pet_id: string; pet_name: string | null; created_at: string | null }[];
             followers: { pet_id: string; pet_name: string | null; created_at: string | null }[] } | null;
  reactions: { given: number | null; received: number | null };
  reports: { filed: number | null; against: number | null };
  privacy_note: string;
}

export interface ResidentRow {
  pet_id: string; candidate_id: string | null; name: string | null; species: string | null; kind: string; status: string;
  availability: string | null; origin: string | null; city: string | null; residence_label: string | null;
  personality: string | null; dream: string | null; source_note: string | null;
  public_since: string | null; adopted_at: string | null; adopted_by: string | null; adopted_by_name: PersonName | null;
  adopted_household_id: string | null; adopted_home_id: string | null;
  /** 这位居民在「内容发布」里已建的文案内容（没有就是 null）。 */
  content_item?: { item_id: string; status: string; live_revision: number | null; draft_revision: number | null } | null;
}

export interface ResidentsView {
  counts?: Record<string, number>; residents: ResidentRow[] | null; note: string;
  /** 没有 user.read 时：领养人一栏被清空，并给出这句说明。 */
  adopters_note?: string;
}

// ---- 第九批：宠物运行总览、暂停、每天生了多少张图 ----
export interface RuntimeModes {
  world_runner: string; heartbeat_mode: string; brain_mode: string; tick_seconds: number;
  world_alive: boolean; cognition_alive: boolean;
  world_configured: boolean; world_state: string; cognition_state: string;
  caps: { brain_per_pet: number; image_per_pet: number };
  accounting_day: string; pause_open: boolean; pause_closed_reason: string | null;
}

export interface PetRuntimeRow {
  pet_id: string; name: string | null; species: string | null; kind: "resident" | "household"; residence: string | null;
  household_id: string | null; owner_user_id: string | null; owner_name: PersonName | null; moved_in: boolean | null;
  heartbeat: { state: string; last_evaluated_at: string | null; next_check_at: string | null; silence_reason: string | null;
               silence_label?: string | null; has_runtime_row: boolean };
  brain: { state: string; started_at: string | null; last_decision_at: string | null; last_decision_by: string | null; next_review_at: string | null };
  rule_life: { slot: string; decision: { code: string; label: string | null } | null; at: string | null } | null;
  trip: { title: string | null; city: string | null; departed_at: string | null; completes_at: string | null } | null;
  paused: boolean;
  pause_record: { paused: boolean; reason: string; changed_by: string; changed_at: string | null; version: number } | null;
  /** 星币余额；没有 economy.read 时为 null（不是 0）。 */
  wallet: number | null;
  /** 今天各用途的额度（已用＋在途）；没有 provider.read 时为 null。 */
  usage_today: Record<string, { used: number; inflight: number }> | null;
}

export interface PetsRuntimeView {
  modes: RuntimeModes; pets: PetRuntimeRow[]; sections: { wallets: boolean; usage: boolean };
  notes: Record<string, string>;
}

export interface PausePreview {
  pet_id: string; name: string | null; resident: boolean; paused: boolean; version: number;
  reason: string | null; changed_by: string | null; changed_at: string | null; blocked_reason: string | null;
  world_running: boolean; pause_effects: string[]; resume_effects: string[];
}

export interface ImageDayCell { calls: number; units: number; buckets: Record<string, number> }
export interface ImagesDailyView {
  days: { day: string; purposes: Record<string, ImageDayCell>; total: { calls: number; units: number };
          global_counter: { used: number; inflight: number } | null }[] | null;
  purposes?: string[]; caps?: { global_daily: number; per_pet_daily: number }; since?: string; today?: string; note: string;
}

// ---- 第十批：经中转站的逐次调用回执（c84a 审查 ADM-COST-01）----
export interface RelayDayCell {
  day: string; purpose: string | null; model: string | null; model_confirmed: boolean;
  measured: { dispatches: number; succeeded: number; images: number; input_text_tokens: number; input_image_tokens: number;
              cached_tokens: number; output_tokens: number; with_usage: number };
  /** 按币种分开的估算合计（只有带价格版本的回执）；没有就是空对象，不是 0。 */
  estimated: Record<string, string>; unpriced: number;
  billed: Record<string, string>; unbilled: number; pending: number; unattributed: number;
}

export interface RelayConsumptionView {
  available: boolean; note?: string;
  capability?: { enabled: boolean; clients: string[]; note: string | null };
  sync?: { batches: number; last_import_at: string | null; receipts: number; unattributed: number; unpriced: number;
           unknown_outcome: number; no_usage: number; billed: number; conflicts: number; rejected: number };
  days?: RelayDayCell[]; since?: string; notes?: Record<string, string>;
}
