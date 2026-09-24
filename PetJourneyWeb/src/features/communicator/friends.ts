/**
 * 通讯器 · TA 的朋友：把 GET /friends（FriendSummary）变成要显示的文字（纯函数，便于单独测试）。
 *
 * 关系不是位置（玩家端方案 4.1）：`last_place` 只说明 TA 们上次在哪碰过面，只写成“最近在某地见过”，
 * 不当成朋友此刻的位置，不写“此刻在 / 正在”，也不在地图上画点。
 */
import type { FriendSummary, PetSpecies } from "@/shared/contracts";

export type ClosenessTone = "new" | "familiar" | "close" | "unknown";
export type Closeness = { label: string; tone: ClosenessTone; rank: number };

/**
 * 熟悉程度：后端 `closeness` 的真实取值就是这三个中文词（web_social/friends.py：见过 1 次“初识”、2–3 次“熟人”、4 次起“好朋友”）。
 * 用 Map 查，不用对象下标——“constructor”这类取值不会碰巧查到原型上的东西。
 */
const CLOSENESS = new Map<string, Closeness>([
  ["初识", { label: "初识", tone: "new", rank: 1 }],
  ["熟人", { label: "熟人", tone: "familiar", rank: 2 }],
  ["好朋友", { label: "好朋友", tone: "close", rank: 3 }],
]);

/** 不认识的取值（后端以后新增或改名）：用中性的“朋友”，绝不把原始值显示出来。 */
const UNKNOWN_CLOSENESS: Closeness = { label: "朋友", tone: "unknown", rank: 0 };

export function closenessOf(raw: string | null | undefined): Closeness {
  return CLOSENESS.get(typeof raw === "string" ? raw.trim() : "") ?? UNKNOWN_CLOSENESS;
}

const SPECIES_NAMES: Record<PetSpecies, string> = { cat: "猫", dog: "狗", rabbit: "兔子", hamster: "仓鼠", bird: "小鸟", parrot: "鹦鹉", other: "小动物" };
const SPECIES = new Map<string, string>(Object.entries(SPECIES_NAMES));

/** 物种的中文名；不认识的代码不显示（不把原始代码露给主人）。 */
export function speciesLabel(raw: string | null | undefined): string | null {
  return typeof raw === "string" ? SPECIES.get(raw.trim()) ?? null : null;
}

/** “见过 N 次”：后端每次真的同时同地遇到才 +1；读不出有效次数就不写。 */
export function meetCountText(count: number): string | null {
  return Number.isFinite(count) && count >= 1 ? `见过 ${Math.floor(count)} 次` : null;
}

/** “最近在某地见过”：只说见过，不说此刻在哪；没有地点就不写。 */
export function lastSeenText(place: string | null | undefined): string | null {
  const name = typeof place === "string" ? place.trim() : "";
  return name ? `最近在${name}见过` : null;
}

/**
 * 点一个朋友去哪：只有看得到公开主页的才给链接，否则只展示信息（不做点了没反应、或点进去是空页的假入口）。
 * - 宠物朋友 → `/pets/:petId`（宠物公开主页）。遇到的前提是两家都公开了动态，所以遇到时一定看得到它的主页
 *   （至少是名字与公开动态）；对方之后若关掉公开，主页页面会自己说找不到——FriendSummary 目前没有
 *   “主页是否可见”的字段，这里不猜、也不为此逐个去试探请求。
 * - 星球居民 → 不给链接：后端的居民朋友是星球上的常住居民（编号形如 `npc:…`），没有公开主页；
 *   `/world/residents/:petId` 是“可以领养的居民”的页面，那些居民若被遇到，回来的是 kind = pet。
 * - 不认识的 kind：不给链接。
 */
export function friendProfileHref(friend: Pick<FriendSummary, "kind" | "friend_id">): string | null {
  if (friend.kind !== "pet" || !friend.friend_id) return null;
  return `/pets/${encodeURIComponent(friend.friend_id)}`;
}

function timeOf(iso: string): number {
  const t = Date.parse(iso);
  return Number.isFinite(t) ? t : 0;
}

function countOf(count: number): number {
  return Number.isFinite(count) ? count : 0;
}

/**
 * 排序：见面次数多的在前；次数相同，熟悉程度高的在前；再相同，最近一次见面更近的在前；最后按名字、编号，保证顺序稳定。
 * 理由：这是一份“关系”清单，越熟的朋友越靠前。按见面次数排——次数是事实（每次真的同时同地遇到才 +1），
 * 熟悉程度本身就是后端按次数给的称呼，两者排出来一致；而且后端以后新增或改名的称呼，不会因为前端不认识就被排到最后。
 * 不按“最近在哪见过”把刚见过的顶到最前：那样列表会被读成“谁刚在附近”的位置动态，关系不是位置。
 * 不改动传入的数组。
 */
export function sortFriends(list: readonly FriendSummary[]): FriendSummary[] {
  return [...list].sort(
    (a, b) =>
      countOf(b.meet_count) - countOf(a.meet_count) ||
      closenessOf(b.closeness).rank - closenessOf(a.closeness).rank ||
      timeOf(b.last_met_at) - timeOf(a.last_met_at) ||
      a.name.localeCompare(b.name, "zh-Hans-CN") ||
      (a.friend_id < b.friend_id ? -1 : a.friend_id > b.friend_id ? 1 : 0),
  );
}
