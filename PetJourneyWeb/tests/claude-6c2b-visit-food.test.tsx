/**
 * 到店页与寻味入口（claude-6c2b 驾校·页面分身，第五批，2026-09-24；巡检 P1 第 4、7 条与主窗口追加的三条）：
 * 1) 到店页按地点类型选画面，只看服务端字段（visit.template、place.provider），不按名字猜：
 *    有门店的（cafe / restaurant）画店内；小路、公园（park）画一小片户外，不写“到店”；其他（generic：进城逛逛、打工）不放场景图。
 *    “商家资料”只给有地图资料或演示资料的门店；没有的字段整行不显示，不写“未提供”；来源写中文署名，不露 amap / world。
 * 2) 宠物形象退路：live 没有照片、或照片加载失败，都显示爪印，不留空圈（原来 .ps-cafe svg 把爪印一起藏了）；店内插画失败退回代码画的店内。
 * 3) 活动按钮文字不孤字折行：手机宽度一律单列放得下，宽屏两列时每格也放得下最长的说法。
 * 4) 旅途卡片入口：live 快照不知道是店还是小路，说法不写“到店 / 座位 / 饮品”。
 * 5) 寻味：/meta 的 food.recommendations 不是 available 时入口不显示；标题按家所在城市说（同城“让 TA 在附近挑一家”）；
 *    行程、偏好的版本号不给玩家看。判断函数导出给地图面板用。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { ComponentType, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, MemoryRouter, Route, RouterProvider, Routes } from "react-router";
import type { Capability, FoodPreference, HomeSnapshot, HouseholdBrief, JourneyMapSnapshot, Visit, VisitActivity, WebMeta } from "@/shared/contracts";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { buildSlotRegistry, SlotProvider } from "@/shared/slots/Slot";
import type { JourneyOverlayProps } from "@/shared/slots/names";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import { fixtureVisit } from "@/fixtures/venue";
import { VisitPage } from "@/features/venue/VisitPage";
import { hasMerchantInfo, visitSetting, visitStateText } from "@/features/venue/visitKind";
import venueModule from "@/features/venue/module";
import { FoodArrivalCard } from "@/features/food_discovery/FoodArrivalCard";
import { foodCardTitle, foodPicksAvailable } from "@/features/food_discovery/availability";
import { PreferenceEditor } from "@/features/food_discovery/PreferenceEditor";
import { createFixtureFoodService } from "@/features/food_discovery/service";

const mode = vi.hoisted(() => ({ dataMode: "fixture" as "fixture" | "live" }));
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
  mode.dataMode = "fixture";
  sessionStorage.clear();
  // 主布局有滚动恢复，示意地图量尺寸用 ResizeObserver；jsdom 都没有
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

/* ---------------- 替身数据：与后端同一种写法（web_journey/service.py、planning.visit_place） ---------------- */

const HOUSEHOLD: HouseholdBrief = {
  household_id: "house-1",
  name: null,
  home_id: "home-1",
  role: "admin",
  home_activated: true,
  member_count: 1,
  pets: [{ pet_id: "pet-a", name: "豆沙", species: "cat", photo_url: null, origin: "own_pet", presence: "visiting", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true }],
};

function homeWith({ photoUrl = null, city = "香港" }: { photoUrl?: string | null; city?: string | null } = {}): HomeSnapshot {
  const base = fixtureHomeSnapshot();
  const place = city ? { habitat: "seaside" as const, habitat_label: "海边", city, area_label: "西贡的海边", display: `${city}·西贡的海边`, timezone: "Asia/Hong_Kong", chosen: true } : null;
  return { ...base, data_origin: "live", presence: "visiting", place, pet: { ...base.pet, pet_id: "pet-a", name: "豆沙", photo_url: photoUrl } } as HomeSnapshot;
}

const WORLD_NOTE = "星球内的地方：世界规则设定，不对应现实地址或商家";
const acts = (list: [VisitActivity["kind"], string][]): VisitActivity[] => list.map(([kind, label]) => ({ activity_id: `va-${kind}`, kind, label, state: "available", result_text: null }));
const PARK_ACTS = acts([["choose_seat", "找块地方躺一会儿"], ["take_photo", "拍一张照片"], ["greet_resident", "和路过的居民打招呼"]]);
const CAFE_ACTS = acts([["choose_seat", "选个座位"], ["order_drink", "点一杯游戏饮品"], ["take_photo", "拍一张合影"], ["greet_resident", "和店里的居民打招呼"]]);
const WORK_ACTS = acts([["choose_seat", "换上工作围裙"], ["greet_resident", "和一起干活的居民打招呼"], ["take_photo", "干活时拍一张照片"]]);

function visitOf(over: { template: Visit["template"]; activities: VisitActivity[]; place: Partial<Visit["place"]>; state?: Visit["state"] }): Visit {
  const base = structuredClone(fixtureVisit("fx-visit-001"));
  return {
    ...base,
    visit_id: "vs-test",
    pet_id: "pet-a",
    state: over.state ?? "active",
    template: over.template,
    activities: over.activities,
    data_origin: "live",
    place: { ...base.place, data_origin: "live", ...over.place },
  };
}

const parkVisit = () => visitOf({ template: "park", activities: PARK_ACTS, place: { provider: "world", place_id: "world:local:stroll", name: "家附近的星球小路", address: null, category: "公园", attribution: WORLD_NOTE } });
const amapCafe = (place: Partial<Visit["place"]> = {}) =>
  visitOf({ template: "cafe", activities: CAFE_ACTS, place: { provider: "amap", place_id: "amap:B0FFTEST", name: "海湾小咖啡", address: "香港西贡海傍街 1 号", category: "咖啡馆", attribution: "地点资料：高德地图", ...place } });
const worldCafe = () => visitOf({ template: "cafe", activities: CAFE_ACTS, place: { provider: "world", place_id: "world:local:cafe", name: "星球居民开的小咖啡馆", address: null, attribution: WORLD_NOTE } });
const workVisit = () => visitOf({ template: "generic", activities: WORK_ACTS, place: { provider: "world", place_id: "world:work:florist", name: "星球上的花店", address: null, category: null, attribution: WORLD_NOTE } });

/** 只放页面该用的服务；读到没给的服务就算失败（证明页面没偷偷请求别的）。 */
function strictServices(services: Record<string, unknown>): ServiceMap {
  return new Proxy(services as unknown as ServiceMap, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof ServiceMap];
      throw new Error(`unexpected service ${prop}`);
    },
  });
}

function renderVisit(visit: Visit, home: HomeSnapshot) {
  mode.dataMode = "live";
  const services = strictServices({
    households: { list: async () => [HOUSEHOLD] },
    world: { home: async () => home },
    visits: { visit: async () => visit, act: async () => visit, choose: async () => { throw new Error("到店页不改行程"); } },
  });
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ServicesProvider services={services}>
        <MemoryRouter initialEntries={[`/visits/${visit.visit_id}`]}>
          <Routes>
            <Route path="/visits/:visitId" element={<HouseholdProvider userId="owner-1"><VisitPage /></HouseholdProvider>} />
          </Routes>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
}

const pageText = () => document.querySelector("main, .ps-page")?.textContent ?? document.body.textContent ?? "";
const subtitle = () => document.querySelector(".ps-topbar__sub")?.textContent;

/* ---------------- 1. 按地点类型选画面 ---------------- */

describe("到店页：按地点类型选画面（只看 template / provider，不按名字猜）", () => {
  it("分类只认字段：cafe / restaurant 是门店，park 是户外，generic 是其他；商家资料要门店且资料来自地图或演示", () => {
    expect(["cafe", "restaurant", "park", "generic"].map((template) => visitSetting({ template: template as Visit["template"] }))).toEqual(["shop", "shop", "outdoor", "other"]);
    expect(hasMerchantInfo(amapCafe())).toBe(true);
    expect(hasMerchantInfo(amapCafe({ provider: "google" }))).toBe(true);
    expect(hasMerchantInfo(amapCafe({ provider: "fixture" }))).toBe(true);
    expect(hasMerchantInfo(worldCafe())).toBe(false);
    expect(hasMerchantInfo({ ...parkVisit(), place: { ...parkVisit().place, provider: "amap" } })).toBe(false);
    // 名字里带“咖啡”也不算门店：只看 template
    expect(visitSetting({ ...parkVisit(), place: { ...parkVisit().place, name: "咖啡馆旁边的小路" } } as Visit)).toBe("outdoor");
    expect(visitStateText("active", "shop")).toBe("在店里");
    expect(visitStateText("active", "outdoor")).toBe("在这儿");
    expect(visitStateText("completed", "outdoor")).toBe("已离开");
    expect(visitStateText("completed", "shop")).toBe("已离店");
  });

  it("家附近的星球小路（park、星球内的地方）：画户外，不画店内、不写到店，没有商家资料和地址行，来源照署名写", async () => {
    renderVisit(parkVisit(), homeWith());
    const card = (await screen.findByText("关于这个地方")).closest(".ps-card") as HTMLElement;
    expect(document.querySelector(".ps-cafe"), "不该用咖啡馆室内图").toBeNull();
    expect(document.querySelector(".ps-outdoor")).toBeTruthy();
    expect(within(card).getByText("家附近的星球小路")).toBeTruthy();
    expect(within(card).getByText(WORLD_NOTE)).toBeTruthy();
    expect(card.textContent).not.toMatch(/地址：|未提供|来源：/);
    expect(pageText()).not.toMatch(/到店|店里|店内|商家资料|未提供/);
    expect(subtitle()).toBe("出门散步");
    expect(screen.getByText("在这儿")).toBeTruthy();
    expect(screen.getByText("豆沙 的出门手帐")).toBeTruthy();
  });

  it("有门店、有高德资料（cafe、amap）：画店内，写商家资料、地址、中文来源和原创场景说明", async () => {
    renderVisit(amapCafe(), homeWith());
    const card = (await screen.findByText("商家资料")).closest(".ps-card") as HTMLElement;
    expect(document.querySelector(".ps-cafe")).toBeTruthy();
    expect(document.querySelector(".ps-outdoor")).toBeNull();
    expect(within(card).getByText("地址：香港西贡海傍街 1 号")).toBeTruthy();
    expect(within(card).getByText("地点资料：高德地图")).toBeTruthy();
    expect(within(card).getByText(/店内画面是动物世界的原创场景/)).toBeTruthy();
    expect(subtitle()).toBe("到店活动");
    expect(screen.getByText("在店里")).toBeTruthy();
    expect(screen.getByText("豆沙 的到店手帐")).toBeTruthy();
  });

  it("门店缺地址、缺署名：地址整行不显示，来源按来源类型补中文，不露 amap，不写未提供", async () => {
    renderVisit(amapCafe({ address: null, attribution: null }), homeWith());
    const card = (await screen.findByText("商家资料")).closest(".ps-card") as HTMLElement;
    expect(card.textContent).not.toMatch(/地址：|未提供|amap/);
    expect(within(card).getByText("地点资料：高德地图")).toBeTruthy();
  });

  it("星球里的咖啡馆（cafe、world）：画店内原创场景，但不叫商家资料、不说“这家店的真实装修”", async () => {
    renderVisit(worldCafe(), homeWith());
    const card = (await screen.findByText("关于这个地方")).closest(".ps-card") as HTMLElement;
    expect(document.querySelector(".ps-cafe")).toBeTruthy();
    expect(pageText()).not.toMatch(/商家资料|未提供/);
    expect(card.textContent).not.toMatch(/真实装修/);
    expect(within(card).getByText(WORLD_NOTE)).toBeTruthy();
  });

  it("打工、进城逛逛（generic）：不放场景图，不写到店", async () => {
    renderVisit(workVisit(), homeWith());
    await screen.findByText("关于这个地方");
    expect(document.querySelector(".ps-cafe")).toBeNull();
    expect(document.querySelector(".ps-outdoor")).toBeNull();
    expect(pageText()).not.toMatch(/到店|店里|店内|商家资料|未提供/);
    expect(subtitle()).toBe("出门活动");
    expect(screen.getByText("豆沙 的出门手帐")).toBeTruthy();
  });
});

/* ---------------- 2. 宠物形象退路 ---------------- */

const pawIn = (scene: string) => document.querySelector(`${scene} .ps-avatar.is-placeholder svg.ps-paw-mark`);

describe("宠物形象退路：不留空圈", () => {
  it("live 没有照片：店内和户外画面里都是爪印占位", async () => {
    renderVisit(amapCafe(), homeWith());
    await screen.findByText("商家资料");
    expect(pawIn(".ps-cafe__pet"), "店内：爪印").toBeTruthy();
    cleanup();
    renderVisit(parkVisit(), homeWith());
    await screen.findByText("关于这个地方");
    expect(pawIn(".ps-outdoor__pet"), "户外：爪印").toBeTruthy();
  });

  it("照片加载失败：换成爪印，不留一张裂图（店内、户外都是）", async () => {
    for (const [visit, scene, portrait] of [[amapCafe(), ".ps-cafe__pet", "ps-cafe__pet-portrait"], [parkVisit(), ".ps-outdoor__pet", "ps-outdoor__pet-portrait"]] as const) {
      renderVisit(visit, homeWith({ photoUrl: "https://media.example/pet-a.webp" }));
      await screen.findByText(/商家资料|关于这个地方/);
      const img = document.querySelector<HTMLImageElement>(`${scene} img.${portrait}`);
      expect(img, `${scene} 先用照片`).toBeTruthy();
      expect(pawIn(scene)).toBeNull();
      fireEvent.error(img!);
      expect(document.querySelector(`${scene} img.${portrait}`), `${scene} 裂图要撤掉`).toBeNull();
      expect(pawIn(scene), `${scene} 换成爪印`).toBeTruthy();
      cleanup();
    }
  });

  it("店内插画加载失败：退回代码画的店内（is-art-failed），不留空底", async () => {
    renderVisit(amapCafe(), homeWith());
    await screen.findByText("商家资料");
    const art = document.querySelector<HTMLImageElement>(".ps-cafe img.ps-cafe__art")!;
    expect(document.querySelector(".ps-cafe.is-art-failed")).toBeNull();
    fireEvent.error(art);
    expect(document.querySelector(".ps-cafe.is-art-failed")).toBeTruthy();
    expect(document.querySelector(".ps-cafe img.ps-cafe__art")).toBeNull();
    expect(document.querySelector(".ps-cafe svg.ps-cafe__drawing")).toBeTruthy();
  });

  it("户外：躺下歇着、打过招呼只看这次到访的动作状态（is-resting、“你好呀”）", async () => {
    const withDone = (visit: Visit, kinds: VisitActivity["kind"][]): Visit => ({ ...visit, activities: visit.activities.map((a) => (kinds.includes(a.kind) ? { ...a, state: "done" as VisitActivity["state"], result_text: "做完了。" } : a)) });
    renderVisit(parkVisit(), homeWith());
    await screen.findByText("关于这个地方");
    expect(document.querySelector(".ps-outdoor.is-resting")).toBeNull();
    expect(screen.queryByText("你好呀")).toBeNull();
    cleanup();
    renderVisit(withDone(parkVisit(), ["choose_seat", "greet_resident"]), homeWith());
    await screen.findByText("关于这个地方");
    expect(document.querySelector(".ps-outdoor.is-resting")).toBeTruthy();
    expect(within(document.querySelector<HTMLElement>(".ps-outdoor")!).getByText("你好呀")).toBeTruthy();
    expect(document.querySelector(".ps-outdoor")!.getAttribute("aria-label")).toBe("豆沙 在家附近的星球小路，找了块地方躺下歇着");
  });
});

/* ---------------- 3. venue.css ---------------- */

function cssRules(file: string): { selector: string; body: string }[] {
  const text = readFileSync(resolve(ROOT, "src/features", file), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const out: { selector: string; body: string }[] = [];
  for (const m of text.matchAll(/([^{}]+)\{([^{}]*)\}/g)) out.push({ selector: m[1].trim().replace(/\s+/g, " "), body: m[2] });
  return out;
}
const decl = (body: string, prop: string) => body.match(new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*([^;]+)`))?.[1].trim();

describe("venue.css：爪印不再被藏、按钮不孤字折行", () => {
  const rules = cssRules("venue/venue.css");

  it("没有哪条规则把场景里的 svg 整片藏掉；代码画的店内平时不显示、插画失败时才显示", () => {
    const hidesAllSvg = rules.filter((r) => /(^|,\s*)\.ps-(cafe|outdoor)[^,]*\ssvg\s*($|,)/.test(r.selector) && decl(r.body, "display") === "none");
    expect(hidesAllSvg.map((r) => r.selector)).toEqual([]);
    expect(decl(rules.find((r) => r.selector === ".ps-cafe__drawing")!.body, "display")).toBe("none");
    expect(decl(rules.find((r) => r.selector === ".ps-cafe.is-art-failed .ps-cafe__drawing")!.body, "display")).toBe("block");
  });

  it("活动按钮：手机宽度（320～430）单列，页面最宽 560 时两列且每格放得下最长的说法（11 个字）", () => {
    const grid = decl(rules.find((r) => r.selector === ".ps-visit-acts")!.body, "grid-template-columns") ?? "";
    const m = grid.match(/^repeat\(auto-fit, minmax\(min\(100%, ([\d.]+)em\), 1fr\)\)$/);
    expect(m, `grid-template-columns = ${grid}`).toBeTruthy();
    // 令牌：正文 15px（--fs-md）、页边 16px、页面最宽 560、格间距 8px；按钮字 13px（--fs-sm）、左右内边距 16、图标 18 + 间距 8、边框 1；活动卡内边距 7 + 边框 1
    const minCol = Number(m![1]) * 15;
    const columns = (viewport: number) => {
      const content = Math.min(viewport, 560) - 32;
      return Math.max(1, Math.floor((content + 8) / (Math.min(minCol, content) + 8)));
    };
    for (const w of [320, 360, 375, 390, 414, 430]) expect(columns(w), `${w} 宽`).toBe(1);
    expect(columns(560)).toBe(2);
    const cell = (560 - 32 - 8) / 2;
    const room = cell - 2 * (7 + 1) - 2 * (16 + 1) - 18 - 8;
    const longest = Math.max(...[...PARK_ACTS, ...CAFE_ACTS, ...WORK_ACTS].map((a) => [...a.label].length));
    expect(longest).toBe(11);
    expect(room).toBeGreaterThanOrEqual(longest * 13);
    // 手机单列时每行的字位（390 宽）同样放得下
    expect(390 - 32 - 2 * (7 + 1) - 2 * (16 + 1) - 18 - 8).toBeGreaterThanOrEqual(longest * 13);
    expect(decl(rules.find((r) => r.selector === ".ps-visit-act__label")!.body, "text-wrap")).toBe("balance");
  });

  it("按钮文字包在 .ps-visit-act__label 里（整句平衡折行的挂点）", async () => {
    renderVisit(parkVisit(), homeWith());
    await screen.findByText("关于这个地方");
    const labels = [...document.querySelectorAll(".ps-visit-act .ps-btn .ps-visit-act__label")].map((el) => el.textContent);
    expect(labels).toEqual(["找块地方躺一会儿", "拍一张照片", "和路过的居民打招呼"]);
  });
});

/* ---------------- 4. 旅途卡片：到访入口 ---------------- */

const baseSnapshot = (over: Partial<JourneyMapSnapshot>): JourneyMapSnapshot =>
  ({ journey_id: "jn-1", pet_id: "pet-a", itinerary_version: 0, lifecycle: "active", destination_title: "在家附近走走", current_visit_id: null, planned_visit_id: null, legs: [], activities: [], activity_entries: [], arrival_context: null, data_origin: "live", ...over }) as unknown as JourneyMapSnapshot;

function renderCard(Card: ComponentType<JourneyOverlayProps>, snapshot: JourneyMapSnapshot, wrap: (node: ReactNode) => ReactNode = (node) => node) {
  return render(<MemoryRouter>{wrap(<Card snapshot={snapshot} nowMs={0} openSheet={() => undefined} />)}</MemoryRouter>);
}

describe("旅途卡片·到访入口：live 不知道是店还是小路，不写到店", () => {
  const Entry = venueModule.slots!.find((s) => s.id === "venue.entry")!.Component as ComponentType<JourneyOverlayProps>;

  it("已经到了：写“TA 已经到了 / 去看看 TA 在那儿做什么”，不写到店、座位、饮品", () => {
    renderCard(Entry, baseSnapshot({ current_visit_id: "vs-1", planned_visit_id: "vs-1" }));
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("/visits/vs-1");
    expect(link.querySelector("strong")?.textContent).toBe("TA 已经到了");
    expect(link.querySelector(".ps-muted")?.textContent).toBe("去看看 TA 在那儿做什么");
    expect(link.textContent).not.toMatch(/到店|店里|座位|饮品/);
  });

  it("还没到：写“这趟要去的地方 / 到了以后才能开始活动”，不写到店", () => {
    renderCard(Entry, baseSnapshot({ planned_visit_id: "vs-1" }));
    const link = screen.getByRole("link");
    expect(link.querySelector("strong")?.textContent).toBe("这趟要去的地方");
    expect(link.querySelector(".ps-muted")?.textContent).toBe("到了以后才能开始活动");
    expect(link.textContent).not.toMatch(/到店|店里|座位|饮品/);
  });

  it("演示到访固定是示例咖啡馆：说法不变", () => {
    renderCard(Entry, baseSnapshot({ data_origin: "fixture", planned_visit_id: "fx-visit-001", current_visit_id: "fx-visit-001" }));
    expect(screen.getByRole("link").textContent).toMatch(/看看 TA 在店里（演示到访）/);
  });
});

/* ---------------- 5. 寻味 ---------------- */

const cap = (key: string, status: Capability["status"]): Capability => ({ key, status, module: "food_discovery", note: null });
const metaWith = (capabilities: Capability[]): WebMeta => ({ api_prefix: "/api/v1/web", contract_version: "0.1.0", server_time: "2026-09-24T07:00:00Z", backend_version: "test", data_origin: "live", auth_methods_available: [], capabilities, applied_migrations: [] });
const OFF = [cap("food.preferences", "available"), cap("food.recommendations", "not_configured")];
const ON = [cap("food.preferences", "available"), cap("food.recommendations", "available")];
const arrival = (city: string) => ({ journey_id: "jn-1", itinerary_version: 0, leg_id: "lg-1", city, destination_timezone: "Asia/Hong_Kong", feasible_arrival_utc: "2026-09-24T07:10:51Z", stay_window_start_utc: "2026-09-24T07:10:51Z", stay_window_end_utc: "2026-09-24T07:50:51Z" });

describe("寻味入口的判断（导出给地图面板）", () => {
  it("foodPicksAvailable：演示模式总能用；live 只认 food.recommendations = available；能力表没到是“不知道”", () => {
    expect(foodPicksAvailable("fixture", [])).toBe(true);
    expect(foodPicksAvailable("fixture", undefined)).toBe(true);
    expect(foodPicksAvailable("live", undefined)).toBeUndefined();
    expect(foodPicksAvailable("live", null)).toBeUndefined();
    expect(foodPicksAvailable("live", OFF)).toBe(false);
    expect(foodPicksAvailable("live", [cap("food.recommendations", "not_implemented")])).toBe(false);
    expect(foodPicksAvailable("live", [cap("food.preferences", "available")])).toBe(false);
    expect(foodPicksAvailable("live", ON)).toBe(true);
  });

  it("foodCardTitle：家就在那座城市说“附近”；别的城市说“到X后”；不知道家在哪不猜", () => {
    expect(foodCardTitle(arrival("香港"), "香港")).toBe("让 TA 在附近挑一家");
    expect(foodCardTitle(arrival("澳门"), "香港")).toBe("到澳门后，让 TA 挑一家");
    for (const unknown of [null, undefined, "", "  "]) expect(foodCardTitle(arrival("香港"), unknown)).toBe("让 TA 在香港挑一家");
  });
});

function renderFoodCard(snapshot: JourneyMapSnapshot, { meta, home }: { meta: () => Promise<WebMeta>; home: HomeSnapshot }) {
  mode.dataMode = "live";
  const calls = { meta: 0 };
  const services = strictServices({
    households: { list: async () => [HOUSEHOLD] },
    world: { home: async () => home },
    platform: { meta: () => { calls.meta++; return meta(); } },
  });
  renderCard(FoodArrivalCard, snapshot, (node) => (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ServicesProvider services={services}>
        <HouseholdProvider userId="owner-1">{node}</HouseholdProvider>
      </ServicesProvider>
    </QueryClientProvider>
  ));
  return calls;
}

const foodLink = () => document.querySelector<HTMLAnchorElement>('a[href="/journey/food"]');
const settle = () => act(async () => { for (let i = 0; i < 5; i++) await new Promise((r) => setTimeout(r, 0)); });

describe("旅途卡片·寻味入口", () => {
  it("能力没开（not_configured，隔离后端与正式环境都这样）：入口不显示，不引人点进去看 503", async () => {
    const calls = renderFoodCard(baseSnapshot({ arrival_context: arrival("香港") }), { meta: async () => metaWith(OFF), home: homeWith() });
    await waitFor(() => expect(calls.meta).toBe(1));
    await settle();
    expect(foodLink()).toBeNull();
  });

  it("/meta 还没回来：先不显示，不先亮一个可能点进去是 503 的入口", async () => {
    const calls = renderFoodCard(baseSnapshot({ arrival_context: arrival("香港") }), { meta: () => new Promise<never>(() => undefined), home: homeWith() });
    await waitFor(() => expect(calls.meta).toBe(1));
    await settle();
    expect(foodLink()).toBeNull();
  });

  it("能力开着、家在香港、TA 就在香港附近：写“让 TA 在附近挑一家”，写预计到达时间，不写版本号、不写到店", async () => {
    renderFoodCard(baseSnapshot({ arrival_context: arrival("香港") }), { meta: async () => metaWith(ON), home: homeWith() });
    await waitFor(() => expect(foodLink()).toBeTruthy());
    const text = foodLink()!.textContent ?? "";
    expect(text).toMatch(/^让 TA 在附近挑一家/);
    expect(text).toMatch(/预计 15:10 到达/);
    expect(text).not.toMatch(/第\s*\d+\s*版|版本|到店/);
  });

  it("家在香港、TA 去澳门：写“到澳门后，让 TA 挑一家”", async () => {
    renderFoodCard(baseSnapshot({ arrival_context: arrival("澳门") }), { meta: async () => metaWith(ON), home: homeWith() });
    await waitFor(() => expect(foodLink()).toBeTruthy());
    expect(foodLink()!.textContent).toMatch(/^到澳门后，让 TA 挑一家/);
  });

  it("家园快照没有住处城市：不猜同城异城，写“让 TA 在香港挑一家”", async () => {
    renderFoodCard(baseSnapshot({ arrival_context: arrival("香港") }), { meta: async () => metaWith(ON), home: homeWith({ city: null }) });
    await waitFor(() => expect(foodLink()).toBeTruthy());
    expect(foodLink()!.textContent).toMatch(/^让 TA 在香港挑一家/);
  });

  it("没有到达上下文：什么都不渲染，也不碰任何服务（插槽里没有旅途时不打扰宿主页面）", () => {
    // 故意不给 QueryClient / 服务 / 家庭上下文：只要调了任何钩子就会抛错
    const { container } = render(<MemoryRouter><FoodArrivalCard snapshot={baseSnapshot({})} nowMs={0} openSheet={() => undefined} /></MemoryRouter>);
    expect(container.textContent).toBe("");
  });

  it("演示模式：能力表是空的也照常显示（演示小样本），标题不猜同城", async () => {
    mode.dataMode = "fixture";
    const modules = loadFeatureModules();
    const services = buildServices(modules, { mode: "fixture", api: createApiClient("/api/v1/web") });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ServicesProvider services={services}>
          <MemoryRouter>
            <HouseholdProvider userId={null}>
              <FoodArrivalCard snapshot={baseSnapshot({ data_origin: "fixture", arrival_context: arrival("香港") })} nowMs={0} openSheet={() => undefined} />
            </HouseholdProvider>
          </MemoryRouter>
        </ServicesProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(foodLink()).toBeTruthy());
    expect(foodLink()!.textContent).toMatch(/^让 TA 在香港挑一家/);
  });
});

describe("寻味页：不露行程、偏好的版本号", () => {
  it("演示整页（火车到香港）：行程与偏好都不写“第 N 版”", async () => {
    const modules = loadFeatureModules();
    const services = buildServices(modules, { mode: "fixture", api: createApiClient("/api/v1/web") });
    const router = createMemoryRouter(buildRoutes(modules), { initialEntries: ["/journey/food"] });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ServicesProvider services={services}>
          <SlotProvider registry={buildSlotRegistry(modules.flatMap((m) => m.slots ?? []))}>
            <RouterProvider router={router} />
          </SlotProvider>
        </ServicesProvider>
      </QueryClientProvider>,
    );
    await screen.findByText("按 TA 的行程");
    await screen.findByText(/^偏好：/);
    expect(screen.getByText("TA 的旅途口味")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/第\s*\d+\s*版/);
  });

  it("live 调整偏好：偏好行不写版本，保存按钮只写“保存”", async () => {
    mode.dataMode = "live";
    const pref: FoodPreference = { ...(await createFixtureFoodService().preference("pet-a", "pet")), version: 3 };
    const services = strictServices({ food: { preference: async () => pref, savePreference: async (_s: unknown, p: FoodPreference) => ({ ...p, version: 4 }) } });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ServicesProvider services={services}>
          <PreferenceEditor petId="pet-a" subject="pet" />
        </ServicesProvider>
      </QueryClientProvider>,
    );
    await screen.findByText("TA 的旅途口味");
    fireEvent.click(screen.getByRole("button", { name: "调整" }));
    expect(screen.getByRole("button", { name: "保存" })).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/第\s*\d+\s*版/);
  });
});
