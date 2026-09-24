/**
 * 生活片段（/timeline）的读法。数据来自 GET /timeline?pet_id=…（后端 app/web_agent/timeline.py 的 timeline()）：
 * 把已经发生的记录按时间串起来，新的在前，最多 100 条。前端只分组、配图标、决定能不能点，标题与小字一律照原文显示，不补、不猜。
 *
 * kind 的全部取值与 ref_id 指向什么（照后端实现逐条核对）：
 * - trip「出发：…」、first_drive「第一次自己开车：…」、work「去打工：…」、home「回到家：…／收工回到家：…」、stamp「护照上盖了…的纪念章」→ 行程 journey_id；
 * - salary「领到工资 N 星币」→ 账本 tx_id；school「报名了爪爪驾校」→ 没有；
 * - exam：新驾校「科目一考试通过…」是考局 session_id，旧版驾考「理论考试通过…」是旧表的 attempt_id，两种混在同一个 kind 里；
 * - credential「拿到星球居民证／开通星球银行卡／…」→ 证件 credential_id；friend「认识了…」→ 朋友 friend_id；
 * - 收藏里的 kind 原样透出：postcard、badge、seed、shared_memory、license_photo、car_voucher → 收藏 item_id
 *   （以后收藏多了新种类，这里也会出现没见过的 kind，标题是“得到一件纪念”）；
 * - guide「写了一份攻略：…」→ 攻略 guide_id。
 *
 * 链接只给能确定页面的：证件 → /credentials/:id、攻略 → /guides/:id（后端按编号读、只核对是不是这只宠物的家人，全家都打得开）。
 * 其余只显示文字：行程、账本、朋友、收藏都没有按这个编号打开的页面；驾考的两种编号分不清，旧编号打不开成绩页，所以也不链。
 * 认不出的 kind 用中性图标；kind 的原始代码不进页面（文字和属性里都没有）。
 */
import type { TimelineItem } from "@/shared/contracts";
import type { IconName } from "@/shared/ui";

/** 查询键只在本模块用：按账号与宠物分开；切换宠物时家庭上下文会清掉除账号、家庭列表以外的缓存。 */
export function timelineKey(userId: string, petId: string) {
  return ["pets", "timeline", userId, petId] as const;
}

export type TimelineTone = "leaf" | "sun" | "coral" | "sky" | "plain";

/** UI-ASSET-005 v1 交付的线性图标（public/ui-assets/UI-ASSET-005/v1/icon-<name>.svg）。 */
export type TimelineAssetIcon =
  | "compass"
  | "car"
  | "bag"
  | "home"
  | "wallet"
  | "steering-wheel"
  | "flag"
  | "id-card"
  | "stamp"
  | "paw"
  | "star"
  | "leaf"
  | "heart"
  | "camera"
  | "ticket"
  | "map";

/** 一条记录的样子：图标来自交付的线性图标（asset）或共享 Icon（ui），外加一个色调；link 只给能确定页面的 kind。 */
export interface TimelineLook {
  icon: { set: "asset"; name: TimelineAssetIcon } | { set: "ui"; name: IconName };
  tone: TimelineTone;
  link?: (refId: string) => string;
}

const asset = (name: TimelineAssetIcon, tone: TimelineTone, link?: (refId: string) => string): TimelineLook => ({ icon: { set: "asset", name }, tone, link });

/** 用 Map 而不是对象字面量：kind 是服务端给的任意字符串，"constructor"、"toString" 这类名字不能从原型链上查到东西。 */
const LOOKS = new Map<string, TimelineLook>([
  ["trip", asset("compass", "sky")],
  ["first_drive", asset("car", "sky")],
  ["work", asset("bag", "sun")],
  ["home", asset("home", "leaf")],
  ["salary", asset("wallet", "sun")],
  ["school", asset("steering-wheel", "leaf")],
  ["exam", asset("flag", "leaf")],
  ["credential", asset("id-card", "leaf", (id) => `/credentials/${encodeURIComponent(id)}`)],
  ["stamp", asset("stamp", "sky")],
  ["friend", asset("paw", "coral")],
  // 交付的线性图标里没有信封，明信片用共享图标里的 mail（同样是 24 网格、圆头描边）。
  ["postcard", { icon: { set: "ui", name: "mail" }, tone: "coral" }],
  ["badge", asset("star", "sun")],
  ["seed", asset("leaf", "leaf")],
  ["shared_memory", asset("heart", "coral")],
  ["license_photo", asset("camera", "coral")],
  ["car_voucher", asset("ticket", "sun")],
  ["guide", asset("map", "sky", (id) => `/guides/${encodeURIComponent(id)}`)],
]);

/** 认不出的 kind：回忆自己的书签图标，不暗示是哪一类事。 */
export const NEUTRAL_LOOK: TimelineLook = { icon: { set: "ui", name: "bookmark" }, tone: "plain" };

export function timelineLook(kind: string): TimelineLook {
  return LOOKS.get(kind) ?? NEUTRAL_LOOK;
}

/**
 * 每条下面那行小字：照原文显示，只有“小字其实是编号”的种类不显示。
 * 证件（credential）的小字是后端给的证件编号（如 PS-CARE-2026-XXXXXX），对主人是一串代码；
 * 编号在点进去的证件页上照样有（卡面、背面），这里不重复露出（2026-09-24 全站文字清理）。
 */
const CODE_DETAIL_KINDS: ReadonlySet<string> = new Set(["credential"]);

export function timelineDetail(item: Pick<TimelineItem, "kind" | "detail">): string | null {
  if (CODE_DETAIL_KINDS.has(item.kind)) return null;
  return item.detail?.trim() ? item.detail : null;
}

/** 能确定页面才给地址；ref_id 缺失或是空白时不给。 */
export function timelineHref(item: Pick<TimelineItem, "kind" | "ref_id">): string | null {
  const ref = item.ref_id?.trim();
  if (!ref) return null;
  const link = LOOKS.get(item.kind)?.link;
  return link ? link(ref) : null;
}

export interface TimelineEntry {
  item: TimelineItem;
  /** 解析出来的时间；读不出来时为 null（放进最后一组“没记下日子的”）。 */
  at: Date | null;
  /** 在接口结果里的位置，作列表 key：同一时刻可能有好几条，标题也可能相同。 */
  index: number;
}

export interface TimelineGroup {
  key: string;
  label: string;
  entries: TimelineEntry[];
}

export const UNDATED_LABEL = "没记下日子的";

const pad = (value: number) => String(value).padStart(2, "0");

function dayKey(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** 本地日期的叫法：今天 / 昨天 / 9 月 22 日；不是今年的写上年份。 */
export function dayLabel(date: Date, now: Date): string {
  if (dayKey(date) === dayKey(now)) return "今天";
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  if (dayKey(date) === dayKey(yesterday)) return "昨天";
  const monthDay = `${date.getMonth() + 1} 月 ${date.getDate()} 日`;
  return date.getFullYear() === now.getFullYear() ? monthDay : `${date.getFullYear()} 年 ${monthDay}`;
}

/** 本地时刻 HH:mm。 */
export function clockText(date: Date): string {
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/**
 * 按本地日期分组：组与组、组内都是新的在前。同一时刻的几条保留接口给的先后
 * （后端已经按“后发生的在前”排好，例如考试通过与签发驾照同一刻，签发在前）。读不出时间的放在最后一组。
 */
export function groupTimeline(items: readonly TimelineItem[], now: Date): TimelineGroup[] {
  const parsed = items.map((item, index) => ({ item, index, ms: Date.parse(item.at) }));
  const dated = parsed.filter((entry) => Number.isFinite(entry.ms)).sort((a, b) => b.ms - a.ms || a.index - b.index);
  const groups: TimelineGroup[] = [];
  for (const { item, index, ms } of dated) {
    const at = new Date(ms);
    const key = dayKey(at);
    let group = groups[groups.length - 1];
    if (!group || group.key !== key) {
      group = { key, label: dayLabel(at, now), entries: [] };
      groups.push(group);
    }
    group.entries.push({ item, at, index });
  }
  const undated = parsed.filter((entry) => !Number.isFinite(entry.ms));
  if (undated.length > 0) {
    groups.push({ key: "undated", label: UNDATED_LABEL, entries: undated.map(({ item, index }) => ({ item, at: null, index })) });
  }
  return groups;
}
