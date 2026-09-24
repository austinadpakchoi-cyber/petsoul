/**
 * 旅行心愿 → 联网攻略 → 手账：玩家端的状态换算（TRV-06，claude-6c2b 分身）。
 *
 * 类型全部来自 "@/shared/contracts"（generated.ts 09:37 版 9c5f1b88f2a60008；TRV-00 合同 v1 §23、§28–§31；字段含义见后端 schemas/web/travel.py）：
 * - 心愿：TravelWish / TravelWaitingReason（十二个码）/ TravelWishStatus / TravelResearchStatus；
 * - 计划：TravelPlan（current_revision + revisions，旧版都留着；页面显示 current_revision 那一版）/ TravelPlanRevision /
 *   TravelStop / TravelFact / TravelSource / TravelOwnerTip / TravelJourneySummary；
 * - 手账：在这一版修订的 journals 里（TravelJournal，phase 分 plan 计划页、memory 回忆页；图状态复用 PhotoStatus，外加 redraw_ticket、image_refused）。
 * contracts 里的 TravelGuide / TravelGuideStop（旧攻略）与 TravelActivity / TravellerRole（别的模块）不是这一套，别混用。
 * 本文件只多一个本地组合 PlanBundle（计划 + 它的心愿）。页面（./PlanPage）、列表（../GuideBookPage）、地图那一行（./wishNote）只认 PlanView。
 *
 * 状态到玩家说法的换算全在这里：玩家只看人话。§5.2 的十二个原因码每个配一句；不认识的码只说中性的话，不露码。
 * 语义不混（§5.2、§11.5）：missing_funds ≠ quota_denied（平台的次数）；research_unknown ≠ 搜不到；fact_stale ≠ 地名不存在；
 * 手账图 unknown ≠ failed（unknown 可能已经画了并计费，只说“还没确认”）；重画入口只在 failed / unknown 且后端给了 redraw_ticket 时出现。
 * 核验：结论只看 verdict；verification 是核验方法，conclusion 是端口自己的说法（只记录、不照单全收），页面都不显示。
 * 三种钱分开：攒钱目标（funds_goal、target_coins，游戏星币）不是路费；路费只认计划这一版上的行程摘要
 * （TravelJourneySummary：fare 是标价、用没用券都不变，fare_waived 为真＝用了券、实付 0，§30）；
 * 现实参考费用挂在价钱类事实上（value 是 {amount, currency, estimated}）：只报已核实、三样都认得出、有日期的，标币种、日期、是否估算；
 * 没核实写“还没核实”，认不出来（包括没写 estimated）整条不报金额，都不写 0；平台调用费用（研究收据）玩家页面永远不读。
 * 计划和回忆分开：出发前不盖到访章；顺路建议单独标出、不算到访；到访只认这一版计划的回忆手账站点上的真实事件
 * （TravelStop.visited_event_ids 计划阶段恒为空、回忆页才有；跨版本不认），回来后没去成的写“下次”。
 * 地图外链只用后端给的 nav_url（高德、WGS-84、核实过的地点才有），前端不拿 lat/lng 自己拼。
 */
import {
  TravelWaitingReasonValues,
  type TravelFact,
  type TravelJournal,
  type TravelJourneySummary,
  type TravelOwnerTip,
  type TravelPlan,
  type TravelPlanRevision,
  type TravelSource,
  type TravelStop,
  type TravelStopRole,
  type TravelWaitingReason,
  type TravelWish,
} from "@/shared/contracts";
import type { ChipTone, IconName } from "@/shared/ui";

/**
 * 计划页的读模型（本地组合，不是 DTO）：一份计划 + 它的心愿。I 定：
 * - 心愿的业务状态与 TA 的理由从 GET /travel/wish 读（TravelWish.status、owner_reason）；
 * - 计划从 GET /travel/plans/{plan_id} 读，手账在这一版修订的 journals 里。
 * （猜）第③期只在两边的 wish_id 对得上时把它们放在一起；对不上（比如以前的心愿）怎么拿状态，待 I 定。
 */
export interface PlanBundle {
  wish: TravelWish;
  plan: TravelPlan;
}

/* ======================= 视图模型：页面只认这个 ======================= */

/** 游戏币的叫法：与钱包、出发站、攻略页一致（主窗口定：用“星币”）。 */
export const COIN_UNIT = "星币";

/** 页面分支用；玩家看不到这几个词。 */
export type PlanStage = "wish" | "ready" | "departed" | "back" | "cancelled" | "unknown";

export interface WaitingItem {
  key: string;
  icon: IconName;
  text: string;
  detail: string | null;
}

export interface PlaceStamp {
  kind: "visited" | "next";
  label: string;
}

export interface PlaceView {
  /**
   * 同一版之内的键：plan_revision + station_id（计划阶段 station_id 可空，空时用序号）。
   * station_id 只在一版计划内有效；跨版本对应同一个地点用 name + role（I 定稿）。
   */
  id: string;
  role: TravelStopRole;
  name: string;
  why: string | null;
  tip: string | null;
  /** 这个地点依据的资料里有过期、说法不一、没核实或找不到的。 */
  pending: boolean;
  /** 后端的 TravelStop.verified。 */
  verified: boolean;
  verifyText: string;
  /** 只有这一版计划的回忆手账里的真实事件才有“到过”；回来后没去成的是“下次”；出发前一律没有。 */
  stamp: PlaceStamp | null;
  /** 后端给的 nav_url，只收 http(s)；没有就不给地图链接（不拿坐标自己拼）。 */
  mapUrl: string | null;
}

export interface LineView {
  text: string;
  /** 支持它的资料里有过期、说法不一、没核实或找不到的，标“待确认”。 */
  pending: boolean;
}

export interface CoinView {
  text: string;
  detail: string | null;
}

export interface RealCostView {
  key: string;
  text: string;
  meta: string;
}

/** 出发前会再核一遍的资料（TravelPlanRevision.preconditions：出发时必须仍然有效的关键事实）。 */
export interface PreconditionView {
  key: string;
  topic: string;
  detail: string | null;
  /** 不是已核对的（或这条资料找不到了）：待确认的说法。 */
  pendingText: string | null;
  /** 已核对且带有效期的：有效到哪天。 */
  until: string | null;
}

export interface JournalStationView {
  key: string;
  name: string;
  role: TravelStopRole;
  /** 只有回忆页有章：到过 / 下次。 */
  stamp: PlaceStamp | null;
}

/** 手账这一页上写的文字（图外可读，TRV-07：屏幕先显示图外文字）。 */
export interface JournalTextView {
  title: string | null;
  summary: string | null;
  stations: JournalStationView[];
  tips: LineView[];
  rain: string | null;
}

export interface JournalView {
  state: "ready" | "drawing" | "unknown" | "failed" | "refused" | "none";
  heading: string;
  caption: string;
  imageUrl: string | null;
  /** 画面按上一版计划画的时候提醒一句（只在有图时）。 */
  staleNote: string | null;
  /** 重画入口：只在 failed / unknown 且后端给了 redraw_ticket 时出现（主人自己点才重画，不自动重画）。 */
  canRedraw: boolean;
  /** 画里的 TA 从哪来（identity_mode 说人话）；只在有图或正在画时说。 */
  identity: string | null;
  /** 手账这一页的文字；没有手账时为 null。 */
  text: JournalTextView | null;
  /** 给“技术信息”的一行（拒绝码、身份说明码），平时收起；玩家只看人话。 */
  tech: string | null;
}

export interface SourceRefView {
  key: string;
  publisher: string;
  href: string | null;
  times: string[];
}

export interface SourceView {
  id: string;
  topic: string;
  /** 这条资料说的是什么（过期、说法不一的旁边有“待确认”，不冒充现在有效）。 */
  detail: string | null;
  pendingText: string | null;
  refs: SourceRefView[];
  /** 资料本身的观测 / 适用 / 发布时间；都没有时照实写“资料本身没有注明日期”。 */
  times: string[];
}

export interface PlanView {
  /** 列表里的键：有计划用 plan_id，没有计划用 wish_id。 */
  key: string;
  /** 点进去的地址：当前心愿 /guides/wish，某一份计划 /guides/plan/:planId（§23.4）。 */
  href: string;
  planRevision: number | null;
  isDemo: boolean;
  stage: PlanStage;
  title: string;
  destination: string;
  /** 这一版计划的标题（TravelPlanRevision.title）。 */
  planTitle: string | null;
  status: { label: string; tone: ChipTone };
  /** 页头一句话。 */
  summary: string;
  /** 列表卡片上的一句：想去 / 准备中时是“还差什么”的第一条。 */
  cardLine: string;
  reason: string | null;
  waiting: WaitingItem[];
  /** 出发前会再核一遍的资料（只在想去 / 可以出发时有）。 */
  preconditions: PreconditionView[];
  /** 行动安排：计划这一版里 TA 写的那段（summary）。 */
  arrangement: string | null;
  planWritten: boolean;
  /** 心愿已经有计划、但这一页没读到计划全文时，去那份计划的地址。 */
  planLink: string | null;
  validity: string | null;
  main: PlaceView;
  suggestions: PlaceView[];
  reminders: LineView[];
  rainPlan: string | null;
  coins: CoinView | null;
  realCosts: RealCostView[];
  journal: JournalView;
  sources: SourceView[];
}

export interface ViewOptions {
  /** 当前宠物的名字；拿不到就写“TA”（主窗口定）。 */
  petName?: string | null;
  /** 演示数据：页面处处挂“演示”，现实参考金额后面带“（演示）”。DTO 里没有这个字段，由读数据的一侧告诉。 */
  isDemo?: boolean;
  /** TA 所在城市的时区。DTO 里没有，从哪来待用户决定；没给就用暂定的 PROVISIONAL_ZONE。 */
  timezone?: string | null;
}

/* ======================= 换算 ======================= */

const STAGE_OF: Record<string, PlanStage> = { active: "wish", ready: "ready", linked: "departed", completed: "back", cancelled: "cancelled" };

function isReason(code: string): code is TravelWaitingReason {
  return (TravelWaitingReasonValues as readonly string[]).includes(code);
}

/** “还差什么”的先后：维护 → 资料 → 计划 → 钱 → 天气 → 约定；第一条同时决定状态标签、列表卡片那句和地图那一行。 */
const WAITING_ORDER: Record<TravelWaitingReason, number> = {
  maintenance: 0,
  research_pending: 1,
  quota_denied: 2,
  research_unknown: 3,
  research_failed: 4,
  plan_stale: 5,
  fact_stale: 6,
  fact_unverified: 7,
  fact_conflicting: 8,
  missing_funds: 9,
  weather_unsuitable: 10,
  commitment_active: 11,
};

/** §5.2 十二个码的状态标签（类型上必须覆盖全部；用例另外手抄合同清单双向核对）。 */
export const WAITING_REASON_CHIPS: Record<TravelWaitingReason, { label: string; tone: ChipTone }> = {
  maintenance: { label: "维护中", tone: "neutral" },
  research_pending: { label: "资料准备中", tone: "sky" },
  quota_denied: { label: "资料晚点查", tone: "sky" },
  research_unknown: { label: "资料待确认", tone: "sun" },
  research_failed: { label: "资料待补", tone: "coral" },
  plan_stale: { label: "计划待更新", tone: "sun" },
  fact_stale: { label: "资料待确认", tone: "sun" },
  fact_unverified: { label: "资料待确认", tone: "sun" },
  fact_conflicting: { label: "资料待确认", tone: "sun" },
  missing_funds: { label: `等攒够${COIN_UNIT}`, tone: "sun" },
  weather_unsuitable: { label: "等天气", tone: "sky" },
  commitment_active: { label: "有约在先", tone: "neutral" },
};

const STAGE_CHIP: Record<Exclude<PlanStage, "wish">, { label: string; tone: ChipTone }> = {
  ready: { label: "可以出发", tone: "leaf" },
  departed: { label: "已出发", tone: "sky" },
  back: { label: "已回来", tone: "leaf" },
  cancelled: { label: "已取消", tone: "neutral" },
  unknown: { label: "状态待确认", tone: "neutral" },
};

/** 事实类别（后端 schemas/web/travel.py 列的 destination_identity / route / opening / weather / notice / ticket_price / …）；不认识的写“其他资料”。 */
const CATEGORY_TEXT: Record<string, string> = {
  destination_identity: "地点",
  route: "路线",
  opening: "开放时间",
  weather: "天气",
  notice: "临时公告",
  ticket_price: "票价",
};

/** 主窗口定的六种中文名；其余照三字母代码显示。 */
const CURRENCY_TEXT: Record<string, string> = { CNY: "人民币", HKD: "港币", MOP: "澳门元", JPY: "日元", USD: "美元", TWD: "新台币" };

/** 结论（verdict）的说法。rejected＝引用了不存在的来源、上游产出有问题，与 unverified（查不到可用来源）不折叠。 */
const VERDICT_TEXT: Record<string, string> = { stale: "过期了，待确认", conflicting: "说法不一，待确认", unverified: "还没核实，待确认", rejected: "没有采用" };

/**
 * 手账里 TA 的样子从哪来（TravelIdentityMode：用证件照，还是不画 TA）。不认识的取值不说（不露码）。
 * 不画 TA 的原因在 identity_note 里（是原因码，比如没有可用的参考照片），只进“技术信息”。
 */
const IDENTITY_TEXT: Record<string, string> = { photo: "画里的 TA 照着 TA 的证件照画", none: "这页手账不画 TA 的样子" };

/**
 * 暂定时区：Asia/Shanghai。
 * TA 所在城市的时区从哪来（DTO 里没有）是待用户决定的事项。这里是“暂定”，不是“默认”：决定之后改这里，别当成已经定了的规则。
 */
export const PROVISIONAL_ZONE = "Asia/Shanghai";

function categoryText(code: string): string {
  return CATEGORY_TEXT[code] ?? "其他资料";
}

function currencyText(code: string): string {
  return CURRENCY_TEXT[code] ?? code;
}

function zoneOf(tz: string | null | undefined): string {
  if (!tz) return PROVISIONAL_ZONE;
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: tz });
    return tz;
  } catch {
    return PROVISIONAL_ZONE;
  }
}

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;

function partsAt(ms: number, zone: string, withTime: boolean): Record<string, string> {
  const options: Intl.DateTimeFormatOptions = { timeZone: zone, year: "numeric", month: "numeric", day: "numeric" };
  if (withTime) Object.assign(options, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  const out: Record<string, string> = {};
  for (const part of new Intl.DateTimeFormat("en-US", options).formatToParts(new Date(ms))) out[part.type] = part.value;
  return out;
}

/** “2026年9月24日”。纯日期不做时区换算；时间点按 TA 所在城市的时区取日期。认不出来就不显示（不伪造）。 */
export function formatDay(value: string | null, zone: string): string | null {
  if (!value) return null;
  const m = DATE_ONLY.exec(value);
  if (m) return `${Number(m[1])}年${Number(m[2])}月${Number(m[3])}日`;
  const ms = Date.parse(value);
  if (Number.isNaN(ms)) return null;
  const p = partsAt(ms, zone, false);
  return `${p.year}年${p.month}月${p.day}日`;
}

/** 有效期的右端（§29.3 左闭右开 [valid_from, valid_until)）：最后有效的是 valid_until 前一刻，所以按前一刻取日期。纯日期照写。 */
function formatUntilDay(value: string | null, zone: string): string | null {
  if (!value) return null;
  if (DATE_ONLY.test(value)) return formatDay(value, zone);
  const ms = Date.parse(value);
  if (Number.isNaN(ms)) return null;
  const p = partsAt(ms - 1, zone, false);
  return `${p.year}年${p.month}月${p.day}日`;
}

/** “2026年9月24日 05:40”；纯日期只到日。 */
export function formatMoment(value: string | null, zone: string): string | null {
  if (!value) return null;
  if (DATE_ONLY.test(value)) return formatDay(value, zone);
  const ms = Date.parse(value);
  if (Number.isNaN(ms)) return null;
  const p = partsAt(ms, zone, true);
  return `${p.year}年${p.month}月${p.day}日 ${p.hour}:${p.minute}`;
}

/** 发布时间：落在当地零点的只写日期（发布日多半只到日，写“00:00”像是编出来的），不在零点的写到分钟。 */
function formatPublished(value: string | null, zone: string): string | null {
  if (!value) return null;
  if (DATE_ONLY.test(value)) return formatDay(value, zone);
  const ms = Date.parse(value);
  if (Number.isNaN(ms)) return null;
  const p = partsAt(ms, zone, true);
  return p.hour === "00" && p.minute === "00" ? `${p.year}年${p.month}月${p.day}日` : `${p.year}年${p.month}月${p.day}日 ${p.hour}:${p.minute}`;
}

function rangeText(from: string | null, until: string | null, zone: string): string | null {
  const a = formatDay(from, zone);
  const b = formatUntilDay(until, zone);
  if (a && b) return a === b ? a : `${a} 至 ${b}`;
  if (a) return `${a} 起`;
  if (b) return `到 ${b} 为止`;
  return null;
}

/** 外链只收 http(s)；javascript:、data:、ftp: 之类一律不做成链接。 */
export function safeHref(raw: string | null | undefined): string | null {
  if (!raw) return null;
  try {
    const url = new URL(raw);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

function hostOf(raw: string | null): string | null {
  const href = safeHref(raw);
  return href ? new URL(href).hostname : null;
}

/** 手账图只收 http(s) 或站内路径（/media/...）；不收协议相对地址和其他协议。 */
function safeImageUrl(raw: string | null): string | null {
  if (!raw) return null;
  if (raw.startsWith("/") && !raw.startsWith("//")) return raw;
  return safeHref(raw);
}

function amountText(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

/**
 * 价钱类事实的 value：{ amount, currency, estimated }（后端定）。三样都认得出才算数，否则整条不报金额：
 * - 金额要是非负数，币种要是 ISO 4217 三字母大写；
 * - estimated 必须写明（true / false）。A 的口径（I 转）：不写 estimated 等于认不出来——
 *   不知道是不是估算的价格，比没有价格更坏，它会让人按准确价格去规划；猜一个默认值，就是替用户做了一个他不知道的假设。
 */
function priceOf(value: unknown): { amount: number; currency: string; estimated: boolean } | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const { amount, currency, estimated } = value as Record<string, unknown>;
  if (typeof amount !== "number" || !Number.isFinite(amount) || amount < 0) return null;
  if (typeof currency !== "string" || !/^[A-Z]{3}$/.test(currency)) return null;
  if (typeof estimated !== "boolean") return null;
  return { amount, currency, estimated };
}

const isPriceFact = (fact: TravelFact) => fact.category.includes("price");

const isVerified = (fact: TravelFact | undefined) => fact?.verdict === "verified";

interface Ctx {
  stage: PlanStage;
  zone: string;
  isDemo: boolean;
  wish: TravelWish;
  revision: TravelPlanRevision | null;
  facts: Map<string, TravelFact>;
  factList: TravelFact[];
  sources: Map<string, TravelSource>;
  /** 这一版计划的回忆手账里的站点（到访只认它）；没有就是 null。 */
  memory: TravelStop[] | null;
}

/** 某个结论的资料说的是哪几类；优先列会卡住出行的（blocks_departure），一条都没卡住才列全部。 */
function topicsWith(ctx: Ctx, verdicts: string[]): string | null {
  const hits = ctx.factList.filter((f) => verdicts.includes(f.verdict));
  const blocking = hits.filter((f) => f.blocks_departure);
  const topics = [...new Set((blocking.length ? blocking : hits).map((f) => categoryText(f.category)))];
  return topics.length ? topics.join("、") : null;
}

function waitingItem(code: string, index: number, ctx: Ctx): WaitingItem {
  const key = `${index}-${code}`;
  switch (code) {
    case "missing_funds": {
      const { target_coins, current_coins, funds_goal, last_considered_at } = ctx.wish;
      const target = target_coins ?? funds_goal;
      if (target == null || current_coins == null) return { key, icon: "coin", text: `${COIN_UNIT}还没攒够`, detail: target != null ? `要攒到 ${target} ${COIN_UNIT}` : null };
      const short = Math.max(0, target - current_coins);
      // 钱包是快照，快照时刻就是 last_considered_at（I 答）。这是攒钱的目标，不是路费。
      const at = formatMoment(last_considered_at, ctx.zone);
      return {
        key,
        icon: "coin",
        text: short > 0 ? `还差 ${short} ${COIN_UNIT}` : `${COIN_UNIT}还在核对`,
        detail: `要攒到 ${target} ${COIN_UNIT}；${at ? `截至 ${at} ` : ""}有 ${current_coins}`,
      };
    }
    case "quota_denied":
      return { key, icon: "refresh", text: "今天查资料的次数用完了，改天再查", detail: null };
    case "research_pending":
      return { key, icon: "compass", text: ctx.wish.research_state === "running" ? "TA 正在查资料" : "资料还在准备", detail: null };
    case "research_unknown":
      return { key, icon: "refresh", text: "查资料的结果还没确认", detail: null };
    case "research_failed":
      return { key, icon: "info", text: "这次查资料没有完成", detail: null };
    case "plan_stale":
      return { key, icon: "refresh", text: "计划是按之前的想法排的，要重新排一下", detail: null };
    case "fact_stale": {
      const topics = topicsWith(ctx, ["stale"]);
      return { key, icon: "refresh", text: "有资料过期了，还在确认", detail: topics ? `过期的是：${topics}` : null };
    }
    case "fact_unverified": {
      const topics = topicsWith(ctx, ["unverified", "rejected"]);
      return { key, icon: "info", text: "有关键资料还没核实，还在确认", detail: topics ? `还没核实的是：${topics}` : null };
    }
    case "fact_conflicting": {
      const topics = topicsWith(ctx, ["conflicting"]);
      return { key, icon: "info", text: "有资料说法不一，还在确认", detail: topics ? `说法不一的是：${topics}` : null };
    }
    case "weather_unsuitable":
      return { key, icon: "sparkle", text: "天气不太合适，等一等", detail: null };
    case "commitment_active":
      // §16.2：只用中性措辞，不带任何私聊原话。
      return { key, icon: "user", text: "家里有安排，先不出门", detail: null };
    case "maintenance":
      return { key, icon: "settings", text: "星球这边在维护，出门先等一等", detail: null };
    default:
      return { key, icon: "info", text: "还有一件事在确认", detail: null };
  }
}

const afterDeparture = (stage: PlanStage) => stage === "departed" || stage === "back" || stage === "cancelled";

/** 回忆手账里有没有这一站的真实到访：同一版之内按 name + role 对应（计划阶段 station_id 可空）；两边都有 station_id 时还要相同。 */
function visitedIn(stations: TravelStop[], stop: TravelStop): boolean {
  return stations.some(
    (s) => s.name === stop.name && s.role === stop.role && (s.station_id == null || stop.station_id == null || s.station_id === stop.station_id) && s.visited_event_ids.length > 0,
  );
}

function placeView(stop: TravelStop, index: number, revision: TravelPlanRevision, ctx: Ctx): PlaceView {
  const own = stop.fact_ids.map((id) => ctx.facts.get(id));
  // 盖章只认这一版计划的回忆手账里的真实事件，而且只在出发之后：出发前（想去 / 准备去 / 状态不明）即使数据里混进了事件也不盖。
  let stamp: PlaceStamp | null = null;
  if (afterDeparture(ctx.stage) && ctx.memory) {
    if (visitedIn(ctx.memory, stop)) stamp = { kind: "visited", label: "到过" };
    else if (ctx.stage === "back") stamp = { kind: "next", label: "下次" };
  }
  return {
    id: `${revision.plan_revision}:${stop.station_id ?? `#${index}`}`,
    role: stop.role,
    name: stop.name,
    why: stop.why?.trim() || null,
    tip: stop.tip?.trim() || null,
    // 找不到的事实 ID 也算待确认：不存在的来源不能通过（§11.1）。
    pending: own.some((f) => !isVerified(f)),
    verified: stop.verified,
    verifyText: stop.verified ? "地点已核对" : "地点待确认",
    stamp,
    mapUrl: safeHref(stop.nav_url),
  };
}

/**
 * 提醒：DTO 的说明是“和支持它的事实一一对应，没有 fact_ids 的提醒不该出现”，所以没有 fact_ids 的不显示（往不显示那边失败）。
 * 注意：合同 §18.4 与 A 的实现（web_travel/facts.py build_plan）只要求“带数字的提醒”有事实支撑，不带数字的提醒会以空 fact_ids 进计划——
 * 两处说法对不上，已报 I；I 定下来之前按 DTO 的说明走。
 */
function reminderViews(tips: TravelOwnerTip[], ctx: Ctx): LineView[] {
  return tips.filter((tip) => tip.text.trim() && tip.fact_ids.length > 0).map((tip) => ({ text: tip.text.trim(), pending: tip.fact_ids.some((id) => !isVerified(ctx.facts.get(id))) }));
}

/** 这条事实说的是哪个地点（subject：station_id 或地名，I 答对）；对不上就不写地名。 */
function placeNameOf(subject: string, ctx: Ctx): string | null {
  const stop = (ctx.revision?.stops ?? []).find((s) => (s.station_id != null && s.station_id === subject) || s.name === subject);
  return stop?.name ?? null;
}

/**
 * 这条资料说的是什么：字符串照写；被判 rejected 的 value 是 null；别的形状不显示（不把对象原样倒给玩家）。
 * 价钱类和“现实参考”同一个口径：只写已核实、认得出来的（{amount, currency, estimated} 三样齐）；没核实的数即使带着也不写。
 */
function factValueText(fact: TravelFact, ctx: Ctx): string | null {
  if (fact.verdict === "rejected") return null;
  if (isPriceFact(fact)) {
    const price = isVerified(fact) ? priceOf(fact.value) : null;
    return price ? `约 ${amountText(price.amount)} ${currencyText(price.currency)}${ctx.isDemo ? "（演示）" : ""}${price.estimated ? "，估算" : ""}` : null;
  }
  const { value } = fact;
  if (typeof value === "string") return value.trim() || null;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return null;
}

function sourceView(fact: TravelFact, ctx: Ctx): SourceView {
  const refs: SourceRefView[] = [];
  fact.source_ids.forEach((id, index) => {
    // 计划里的来源只含已核验事实引用到的（后端定）：别的事实引用的来源不在列表里，就不列，不说成“没有来源”。
    const src = ctx.sources.get(id);
    if (!src) return;
    const retrieved = formatMoment(src.retrieved_at, ctx.zone);
    const published = formatPublished(src.published_at, ctx.zone);
    refs.push({
      key: `${index}-${id}`,
      publisher: src.publisher?.trim() || hostOf(src.url) || "来源没有注明",
      href: safeHref(src.url),
      times: [retrieved ? `抓取于 ${retrieved}` : null, published ? `发布于 ${published}` : null].filter((t): t is string => Boolean(t)),
    });
  });
  // 已核对的事实却一条来源都对不上：照实说。
  if (refs.length === 0 && isVerified(fact)) refs.push({ key: "none", publisher: "来源没有注明", href: null, times: [] });
  const refRetrieved = refs.some((r) => r.times.some((t) => t.startsWith("抓取于")));
  const refPublished = refs.some((r) => r.times.some((t) => t.startsWith("发布于")));
  const observed = formatMoment(fact.observed_at, ctx.zone);
  const applies = rangeText(fact.valid_from, fact.valid_until, ctx.zone);
  // 事实自己也带抓取 / 发布时间；来源那行已经写了的不重复。
  const retrieved = refRetrieved ? null : formatMoment(fact.retrieved_at, ctx.zone);
  const published = refPublished ? null : formatPublished(fact.published_at, ctx.zone);
  const times = [
    observed ? `观测于 ${observed}` : null,
    applies ? `适用：${applies}` : null,
    retrieved ? `抓取于 ${retrieved}` : null,
    published ? `发布于 ${published}` : null,
  ].filter((t): t is string => Boolean(t));
  // 资料本身没写日期就照实说，不拿抓取时间冒充资料的年代。
  if (!observed && !applies && !refPublished && !published) times.push("资料本身没有注明日期");
  return {
    id: fact.fact_id,
    topic: categoryText(fact.category),
    detail: factValueText(fact, ctx),
    pendingText: isVerified(fact) ? null : (VERDICT_TEXT[fact.verdict] ?? "待确认"),
    refs,
    times,
  };
}

/** 事实的日期：观测日 → 适用区间 → 发布日（事实的、来源的）→ 抓取日（事实的、来源的）。价钱常带适用区间，只写起始日会被读成“那天的价”。 */
function factDate(fact: TravelFact, ctx: Ctx): string | null {
  const observed = formatDay(fact.observed_at, ctx.zone);
  if (observed) return observed;
  const window = rangeText(fact.valid_from, fact.valid_until, ctx.zone);
  if (window) return window;
  const sources = fact.source_ids.map((id) => ctx.sources.get(id)).filter((s): s is TravelSource => Boolean(s));
  for (const value of [fact.published_at, ...sources.map((s) => s.published_at), fact.retrieved_at, ...sources.map((s) => s.retrieved_at)]) {
    const day = formatDay(value, ctx.zone);
    if (day) return day;
  }
  return null;
}

/**
 * 现实参考费用（挂在价钱类事实上，一个地点可以有多条），只给主人看，不换算成星币：
 * - 没核实（过期、说法不一、没核实、没采用）：写“还没核实”，即使带着数也不报——不拿没核实的数冒充现在的价；
 * - 核实了但金额认不出来（币种、金额不对，或没写明是不是估算），或资料没有任何日期：整条不报金额，写“金额说不准，先不写”；
 * - 都齐了：约多少、币种中文名、日期，估算的标“估算”。
 */
function realCostViews(ctx: Ctx): RealCostView[] {
  const demo = ctx.isDemo ? "（演示）" : "";
  return ctx.factList.filter(isPriceFact).map((f) => {
    const place = placeNameOf(f.subject, ctx);
    const label = place ? `${place}的${categoryText(f.category)}` : categoryText(f.category);
    const day = factDate(f, ctx);
    if (!isVerified(f)) return { key: f.fact_id, text: `${label}：还没核实${demo}`, meta: day ? `${day} · 待核` : "待核" };
    const price = priceOf(f.value);
    if (!price || !day) return { key: f.fact_id, text: `${label}：金额说不准，先不写${demo}`, meta: day ?? "资料没有注明日期" };
    return { key: f.fact_id, text: `${label}：约 ${amountText(price.amount)} ${currencyText(price.currency)}${demo}`, meta: price.estimated ? `${day} · 估算` : day };
  });
}

/**
 * 出发前会再核一遍的资料（preconditions：出发时必须仍然有效的关键事实，fact_id）。
 * 出发那一刻 C 逐条核（web_journey/service.py _assert_preconditions_fresh）：过期了就不出发，重新查一遍。只在想去 / 可以出发时说。
 */
function preconditionViews(ctx: Ctx): PreconditionView[] {
  if (ctx.stage !== "wish" && ctx.stage !== "ready") return [];
  return (ctx.revision?.preconditions ?? []).map((id, index) => {
    const fact = ctx.facts.get(id);
    if (!fact) return { key: `${index}-${id}`, topic: "其他资料", detail: null, pendingText: "这条资料找不到了，待确认", until: null };
    const until = isVerified(fact) ? formatUntilDay(fact.valid_until, ctx.zone) : null;
    return {
      key: `${index}-${id}`,
      topic: categoryText(fact.category),
      detail: factValueText(fact, ctx),
      pendingText: isVerified(fact) ? null : (VERDICT_TEXT[fact.verdict] ?? "待确认"),
      until: until ? `有效到 ${until}` : null,
    };
  });
}

/**
 * 星币：出发前说攒钱目标（不是路费）；出发后只认这一版计划上的行程摘要（§30），绝不拿攒钱目标顶。
 * - fare 是这趟的标价，用没用券都不变；fare_waived 为真＝用了借车券、实付 0、省下 fare（这张券唯一能被看见的地方）；
 * - fare 为 0：这趟不花路费（带着券也一样，不写“省下 0”）；
 * - 形状不对（缺字段、fare 不是非负数）或还没关联行程：不显示路费。
 * 出发后才有这一行，包括出发后提前结束（取消但有行程）的回顾。
 */
function coinView(journey: TravelJourneySummary | null, ctx: Ctx): CoinView | null {
  const { wish } = ctx;
  if (ctx.stage === "wish" || ctx.stage === "ready") {
    const goal = wish.target_coins ?? wish.funds_goal;
    if (goal == null) return null;
    const text = `攒钱目标 ${goal} ${COIN_UNIT}`;
    if (ctx.stage === "ready") return { text, detail: "已经攒够" };
    if (wish.waiting_reasons.includes("missing_funds") && wish.current_coins != null) {
      const at = formatMoment(wish.last_considered_at, ctx.zone);
      return { text, detail: `${at ? `截至 ${at} ` : ""}有 ${wish.current_coins}，还差 ${Math.max(0, goal - wish.current_coins)}` };
    }
    return { text, detail: null };
  }
  if (afterDeparture(ctx.stage)) {
    if (!journey) return null;
    const { fare, fare_waived: waived } = journey as Partial<TravelJourneySummary>;
    if (typeof fare !== "number" || !Number.isFinite(fare) || fare < 0 || typeof waived !== "boolean") return null;
    if (fare === 0) return { text: "这趟不花路费", detail: null };
    // 用了券：实付 0。fare 是省下的，不是花出去的。
    if (waived) return { text: `用了借车券，省下 ${amountText(fare)} ${COIN_UNIT}`, detail: null };
    return { text: `路费 ${amountText(fare)} ${COIN_UNIT}`, detail: "出发时从 TA 的星球银行卡付过" };
  }
  return null;
}

/** 这一版计划的手账：同一种页（plan / memory）取最新的一版（journal_revision 最大）。 */
function latestJournal(revision: TravelPlanRevision | null, phase: TravelJournal["phase"]): TravelJournal | null {
  let best: TravelJournal | null = null;
  for (const journal of revision?.journals ?? []) {
    if (journal.phase === phase && (!best || journal.journal_revision > best.journal_revision)) best = journal;
  }
  return best;
}

/** 手账这一页上的文字：标题、一句话、站点（回忆页带章）、提醒、雨天备选。 */
function journalText(journal: TravelJournal, ctx: Ctx): JournalTextView {
  const memory = journal.phase === "memory";
  return {
    title: journal.title?.trim() || null,
    summary: journal.summary?.trim() || null,
    stations: journal.stations.map((s, index) => {
      let stamp: PlaceStamp | null = null;
      // 章只在回忆页、而且只在出发之后（和地点卡同一个口径）。
      if (memory && afterDeparture(ctx.stage)) {
        if (s.visited_event_ids.length > 0) stamp = { kind: "visited", label: "到过" };
        else if (ctx.stage === "back") stamp = { kind: "next", label: "下次" };
      }
      return { key: `${s.station_id ?? `#${index}`}:${s.name}`, name: s.name, role: s.role, stamp };
    }),
    tips: reminderViews(journal.owner_tips, ctx),
    rain: journal.rain_alternative?.trim() || null,
  };
}

function journalView(journal: TravelJournal | null, planRevision: number | null, ctx: Ctx): JournalView {
  const none: JournalView = { state: "none", heading: "手账", caption: "这一页只有文字，没有手账图", imageUrl: null, staleNote: null, canRedraw: false, identity: null, text: null, tech: null };
  if (!journal) return none;
  const heading = journal.phase === "memory" ? "回忆手账" : "计划手账";
  const text = journalText(journal, ctx);
  // 重画入口只在 failed / unknown 且后端给了 redraw_ticket 时出现（有票才显示）。
  const ticket = Boolean(journal.redraw_ticket?.trim());
  const canRedraw = ticket && (journal.image_status === "failed" || journal.image_status === "unknown");
  const refused = journal.image_refused?.trim() || null;
  if (refused) {
    // 被拒：没有图，手账文字照样在；拒绝码只进“技术信息”。
    return { state: "refused", heading, caption: "这次没有配图", imageUrl: null, staleNote: null, canRedraw, identity: null, text, tech: refused };
  }
  // §11.5：“没有手账图”用 image_status 缺省表达（没接插画），不是 failed。
  if (journal.image_status == null) return { ...none, heading, text };
  // 画里的 TA 从哪来：只在有图或正在画时说；“不画 TA”的原因码只进“技术信息”。
  const identity = IDENTITY_TEXT[journal.identity_mode] ?? null;
  const identityTech = journal.identity_mode === "none" ? journal.identity_note?.trim() || null : null;
  switch (journal.image_status) {
    case "ready": {
      const url = safeImageUrl(journal.image_url);
      if (!url) return { state: "unknown", heading, caption: "手账结果还没确认", imageUrl: null, staleNote: null, canRedraw, identity: null, text, tech: null };
      // 不变量：journals 挂在这一版修订上，按理 plan_revision 一定相同；万一不同，说一句按上一版画的。
      const stale = planRevision != null && journal.plan_revision !== planRevision;
      return {
        state: "ready",
        heading,
        caption: "手账画面只画风景和心情；地名、时间、费用以这一页的文字为准",
        imageUrl: url,
        staleNote: stale ? "这张手账是按上一版计划画的，以这一页的文字为准" : null,
        canRedraw: false,
        identity,
        text,
        tech: identityTech,
      };
    }
    case "processing":
      return { state: "drawing", heading, caption: "手账在画", imageUrl: null, staleNote: null, canRedraw: false, identity, text, tech: identityTech };
    case "failed":
      return { state: "failed", heading, caption: "这次手账没画成", imageUrl: null, staleNote: null, canRedraw, identity: null, text, tech: null };
    default:
      // unknown 与不认识的状态：只说“还没确认”，不说失败（可能已经画了并计费，§11.5）；不自动重画。
      return { state: "unknown", heading, caption: "手账结果还没确认", imageUrl: null, staleNote: null, canRedraw, identity: null, text, tech: null };
  }
}

function titleOf(stage: PlanStage, who: string, destination: string): string {
  switch (stage) {
    case "wish":
      return `${who} 想去 ${destination}`;
    case "ready":
      return `${who} 准备去 ${destination}`;
    case "departed":
      return `${who} 出发去 ${destination} 了`;
    case "back":
      return `${who} 从 ${destination} 回来了`;
    case "cancelled":
      return `去 ${destination} 的心愿先放下了`;
    default:
      return `${who} 的旅行计划`;
  }
}

function outcomeLine(places: PlaceView[], hasMemory: boolean): string {
  if (!hasMemory) return "TA 回来了，到访记录还在整理";
  const visited = places.filter((p) => p.stamp?.kind === "visited").length;
  const next = places.filter((p) => p.stamp?.kind === "next").length;
  if (visited && next) return `去了 ${visited} 个地方，${next} 个留到下次`;
  if (visited) return `去了 ${visited} 个地方`;
  if (next) return `这趟没有到访记录，${next} 个地方留到下次`;
  return "这趟没有到访记录";
}

/** 计划当前那一版（current_revision）；找不到就当没有计划全文。 */
function currentRevision(plan: TravelPlan | null): TravelPlanRevision | null {
  if (!plan) return null;
  return plan.revisions.find((r) => r.plan_revision === plan.current_revision) ?? null;
}

function build(wish: TravelWish, plan: TravelPlan | null, key: string, href: string, options: ViewOptions): PlanView {
  const stage = STAGE_OF[wish.status] ?? "unknown";
  const revision = currentRevision(plan);
  const memoryJournal = latestJournal(revision, "memory");
  // 回来以后有回忆页就显示回忆页，否则显示计划页。
  const shownJournal = memoryJournal ?? latestJournal(revision, "plan");
  // 不变量：到访只认这一版计划的回忆页（journals 挂在修订上，plan_revision 按理一定相同）。
  const memory = memoryJournal && revision && memoryJournal.plan_revision === revision.plan_revision ? memoryJournal.stations : null;
  const ctx: Ctx = {
    stage,
    zone: zoneOf(options.timezone),
    isDemo: options.isDemo === true,
    wish,
    revision,
    facts: new Map((revision?.facts ?? []).map((f) => [f.fact_id, f])),
    factList: revision?.facts ?? [],
    sources: new Map((revision?.sources ?? []).map((s) => [s.source_id, s])),
    memory,
  };
  const who = options.petName?.trim() || "TA";

  // 只有“想去”（active）才列“还差什么”；排序后的第一条同时决定状态标签、列表卡片那句和地图那一行。
  const ordered =
    stage === "wish"
      ? (wish.waiting_reasons ?? [])
          .map((code, index) => ({ code: String(code), index }))
          .sort((a, b) => (isReason(a.code) ? WAITING_ORDER[a.code] : 99) - (isReason(b.code) ? WAITING_ORDER[b.code] : 99) || a.index - b.index)
      : [];
  const waiting = ordered.map(({ code, index }) => waitingItem(code, index, ctx));
  const firstCode = ordered[0]?.code;
  const status = stage === "wish" ? (firstCode && isReason(firstCode) ? WAITING_REASON_CHIPS[firstCode] : { label: "还在准备", tone: "neutral" as ChipTone }) : STAGE_CHIP[stage];

  const stops = revision?.stops ?? [];
  const mainIndex = stops.findIndex((s) => s.role === "main");
  const main: PlaceView =
    revision && mainIndex >= 0
      ? placeView(stops[mainIndex], mainIndex, revision, ctx)
      : { id: `${wish.wish_id}:destination`, role: "main", name: wish.destination_name, why: null, tip: null, pending: false, verified: false, verifyText: "地点待确认", stamp: null, mapUrl: null };
  const suggestions = revision ? stops.flatMap((s, i) => (i !== mainIndex && s.role === "suggested" ? [placeView(s, i, revision, ctx)] : [])) : [];

  const outcome = outcomeLine([main, ...suggestions], Boolean(memory));
  const journeyId = plan ? (revision?.journey?.journey_id ?? wish.journey_id) : wish.journey_id;
  const summary =
    stage === "wish"
      ? waiting.length
        ? `还差 ${waiting.length} 件事，准备好了再出发`
        : "还在准备，准备好了再出发"
      : stage === "ready"
        ? "该准备的都齐了"
        : stage === "departed"
          ? `${who} 已经在路上；回来以后，真的到过的地方才盖章`
          : stage === "back"
            ? outcome
            : stage === "cancelled"
              ? journeyId
                ? "这趟提前结束了，只给真的到过的地方盖章"
                : "这个心愿先放下了，没有出发"
              : "这份计划的状态还在确认";
  const cardLine =
    stage === "wish"
      ? (waiting[0]?.text ?? "还在准备")
      : stage === "ready"
        ? "都准备好了"
        : stage === "departed"
          ? "已经在路上"
          : stage === "back"
            ? outcome
            : stage === "cancelled"
              ? "这个心愿先放下了"
              : "状态还在确认";

  return {
    key,
    href,
    planRevision: revision?.plan_revision ?? null,
    isDemo: ctx.isDemo,
    stage,
    title: titleOf(stage, who, wish.destination_name),
    destination: wish.destination_name,
    planTitle: revision?.title?.trim() || null,
    status,
    summary,
    cardLine,
    reason: wish.owner_reason?.trim() || null,
    waiting,
    preconditions: preconditionViews(ctx),
    arrangement: revision?.summary?.trim() || null,
    planWritten: Boolean(revision),
    planLink: !revision && wish.plan_id ? `/guides/plan/${encodeURIComponent(wish.plan_id)}` : null,
    validity: revision ? rangeText(revision.valid_from, revision.valid_until, ctx.zone) : null,
    main,
    suggestions,
    reminders: reminderViews(revision?.owner_tips ?? [], ctx),
    rainPlan: revision?.rain_alternative?.trim() || null,
    coins: coinView(revision?.journey ?? null, ctx),
    realCosts: realCostViews(ctx),
    journal: journalView(shownJournal, revision?.plan_revision ?? null, ctx),
    sources: ctx.factList.map((fact) => sourceView(fact, ctx)),
  };
}

/**
 * GET /travel/wish → 页面 /guides/wish：当前活动心愿。TravelWish 只带 plan_id / plan_revision、不带计划全文；
 * 计划全文在 /guides/plan/:planId（GET /travel/plans/{plan_id}），这一页给一个去那里的链接。
 */
export function viewOfWish(wish: TravelWish, options: ViewOptions = {}): PlanView {
  return build(wish, null, wish.wish_id, "/guides/wish", options);
}

/** /guides/plan/:planId：某一份计划（显示 current_revision 那一版）。 */
export function viewOfPlan(bundle: PlanBundle, options: ViewOptions = {}): PlanView {
  return build(bundle.wish, bundle.plan, bundle.plan.plan_id, `/guides/plan/${encodeURIComponent(bundle.plan.plan_id)}`, options);
}

/** 地图主状态面板那一行（第②期）：只在想去 / 可以出发时出现，“想去 {目的地} · {还差什么第一条}”。 */
export function wishNoteLine(view: PlanView): string | null {
  if (view.stage === "wish") return `想去 ${view.destination} · ${view.waiting[0]?.text ?? "还在准备"}`;
  if (view.stage === "ready") return `想去 ${view.destination} · 都准备好了`;
  return null;
}
