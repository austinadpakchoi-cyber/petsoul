/**
 * claude-6c2b · 计划页接真实数据（2026-09-24 23:2x，主窗口派）：/guides/plan/:planId 在 live 读 GET /travel/plans/{plan_id}。
 * - 服务：visits.travelPlan 显式带当前宠物（与 travelWish 同一口径）；演示实现照演示计划答，没有就 404 plan_not_found。
 * - 页面：和 GET /travel/wish 的当前心愿按 wish_id 对上才放在一起；对不上、心愿读不到，都只按计划本身说
 *   （状态从计划推：有回忆页＝已回来，关联了行程＝已出发，都没有＝状态待确认；TA 的理由、还差什么不显示也不编）；心愿还在读时先等它。
 * - 只显示 current_revision 那一版；数据里没有的块整块不显示，不写“没有写 / 未提供”。
 * - 驾校触点：fare_waived 为真写“用了驾校借车券，这趟不用租车费”，标价划掉显示；标价绝不说成付过的钱。
 * - 404 plan_not_found 说“这份计划还没写好，或者已经不在了”，原因码只在“技术信息”里；后端没有这条路（路由级 404）走统一错误态，两者分开。
 * - 手账图四态：processing“画着呢”、ready 显示图、failed / unknown 有重画凭据才说“稍后可以重画”（一句说明，不是按钮：重画命令后端还没挂）；
 *   时间用这一页自己的 created_at。整页只读：除了读家庭、心愿、计划，不调任何服务（更不会自己发起重画）。
 * - 地图链接只用后端给的 nav_url（核实过、有坐标才有），前端不拿坐标自己拼。
 */
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import type { HouseholdBrief, TravelJournal, TravelPlan, TravelPlanRevision, TravelWish, WebErrorEnvelope } from "@/shared/contracts";
import type { ApiClient } from "@/shared/api/client";
import { ApiError, PLAYER_ERROR_TEXT } from "@/shared/api/errors";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceContext, ServiceMap, VisitService } from "@/shared/services/types";
import { HouseholdProvider } from "@/shared/session/householdContext";
import journeyModule from "@/features/journey/module";
import { PlanPage } from "@/features/journey/travelPlan/PlanPage";
import { isPlanNotFound } from "@/features/journey/travelPlan/data";
import { DEMO_PLANS } from "@/features/journey/travelPlan/fixture";

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
  sessionStorage.clear();
  vi.stubGlobal("scrollTo", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/* ---------------- 按契约造的数据（generated 的 TravelPlan / TravelWish） ---------------- */

const household = {
  household_id: "hh-1",
  name: "我们的家",
  home_id: "home-1",
  role: "admin",
  home_activated: true,
  member_count: 1,
  pets: [{ pet_id: "p-1", name: "栗子", species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true }],
} as unknown as HouseholdBrief;

const NAV = "https://uri.amap.com/marker?position=118.1,24.4&name=%E6%B5%B7%E8%BE%B9%E6%AD%A5%E9%81%93&coordinate=wgs84&callnative=0";

function journal(over: Partial<TravelJournal> = {}): TravelJournal {
  return {
    journal_id: "tj-tp-live-1-plan",
    journal_revision: 1,
    plan_id: "tp-live-1",
    plan_revision: 2,
    phase: "plan",
    title: "海边步道的一天",
    summary: "早上出门，沿着步道走到灯塔。",
    stations: [
      { station_id: "st-0", name: "海边步道", role: "main", why: null, tip: null, fact_ids: [], verified: true, lat: 24.4, lng: 118.1, nav_url: NAV, visited_event_ids: [] },
      { station_id: "st-1", name: "旧灯塔", role: "suggested", why: null, tip: null, fact_ids: [], verified: false, lat: 24.41, lng: 118.12, nav_url: null, visited_event_ids: [] },
    ],
    owner_tips: [{ text: "傍晚风大，带件外套。", fact_ids: ["f-weather"] }],
    rain_alternative: "下雨就去海边的书店坐一会儿。",
    sources: [],
    identity_mode: "photo",
    identity_note: null,
    template_revision: "t1",
    image_status: "processing",
    image_url: null,
    image_refused: null,
    redraw_ticket: null,
    event_ids: [],
    created_at: "2026-09-24T05:22:00Z",
    updated_at: "2026-09-24T05:22:00Z",
    ...over,
  };
}

function revision(over: Partial<TravelPlanRevision> = {}): TravelPlanRevision {
  return {
    plan_id: "tp-live-1",
    plan_revision: 2,
    wish_id: "w-live-9",
    wish_revision_at_build: 4,
    pet_id: "p-1",
    destination_key: "seaside-walk",
    operation_id: "travel_research:w-live-9:2:1",
    title: "沿着海边走到旧灯塔",
    summary: "上午出门，先在步道上慢慢走，再去旧灯塔看看。",
    rain_alternative: "下雨就去海边的书店坐一会儿。",
    stops: [
      { station_id: null, name: "海边步道", role: "main", why: "TA 想听一会儿浪。", tip: "早上人少。", fact_ids: ["f-open"], verified: true, lat: 24.4, lng: 118.1, nav_url: NAV, visited_event_ids: [] },
      { station_id: null, name: "旧灯塔", role: "suggested", why: "顺路能看到海。", tip: null, fact_ids: [], verified: false, lat: 24.41, lng: 118.12, nav_url: null, visited_event_ids: [] },
    ],
    owner_tips: [{ text: "傍晚风大，带件外套。", fact_ids: ["f-weather"] }],
    preconditions: [],
    sources: [{ source_id: "s-1", url: "https://example.org/seaside", publisher: "示例海边管理处", retrieved_at: "2026-09-24T04:00:00Z", published_at: "2026-09-20T00:00:00Z" }],
    facts: [
      { fact_id: "f-open", category: "opening", subject: "海边步道", value: "全天开放", source_ids: ["s-1"], verification: "official_page", conclusion: "页面写明全天开放", verdict: "verified", blocks_departure: true, retrieved_at: "2026-09-24T04:00:00Z", published_at: "2026-09-20T00:00:00Z", observed_at: null, valid_from: null, valid_until: null },
      { fact_id: "f-weather", category: "weather", subject: "海边步道", value: "傍晚有风", source_ids: ["s-1"], verification: "weather_api", conclusion: "预报傍晚 5 级风", verdict: "verified", blocks_departure: false, retrieved_at: "2026-09-24T04:00:00Z", published_at: null, observed_at: "2026-09-24T04:00:00Z", valid_from: null, valid_until: null },
    ],
    valid_from: "2026-09-25T16:00:00Z",
    valid_until: "2026-09-26T16:00:00Z",
    journey: { journey_id: "j-9", fare: 20, fare_waived: true },
    journals: [journal()],
    created_at: "2026-09-24T05:20:00Z",
    ...over,
  };
}

/** 两版：第 1 版是旧的（去的是别处），current_revision 指第 2 版。 */
function plan(over: Partial<TravelPlanRevision> = {}): TravelPlan {
  const old = revision({ plan_revision: 1, title: "旧的一版：去码头", stops: [{ station_id: null, name: "旧码头", role: "main", why: null, tip: null, fact_ids: [], verified: true, lat: null, lng: null, nav_url: null, visited_event_ids: [] }], journals: [] });
  return { plan_id: "tp-live-1", wish_id: "w-live-9", current_revision: 2, revisions: [old, revision(over)] };
}

const wish = (over: Partial<TravelWish> = {}): TravelWish => ({
  wish_id: "w-live-9",
  pet_id: "p-1",
  wish_revision: 5,
  status: "linked",
  destination_key: "seaside-walk",
  destination_name: "海边步道",
  city: "厦门",
  owner_reason: "想去海边听一会儿浪。",
  funds_goal: 20,
  waiting_reasons: [],
  research_state: "ready",
  research_round: 2,
  plan_id: "tp-live-1",
  plan_revision: 2,
  journey_id: "j-9",
  reconsider_after: null,
  last_considered_at: "2026-09-24T05:00:00Z",
  plan_stale: false,
  target_coins: 20,
  current_coins: 25,
  candidates: [],
  ...over,
});

const envelope = (status: number, code: WebErrorEnvelope["error"]["code"], message: string, details: Record<string, unknown> | null) =>
  ApiError.fromEnvelope(status, { error: { code, message, request_id: "req_plan_1", retryable: false, details } }, null);
const PLAN_NOT_FOUND = () => envelope(404, "NOT_FOUND", "没有这份计划。", { reason: "plan_not_found" });
const ROUTE_404 = () => envelope(404, "NOT_FOUND", "没有找到这个接口。", null);

/* ---------------- 渲染：只给读家庭、心愿、计划三样，别的服务一碰就失败 ---------------- */

function strictServices(services: Record<string, unknown>): ServiceMap {
  return new Proxy(services as unknown as ServiceMap, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof ServiceMap];
      throw new Error(`unexpected service ${prop}`);
    },
  });
}

function strictVisits(visits: Partial<VisitService>) {
  return new Proxy(visits, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof VisitService];
      throw new Error(`unexpected visits.${prop}`);
    },
  });
}

function renderPlan(opts: { travelPlan: VisitService["travelPlan"]; travelWish?: VisitService["travelWish"]; path?: string }): { travelPlan: ReturnType<typeof vi.fn>; travelWish: ReturnType<typeof vi.fn> } {
  const travelPlan = vi.fn(opts.travelPlan);
  const travelWish = vi.fn(opts.travelWish ?? (async () => wish()));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const page: ReactElement = <PlanPage />;
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={strictServices({ households: { list: async () => [household] }, visits: strictVisits({ travelPlan, travelWish }) })}>
        <MemoryRouter initialEntries={[opts.path ?? "/guides/plan/tp-live-1"]}>
          <Routes>
            <Route path="/guides/plan/:planId" element={<HouseholdProvider userId="u-1">{page}</HouseholdProvider>} />
            <Route path="/guides" element={<p data-testid="guide-list">手账列表</p>} />
          </Routes>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { travelPlan, travelWish };
}

const heading = (name: string | RegExp) => screen.findByRole("heading", { level: 1, name });
const sectionTitles = () => [...document.querySelectorAll(".ps-plan h2")].map((h) => h.textContent);
function section(title: string): HTMLElement {
  const h2 = [...document.querySelectorAll(".ps-plan h2")].find((el) => el.textContent === title);
  expect(h2, `没有“${title}”这一块`).toBeTruthy();
  return h2!.closest("section") as HTMLElement;
}
/** 玩家看得见的字（收起的“技术信息”除外）。 */
function plainText(): string {
  const copy = document.body.cloneNode(true) as HTMLElement;
  copy.querySelectorAll("details").forEach((d) => d.remove());
  return copy.textContent ?? "";
}

/* ---------------- 服务 ---------------- */

describe("计划的服务：live 读 GET /travel/plans/{plan_id} 带当前宠物；演示照演示计划答", () => {
  it("live：路径里的计划号要转义，query 带 pet_id，信号透传", async () => {
    const request = vi.fn(async () => plan());
    const ctx = { mode: "live", api: { request, base: "/api/v1/web" } as unknown as ApiClient } as ServiceContext;
    const live = journeyModule.services!.visits!.live!(ctx) as VisitService;
    const signal = new AbortController().signal;
    await expect(live.travelPlan("tp/live 1", "p-1", signal)).resolves.toMatchObject({ plan_id: "tp-live-1" });
    expect(request).toHaveBeenCalledWith("/travel/plans/tp%2Flive%201", { query: { pet_id: "p-1" }, signal });
  });

  it("演示：有这一份就给演示计划；没有就像后端一样答 404 plan_not_found", async () => {
    const ctx = { mode: "fixture", api: {} as ApiClient } as ServiceContext;
    const fixture = journeyModule.services!.visits!.fixture!(ctx) as VisitService;
    const first = DEMO_PLANS[0].plan;
    await expect(fixture.travelPlan(first.plan_id, null)).resolves.toMatchObject({ plan_id: first.plan_id });
    const missing = await fixture.travelPlan("fx-plan-nowhere", null).catch((error: unknown) => error);
    expect(isPlanNotFound(missing)).toBe(true);
  });
});

/* ---------------- 与心愿对上 / 对不上 ---------------- */

describe("计划页：与当前心愿按 wish_id 对上才放在一起", () => {
  it("对上（已出发的心愿）：标题用名字与心愿的目的地，TA 的理由在；两边都显式带当前宠物；只显示 current_revision 那一版", async () => {
    const { travelPlan, travelWish } = renderPlan({ travelPlan: async () => plan() });
    expect(await heading("栗子 出发去 海边步道 了")).toBeTruthy();
    expect(travelPlan).toHaveBeenCalledWith("tp-live-1", "p-1", expect.anything());
    expect(travelWish).toHaveBeenCalledWith("p-1", expect.anything());
    expect(text(".ps-plan-hero__plan")).toBe("沿着海边走到旧灯塔");
    expect(section("我为什么想去").textContent).toContain("想去海边听一会儿浪。");
    expect(document.body.textContent).not.toMatch(/旧码头|旧的一版|演示/);
  });

  it("对不上（以前的心愿）：只按计划本身说——关联了行程＝已出发；没有“我为什么想去”“还差什么”，也不编理由", async () => {
    renderPlan({ travelPlan: async () => plan(), travelWish: async () => wish({ wish_id: "w-newer", destination_name: "山里的湖", status: "active", waiting_reasons: ["missing_funds"] }) });
    expect(await heading("栗子 出发去 海边步道 了")).toBeTruthy();
    expect(text(".ps-plan-hero .ps-chip")).toBe("已出发");
    expect(sectionTitles()).not.toContain("我为什么想去");
    expect(sectionTitles()).not.toContain("还差什么");
    expect(document.body.textContent).not.toMatch(/山里的湖|想去海边听一会儿浪|攒钱目标/);
  });

  it("只按计划说时的状态：有回忆页＝已回来；没有行程也没有回忆页＝状态待确认（不猜想去 / 可以出发）", async () => {
    const memory = journal({ journal_id: "tj-tp-live-1-memory", phase: "memory", image_status: null, stations: journal().stations.map((s, i) => ({ ...s, visited_event_ids: i === 0 ? ["j-9:visit_started"] : [] })) });
    renderPlan({ travelPlan: async () => plan({ journals: [journal(), memory] }), travelWish: async () => null });
    expect(await heading("栗子 从 海边步道 回来了")).toBeTruthy();
    expect(text(".ps-plan-hero .ps-chip")).toBe("已回来");
    cleanup();
    renderPlan({ travelPlan: async () => plan({ journey: null }), travelWish: async () => null });
    expect(await heading("栗子 的旅行计划")).toBeTruthy();
    expect(text(".ps-plan-hero .ps-chip")).toBe("状态待确认");
    expect(sectionTitles()).not.toContain("还差什么");
  });

  it("心愿读不到（出错）也照样按计划本身显示计划，不整页报错", async () => {
    renderPlan({ travelPlan: async () => plan(), travelWish: async () => Promise.reject(new Error("boom")) });
    expect(await heading("栗子 出发去 海边步道 了")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(sectionTitles()).not.toContain("我为什么想去");
  });

  it("心愿还在读时先等它：计划先到也不先按计划本身说（不跳一下）", async () => {
    let release: (value: TravelWish | null) => void = () => {};
    renderPlan({ travelPlan: async () => plan(), travelWish: () => new Promise<TravelWish | null>((resolve) => (release = resolve)) });
    expect(await screen.findByText("正在翻开 TA 的计划…")).toBeTruthy();
    await new Promise((r) => setTimeout(r, 30));
    expect(document.querySelector(".ps-plan")).toBeNull();
    release(wish());
    expect(await heading("栗子 出发去 海边步道 了")).toBeTruthy();
    expect(section("我为什么想去")).toBeTruthy();
  });
});

function text(selector: string): string {
  return document.querySelector(selector)?.textContent ?? "";
}

/* ---------------- 驾校触点：借车券 ---------------- */

describe("花费：用了驾校借车券写清楚，标价划掉，不说成付过", () => {
  it("fare_waived：写“用了驾校借车券，这趟不用租车费”，标价 20 星币划掉；不出现“路费 20”“花了”“付过”“实付”", async () => {
    renderPlan({ travelPlan: async () => plan() });
    const money = await waitFor(() => {
      const el = document.querySelector('[data-money="coins"]');
      expect(el).toBeTruthy();
      return el as HTMLElement;
    });
    expect(money.textContent).toContain("用了驾校借车券，这趟不用租车费");
    const struck = money.querySelectorAll("s");
    expect(struck).toHaveLength(1);
    expect(struck[0].textContent).toBe("20 星币");
    expect(struck[0].parentElement?.textContent).toBe("标价 20 星币");
    expect(money.textContent).not.toMatch(/路费 20|花了|付过|实付|省下/);
  });

  it("没用券：照常写路费与“付过”，没有划线；fare 为 0 写不花路费", async () => {
    renderPlan({ travelPlan: async () => plan({ journey: { journey_id: "j-9", fare: 8, fare_waived: false } }) });
    const money = await waitFor(() => {
      const el = document.querySelector('[data-money="coins"]');
      expect(el).toBeTruthy();
      return el as HTMLElement;
    });
    expect(money.textContent).toContain("路费 8 星币");
    expect(money.querySelector("s")).toBeNull();
    cleanup();
    renderPlan({ travelPlan: async () => plan({ journey: { journey_id: "j-9", fare: 0, fare_waived: true } }) });
    await heading("栗子 出发去 海边步道 了");
    expect(document.querySelector('[data-money="coins"]')?.textContent).toContain("这趟不花路费");
    expect(document.querySelector('[data-money="coins"] s')).toBeNull();
  });
});

/* ---------------- 找不到：计划不在 ≠ 路由没挂 ---------------- */

describe("找不到：plan_not_found 说人话；路由级 404 走统一错误态，两者分开", () => {
  it("404 plan_not_found：“这份计划还没写好，或者已经不在了”；原因码只在收起的“技术信息”里；没有重试键；“回到手账列表”点了就去 /guides", async () => {
    renderPlan({ travelPlan: async () => Promise.reject(PLAN_NOT_FOUND()) });
    expect(await screen.findByText("这份计划还没写好，或者已经不在了")).toBeTruthy();
    const toList = screen.getByRole("link", { name: "回到手账列表" });
    expect(toList.getAttribute("href")).toBe("/guides");
    const tech = document.querySelector("details.ps-state__tech") as HTMLDetailsElement;
    expect(tech.open).toBe(false);
    expect(tech.querySelector(".ps-state__meta")?.textContent).toBe("NOT_FOUND · plan_not_found · request_id req_plan_1");
    expect(plainText()).not.toMatch(/NOT_FOUND|plan_not_found|req_plan_1/);
    expect(screen.queryByRole("button", { name: "重试" })).toBeNull();
    fireEvent.click(toList);
    expect(await screen.findByTestId("guide-list")).toBeTruthy();
  });

  it("后端没有这条路（路由级 404，不带 details）：不说“计划还没写好”，走统一错误态（没有找到 + 人话），原话只在“技术信息”里", async () => {
    renderPlan({ travelPlan: async () => Promise.reject(ROUTE_404()) });
    const alert = await screen.findByRole("alert");
    expect(alert.querySelector(".ps-state__title")?.textContent).toBe("没有找到");
    expect(plainText()).toContain(PLAYER_ERROR_TEXT.notFound);
    expect(document.body.textContent).not.toContain("这份计划还没写好");
    expect(plainText()).not.toContain("接口");
    expect(within(alert).queryByRole("button", { name: "重试" })).toBeNull();
  });

  it("网络断了这类能再试的：统一错误态带重试，点了再读一次", async () => {
    let calls = 0;
    const { travelPlan } = renderPlan({
      travelPlan: async () => {
        calls += 1;
        if (calls === 1) throw new ApiError({ kind: "network", code: "NETWORK_ERROR", message: "网络连接失败", retryable: true });
        return plan();
      },
    });
    fireEvent.click(await screen.findByRole("button", { name: "重试" }));
    expect(await heading("栗子 出发去 海边步道 了")).toBeTruthy();
    expect(travelPlan).toHaveBeenCalledTimes(2);
  });

  it("409 pet_required：说“需要先选一只宠物”，不当成普通出错", async () => {
    renderPlan({ travelPlan: async () => Promise.reject(envelope(409, "CONFLICT", "请先选宠物。", { reason: "pet_required" })) });
    expect(await screen.findByText("需要先选一只宠物")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

/* ---------------- 手账图四态 ---------------- */

describe("手账图：processing 画着呢、ready 显示图、failed / unknown 有凭据才说能重画（说明，不是按钮）；时间用这一页自己的", () => {
  async function journalFigure(over: Partial<TravelJournal>) {
    renderPlan({ travelPlan: async () => plan({ journals: [journal(over)] }) });
    await heading("栗子 出发去 海边步道 了");
    return section("计划手账");
  }
  const redraw = (el: HTMLElement) => el.querySelector(".ps-plan-journal__redraw");

  it("processing：“画着呢”，没有图，没有重画；这一页写于 13:22（按这一页自己的 created_at，UTC 05:22）", async () => {
    const el = await journalFigure({ image_status: "processing" });
    expect(el.textContent).toContain("画着呢");
    expect(el.querySelector("img")).toBeNull();
    expect(redraw(el)).toBeNull();
    expect(el.querySelector(".ps-plan-journal__time")?.textContent).toBe("这一页写于 2026年9月24日 13:22");
  });

  it("ready：显示后端给的图（站内路径），不给重画", async () => {
    const el = await journalFigure({ image_status: "ready", image_url: "/api/v1/web/media/illustrations/il-1" });
    expect(el.querySelector("img")?.getAttribute("src")).toBe("/api/v1/web/media/illustrations/il-1");
    expect(redraw(el)).toBeNull();
  });

  it("failed + 重画凭据：“这次手账没画成”＋“稍后可以重画”；那是一句说明，不是按钮也不是链接", async () => {
    const el = await journalFigure({ image_status: "failed", redraw_ticket: "task-1#2" });
    expect(el.textContent).toContain("这次手账没画成");
    const note = redraw(el)!;
    expect(note.textContent).toBe("稍后可以在这里重画这张手账。");
    expect(note.tagName).toBe("P");
    expect(within(el).queryByRole("button")).toBeNull();
    expect(note.querySelector("a, button")).toBeNull();
  });

  it("unknown + 重画凭据：“手账结果还没确认”（不说没画成）＋“稍后可以重画”", async () => {
    const el = await journalFigure({ image_status: "unknown", redraw_ticket: "task-1#3" });
    expect(el.textContent).toContain("手账结果还没确认");
    expect(el.textContent).not.toContain("没画成");
    expect(redraw(el)).toBeTruthy();
  });

  it("failed / unknown 没有凭据：没有重画的说法", async () => {
    for (const status of ["failed", "unknown"] as const) {
      const el = await journalFigure({ image_status: status, redraw_ticket: null });
      expect(redraw(el), status).toBeNull();
      cleanup();
    }
  });
});

/* ---------------- 字段读法 ---------------- */

describe("字段读法：地图链接只用 nav_url；数据里没有的块整块不显示", () => {
  it("核实过的主目的地：“在地图上看”就是后端的 nav_url；没核实的顺路建议有坐标也没有链接", async () => {
    renderPlan({ travelPlan: async () => plan() });
    await heading("栗子 出发去 海边步道 了");
    const links = [...document.querySelectorAll<HTMLAnchorElement>(".ps-plan-place a")];
    expect(links.map((a) => a.getAttribute("href"))).toEqual([NAV]);
    expect(links[0].getAttribute("target")).toBe("_blank");
    expect(links[0].getAttribute("rel")).toBe("noopener noreferrer");
    expect(section("顺路建议").querySelector("a")).toBeNull();
  });

  it("这一版没写行动安排、没有顺路建议、没有资料、还没有手账：这几块整块不显示，不写“没有写 / 未提供”", async () => {
    renderPlan({
      travelPlan: async () => plan({ summary: "", valid_from: null, valid_until: null, stops: [revision().stops[0]], facts: [], sources: [], owner_tips: [], journals: [], rain_alternative: null }),
    });
    await heading("栗子 出发去 海边步道 了");
    expect(sectionTitles()).toEqual(["我为什么想去", "主目的地", "花费"]);
    expect(document.body.textContent).not.toMatch(/没有写|未提供|没有列出|没有顺路|没有原因|只有文字/);
  });
});
