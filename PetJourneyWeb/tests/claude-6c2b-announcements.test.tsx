/**
 * claude-6c2b · 通讯器 · 公告（玩家端方案 7.1 / 11 节，GET /announcements）：
 * - 类型用契约（AnnouncementFeed / AnnouncementItem）；路由还没关联 response_model，所以运行时逐条校验保留——
 *   缺字段、类型不对的条目丢掉，外层不符合契约（没有数组、没有 as_of）给可重试的错误；不认识的级别收成 info；
 * - 入口：通讯器标题栏下面一条细条（顶上那一排 320 宽已满，不加第五个分段）。有未读：最新一条未读的标题、按级别着色、
 *   点它去 /announcements；全都读过：同一位置收成安静的一行，仍能点进去；没有公告 / 读取中 / 出错 / 读不到（not_installed）：一行都不占；
 * - 已读按账号分开（localStorage 键带用户编号；演示或拿不到时是 "fixture"），每个账号按 slug + revision 记；
 *   revision 变了重新算未读；两个账号的已读互不影响；localStorage 抛错时不崩、当作未读；
 * - 公告页：按生效时间倒序；正文按原文排；配图只用服务端给的站内地址并带 alt；站内链接用 Link，只有 http(s) 做外链
 *   （新窗口、rel="noopener noreferrer"、写明“外部链接”），其它一律不做成链接；空 / 出错可重试 / not_installed 温和说明“暂时不可用”；
 *   打开时把当前所有公告记为已读，这次之前没读过的标“新”；
 * - 接线：/announcements 是全屏页（WorldGate 守、无底栏），左上角回 /communicator；演示数据明确标“演示”；
 *   live 服务请求 {apiBase}/announcements 并过解析。
 * - 通讯器输入区的类名是 .ps-comm-composer：接待页也有全局 .ps-composer，同名会互相覆盖（发送按钮掉到下一行、深色下一块白）。
 * 页面上的“级别”只写“公告 / 通知 / 维护”，后端原始代码不出现。
 */
import { readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, MemoryRouter, Route, RouterProvider, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { HomeSnapshot, HouseholdBrief, MessageThread, SessionState } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import communicatorModule from "@/features/communicator/module";
import { AnnouncementsPage } from "@/features/communicator/AnnouncementsPage";
import {
  announcementDay,
  announcementImageSrc,
  announcementLink,
  announcementsKey,
  FIXTURE_READ_ACCOUNT,
  isUnread,
  markAnnouncementsRead,
  parseAnnouncement,
  parseAnnouncementFeed,
  parseReadState,
  pickStripAnnouncement,
  READ_STORAGE_PREFIX,
  readAccountOf,
  readRawReadState,
  readStorageKey,
  severityOf,
  sortAnnouncements,
  type Announcement,
  type AnnouncementFeed,
  type AnnouncementSource,
} from "@/features/communicator/announcements";

// 源码文本一律用 fs 直接读。别用 `xxx.css?raw`：Vitest 默认不处理样式，`.css?raw` 读回来是空串，
// “不再定义某个类”这种否定断言会在空串上白白通过（实测踩过）。所以每条否定断言旁边都配一条肯定断言。
const COMMUNICATOR_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "..", "src", "features", "communicator");
const readCommunicatorSource = (file: string) => readFileSync(resolve(COMMUNICATOR_DIR, file), "utf8");

// 同一个文件里要切 fixture / live：env 用 getter 读一个可改的开关（WorldGate、家庭上下文与公告页都在渲染时才读 env.dataMode）。
const mode = vi.hoisted(() => ({ dataMode: "live" as "fixture" | "live" }));
vi.mock("@/shared/config/env", () => ({
  env: {
    get dataMode() {
      return mode.dataMode;
    },
    isDev: false,
    apiBase: "/api/v1/web",
  },
}));

beforeEach(() => {
  mode.dataMode = "live";
  localStorage.clear();
  sessionStorage.clear();
  vi.stubGlobal("scrollTo", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
});

/* ---------------- 测试数据 ---------------- */

const PET_ID = "pet-mine";
const PET_NAME = "栗子";
const VIEWER = "owner-1";
const AS_OF = "2026-09-24T00:00:00+00:00";

const item = (over: Partial<Announcement> & Pick<Announcement, "item_id" | "slug">): Announcement => ({
  revision: 1,
  title: `标题-${over.slug}`,
  body: "正文",
  severity: "info",
  link: null,
  image_asset_id: null,
  image_url: null,
  effective_at: "2026-09-20T12:00:00Z",
  expires_at: null,
  ...over,
});

const feedOf = (announcements: Announcement[], source: AnnouncementSource = "live"): AnnouncementFeed => ({ announcements, as_of: AS_OF, source });

/** 接口原样的一条（后端 live_announcements 的投影，全部字段）。 */
const rawItem = (over: Record<string, unknown> = {}): Record<string, unknown> => ({
  item_id: "CT-GOOD00000001",
  slug: "autumn-notice",
  revision: 3,
  title: "秋天的通知",
  body: "第一行\n第二行",
  severity: "notice",
  link: "/memories",
  image_asset_id: "AS-0123456789ABCDEF",
  image_url: "/api/v1/web/assets/AS-0123456789ABCDEF",
  effective_at: "2026-09-21T08:00:00+00:00",
  expires_at: null,
  ...over,
});

function household(): HouseholdBrief {
  return {
    household_id: "house-1",
    name: "海边的家",
    home_id: "home-1",
    role: "admin",
    home_activated: true,
    member_count: 2,
    pets: [{ pet_id: PET_ID, name: PET_NAME, species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true }],
  };
}

function home(): HomeSnapshot {
  const base = fixtureHomeSnapshot();
  return { ...base, data_origin: "live", pet: { ...base.pet, pet_id: PET_ID, name: PET_NAME, photo_url: null } };
}

const emptyThread = (): MessageThread => ({ pet_id: PET_ID, items: [], next_cursor: null, data_origin: "live" });

/** 某个账号的本机已读记录：直接写成存储格式（模拟以前读过）。 */
function rememberRead(entries: Array<[string, number]>, account: string = VIEWER) {
  localStorage.setItem(readStorageKey(account), JSON.stringify({ v: 1, read: entries }));
}

/** 本机现有的全部公告已读键。 */
function readKeysInStorage(): string[] {
  const keys: string[] = [];
  for (let index = 0; index < localStorage.length; index += 1) {
    const key = localStorage.key(index);
    if (key?.startsWith(READ_STORAGE_PREFIX)) keys.push(key);
  }
  return keys.sort();
}

/* ---------------- 渲染 ---------------- */

/** 只放页面该用的服务；读到没给的服务就算失败（证明页面没偷偷请求别的）。 */
function strictServices(services: Record<string, unknown>): ServiceMap {
  return new Proxy(services as unknown as ServiceMap, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof ServiceMap];
      throw new Error(`unexpected service ${prop}`);
    },
  });
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
}

const communicatorRoute = communicatorModule.routes?.find((route) => route.path === "communicator")?.element;

/** live：经通讯器模块自己注册的路由元素渲染，外面套与应用相同的家庭上下文（userId 就是登录的人）。 */
function renderCommunicator(feed: () => Promise<AnnouncementFeed>, entry = "/communicator", userId = VIEWER) {
  const announcements = vi.fn(feed);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider
        services={strictServices({
          households: { list: async () => [household()] },
          world: { home: async () => home() },
          communicator: { thread: async () => emptyThread(), send: vi.fn(), announcements },
          social: { friends: async () => [] },
          transport: { guides: async () => [] },
          economy: { collection: async () => [] },
        })}
      >
        <MemoryRouter initialEntries={[entry]}>
          <HouseholdProvider userId={userId}>
            <Routes>
              <Route path="/communicator" element={communicatorRoute} />
              <Route path="*" element={null} />
            </Routes>
            <LocationProbe />
          </HouseholdProvider>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
  const settled = (status: "success" | "error" | "pending") =>
    waitFor(() => expect(client.getQueryState(announcementsKey(userId))?.status).toBe(status));
  return { announcements, client, settled };
}

/** 通讯器页已经画出来（标题栏里有宠物名）。 */
const communicatorReady = () => screen.findByText(`和 ${PET_NAME} 的通讯`);
const strip = () => document.querySelector<HTMLAnchorElement>(".ps-announce-strip");

/**
 * 公告页（直接渲染页面组件；接线与守卫在最后一组经真实路由表测）。
 * 给了 userId 就套上 live 的家庭上下文（已读记在这个账号下）；不给就没有家庭上下文（拿不到用户编号，记在 "fixture" 下）。
 */
function renderPage(feed: () => Promise<AnnouncementFeed>, services?: ServiceMap, userId?: string) {
  const announcements = vi.fn(feed);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const routes = (
    <Routes>
      <Route path="/announcements" element={<AnnouncementsPage />} />
      <Route path="*" element={null} />
    </Routes>
  );
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services ?? strictServices({ communicator: { thread: vi.fn(), send: vi.fn(), announcements }, households: { list: async () => [household()] } })}>
        <MemoryRouter initialEntries={["/announcements"]}>
          {userId ? <HouseholdProvider userId={userId}>{routes}</HouseholdProvider> : routes}
          <LocationProbe />
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { announcements, client };
}

const list = () => screen.findByRole("list", { name: "全部公告" });
const articles = (root: HTMLElement) => within(root).getAllByRole("article");
const articleOf = (root: HTMLElement, title: string) => {
  const found = articles(root).find((a) => a.querySelector("h2")?.textContent === title);
  if (!found) throw new Error(`找不到公告「${title}」`);
  return found;
};

/** 真实路由表 + 演示服务（fixture）。 */
function renderFixtureApp(path: string) {
  mode.dataMode = "fixture";
  const modules = loadFeatureModules();
  const services = buildServices(modules, { mode: "fixture", api: createApiClient("/api/v1/web") });
  const router = createMemoryRouter(buildRoutes(modules), { initialEntries: [path] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { router, container: view.container };
}

/** 假的 fetch：记下请求，回一个 JSON。 */
function fakeFetch(payload: unknown) {
  const calls: Array<{ url: string; init: RequestInit | undefined }> = [];
  const impl: typeof fetch = async (input, init) => {
    calls.push({ url: String(input), init });
    return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  return { impl, calls };
}

/** 把 window.localStorage 整个换成“一碰就抛错”（某些浏览器设置下连取它都会抛），用完复原。 */
function breakLocalStorage(): () => void {
  const own = Object.getOwnPropertyDescriptor(window, "localStorage");
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    get() {
      throw new DOMException("storage is blocked", "SecurityError");
    },
  });
  return () => {
    if (own) Object.defineProperty(window, "localStorage", own);
    else delete (window as unknown as Record<string, unknown>).localStorage;
  };
}

/** 去掉注释的样式文本里某个选择器第一条规则的正文。 */
const stripComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, "");
const ruleIn = (css: string, selector: string) =>
  new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\{([^}]*)\\}`).exec(css)?.[1] ?? "";

/* ---------------- 解析（纯函数） ---------------- */

describe("解析：逐条校验成契约类型，坏条目丢掉", () => {
  it("缺字段、类型不对、空白标题、读不出的时间、重复编号的条目丢掉；好的原样保留，可空字段（含生效时间）缺省按 null", () => {
    const minimal = { item_id: "CT-MINIMAL0001", slug: "minimal", revision: 1, title: "只有必需字段", body: "", severity: "info" };
    const payload = {
      as_of: AS_OF,
      source: "live",
      announcements: [
        rawItem(),
        minimal,
        rawItem({ item_id: "CT-DUP", slug: undefined }),
        rawItem({ item_id: "CT-DUP2", slug: "" }),
        rawItem({ item_id: "CT-R1", revision: "3" }),
        rawItem({ item_id: "CT-R2", revision: 0 }),
        rawItem({ item_id: "CT-R3", revision: 1.5 }),
        rawItem({ item_id: "CT-T1", title: 42 }),
        rawItem({ item_id: "CT-T2", title: "   " }),
        rawItem({ item_id: "CT-B1", body: null }),
        rawItem({ item_id: "CT-S1", severity: undefined }),
        rawItem({ item_id: "CT-S2", severity: 2 }),
        rawItem({ item_id: "CT-E1", effective_at: "不是时间" }),
        rawItem({ item_id: "CT-E2", effective_at: 1790000000 }),
        rawItem({ item_id: "CT-L1", link: 42 }),
        rawItem({ item_id: "CT-I1", image_url: { href: "/x" } }),
        rawItem({ item_id: "CT-I2", image_asset_id: 7 }),
        rawItem({ item_id: "CT-X1", expires_at: false }),
        rawItem({ item_id: undefined }),
        rawItem({ slug: "same-id-again" }), // 与第一条同一个 item_id：只留第一条
        null,
        "公告",
        [rawItem({ item_id: "CT-IN-ARRAY" })],
      ],
    };
    const feed = parseAnnouncementFeed(payload);
    expect(feed.source).toBe("live");
    expect(feed.as_of).toBe(AS_OF);
    expect(feed.announcements).toEqual([
      {
        item_id: "CT-GOOD00000001",
        slug: "autumn-notice",
        revision: 3,
        title: "秋天的通知",
        body: "第一行\n第二行",
        severity: "notice",
        link: "/memories",
        image_asset_id: "AS-0123456789ABCDEF",
        image_url: "/api/v1/web/assets/AS-0123456789ABCDEF",
        effective_at: "2026-09-21T08:00:00+00:00",
        expires_at: null,
      },
      { ...minimal, link: null, image_asset_id: null, image_url: null, effective_at: null, expires_at: null },
    ]);
  });

  it("不认识的级别不丢条目，收成契约里的 info（显示为“公告”）；单条解析对非对象直接给 null", () => {
    expect(parseAnnouncement(rawItem({ severity: "urgent" }))?.severity).toBe("info");
    expect(parseAnnouncement(rawItem({ severity: " maintenance " }))?.severity).toBe("maintenance");
    for (const bad of [null, undefined, 1, "x", [], true]) expect(parseAnnouncement(bad)).toBeNull();
  });

  it("外层不符合契约（不是对象、announcements 不是数组、没有 as_of）抛可重试的错误，不假装“没有公告”；source 只认 not_installed，其余按 live", () => {
    for (const bad of [null, undefined, "x", [], {}, { announcements: "x", as_of: AS_OF }, { announcements: null, as_of: AS_OF }, { announcements: [] }, { announcements: [], as_of: 5 }, { announcements: [], as_of: " " }]) {
      let caught: unknown;
      try {
        parseAnnouncementFeed(bad);
      } catch (error) {
        caught = error;
      }
      expect(caught, JSON.stringify(bad)).toBeInstanceOf(ApiError);
      expect((caught as ApiError).retryable).toBe(true);
    }
    expect(parseAnnouncementFeed({ announcements: [], source: "not_installed", as_of: AS_OF })).toEqual({ announcements: [], as_of: AS_OF, source: "not_installed" });
    expect(parseAnnouncementFeed({ announcements: [], as_of: AS_OF }).source).toBe("live");
    expect(parseAnnouncementFeed({ announcements: [], as_of: AS_OF, source: "fixture" }).source).toBe("live"); // 契约的 source 只有 live / not_installed
  });

  it("按生效时间倒序，没有生效时间的排最后，时间相同保持接口顺序；不改动传入的数组", () => {
    const input = [
      item({ item_id: "0", slug: "no-time", effective_at: null }),
      item({ item_id: "1", slug: "old", effective_at: "2026-09-01T00:00:00Z" }),
      item({ item_id: "2", slug: "new", effective_at: "2026-09-23T00:00:00+08:00" }),
      item({ item_id: "3", slug: "tie-a", effective_at: "2026-09-10T00:00:00Z" }),
      item({ item_id: "4", slug: "tie-b", effective_at: "2026-09-10T08:00:00+08:00" }),
      item({ item_id: "5", slug: "no-time-2", effective_at: null }),
    ];
    const copy = [...input];
    expect(sortAnnouncements(input).map((a) => a.slug)).toEqual(["new", "tie-a", "tie-b", "old", "no-time", "no-time-2"]);
    expect(input).toEqual(copy);
  });

  it("级别：info / notice / maintenance → 公告 / 通知 / 维护；不认识的按“公告”，不回显原始值", () => {
    expect(severityOf("info")).toMatchObject({ tone: "info", label: "公告" });
    expect(severityOf("notice")).toMatchObject({ tone: "notice", label: "通知" });
    expect(severityOf(" maintenance ")).toMatchObject({ tone: "maintenance", label: "维护" });
    for (const raw of ["urgent", "", "constructor", "__proto__", null, undefined]) {
      expect(severityOf(raw)).toMatchObject({ tone: "info", label: "公告" });
    }
  });

  it("生效日期：今年写“9月20日”，往年带年份；没有或读不出来不写", () => {
    expect(announcementDay("2026-09-20T12:00:00Z", new Date("2026-10-01T12:00:00Z"))).toBe("9月20日");
    expect(announcementDay("2026-09-20T12:00:00Z", new Date("2027-01-05T12:00:00Z"))).toBe("2026年9月20日");
    expect(announcementDay("不是时间")).toBe("");
    expect(announcementDay(null)).toBe("");
  });
});

describe("链接与配图：只有站内路径和 http(s) 做成链接，配图只用站内地址", () => {
  it("站内路径 → 站内链接（规整后的路径、查询、片段）", () => {
    expect(announcementLink("/memories")).toEqual({ kind: "internal", to: "/memories" });
    expect(announcementLink("/life?tab=jobs#top")).toEqual({ kind: "internal", to: "/life?tab=jobs#top" });
    expect(announcementLink("/a/../garden")).toEqual({ kind: "internal", to: "/garden" });
  });

  it("http / https → 外链（带出对方站点）；带账号密码的网址不做", () => {
    expect(announcementLink("https://example.com/news?id=1")).toEqual({ kind: "external", href: "https://example.com/news?id=1", host: "example.com" });
    expect(announcementLink("HTTP://Example.org")).toEqual({ kind: "external", href: "http://example.org/", host: "example.org" });
    expect(announcementLink("https://petsoul.games@evil.example/")).toEqual({ kind: "none" });
    expect(announcementLink("https://user:pw@example.com/")).toEqual({ kind: "none" });
  });

  it("其它一律不做成链接：别的协议、//别的站、反斜杠、空白与控制字符、相对路径、空值", () => {
    const refused = [
      "javascript:alert(1)",
      "JavaScript:alert(1)",
      "data:text/html,<b>hi</b>",
      "mailto:someone@example.com",
      "tel:10086",
      "ftp://example.com/file",
      "blob:https://example.com/1",
      "//evil.example/x",
      "/\\evil.example",
      "/\t/evil.example",
      "/\n/evil.example",
      " /memories",
      "https://exa\tmple.com",
      "https://example.com/a b",
      "memories",
      "./memories",
      "",
      null,
      undefined,
    ];
    for (const raw of refused) expect(announcementLink(raw), String(raw)).toEqual({ kind: "none" });
  });

  it("配图：服务端的站内地址照用；外站（含 https）、data:、javascript:、//别的站、带空白的都不加载", () => {
    expect(announcementImageSrc("/api/v1/web/assets/AS-0123456789ABCDEF")).toBe("/api/v1/web/assets/AS-0123456789ABCDEF");
    for (const raw of ["https://cdn.example.com/a.png", "http://example.com/a.png", "data:image/png;base64,AAAA", "javascript:alert(1)", "//evil.example/a.png", "/\\evil.example/a.png", "/a b.png", "a.png", "", null]) {
      expect(announcementImageSrc(raw), String(raw)).toBeNull();
    }
  });
});

describe("已读：按账号分开，每个账号按 slug + revision 记在本机", () => {
  it("记在哪个账号下：有用户编号用用户编号，演示或拿不到时是固定的 \"fixture\"；键带账号", () => {
    expect(readAccountOf("owner-1")).toBe("owner-1");
    for (const none of [null, undefined, ""]) expect(readAccountOf(none)).toBe(FIXTURE_READ_ACCOUNT);
    expect(FIXTURE_READ_ACCOUNT).toBe("fixture");
    expect(readStorageKey("owner-1")).toBe("petsoul:announcements:read:v1:owner-1");
    expect(readStorageKey(FIXTURE_READ_ACCOUNT)).toBe("petsoul:announcements:read:v1:fixture");
    expect(readStorageKey("a:b/c")).toBe("petsoul:announcements:read:v1:a%3Ab%2Fc");
  });

  it("记过这一版才算读过；revision 变了重新算未读；别的 slug 同一个版本号不算读过", () => {
    const v1 = item({ item_id: "1", slug: "news", revision: 1 });
    const other = item({ item_id: "2", slug: "other", revision: 1 });
    expect(isUnread(v1, parseReadState(readRawReadState(VIEWER)))).toBe(true);
    expect(markAnnouncementsRead(VIEWER, [v1])).toBe(true);
    const read = parseReadState(readRawReadState(VIEWER));
    expect(isUnread(v1, read)).toBe(false);
    expect(isUnread({ ...v1, revision: 2 }, read)).toBe(true);
    expect(isUnread(other, read)).toBe(true);
    // 读了新版本：记录按 slug 覆盖成新版本号，旧版本不再算读过。
    markAnnouncementsRead(VIEWER, [{ ...v1, revision: 2 }]);
    const after = parseReadState(readRawReadState(VIEWER));
    expect(after.get("news")).toBe(2);
    expect(isUnread(v1, after)).toBe(true);
    // 没有变化时不重写。
    expect(markAnnouncementsRead(VIEWER, [{ ...v1, revision: 2 }])).toBe(false);
  });

  it("两个账号各自的已读互不影响：A 记过的，B 仍是未读；B 再记也不改 A 的记录", () => {
    const news = item({ item_id: "1", slug: "news", revision: 3 });
    markAnnouncementsRead("owner-a", [news]);
    const aRecord = readRawReadState("owner-a");
    expect(isUnread(news, parseReadState(aRecord))).toBe(false);
    expect(isUnread(news, parseReadState(readRawReadState("owner-b")))).toBe(true);
    expect(isUnread(news, parseReadState(readRawReadState(FIXTURE_READ_ACCOUNT)))).toBe(true);
    markAnnouncementsRead("owner-b", [news, item({ item_id: "2", slug: "b-only", revision: 1 })]);
    expect(readRawReadState("owner-a")).toBe(aRecord);
    expect([...parseReadState(readRawReadState("owner-b")).keys()]).toEqual(["news", "b-only"]);
    expect(readKeysInStorage()).toEqual([readStorageKey("owner-a"), readStorageKey("owner-b")]);
  });

  it("本机记录坏了（不是 JSON、版本不对、条目不对）当作没读过；原型上的名字查不到东西", () => {
    for (const raw of ["不是 JSON", "null", "[]", '{"v":2,"read":[["news",1]]}', '{"v":1,"read":"news"}']) {
      expect(parseReadState(raw).size, raw).toBe(0);
    }
    const mixed = parseReadState(JSON.stringify({ v: 1, read: [["news", 1], ["bad", "1"], [1, 1], ["", 1], ["x"], ["frac", 1.5], "junk"] }));
    expect([...mixed.entries()]).toEqual([["news", 1]]);
    expect(isUnread(item({ item_id: "c", slug: "constructor", revision: 1 }), parseReadState(null))).toBe(true);
  });

  it("细条挑哪条：有未读放最新的未读（不是接口第一条）；全读过放最新的一条并标成已读；没有公告返回 null", () => {
    const a = item({ item_id: "a", slug: "a", effective_at: "2026-09-20T00:00:00Z" });
    const b = item({ item_id: "b", slug: "b", effective_at: "2026-09-23T00:00:00Z" });
    const c = item({ item_id: "c", slug: "c", effective_at: "2026-09-22T00:00:00Z" });
    const readB = new Map([["b", 1]]);
    expect(pickStripAnnouncement([a, b, c], readB)).toEqual({ announcement: c, unread: true });
    const allRead = new Map([["a", 1], ["b", 1], ["c", 1]]);
    expect(pickStripAnnouncement([a, b, c], allRead)).toEqual({ announcement: b, unread: false });
    expect(pickStripAnnouncement([], allRead)).toBeNull();
  });
});

/* ---------------- 通讯器顶上的细条（live） ---------------- */

describe("通讯器 · 公告细条", () => {
  it("有未读：放最新一条未读的标题，按级别着色，点它去 /announcements；不占顶上那一排（仍是三个分区 + 朋友圈）", async () => {
    rememberRead([["newest-read", 1]]);
    renderCommunicator(async () =>
      feedOf([
        item({ item_id: "1", slug: "older-unread", title: "旧的一条", effective_at: "2026-09-18T00:00:00Z" }),
        item({ item_id: "2", slug: "newest-read", title: "最新但读过", effective_at: "2026-09-23T00:00:00Z" }),
        item({ item_id: "3", slug: "maint", title: "周六凌晨维护两小时", severity: "maintenance", effective_at: "2026-09-21T00:00:00Z" }),
      ]),
    );
    const link = await screen.findByRole("link", { name: "有新维护公告：周六凌晨维护两小时" });
    expect(link).toBe(strip());
    expect(link.getAttribute("href")).toBe("/announcements");
    expect(link.getAttribute("data-unread")).toBe("true");
    expect(link.classList.contains("ps-announce--maintenance")).toBe(true);
    expect(link.querySelector(".ps-announce-tag")?.textContent).toBe("维护");
    expect(link.querySelector(".ps-announce-strip__title")?.textContent).toBe("周六凌晨维护两小时");
    expect(link.querySelector(".ps-announce-strip__dot")).toBeTruthy();
    expect(document.body.textContent).not.toContain("maintenance");

    const group = screen.getByRole("group", { name: "通讯器分区" });
    expect(within(group).getAllByRole("button").map((b) => b.textContent)).toEqual(["我和 TA", "家庭来信", "TA 的朋友"]);
    expect(within(group).getAllByRole("link").map((a) => a.textContent)).toEqual(["朋友圈"]);
    expect(group.contains(link)).toBe(false);
    expect(link.compareDocumentPosition(group) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy(); // 细条在分区那一排上面

    fireEvent.click(link);
    expect(screen.getByTestId("location").textContent).toBe("/announcements");
  });

  it("按级别着色：通知、一般各用各的颜色", async () => {
    renderCommunicator(async () => feedOf([item({ item_id: "1", slug: "n", title: "新功能来了", severity: "notice" })]));
    const notice = await screen.findByRole("link", { name: "有新通知：新功能来了" });
    expect(notice.classList.contains("ps-announce--notice")).toBe(true);
    expect(notice.querySelector(".ps-announce-tag")?.textContent).toBe("通知");
    cleanup();

    renderCommunicator(async () => feedOf([item({ item_id: "1", slug: "i", title: "一般的公告", severity: "info" })]));
    const info = await screen.findByRole("link", { name: "有新公告：一般的公告" });
    expect(info.classList.contains("ps-announce--info")).toBe(true);
    expect(info.querySelector(".ps-announce-tag")?.textContent).toBe("公告");
  });

  it("没有公告：一行都不占；读不到（not_installed）、读取失败、还在读取时同样不占", async () => {
    const cases: Array<[string, () => Promise<AnnouncementFeed>, "success" | "error" | "pending"]> = [
      ["空列表", async () => feedOf([]), "success"],
      ["not_installed", async () => feedOf([], "not_installed"), "success"],
      ["出错", async () => { throw new ApiError({ kind: "network", code: "NETWORK_ERROR", message: "网络连接失败", retryable: true }); }, "error"],
      ["读取中", () => new Promise<AnnouncementFeed>(() => undefined), "pending"],
    ];
    for (const [label, feed, status] of cases) {
      const { settled, announcements } = renderCommunicator(feed);
      await communicatorReady();
      await waitFor(() => expect(announcements, label).toHaveBeenCalled());
      await settled(status);
      expect(strip(), label).toBeNull();
      expect(document.querySelector(".ps-announce-tag"), label).toBeNull();
      expect(screen.queryByRole("link", { name: /公告|通知|维护/ }), label).toBeNull();
      expect(screen.queryByRole("alert"), label).toBeNull(); // 出错只在公告页说，不在通讯器里打扰
      cleanup();
    }
  });

  it("全都读过：同一位置收成安静的一行（不着色、没有圆点），仍链到公告页；后台发了新版本（revision 变了）又变回未读", async () => {
    rememberRead([["news", 1]]);
    renderCommunicator(async () => feedOf([item({ item_id: "1", slug: "news", revision: 1, title: "读过的公告", severity: "maintenance" })]));
    const quiet = await screen.findByRole("link", { name: "公告：读过的公告" });
    expect(quiet.getAttribute("href")).toBe("/announcements");
    expect(quiet.getAttribute("data-unread")).toBe("false");
    expect(quiet.classList.contains("ps-announce-strip--read")).toBe(true);
    expect(quiet.classList.contains("ps-announce--maintenance")).toBe(false);
    expect(quiet.querySelector(".ps-announce-strip__dot")).toBeNull();
    expect(quiet.querySelector(".ps-announce-tag")?.textContent).toBe("公告");
    cleanup();

    renderCommunicator(async () => feedOf([item({ item_id: "1", slug: "news", revision: 2, title: "读过的公告（更新）", severity: "maintenance" })]));
    const again = await screen.findByRole("link", { name: "有新维护公告：读过的公告（更新）" });
    expect(again.getAttribute("data-unread")).toBe("true");
  });

  it("两个账号各自的已读互不影响：A 读过、B 仍是未读；B 打开公告页只记 B 的，A 的记录一个字不变", async () => {
    const news = item({ item_id: "1", slug: "news", revision: 2, title: "两家都会看到的公告" });
    markAnnouncementsRead("owner-a", [news]);
    const aRecord = readRawReadState("owner-a");

    renderCommunicator(async () => feedOf([news]), "/communicator", "owner-a");
    expect(await screen.findByRole("link", { name: "公告：两家都会看到的公告" })).toBeTruthy();
    cleanup();

    renderCommunicator(async () => feedOf([news]), "/communicator", "owner-b");
    expect(await screen.findByRole("link", { name: "有新公告：两家都会看到的公告" })).toBeTruthy();
    cleanup();

    renderPage(async () => feedOf([news]), undefined, "owner-b");
    const root = await list();
    await waitFor(() => expect(parseReadState(readRawReadState("owner-b")).get("news")).toBe(2));
    expect(articleOf(root, "两家都会看到的公告").querySelector(".ps-announcement__new")?.textContent).toBe("新"); // 对 B 来说是新的
    expect(readRawReadState("owner-a")).toBe(aRecord);
    expect(readRawReadState(FIXTURE_READ_ACCOUNT)).toBeNull();
    cleanup();

    renderCommunicator(async () => feedOf([news]), "/communicator", "owner-b");
    expect(await screen.findByRole("link", { name: "公告：两家都会看到的公告" })).toBeTruthy();
    expect(readKeysInStorage()).toEqual([readStorageKey("owner-a"), readStorageKey("owner-b")]);
  });

  it("本页写入已读、别的标签页写入已读：细条都立刻跟着变，不用刷新；别的账号的写入不影响", async () => {
    const news = item({ item_id: "1", slug: "news", revision: 4, title: "一条新公告" });
    renderCommunicator(async () => feedOf([news]));
    expect(await screen.findByRole("link", { name: "有新公告：一条新公告" })).toBeTruthy();
    act(() => {
      markAnnouncementsRead("someone-else", [news]);
    });
    expect(screen.getByRole("link", { name: "有新公告：一条新公告" })).toBeTruthy();
    act(() => {
      markAnnouncementsRead(VIEWER, [news]);
    });
    expect(await screen.findByRole("link", { name: "公告：一条新公告" })).toBeTruthy();

    // 别的标签页：直接改存储，再发浏览器自带的 storage 事件。
    act(() => {
      rememberRead([["news", 3]]);
      window.dispatchEvent(new StorageEvent("storage", { key: readStorageKey(VIEWER) }));
    });
    expect(await screen.findByRole("link", { name: "有新公告：一条新公告" })).toBeTruthy();
  });

  it("localStorage 读写抛错：不崩，细条照常显示（当作未读）", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
    const news = item({ item_id: "1", slug: "news", title: "存储坏了也照常" });
    renderCommunicator(async () => feedOf([news]));
    expect(await screen.findByRole("link", { name: "有新公告：存储坏了也照常" })).toBeTruthy();
    expect(markAnnouncementsRead(VIEWER, [news])).toBe(false);
    expect(readRawReadState(VIEWER)).toBeNull();
    expect(screen.getByRole("link", { name: "有新公告：存储坏了也照常" })).toBeTruthy();
  });

  it("连 window.localStorage 本身都取不到：不崩，细条当作未读", async () => {
    const restore = breakLocalStorage();
    try {
      expect(() => window.localStorage).toThrow();
      renderCommunicator(async () => feedOf([item({ item_id: "1", slug: "news", title: "拿不到存储" })]));
      expect(await screen.findByRole("link", { name: "有新公告：拿不到存储" })).toBeTruthy();
    } finally {
      restore();
    }
    expect(() => window.localStorage.getItem("x")).not.toThrow();
  });
});

/* ---------------- 公告页 ---------------- */

describe("公告页 /announcements", () => {
  it("列出全部公告，按生效时间倒序：级别、生效日期、标题、正文按原文排、配图用服务端地址并带 alt", async () => {
    const body = "第一行\n\n第三行  两个空格\n<b>不是标签</b>";
    renderPage(async () =>
      feedOf([
        item({ item_id: "1", slug: "older", title: "早一点的公告", effective_at: "2026-09-10T12:00:00Z" }),
        item({
          item_id: "2",
          slug: "newest",
          title: "最新的维护",
          body,
          severity: "maintenance",
          image_url: "/api/v1/web/assets/AS-0123456789ABCDEF",
          image_asset_id: "AS-0123456789ABCDEF",
          effective_at: "2026-09-20T12:00:00Z",
        }),
        item({ item_id: "3", slug: "middle", title: "中间的通知", severity: "notice", effective_at: "2026-09-15T12:00:00Z", image_url: "https://cdn.example.com/x.png" }),
        item({ item_id: "4", slug: "timeless", title: "没有生效时间的公告", effective_at: null }),
      ]),
    );
    const root = await list();
    expect(articles(root).map((a) => a.querySelector("h2")?.textContent)).toEqual(["最新的维护", "中间的通知", "早一点的公告", "没有生效时间的公告"]);

    const newest = articleOf(root, "最新的维护");
    expect(within(newest).getByRole("heading", { level: 2, name: "最新的维护" })).toBeTruthy();
    expect(newest.getAttribute("aria-labelledby")).toBe(newest.querySelector("h2")?.id);
    expect(newest.querySelector(".ps-announce-tag")?.textContent).toBe("维护");
    expect(newest.classList.contains("ps-announce--maintenance")).toBe(true);
    const time = newest.querySelector("time");
    expect(time?.getAttribute("datetime")).toBe("2026-09-20T12:00:00Z");
    expect(time?.textContent).toMatch(/9月20日$/);
    expect(newest.querySelector(".ps-announcement__body")?.textContent).toBe(body); // 原文，不折叠空白、不解析标签
    expect(newest.querySelector("b")).toBeNull();
    const img = within(newest).getByRole("img");
    expect(img.getAttribute("src")).toBe("/api/v1/web/assets/AS-0123456789ABCDEF");
    expect(img.getAttribute("alt")).toBe("公告「最新的维护」的配图");

    // 外站配图不加载；没有配图的不留空框；没有生效时间的不写日期。
    expect(articleOf(root, "中间的通知").querySelector("img")).toBeNull();
    expect(articleOf(root, "中间的通知").querySelector("figure")).toBeNull();
    expect(articleOf(root, "早一点的公告").querySelector("figure")).toBeNull();
    expect(articleOf(root, "中间的通知").querySelector(".ps-announce-tag")?.textContent).toBe("通知");
    expect(articleOf(root, "早一点的公告").querySelector(".ps-announce-tag")?.textContent).toBe("公告");
    expect(articleOf(root, "没有生效时间的公告").querySelector("time")).toBeNull();
  });

  it("配图读不出来（素材下架后 404）：这一块不显示，公告照常", async () => {
    renderPage(async () => feedOf([item({ item_id: "1", slug: "pic", title: "带图的公告", image_url: "/api/v1/web/assets/AS-GONE000000000000" })]));
    const root = await list();
    const img = within(root).getByRole("img", { name: "公告「带图的公告」的配图" });
    fireEvent.error(img);
    await waitFor(() => expect(root.querySelector("figure")).toBeNull());
    expect(articleOf(root, "带图的公告")).toBeTruthy();
  });

  it("打开公告页：当前所有公告记为已读（拿不到用户编号时记在 \"fixture\" 下）；这次打开前没读过的标“新”，读过的不标", async () => {
    rememberRead([["seen", 2], ["bumped", 1], ["gone", 9]], FIXTURE_READ_ACCOUNT);
    renderPage(async () =>
      feedOf([
        item({ item_id: "1", slug: "seen", revision: 2, title: "读过的" }),
        item({ item_id: "2", slug: "bumped", revision: 2, title: "出了新版本的" }),
        item({ item_id: "3", slug: "fresh", revision: 1, title: "没见过的" }),
      ]),
    );
    const root = await list();
    await waitFor(() => expect(articleOf(root, "没见过的").querySelector(".ps-announcement__new")?.textContent).toBe("新"));
    expect(articleOf(root, "出了新版本的").querySelector(".ps-announcement__new")?.textContent).toBe("新");
    expect(articleOf(root, "读过的").querySelector(".ps-announcement__new")).toBeNull();

    const read = parseReadState(readRawReadState(FIXTURE_READ_ACCOUNT));
    expect(read.get("seen")).toBe(2);
    expect(read.get("bumped")).toBe(2);
    expect(read.get("fresh")).toBe(1);
    expect(read.get("gone")).toBe(9); // 这次没出现的旧记录不乱删
    expect(readKeysInStorage()).toEqual([readStorageKey(FIXTURE_READ_ACCOUNT)]);
  });

  it("链接：站内 → 应用内跳转（不开新窗口）；http(s) → 新窗口 + rel + “外部链接”与站点名；其它协议不做成链接", async () => {
    const refused = ["javascript:alert(1)", "data:text/html,hi", "mailto:a@example.com", "//evil.example/x", "/\\evil.example", "https://petsoul.games@evil.example/"];
    renderPage(async () =>
      feedOf([
        item({ item_id: "in", slug: "in", title: "站内链接", link: "/memories?tab=cards", effective_at: "2026-09-23T00:00:00Z" }),
        item({ item_id: "out", slug: "out", title: "外部链接", link: "https://example.com/news?id=1", effective_at: "2026-09-22T00:00:00Z" }),
        ...refused.map((link, index) => item({ item_id: `bad-${index}`, slug: `bad-${index}`, title: `不做链接 ${index}`, link, effective_at: "2026-09-01T00:00:00Z" })),
      ]),
    );
    const root = await list();

    const external = within(articleOf(root, "外部链接")).getByRole("link");
    expect(external.getAttribute("href")).toBe("https://example.com/news?id=1");
    expect(external.getAttribute("target")).toBe("_blank");
    expect(external.getAttribute("rel")).toBe("noopener noreferrer");
    expect(external.textContent).toContain("外部链接");
    expect(external.textContent).toContain("example.com");
    expect(external.getAttribute("aria-label")).toBe("外部链接：example.com（在新窗口打开）");

    refused.forEach((raw, index) => {
      const article = articleOf(root, `不做链接 ${index}`);
      expect(article.querySelector("a"), raw).toBeNull();
      expect(article.textContent, raw).not.toContain(raw); // 不把原始地址当文字露出来
    });

    const internal = within(articleOf(root, "站内链接")).getByRole("link", { name: "查看详情" });
    expect(internal.getAttribute("href")).toBe("/memories?tab=cards");
    expect(internal.hasAttribute("target")).toBe(false);
    fireEvent.click(internal);
    expect(screen.getByTestId("location").textContent).toBe("/memories?tab=cards");
  });

  it("空：一句“暂时没有公告”，不是错误", async () => {
    renderPage(async () => feedOf([]));
    expect(await screen.findByText("暂时没有公告")).toBeTruthy();
    expect(screen.queryByRole("list", { name: "全部公告" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("读不到（not_installed）：温和说明“公告暂时不可用”，不是错误样式、不说成“没有公告”", async () => {
    renderPage(async () => feedOf([], "not_installed"));
    expect(await screen.findByText("公告暂时不可用")).toBeTruthy();
    expect(screen.queryByText("暂时没有公告")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(document.body.textContent).not.toContain("not_installed");
  });

  it("出错：给可重试的错误态，点“重试”再请求一次，成功后显示列表", async () => {
    let calls = 0;
    const { announcements } = renderPage(async () => {
      calls += 1;
      if (calls === 1) throw new ApiError({ kind: "http", status: 500, code: "INTERNAL_ERROR", message: "公告暂时读不出来", retryable: false });
      return feedOf([item({ item_id: "1", slug: "ok", title: "重试之后的公告" })]);
    });
    const alert = await screen.findByRole("alert");
    fireEvent.click(within(alert).getByRole("button", { name: "重试" }));
    const root = await list();
    expect(announcements).toHaveBeenCalledTimes(2);
    expect(articles(root)).toHaveLength(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("live 服务经解析：外层坏了 → 页面给可重试的错误；坏条目丢掉、好的照常显示", async () => {
    const broken = fakeFetch({ oops: true });
    renderPage(async () => feedOf([]), buildServices([communicatorModule], { mode: "live", api: createApiClient("/api/v1/web", broken.impl) }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("公告暂时读不出来");
    expect(within(alert).getByRole("button", { name: "重试" })).toBeTruthy();
    cleanup();

    const mixed = fakeFetch({ announcements: [rawItem(), rawItem({ item_id: "CT-BAD", revision: "x" }), 7], as_of: AS_OF, source: "live" });
    renderPage(async () => feedOf([]), buildServices([communicatorModule], { mode: "live", api: createApiClient("/api/v1/web", mixed.impl) }));
    const root = await list();
    expect(articles(root).map((a) => a.querySelector("h2")?.textContent)).toEqual(["秋天的通知"]);
  });

  it("localStorage 读写都抛错（连 window.localStorage 都取不到）：页面照常列出公告、不崩", async () => {
    const restore = breakLocalStorage();
    try {
      renderPage(async () => feedOf([item({ item_id: "1", slug: "a", title: "存储不可用时的公告" })]));
      const root = await list();
      expect(articles(root)).toHaveLength(1);
      await waitFor(() => expect(articleOf(root, "存储不可用时的公告").querySelector(".ps-announcement__new")).toBeTruthy()); // 读不到就当没读过
      expect(screen.queryByRole("alert")).toBeNull();
    } finally {
      restore();
    }
  });
});

/* ---------------- 接线：真实路由表、演示数据、live 请求 ---------------- */

describe("接线", () => {
  it("/announcements 是全屏页（无底栏）；左上角返回 /communicator；演示模式标“演示公告”，每条标题都带“（演示）”", async () => {
    const { router, container } = renderFixtureApp("/announcements");
    const root = await list();
    expect(articles(root).length).toBeGreaterThan(0);
    for (const article of articles(root)) expect(article.querySelector("h2")?.textContent).toMatch(/^（演示）/);
    expect(screen.getByText("演示公告")).toBeTruthy();
    expect(screen.getByText("公告", { selector: ".ps-topbar__title" })).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "主导航" })).toBeNull();
    expect(container.querySelector(".ps-shell--bare")).toBeTruthy();
    // 演示里的站内链接指向本站已有的页面；配图用本站已有的素材。
    for (const a of within(root).queryAllByRole("link")) expect(a.getAttribute("href")?.startsWith("/")).toBe(true);
    for (const img of within(root).queryAllByRole("img")) expect(img.getAttribute("src")?.startsWith("/")).toBe(true);

    const back = screen.getByRole("link", { name: "返回" });
    expect(back.getAttribute("href")).toBe("/communicator");
    fireEvent.click(back);
    await waitFor(() => expect(router.state.location.pathname).toBe("/communicator"));
  });

  it("通讯器（演示）：细条是最新一条演示公告 → 点进公告页 → 返回后细条变安静；演示模式的已读记在 \"fixture\" 下", async () => {
    const { router } = renderFixtureApp("/communicator");
    const unread = await screen.findByRole("link", { name: /^有新.*：（演示）/ });
    expect(unread.getAttribute("data-unread")).toBe("true");
    const title = unread.querySelector(".ps-announce-strip__title")?.textContent ?? "";
    fireEvent.click(unread);
    await waitFor(() => expect(router.state.location.pathname).toBe("/announcements"));
    const root = await list();
    expect(articles(root)[0].querySelector("h2")?.textContent).toBe(title); // 细条放的就是最新的那条
    await waitFor(() => expect(parseReadState(readRawReadState(FIXTURE_READ_ACCOUNT)).size).toBe(articles(root).length));
    expect(readKeysInStorage()).toEqual(["petsoul:announcements:read:v1:fixture"]);

    fireEvent.click(screen.getByRole("link", { name: "返回" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/communicator"));
    const quiet = await screen.findByRole("link", { name: `公告：${title}` });
    expect(quiet.getAttribute("data-unread")).toBe("false");
    expect(within(screen.getByRole("navigation", { name: "主导航" })).getByRole("link", { name: "通讯器" }).getAttribute("aria-current")).toBe("page");
  });

  it("live：/announcements 由 WorldGate 守——未登录去欢迎页、一条公告都不请求；登录且入住完成才显示，按登录的人分键、记已读", async () => {
    const element = communicatorModule.bareRoutes?.find((route) => route.path === "announcements")?.element;
    const renderGate = (session: SessionState) => {
      const announcements = vi.fn(async () => feedOf([item({ item_id: "1", slug: "gate", title: "登录后才看到" })]));
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={client}>
          <ServicesProvider
            services={strictServices({
              session: { current: async () => session },
              households: { list: async () => [household()] },
              communicator: { thread: vi.fn(), send: vi.fn(), announcements },
            })}
          >
            <MemoryRouter initialEntries={["/announcements"]}>
              <Routes>
                <Route path="/announcements" element={element} />
                <Route path="*" element={null} />
              </Routes>
              <LocationProbe />
            </MemoryRouter>
          </ServicesProvider>
        </QueryClientProvider>,
      );
      return { announcements, client };
    };

    const guest = renderGate({ authenticated: false, user: null, csrf_required: false, expires_at: null, onboarding: null });
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/welcome"));
    expect(guest.announcements).not.toHaveBeenCalled();
    cleanup();

    const member = renderGate({
      authenticated: true,
      user: { user_id: VIEWER, display_name: "主人", username: "owner", auth_method: "web_password" },
      csrf_required: true,
      expires_at: null,
      onboarding: { step: "active", pet_id: PET_ID, home_id: "home-1", reception_session_id: null, reception_skipped: true, home_activated_at: "2026-09-20T00:00:00Z", pet_origin: "own_pet" },
    });
    const root = await list();
    expect(articles(root).map((a) => a.querySelector("h2")?.textContent)).toEqual(["登录后才看到"]);
    expect(screen.getByTestId("location").textContent).toBe("/announcements");
    expect(member.client.getQueryState(announcementsKey(VIEWER))?.status).toBe("success");
    await waitFor(() => expect(parseReadState(readRawReadState(VIEWER)).get("gate")).toBe(1));
    expect(readKeysInStorage()).toEqual([readStorageKey(VIEWER)]);
  });

  it("live 服务：请求 GET {apiBase}/announcements（带 cookie），结果过解析", async () => {
    const payload = { announcements: [rawItem(), rawItem({ item_id: "CT-NO-TITLE", title: "" })], as_of: AS_OF, source: "live" };
    const fetcher = fakeFetch(payload);
    const services = buildServices([communicatorModule], { mode: "live", api: createApiClient("/api/v1/web", fetcher.impl) });
    const feed = await services.communicator.announcements();
    expect(fetcher.calls).toHaveLength(1);
    expect(fetcher.calls[0].url).toBe("/api/v1/web/announcements");
    expect(fetcher.calls[0].init?.method).toBe("GET");
    expect(fetcher.calls[0].init?.credentials).toBe("include");
    expect(feed.announcements.map((a) => a.slug)).toEqual(["autumn-notice"]);
    expect(feed.source).toBe("live");
  });
});

/* ---------------- 样式：只用主题变量 ---------------- */

describe("公告样式只用主题变量", () => {
  const css = stripComments(readCommunicatorSource("announcements.css"));

  it("去掉注释后没有写死的颜色（#十六进制、rgb()/hsl()、white/black）", () => {
    expect(css.match(/#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(|(?<![\w-])(?:white|black)(?![\w-])/g) ?? []).toEqual([]);
  });

  it("三个级别的颜色都来自令牌；正文按原文排（pre-wrap）；细条标题一行省略", () => {
    for (const [selector, token] of [[".ps-announce--info", "--c-sea"], [".ps-announce--notice", "--c-sun"], [".ps-announce--maintenance", "--c-coral"]] as const) {
      const body = ruleIn(css, selector);
      expect(body, selector).toMatch(new RegExp(`--ann-accent:\\s*var\\(${token}\\)`));
      expect(body, selector).toMatch(/--ann-soft:\s*var\(--c-/);
    }
    expect(ruleIn(css, ".ps-announcement__body")).toMatch(/white-space:\s*pre-wrap/);
    const title = ruleIn(css, ".ps-announce-strip__title");
    expect(title).toMatch(/white-space:\s*nowrap/);
    expect(title).toMatch(/text-overflow:\s*ellipsis/);
  });
});

/* ---------------- 通讯器输入区：类名不和接待页撞 ---------------- */

describe("通讯器输入区：.ps-comm-composer（接待页也有全局 .ps-composer，同名会互相覆盖）", () => {
  it("communicator.css 去掉注释后不再定义裸的 .ps-composer；输入区规则在 .ps-comm-composer 下，输入框与发送按钮排成一行（flex）", () => {
    const css = stripComments(readCommunicatorSource("communicator.css"));
    // 先证明读到的是真的样式表（否则下面的否定断言在空串上也会通过）。
    expect(css).toMatch(/\.ps-msg\s*\{/);
    expect(css).not.toMatch(/\.ps-composer(?![\w-])/);
    expect(ruleIn(css, ".ps-comm-composer")).toMatch(/display:\s*flex/);
    expect(ruleIn(css, ".ps-comm-composer .ps-input")).toMatch(/flex:\s*1/);
  });

  it("module 用的是新类名：源码里没有 ps-composer；渲染出来的输入框在 form.ps-comm-composer 里", async () => {
    const source = readCommunicatorSource("module.tsx");
    expect(source).toContain('className="ps-comm-composer"');
    expect(source).not.toMatch(/(?<![\w-])ps-composer(?![\w-])/);
    renderCommunicator(async () => feedOf([]));
    const input = await screen.findByRole("textbox", { name: "消息内容" });
    expect(input.closest("form")?.className).toBe("ps-comm-composer");
    expect(document.querySelector(".ps-composer")).toBeNull();
  });

  it("除了 communicator.css，没有别的样式文件定义 .ps-comm-composer（防止再撞名）", () => {
    const root = resolve(dirname(fileURLToPath(import.meta.url)), "..", "src");
    const owners = readdirSync(root, { recursive: true, encoding: "utf8" })
      .filter((file) => file.endsWith(".css"))
      .filter((file) => /\.ps-comm-composer(?![\w-])/.test(stripComments(readFileSync(resolve(root, file), "utf8"))))
      .map((file) => file.replace(/\\/g, "/"));
    expect(owners).toEqual(["features/communicator/communicator.css"]);
  });
});
