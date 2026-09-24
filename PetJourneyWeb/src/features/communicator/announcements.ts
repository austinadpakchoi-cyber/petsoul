/**
 * 通讯器 · 公告（玩家端方案 7.1、11 节）：GET /announcements 的逐条解析、链接与配图分类、级别说法、本机已读记录。
 * 这里全是纯函数（不碰 React），页面与细条共用；单独测试见 tests/claude-6c2b-announcements.test.tsx。
 *
 * 类型用契约（generated.ts 的 AnnouncementFeed / AnnouncementItem / AnnouncementSeverity / AnnouncementSource），不再自定义。
 * **运行时逐条校验保留**：路由的 response_model 还没关联（归运营后台 adm1），服务端暂时不保证形状——
 * 解析的职责就是把“不保证形状的 JSON”变成“符合契约类型的数据”，不符合的条目丢掉，不让页面崩。
 *
 * 后端事实（以代码为准）：
 * - 响应 `{announcements, as_of, source}`；`source = "not_installed"` 的意思是**读不到**（后端没装运营后台），不是“没有公告”；
 * - 每条：item_id、slug、revision（只增不减的版本号）、title、body（纯文本，后台拒收 HTML）、severity、
 *   link、image_asset_id、image_url、effective_at、expires_at；后端已按生效时间倒序、只给已生效未过期的；
 * - severity 只有 info / notice / maintenance（后台说法“一般 / 通知 / 维护”）；
 * - link 后台只收“以 / 开头的站内相对路径”；image_url 是受控入口 `/api/v1/web/assets/{id}`。
 * 前端不因为后端这样校验就照单全收：`startsWith("/")` 也放得进 `//别的站`，所以链接与配图在这里再判一次。
 */
import { ApiError } from "@/shared/api/errors";
import { AnnouncementSeverityValues, type AnnouncementFeed, type AnnouncementItem, type AnnouncementSeverity, type AnnouncementSource } from "@/shared/contracts";

/* ---------------- 类型（来自契约） ---------------- */

export type { AnnouncementFeed, AnnouncementSeverity, AnnouncementSource };
/**
 * 一条公告＝契约的 AnnouncementItem。几个字段的约定：revision 是这条公告当前生效的版本号（已读按 slug + revision 记）；
 * body 是纯文本、按原文排；effective_at 契约里可空（后端实际总会给，缺了就不写日期、排在最后）。
 */
export type Announcement = AnnouncementItem;

/* ---------------- 解析：逐条校验，坏条目丢掉 ---------------- */

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const filled = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;
const SEVERITIES: ReadonlySet<string> = new Set<string>(AnnouncementSeverityValues);

const INVALID = Symbol("invalid");
/** 可空的文本字段：缺省或 null 都当 null；给了却不是文本＝类型不对。 */
function nullableText(value: unknown): string | null | typeof INVALID {
  if (value === undefined || value === null) return null;
  return typeof value === "string" ? value : INVALID;
}

/** 不认识的级别（后端以后新增或改名）收成“info”——照常显示成一般的“公告”，不因为多了一个级别就把公告丢掉。 */
function severityValue(raw: string): AnnouncementSeverity {
  const trimmed = raw.trim();
  return SEVERITIES.has(trimmed) ? (trimmed as AnnouncementSeverity) : "info";
}

/**
 * 解析一条公告。必需字段（item_id、slug、revision、title、body、severity）缺了或类型不对 → null（整条丢掉）；
 * 可空字段（link、image_asset_id、image_url、effective_at、expires_at）缺省按 null，给了别的类型同样整条丢掉。
 * revision 必须是 ≥ 1 的整数；标题不能是空白（细条上只有标题一行）；effective_at 给了就必须读得出时间（排序要用）。
 */
export function parseAnnouncement(raw: unknown): Announcement | null {
  if (!isRecord(raw)) return null;
  const { item_id, slug, revision, title, body, severity } = raw;
  if (!filled(item_id) || !filled(slug) || !filled(title)) return null;
  if (typeof body !== "string" || typeof severity !== "string") return null;
  if (typeof revision !== "number" || !Number.isSafeInteger(revision) || revision < 1) return null;
  const link = nullableText(raw.link);
  const imageAssetId = nullableText(raw.image_asset_id);
  const imageUrl = nullableText(raw.image_url);
  const effectiveAt = nullableText(raw.effective_at);
  const expiresAt = nullableText(raw.expires_at);
  if (link === INVALID || imageAssetId === INVALID || imageUrl === INVALID || effectiveAt === INVALID || expiresAt === INVALID) return null;
  if (effectiveAt !== null && !Number.isFinite(Date.parse(effectiveAt))) return null;
  return {
    item_id,
    slug,
    revision,
    title,
    body,
    severity: severityValue(severity),
    link,
    image_asset_id: imageAssetId,
    image_url: imageUrl,
    effective_at: effectiveAt,
    expires_at: expiresAt,
  };
}

/**
 * 解析整个响应。外层不对（不是对象、announcements 不是数组、没有 as_of）说明这次响应本身不符合契约：抛可重试的错误，
 * 由页面给“重试”，不假装“暂时没有公告”。里层逐条解析，坏条目丢掉；同一个 item_id 出现两次只留第一条。
 * source 只认 "not_installed"（读不到），其余按 "live"。
 */
export function parseAnnouncementFeed(raw: unknown): AnnouncementFeed {
  if (!isRecord(raw) || !Array.isArray(raw.announcements) || !filled(raw.as_of)) {
    throw new ApiError({ kind: "http", code: "INTERNAL_ERROR", message: "公告暂时读不出来，请稍后再试。", retryable: true });
  }
  const seen = new Set<string>();
  const announcements: Announcement[] = [];
  for (const item of raw.announcements) {
    const parsed = parseAnnouncement(item);
    if (!parsed || seen.has(parsed.item_id)) continue;
    seen.add(parsed.item_id);
    announcements.push(parsed);
  }
  return { announcements, as_of: raw.as_of, source: raw.source === "not_installed" ? "not_installed" : "live" };
}

/** 生效时间；没有的排在最后。 */
const effectiveTime = (announcement: Announcement): number =>
  announcement.effective_at ? Date.parse(announcement.effective_at) : Number.NEGATIVE_INFINITY;

/** 按生效时间倒序（新的在前）；没有生效时间的排最后；时间相同保持接口给的顺序。不改动传入的数组。 */
export function sortAnnouncements(list: readonly Announcement[]): Announcement[] {
  return [...list].sort((a, b) => {
    const ta = effectiveTime(a);
    const tb = effectiveTime(b);
    return ta === tb ? 0 : tb > ta ? 1 : -1;
  });
}

/* ---------------- 级别 ---------------- */

export type SeverityView = { tone: AnnouncementSeverity; label: string; noun: string };

/** 玩家看到的说法：一般的就叫“公告”（后台的“一般”对玩家不好懂），另两级沿用后台的“通知”“维护”。用 Map 查，不碰原型。 */
const SEVERITY = new Map<string, SeverityView>([
  ["info", { tone: "info", label: "公告", noun: "公告" }],
  ["notice", { tone: "notice", label: "通知", noun: "通知" }],
  ["maintenance", { tone: "maintenance", label: "维护", noun: "维护公告" }],
]);
const DEFAULT_SEVERITY = SEVERITY.get("info")!;

/** 解析已把不认识的级别收成 info；这里再兜一次（直接拿到的数据也不把原始值露出来）。 */
export function severityOf(raw: string | null | undefined): SeverityView {
  return SEVERITY.get(typeof raw === "string" ? raw.trim() : "") ?? DEFAULT_SEVERITY;
}

/* ---------------- 链接与配图 ---------------- */

export type AnnouncementLink = { kind: "internal"; to: string } | { kind: "external"; href: string; host: string } | { kind: "none" };
const NO_LINK: AnnouncementLink = { kind: "none" };

/**
 * 浏览器解析网址时会删掉制表符和换行、把反斜杠当斜杠：`/\t/别的站`、`/\别的站` 实际都会去别的站。
 * 所以带空白、控制字符或反斜杠的一律不做成链接。
 */
const UNSAFE_URL_CHARS = /[\s\u0000-\u001f\u007f\\]/;
/** 只用来判断“解析后还在不在本站”的假站点，从不发请求。 */
const PROBE_ORIGIN = "https://petsoul.invalid";

/** 站内路径：以单个 / 开头、解析后仍在本站；返回规整后的 路径?查询#片段。不是就 null。 */
function sitePath(raw: string): string | null {
  if (!raw.startsWith("/") || raw.startsWith("//") || UNSAFE_URL_CHARS.test(raw)) return null;
  try {
    const url = new URL(raw, PROBE_ORIGIN);
    return url.origin === PROBE_ORIGIN ? `${url.pathname}${url.search}${url.hash}` : null;
  } catch {
    return null;
  }
}

/**
 * 公告里的链接怎么做：
 * - 站内路径 → react-router 的 Link（不离开应用）；
 * - http / https 外链 → 新窗口打开并标明“外部链接”（页面上写出对方站点）；带账号密码的网址（`https://本站@别的站`）不做；
 * - 其它一律不做成链接（javascript:、data:、mailto:、`//别的站`、相对路径……）。
 * 后端目前只收站内路径；外链这一支是前端自己的底线，不是后台已开放的能力。
 */
export function announcementLink(raw: string | null | undefined): AnnouncementLink {
  if (typeof raw !== "string" || !raw) return NO_LINK;
  const path = sitePath(raw);
  if (path) return { kind: "internal", to: path };
  if (!/^https?:\/\//i.test(raw) || UNSAFE_URL_CHARS.test(raw)) return NO_LINK;
  try {
    const url = new URL(raw);
    if ((url.protocol !== "http:" && url.protocol !== "https:") || !url.hostname || url.username || url.password) return NO_LINK;
    return { kind: "external", href: url.href, host: url.host };
  } catch {
    return NO_LINK;
  }
}

/**
 * 配图地址：只用服务端给的站内地址（后端的受控入口 `/api/v1/web/assets/{id}`；素材下架后它会 404，页面随之不显示）。
 * 别处的图（包括 https）不加载——后端承诺“玩家侧不会拿到别处的图”，前端不替它破这个例，也不让第三方拿到玩家的访问记录。
 */
export function announcementImageSrc(raw: string | null | undefined): string | null {
  if (typeof raw !== "string" || !raw) return null;
  return sitePath(raw) ? raw : null;
}

/** 生效日期：今年的写“9月24日”，往年的带上年份。没有或读不出来就不写。 */
export function announcementDay(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (!Number.isFinite(date.getTime())) return "";
  const options: Intl.DateTimeFormatOptions =
    date.getFullYear() === now.getFullYear() ? { month: "long", day: "numeric" } : { year: "numeric", month: "long", day: "numeric" };
  return new Intl.DateTimeFormat("zh-CN", options).format(date);
}

/* ---------------- 本机已读记录（按账号分开；每个账号按 slug + revision 记） ---------------- */

/**
 * localStorage 键的前缀，后面接账号：登录的人用用户编号；演示（fixture）或拿不到用户编号时用固定的 "fixture"。
 * 同一台设备上两个账号的已读互不影响。早先不带账号的旧键（`petsoul:announcements:read:v1`）不迁移——读不到就当未读。
 * 内容形如 {"v":1,"read":[["slug",3],…]}：同一个 slug 只记最近读过的那个版本号。
 */
export const READ_STORAGE_PREFIX = "petsoul:announcements:read:v1:";
export const FIXTURE_READ_ACCOUNT = "fixture";
/** 已读记在哪个账号下：有用户编号用用户编号，没有（演示、拿不到）用 "fixture"。 */
export const readAccountOf = (userId: string | null | undefined): string => (typeof userId === "string" && userId ? userId : FIXTURE_READ_ACCOUNT);
export const readStorageKey = (account: string): string => `${READ_STORAGE_PREFIX}${encodeURIComponent(account)}`;
/** 同一页里写完已读后广播的事件（别的标签页靠浏览器自带的 storage 事件）。 */
export const READ_CHANGED_EVENT = "petsoul:announcements-read";
/** 每个账号最多记这么多个 slug：公告很少，这只是防止本机记录无限长。 */
const READ_LIMIT = 200;

export type ReadMap = ReadonlyMap<string, number>;

function localStore(): Storage | null {
  try {
    return window.localStorage; // 某些浏览器设置下，连取 localStorage 这一步都会抛错
  } catch {
    return null;
  }
}

/** 这个账号在本机原样的已读记录；读不到（被禁用、抛错）就是 null——当作都没读过。 */
export function readRawReadState(account: string): string | null {
  try {
    return localStore()?.getItem(readStorageKey(account)) ?? null;
  } catch {
    return null;
  }
}

/** 把原样记录解析成 slug → revision。坏掉的记录当作没有；不认识的条目跳过。 */
export function parseReadState(raw: string | null): Map<string, number> {
  const read = new Map<string, number>();
  if (!raw) return read;
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return read;
  }
  if (!isRecord(data) || data.v !== 1 || !Array.isArray(data.read)) return read;
  for (const entry of data.read) {
    if (Array.isArray(entry) && entry.length === 2 && filled(entry[0]) && typeof entry[1] === "number" && Number.isSafeInteger(entry[1])) {
      read.set(entry[0], entry[1]);
    }
  }
  return read;
}

/** 未读：这个账号在本机没记过这个 slug，或记的不是这个版本（后台发了新版本就重新算未读）。 */
export function isUnread(announcement: Pick<Announcement, "slug" | "revision">, read: ReadMap): boolean {
  return read.get(announcement.slug) !== announcement.revision;
}

/** 页面上“新”标记用的键。 */
export const readKeyOf = (announcement: Pick<Announcement, "slug" | "revision">): string => `${announcement.slug}#${announcement.revision}`;

/**
 * 在这个账号下把这些公告记为已读（每个 slug 记当前 revision），不碰别的账号的记录。
 * 写不进去（被禁用、满了、抛错）就算了：下次照样当未读，页面不受影响。没有变化时不写。返回这次是否真的写进去了。
 */
export function markAnnouncementsRead(account: string, list: readonly Pick<Announcement, "slug" | "revision">[]): boolean {
  const read = parseReadState(readRawReadState(account));
  if (list.every((announcement) => !isUnread(announcement, read))) return false;
  for (const announcement of list) {
    read.delete(announcement.slug); // 先删再加：刚读过的排到最后，超出上限时丢的是最早读的
    read.set(announcement.slug, announcement.revision);
  }
  try {
    const store = localStore();
    if (!store) return false;
    store.setItem(readStorageKey(account), JSON.stringify({ v: 1, read: [...read.entries()].slice(-READ_LIMIT) }));
  } catch {
    return false;
  }
  try {
    window.dispatchEvent(new Event(READ_CHANGED_EVENT));
  } catch {
    // 广播不了只影响同页别处的即时刷新，下次渲染照样读得到
  }
  return true;
}

/**
 * 通讯器顶上的细条放哪一条：有未读就放最新的一条未读（按生效时间）；全都读过就放最新的一条、安静地显示（仍能点进去重看）；
 * 没有公告返回 null——一行都不占。
 */
export function pickStripAnnouncement(list: readonly Announcement[], read: ReadMap): { announcement: Announcement; unread: boolean } | null {
  if (!list.length) return null;
  const sorted = sortAnnouncements(list);
  const unread = sorted.find((announcement) => isUnread(announcement, read));
  return unread ? { announcement: unread, unread: true } : { announcement: sorted[0], unread: false };
}

/* ---------------- 查询键与演示数据 ---------------- */

/** 本模块自己的查询键（不进共享的 queryKeys）：按看的人分开——登录与否看到的公告不同，换账号不串缓存。 */
export const announcementsKey = (viewer: string | null) => ["announcements", "list", viewer ?? "-"] as const;

/**
 * 演示世界（fixture）的公告。契约的 source 只有 live / not_installed，没有“演示”这一值，所以演示身份不靠 source 表达：
 * 标题一律以“（演示）”开头，公告页在演示模式下挂“演示公告”标识（按 env.dataMode，与卡包等页同一做法）——不冒充真实运营公告，
 * 也不宣布任何真实安排（没有真的维护、没有真的活动）。站内链接与配图只用本站已有的页面和素材。
 */
export function demoAnnouncementFeed(): AnnouncementFeed {
  return {
    source: "live",
    as_of: "2026-09-24T02:00:00Z",
    announcements: [
      {
        item_id: "fx-announcement-3",
        slug: "demo-maintenance",
        revision: 1,
        title: "（演示）维护公告会是这个样子",
        body: "这是一条演示公告，不是真实的通知，也没有安排任何维护。\n真实的维护公告会写明开始和结束的时间。",
        severity: "maintenance",
        link: null,
        image_asset_id: null,
        image_url: null,
        effective_at: "2026-09-24T01:00:00Z",
        expires_at: null,
      },
      {
        item_id: "fx-announcement-2",
        slug: "demo-picture",
        revision: 1,
        title: "（演示）公告也可以带一张配图",
        body: "演示：配图放在正文下面，整张显示、不裁切。",
        severity: "info",
        link: null,
        image_asset_id: null,
        image_url: "/ui-assets/UI-ASSET-001/v1/habitat-seaside.webp",
        effective_at: "2026-09-23T12:00:00Z",
        expires_at: null,
      },
      {
        item_id: "fx-announcement-1",
        slug: "demo-welcome",
        revision: 1,
        title: "（演示）通讯器里可以看公告了",
        body: "演示：平台的通知都会放在这里。\n有新公告时，通讯器顶上会提醒你；读过之后那一行会变安静。\n\n下面的链接是站内链接，点了不会离开 PetSoul。",
        severity: "notice",
        link: "/memories",
        image_asset_id: null,
        image_url: null,
        effective_at: "2026-09-22T09:00:00Z",
        expires_at: null,
      },
    ],
  };
}
