/**
 * claude-6c2b（分身）· 回忆 · 生活片段（/timeline；方案 docs/product/PETSOUL-PLAYER-UI-MAP-FIRST-PLAN-2026-09-24.md 第 7.2、11 节）：
 * - 读 GET /timeline?pet_id=…（后端 app/web_agent/timeline.py）：请求一定带当前宠物；切换宠物后按新宠物重新读，
 *   上一只的结果（包括晚到的）不会出现在新宠物名下；
 * - 按本地日期分组（今天 / 昨天 / 9 月 22 日 / 不是今年的写年份），组与组、组内都是新的在前；同一时刻保留接口给的先后；
 * - 每条照原文显示标题与小字；图标按 kind 选，认不出的 kind 用中性图标，kind 的原始代码不出现在页面上（文字和属性里都没有）；
 * - 只有能确定页面的才做成链接：证件 → /credentials/:id、攻略 → /guides/:id；行程、工资、驾考、纪念章、朋友、收藏只显示文字；
 * - 空：温和的一句话；出错：统一错误态，点重试再读一次；演示模式（服务报能力未接入）：说明演示里没有，不编数据、不露能力代码；
 * - 路由：/timeline 全屏、左上角回 /memories、没有任何底栏；回忆页的“生活片段”入口点进来就是这页。
 * 时间：只替换 Date（固定在本地 2026-09-24 15:00），计时器照常走，查询与 waitFor 不受影响。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import type { HouseholdBrief, SessionState, TimelineItem } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import { TimelinePage } from "@/features/memories/TimelinePage";
import { clockText, dayLabel, groupTimeline, NEUTRAL_LOOK, timelineHref, timelineLook, UNDATED_LABEL } from "@/features/memories/timeline";

// 同一个文件里要切 fixture / live：env 用 getter 读一个可改的开关（页面在渲染时才读 env.dataMode）。
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

/** 固定的“现在”：本地 2026 年 9 月 24 日 15:00。 */
const NOW = new Date(2026, 8, 24, 15, 0, 0);

beforeEach(() => {
  mode.dataMode = "live";
  sessionStorage.clear();
  // 全屏页的布局里有滚动恢复；jsdom 没有 scrollTo。
  vi.stubGlobal("scrollTo", vi.fn());
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/* ---------------- 测试数据 ---------------- */

/** 本地时间的某一刻（与运行机器的时区无关：先按本地时间造，再转成接口里的 ISO 字符串）。 */
const local = (month: number, day: number, hour: number, minute: number, year = 2026) => new Date(year, month - 1, day, hour, minute).toISOString();

const item = (over: Partial<TimelineItem> & Pick<TimelineItem, "at" | "kind" | "title">): TimelineItem => ({ detail: null, ref_id: null, ...over });

/** 接口原样：故意打乱顺序，页面自己分组、排序。 */
const ITEMS: TimelineItem[] = [
  item({ at: local(9, 22, 10, 0), kind: "trip", title: "出发：坐船去澳门", detail: "澳门", ref_id: "jr-macau" }),
  item({ at: local(9, 24, 9, 12), kind: "work", title: "去打工：在咖啡馆帮工", detail: "厦门", ref_id: "jr-work" }),
  item({ at: local(9, 23, 20, 30), kind: "home", title: "回到家：海边咖啡馆", ref_id: "jr-cafe" }),
  item({ at: local(9, 24, 14, 5), kind: "salary", title: "领到工资 24 星币", detail: "在咖啡馆帮工的工钱", ref_id: "tx-1" }),
  item({ at: local(12, 31, 18, 0, 2025), kind: "credential", title: "拿到星球居民证", detail: "PS-ID-2025-ABCD", ref_id: "cr-id" }),
  item({ at: local(9, 23, 8, 0), kind: "friend", title: "认识了新朋友豆包", detail: "海边咖啡馆", ref_id: "pet-doubao" }),
  item({ at: local(9, 24, 11, 40), kind: "guide", title: "写了一份攻略：海边的一天", ref_id: "gd-1" }),
];

const EXPECTED_DAYS = ["今天", "昨天", "9 月 22 日", "2025 年 12 月 31 日"];

/** 后端 app/web_agent/timeline.py 会给出的全部 kind（收藏里的 kind 原样透出）。 */
const BACKEND_KINDS = [
  "trip", "first_drive", "work", "home", "salary", "school", "exam", "credential", "stamp", "friend",
  "postcard", "badge", "seed", "shared_memory", "license_photo", "car_voucher", "guide",
];

const householdPet = (petId: string, name: string): HouseholdBrief["pets"][number] => ({
  pet_id: petId,
  name,
  species: "cat",
  photo_url: null,
  origin: "own_pet",
  presence: "at_home",
  join_step: "moved_in",
  joined_at: "2026-09-20T00:00:00Z",
  added_by_you: true,
});

const household = (pets = [householdPet("pet-a", "奶茶")]): HouseholdBrief => ({
  household_id: "house-1",
  name: "海边的家",
  home_id: "home-1",
  role: "admin",
  home_activated: true,
  member_count: 2,
  pets,
});

const SIGNED_IN: SessionState = {
  authenticated: true,
  user: { user_id: "owner-1", display_name: "小林", username: "lin", auth_method: "web_password" },
  csrf_required: false,
  expires_at: null,
  onboarding: { step: "active", pet_id: "pet-a", home_id: "home-1", reception_session_id: null, reception_skipped: false, home_activated_at: null, pet_origin: "own_pet" },
};

const ERROR_WORDS = /接入|能力|服务端|接口|fixture|capability|life\.timeline/;

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

function liveBase(pets = [householdPet("pet-a", "奶茶")]) {
  return {
    session: { current: async () => SIGNED_IN },
    households: { list: async () => [household(pets)] },
  };
}

/** 只挂生活片段页，外加几个链接目标的占位页（看点击后到了哪）。 */
function renderTimeline(services: Record<string, unknown>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/timeline", element: <TimelinePage /> },
      { path: "/memories", element: <p>回忆页</p> },
      { path: "/credentials/:credentialId", element: <p>证件页</p> },
      { path: "/guides/:guideId", element: <p>攻略页</p> },
    ],
    { initialEntries: ["/timeline"] },
  );
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={strictServices(services)}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return Object.assign(router, { client });
}

/** 经真实路由表与真实服务注册表渲染（fixture 或 live；live 的网络由 fetchImpl 假装）。 */
function renderApp(path: string, dataMode: "fixture" | "live", fetchImpl?: typeof fetch) {
  mode.dataMode = dataMode;
  const modules = loadFeatureModules();
  const services = buildServices(modules, { mode: dataMode, api: createApiClient("/api/v1/web", fetchImpl) });
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

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

/** 每一组：标题（日期）→ 各条的标题、时刻、小字、链接、图标名、色调。 */
function readDays() {
  return [...document.querySelectorAll(".ps-tl-day")].map((section) => ({
    label: section.querySelector("h2")?.textContent ?? null,
    rows: [...section.querySelectorAll(".ps-tl-item")].map((li) => ({
      title: li.querySelector(".ps-tl-card__title")?.textContent ?? null,
      time: li.querySelector("time")?.textContent ?? null,
      detail: li.querySelector(".ps-tl-card__detail")?.textContent ?? null,
      href: li.querySelector("a")?.getAttribute("href") ?? null,
      icon: li.querySelector(".ps-tl-mark")?.getAttribute("data-icon") ?? null,
      tone: li.querySelector(".ps-tl-mark")?.getAttribute("data-tone") ?? null,
    })),
  }));
}

/* ---------------- 纯函数：分组、排序、链接、图标 ---------------- */

describe("分组与排序（groupTimeline）", () => {
  it("按本地日期分组：今天 / 昨天 / 9 月 22 日 / 不是今年写年份；组与组、组内都是新的在前", () => {
    const groups = groupTimeline(ITEMS, NOW);
    expect(groups.map((group) => group.label)).toEqual(EXPECTED_DAYS);
    expect(groups.map((group) => group.entries.map((entry) => entry.item.title))).toEqual([
      ["领到工资 24 星币", "写了一份攻略：海边的一天", "去打工：在咖啡馆帮工"],
      ["回到家：海边咖啡馆", "认识了新朋友豆包"],
      ["出发：坐船去澳门"],
      ["拿到星球居民证"],
    ]);
  });

  it("同一时刻的几条保留接口给的先后（后端已按“后发生的在前”排好），前后的照样按时间排", () => {
    const same = local(9, 24, 10, 0);
    const list = [
      item({ at: local(9, 24, 9, 0), kind: "trip", title: "更早的一条" }),
      item({ at: same, kind: "credential", title: "拿到驾驶证", ref_id: "cr-dl" }),
      item({ at: same, kind: "exam", title: "科目四考试通过", detail: "96 分", ref_id: "ds-1" }),
      item({ at: local(9, 24, 11, 0), kind: "badge", title: "更晚的一条" }),
    ];
    expect(groupTimeline(list, NOW)[0].entries.map((entry) => entry.item.title)).toEqual(["更晚的一条", "拿到驾驶证", "科目四考试通过", "更早的一条"]);
    // 同一时刻换个先后给：跟着接口走，不按 kind 或标题另排。
    const swapped = [list[0], list[2], list[1], list[3]];
    expect(groupTimeline(swapped, NOW)[0].entries.map((entry) => entry.item.title)).toEqual(["更晚的一条", "科目四考试通过", "拿到驾驶证", "更早的一条"]);
  });

  it("跨午夜按本地日期分：本地 0:10 算今天、前一晚 23:50 算昨天（不按 UTC 日期），时刻也写本地的", () => {
    const groups = groupTimeline(
      [
        item({ at: local(9, 23, 23, 50), kind: "home", title: "回到家：夜里的海边" }),
        item({ at: local(9, 24, 0, 10), kind: "friend", title: "认识了新朋友豆包" }),
      ],
      NOW,
    );
    expect(groups.map((group) => [group.label, group.entries.map((entry) => entry.item.title)])).toEqual([
      ["今天", ["认识了新朋友豆包"]],
      ["昨天", ["回到家：夜里的海边"]],
    ]);
    expect(groups.map((group) => clockText(group.entries[0].at as Date))).toEqual(["00:10", "23:50"]);
  });

  it("读不出时间的放在最后一组“没记下日子的”，彼此保留原来的先后；空列表没有组", () => {
    const list = [
      item({ at: "不是时间", kind: "trip", title: "时间坏了一" }),
      item({ at: local(9, 24, 9, 0), kind: "work", title: "今天早上" }),
      item({ at: "", kind: "home", title: "时间坏了二" }),
    ];
    const groups = groupTimeline(list, NOW);
    expect(groups.map((group) => group.label)).toEqual(["今天", UNDATED_LABEL]);
    expect(groups[1].entries.map((entry) => entry.item.title)).toEqual(["时间坏了一", "时间坏了二"]);
    expect(groups[1].entries.every((entry) => entry.at === null)).toBe(true);
    expect(groupTimeline([], NOW)).toEqual([]);
  });

  it("日期的叫法跨月、跨年都按本地日历算", () => {
    const oct1 = new Date(2026, 9, 1, 0, 30);
    expect(dayLabel(new Date(2026, 8, 30, 23, 59), oct1)).toBe("昨天");
    expect(dayLabel(new Date(2026, 9, 1, 0, 1), oct1)).toBe("今天");
    const jan1 = new Date(2027, 0, 1, 8, 0);
    expect(dayLabel(new Date(2026, 11, 31, 22, 0), jan1)).toBe("昨天");
    expect(dayLabel(new Date(2026, 11, 30, 22, 0), jan1)).toBe("2026 年 12 月 30 日");
    expect(dayLabel(new Date(2026, 8, 22, 10, 0), NOW)).toBe("9 月 22 日");
  });
});

describe("链接只给能确定页面的（timelineHref）", () => {
  it("证件 → /credentials/:id、攻略 → /guides/:id（编号做 URL 编码）", () => {
    expect(timelineHref({ kind: "credential", ref_id: "cr 1/2" })).toBe("/credentials/cr%201%2F2");
    expect(timelineHref({ kind: "guide", ref_id: "gd-1" })).toBe("/guides/gd-1");
  });

  it.each([...BACKEND_KINDS.filter((kind) => kind !== "credential" && kind !== "guide"), "mystery_kind", "constructor", "toString", "__proto__"])(
    "%s 有编号也不链（没有按这个编号打开的页面，或拿不准）",
    (kind) => {
      expect(timelineHref({ kind, ref_id: "ref-1" })).toBeNull();
    },
  );

  it("证件、攻略没有编号（null / 空白）时也不链", () => {
    expect(timelineHref({ kind: "credential", ref_id: null })).toBeNull();
    expect(timelineHref({ kind: "guide", ref_id: "   " })).toBeNull();
  });
});

describe("图标（timelineLook）", () => {
  it("后端的每一种 kind 都有自己的图标；认不出的（包括原型链上的名字）用中性图标", () => {
    for (const kind of BACKEND_KINDS) expect(timelineLook(kind)).not.toBe(NEUTRAL_LOOK);
    for (const kind of ["mystery_kind", "constructor", "toString", "__proto__", "hasOwnProperty", ""]) expect(timelineLook(kind)).toBe(NEUTRAL_LOOK);
  });
});

/* ---------------- 页面（live，服务桩） ---------------- */

describe("生活片段页", () => {
  it("分组与排序：日期组、组内先后、时刻、原文；请求带当前宠物；左上角回回忆、没有底栏", async () => {
    const asked: Array<{ petId: string; signal: boolean }> = [];
    const { client } = renderTimeline({
      ...liveBase(),
      pets: {
        timeline: async (petId: string, signal?: AbortSignal) => {
          asked.push({ petId, signal: signal instanceof AbortSignal });
          return ITEMS;
        },
      },
    });
    await screen.findByText("领到工资 24 星币");
    // 缓存按账号与宠物分开（换宠物、换账号都不会读到别人的一份）。
    expect(client.getQueryCache().findAll({ queryKey: ["pets", "timeline"] }).map((query) => query.queryKey)).toEqual([["pets", "timeline", "owner-1", "pet-a"]]);
    const days = readDays();
    expect(days.map((day) => day.label)).toEqual(EXPECTED_DAYS);
    expect(days[0].rows.map((row) => [row.title, row.time])).toEqual([
      ["领到工资 24 星币", "14:05"],
      ["写了一份攻略：海边的一天", "11:40"],
      ["去打工：在咖啡馆帮工", "09:12"],
    ]);
    expect(days[1].rows.map((row) => [row.title, row.time])).toEqual([
      ["回到家：海边咖啡馆", "20:30"],
      ["认识了新朋友豆包", "08:00"],
    ]);
    expect(days[2].rows.map((row) => row.title)).toEqual(["出发：坐船去澳门"]);
    expect(days[3].rows.map((row) => [row.title, row.detail])).toEqual([["拿到星球居民证", "PS-ID-2025-ABCD"]]);
    // 小字照原文；没有小字的不画空行。
    expect(days[0].rows.map((row) => row.detail)).toEqual(["在咖啡馆帮工的工钱", null, "厦门"]);
    expect(days[1].rows.map((row) => row.detail)).toEqual([null, "海边咖啡馆"]);
    // 按当前宠物读，带上取消信号。
    expect(asked).toEqual([{ petId: "pet-a", signal: true }]);
    // 顶部：标题、TA 的名字与头像；左上角回 /memories；全屏页没有任何底栏。
    expect(screen.getByRole("heading", { level: 1, name: "生活片段" })).toBeTruthy();
    expect(screen.getByText("奶茶走过的日子，都按时间记着。")).toBeTruthy();
    expect(screen.getByRole("img", { name: "奶茶" }).textContent).toBe("");
    expect(screen.getByRole("link", { name: "返回回忆" }).getAttribute("href")).toBe("/memories");
    expect(screen.queryAllByRole("navigation")).toHaveLength(0);
  });

  it("未知 kind：中性图标，页面文字和 DOM 属性里都不出现 kind 的原始代码；有编号也不链", async () => {
    renderTimeline({
      ...liveBase(),
      pets: {
        timeline: async () => [
          item({ at: local(9, 24, 10, 0), kind: "mystery_kind_x", title: "得到一件纪念", detail: "一片银杏叶", ref_id: "it-9" }),
          item({ at: local(9, 24, 9, 0), kind: "constructor", title: "一段没见过的记录" }),
          item({ at: local(9, 24, 8, 0), kind: "shared_memory", title: "和你一起听歌/看片的回忆", detail: "去坐船去澳门的路上，你陪 TA 一起听/看了约 12 分钟", ref_id: "it-3" }),
          item({ at: local(9, 24, 7, 0), kind: "first_drive", title: "第一次自己开车：海边兜风", detail: "厦门", ref_id: "jr-9" }),
        ],
      },
    });
    await screen.findByText("得到一件纪念");
    const rows = readDays()[0].rows;
    expect(rows.map((row) => [row.title, row.detail])).toEqual([
      ["得到一件纪念", "一片银杏叶"],
      ["一段没见过的记录", null],
      ["和你一起听歌/看片的回忆", "去坐船去澳门的路上，你陪 TA 一起听/看了约 12 分钟"],
      ["第一次自己开车：海边兜风", "厦门"],
    ]);
    expect(rows.map((row) => [row.icon, row.tone])).toEqual([
      [NEUTRAL_LOOK.icon.name, "plain"],
      [NEUTRAL_LOOK.icon.name, "plain"],
      ["heart", "coral"],
      ["car", "sky"],
    ]);
    expect(rows.every((row) => row.href === null)).toBe(true);
    const html = document.body.innerHTML;
    for (const code of ["mystery_kind_x", "constructor", "shared_memory", "first_drive"]) expect(html).not.toContain(code);
    expect(document.body.textContent).not.toMatch(/mystery|kind/i);
  });

  it("链接只给能确定的：证件、攻略可点（编号编码），驾考、行程、工资、朋友、明信片、纪念章只显示文字", async () => {
    const router = renderTimeline({
      ...liveBase(),
      pets: {
        timeline: async () => [
          item({ at: local(9, 24, 14, 0), kind: "credential", title: "拿到驾驶证", detail: "PSD-2026-XYZW", ref_id: "cr-dl 1" }),
          item({ at: local(9, 24, 13, 0), kind: "guide", title: "写了一份攻略：海边的一天", ref_id: "gd-7" }),
          item({ at: local(9, 24, 12, 0), kind: "exam", title: "科目四考试通过", detail: "96 分", ref_id: "ds-abc" }),
          item({ at: local(9, 24, 11, 0), kind: "trip", title: "出发：坐船去澳门", detail: "澳门", ref_id: "jr-1" }),
          item({ at: local(9, 24, 10, 0), kind: "salary", title: "领到工资 24 星币", detail: "工钱", ref_id: "tx-1" }),
          item({ at: local(9, 24, 9, 0), kind: "friend", title: "认识了星球居民鹦鹉阿绿", detail: "海边咖啡馆", ref_id: "npc:parrot" }),
          item({ at: local(9, 24, 8, 0), kind: "postcard", title: "寄回一张明信片", detail: "来自澳门的明信片", ref_id: "it-1" }),
          item({ at: local(9, 24, 7, 0), kind: "stamp", title: "护照上盖了澳门的纪念章", ref_id: "jr-1" }),
          item({ at: local(9, 24, 6, 0), kind: "credential", title: "开通星球银行卡", detail: "PSB-2026-XYZW", ref_id: null }),
        ],
      },
    });
    await screen.findByText("拿到驾驶证");
    const rows = readDays()[0].rows;
    expect(rows.map((row) => row.href)).toEqual(["/credentials/cr-dl%201", "/guides/gd-7", null, null, null, null, null, null, null]);
    const list = document.querySelector(".ps-tl-days") as HTMLElement;
    expect(within(list).getAllByRole("link")).toHaveLength(2);
    // 只有可点的两条带箭头。
    expect(list.querySelectorAll(".ps-tl-card__go")).toHaveLength(2);
    fireEvent.click(within(list).getAllByRole("link")[0]);
    expect(await screen.findByText("证件页")).toBeTruthy();
    expect(router.state.location.pathname).toMatch(/^\/credentials\/cr-dl(%20| )1$/);
  });

  it("空：一句温和的话（带 TA 的名字），没有列表、没有错误和按钮", async () => {
    renderTimeline({ ...liveBase(), pets: { timeline: async () => [] } });
    expect(await screen.findByText("奶茶的生活片段还空着")).toBeTruthy();
    const note = document.querySelector(".ps-tl-note") as HTMLElement;
    expect(note.getAttribute("role")).toBe("status");
    expect(note.textContent).toContain("等奶茶出门走走、打一份工、认识新朋友");
    expect(document.querySelector(".ps-tl-days")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
    expect(document.body.textContent).not.toMatch(ERROR_WORDS);
  });

  it("出错：统一错误态（role=alert），点“重试”再读一次，读到了就显示", async () => {
    let calls = 0;
    renderTimeline({
      ...liveBase(),
      pets: {
        timeline: async () => {
          calls += 1;
          if (calls === 1) throw new ApiError({ kind: "http", status: 500, code: "INTERNAL_ERROR", message: "服务端出错了", retryable: true });
          return [ITEMS[3]];
        },
      },
    });
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("没能完成这一步");
    expect(document.querySelector(".ps-tl-days")).toBeNull();
    fireEvent.click(within(alert).getByRole("button", { name: /重试/ }));
    expect(await screen.findByText("领到工资 24 星币")).toBeTruthy();
    expect(calls).toBe(2);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("切换宠物：按新宠物重新读；上一只的请求晚到也不会出现在新宠物名下", async () => {
    const pending = new Map<string, (items: TimelineItem[]) => void>();
    const asked: string[] = [];
    renderTimeline({
      ...liveBase([householdPet("pet-a", "奶茶"), householdPet("pet-b", "豆包")]),
      pets: {
        timeline: (petId: string) => {
          asked.push(petId);
          return new Promise<TimelineItem[]>((resolve) => pending.set(petId, resolve));
        },
      },
    });
    await waitFor(() => expect(asked).toEqual(["pet-a"]));
    // 奶茶的还没回来，就切到豆包。
    fireEvent.click(screen.getByRole("button", { name: /查看 豆包/ }));
    await waitFor(() => expect(asked).toEqual(["pet-a", "pet-b"]));
    await act(async () => pending.get("pet-b")?.([item({ at: local(9, 24, 10, 0), kind: "trip", title: "出发：豆包去海边", detail: "厦门" })]));
    expect(await screen.findByText("出发：豆包去海边")).toBeTruthy();
    // 奶茶的结果这时才到。
    await act(async () => pending.get("pet-a")?.([item({ at: local(9, 24, 11, 0), kind: "work", title: "去打工：奶茶在书店理书" })]));
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(screen.queryByText("去打工：奶茶在书店理书")).toBeNull();
    expect(readDays().flatMap((day) => day.rows.map((row) => row.title))).toEqual(["出发：豆包去海边"]);
    expect(screen.getByText("豆包走过的日子，都按时间记着。")).toBeTruthy();
    expect(asked).toEqual(["pet-a", "pet-b"]);
  });
});

/* ---------------- 服务：live 请求带 pet_id；演示模式不编 ---------------- */

describe("pets.timeline 服务", () => {
  it("live：GET /api/v1/web/timeline?pet_id=…（编号编码），原样返回；取消信号接到请求上", async () => {
    const calls: Array<{ url: string; method: string }> = [];
    const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), method: init?.method ?? "GET" });
      if (String(input).includes("pet_id=slow")) {
        return new Promise<Response>((_resolve, reject) => init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))));
      }
      return json(ITEMS);
    }) as typeof fetch;
    const services = buildServices(loadFeatureModules(), { mode: "live", api: createApiClient("/api/v1/web", fetchImpl) });
    expect(await services.pets.timeline("pet-a")).toEqual(ITEMS);
    await services.pets.timeline("pet a/1");
    expect(calls).toEqual([
      { url: "/api/v1/web/timeline?pet_id=pet-a", method: "GET" },
      { url: "/api/v1/web/timeline?pet_id=pet+a%2F1", method: "GET" },
    ]);
    const controller = new AbortController();
    const slow = services.pets.timeline("slow", controller.signal).catch((error: unknown) => error);
    controller.abort();
    expect(await slow).toMatchObject({ code: "ABORTED" });
  });

  it("演示模式：不拼、不编，报“能力未接入”", async () => {
    const services = buildServices(loadFeatureModules(), { mode: "fixture", api: createApiClient("/api/v1/web") });
    const error = await services.pets.timeline(fixtureHomeSnapshot().pet.pet_id).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).isCapabilityUnavailable).toBe(true);
    expect((error as ApiError).details).toEqual({ capability: "life.timeline" });
  });
});

/* ---------------- 经真实路由表 ---------------- */

describe("路由 /timeline", () => {
  const FIXTURE_PET = fixtureHomeSnapshot().pet; // 演示世界的样板宠物

  it("演示模式：全屏、没有底栏；说明演示里没有生活片段，不编数据、不给重试、不露能力代码", async () => {
    const { container } = renderApp("/timeline", "fixture");
    expect(await screen.findByText("演示模式没有生活片段")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1, name: "生活片段" })).toBeTruthy();
    expect(screen.getByText(`${FIXTURE_PET.name}走过的日子，都按时间记着。`)).toBeTruthy();
    expect(screen.getByRole("link", { name: "返回回忆" }).getAttribute("href")).toBe("/memories");
    expect(screen.queryAllByRole("navigation")).toHaveLength(0);
    expect(container.querySelector(".ps-shell--bare")?.className).toContain("ps-shell--no-tabs");
    expect(document.querySelector(".ps-tl-days")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("button", { name: /重试/ })).toBeNull();
    expect(document.body.textContent).not.toMatch(ERROR_WORDS);
  });

  it("从回忆页的“生活片段”入口点进来，左上角再回到回忆", async () => {
    const { router } = renderApp("/memories", "fixture");
    const nav = await screen.findByRole("navigation", { name: "回忆里的入口" });
    const entry = within(nav).getAllByRole("link")[0];
    expect(entry.getAttribute("href")).toBe("/timeline");
    expect(entry.textContent).toContain("生活片段");
    fireEvent.click(entry);
    expect(await screen.findByRole("heading", { level: 1, name: "生活片段" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/timeline");
    fireEvent.click(screen.getByRole("link", { name: "返回回忆" }));
    expect(await screen.findByRole("heading", { level: 1, name: "回忆" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/memories");
  });

  it("live：请求 URL 带当前宠物的 pet_id；切到另一只后按它的 pet_id 重新读，留在本页", async () => {
    const urls: string[] = [];
    const fetchImpl = (async (input: RequestInfo | URL) => {
      const url = String(input);
      urls.push(url);
      const path = url.replace("/api/v1/web", "");
      if (path === "/session") return json(SIGNED_IN);
      if (path === "/households") return json([household([householdPet("pet-a", "奶茶"), householdPet("pet-b", "豆包")])]);
      if (path.startsWith("/timeline")) {
        const pet = new URLSearchParams(path.split("?")[1] ?? "").get("pet_id");
        const title = pet === "pet-a" ? "去打工：奶茶在书店理书" : pet === "pet-b" ? "出发：豆包去海边" : "不该出现";
        return json([item({ at: local(9, 24, 10, 0), kind: "work", title })]);
      }
      return new Response("", { status: 404 });
    }) as typeof fetch;
    const { router } = renderApp("/timeline", "live", fetchImpl);
    expect(await screen.findByText("去打工：奶茶在书店理书")).toBeTruthy();
    const timelineUrls = () => urls.filter((url) => url.includes("/timeline"));
    expect(timelineUrls()).toEqual(["/api/v1/web/timeline?pet_id=pet-a"]);
    fireEvent.click(screen.getByRole("button", { name: /查看 豆包/ }));
    expect(await screen.findByText("出发：豆包去海边")).toBeTruthy();
    expect(screen.queryByText("去打工：奶茶在书店理书")).toBeNull();
    expect(timelineUrls()).toEqual(["/api/v1/web/timeline?pet_id=pet-a", "/api/v1/web/timeline?pet_id=pet-b"]);
    expect(router.state.location.pathname).toBe("/timeline");
  });
});
