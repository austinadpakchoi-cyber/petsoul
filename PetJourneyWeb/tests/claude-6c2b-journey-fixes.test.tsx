/**
 * 旅途页四处修正（claude-6c2b 驾校·页面分身，第六批，2026-09-24，主窗口授权）：
 * 1) 附近走走也写“在店里”：是不是店改看这次到访的场景模板（venue/visitKind：cafe / restaurant 才算店），
 *    小路、公园、打工的地方，以及到访还没读到时，都说“到了”，不写“店”字；图标也只有店才用杯子。
 * 2) 旅途图音符压字：一起听 / 一起看的徽标挪到交通工具右下方，车在目的地上、车在起点时都不压地名，也不压车身；
 *    几何按页面实际渲染出的位置（地点 g 的 translate、徽标锚点的 translate）加上 CSS 里的尺寸算，CSS 数字直接从样式文件读。
 * 3) 推荐详情页“来源与版本”：不露资料 / 规则 / 偏好的版本号和 fixture 这类状态代码，换成中文；认不出的状态整行不显示。
 * 4) 底图请求：容器量出小于 64 的尺寸（服务端下限）时不请求——实测整页截图时视口被临时压成 1px 宽，地图量到 32×340、发出宽 32 的请求被 422 拒绝。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router";
import type { BasemapView, FoodRecommendation, HomeSnapshot, JourneyLeg, JourneyMapSnapshot, MapActivityEntry, Visit } from "@/shared/contracts";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { buildSlotRegistry, SlotProvider } from "@/shared/slots/Slot";
import { SchematicMapSurface } from "@/shared/map";
import { Icon } from "@/shared/ui";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import { fixtureVisit } from "@/fixtures/venue";
import { fixtureRecommendation } from "@/fixtures/food";
import { tripState } from "@/features/journey/JourneyPage";
import { JourneyStatusPanel } from "@/features/journey/JourneyStatusPanel";
import { RecommendationDetailPage } from "@/features/food_discovery/RecommendationDetailPage";

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

/** 地图容器固定量到 390 宽页面上的旅途地图大小（390×540）。 */
class FixedResizeObserver {
  constructor(private readonly callback: ResizeObserverCallback) {}
  observe() {
    this.callback([{ contentRect: { width: 390, height: 540 } } as ResizeObserverEntry], this as unknown as ResizeObserver);
  }
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  mode.dataMode = "fixture";
  sessionStorage.clear();
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal("ResizeObserver", FixedResizeObserver);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const css = (file: string) => readFileSync(resolve(ROOT, "src", file), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const rule = (text: string, selector: string) => {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const m = text.match(new RegExp(`(?:^|\\})\\s*${escaped}\\s*\\{([^}]*)\\}`));
  if (!m) throw new Error(`样式里找不到 ${selector}`);
  return m[1];
};
const px = (body: string, prop: string) => {
  const m = body.match(new RegExp(`(?:^|;)\\s*${prop}\\s*:\\s*(-?[\\d.]+)px`));
  if (!m) throw new Error(`没有 ${prop}`);
  return Number(m[1]);
};

/* ---------------- 替身旅程：家 → 家附近的星球小路（步行），坐标取 18779 那一趟 ---------------- */

const HOME = { name: "家", lat: 22.3787, lng: 114.2745 };
const PATH = { name: "家附近的星球小路", lat: 22.3742, lng: 114.2775 };
const iso = (ms: number) => new Date(ms).toISOString();

function walk(id: string, from: typeof HOME, to: typeof HOME, departMs: number, arriveMs: number, phase: JourneyLeg["phase"], sequence: number): JourneyLeg {
  const node = (p: typeof HOME, suffix: string) => ({ node_id: `${id}-${suffix}`, name: p.name, kind: "place", timezone: "Asia/Hong_Kong", lat: p.lat, lng: p.lng, verified: true });
  return {
    leg_id: id, journey_id: "jn-t", sequence, kind: "main", mode: "walk", role: "walker", world_service: null,
    origin: node(from, "o"), destination: node(to, "d"),
    times: { origin_timezone: "Asia/Hong_Kong", destination_timezone: "Asia/Hong_Kong", planned_departure_utc: iso(departMs), planned_arrival_utc: iso(arriveMs), estimated_departure_utc: null, estimated_arrival_utc: null, actual_departure_utc: null, actual_arrival_utc: null },
    time_basis: "routed_estimate", freshness: "fresh", position_basis: "simulated_route", phase, itinerary_version: 1, route: [], reference: null, rescheduled_reason: null,
  } as unknown as JourneyLeg;
}

const music = (legId: string): MapActivityEntry => ({ entry_id: "en-1", leg_id: legId, activity_id: "act-1", badge: "music", badge_state: "active", media_session_id: "ms-1", label: "TA 在听《窗边的小调》", actions: [] });

/** where：车在目的地上（出门那段刚走完，TA 到了）或车在起点（刚要从家出发）。 */
function snapshotAt(where: "destination" | "origin", visitId: string | null = null): JourneyMapSnapshot {
  const now = Date.now();
  const out = where === "destination" ? walk("lg-out", HOME, PATH, now - 12 * 60_000, now - 1_000, "arrived", 1) : walk("lg-out", HOME, PATH, now + 2_000, now + 12 * 60_000, "boarding", 1);
  const back = walk("lg-back", PATH, HOME, now + 40 * 60_000, now + 52 * 60_000, "scheduled", 2);
  return {
    journey_id: "jn-t", pet_id: "fx-pet-001", itinerary_version: 1, lifecycle: "active", destination_title: "在家附近走走",
    current_visit_id: visitId, planned_visit_id: visitId ?? "vs-t", server_time: iso(now), legs: [out, back], current_leg_id: "lg-out",
    vehicle: null, activities: [], activity_entries: [music("lg-out")], arrival_context: null, data_origin: "fixture",
  } as unknown as JourneyMapSnapshot;
}

function visitWith(template: Visit["template"]): Visit {
  return { ...structuredClone(fixtureVisit("fx-visit-001")), visit_id: "vs-t", template };
}

/** 整个应用（真实路由表 + 全部模块的插槽），演示服务；只把旅程、到访、一起听的会话换成替身。 */
function renderJourney(snapshot: JourneyMapSnapshot, visit: () => Promise<Visit>) {
  const modules = loadFeatureModules();
  const base = buildServices(modules, { mode: "fixture", api: createApiClient("/api/v1/web") });
  const services = {
    ...base,
    transport: { ...base.transport, journeyMap: async () => snapshot, fixtureScenarios: () => [] },
    visits: { ...base.visits, visit },
    companionMedia: { ...base.companionMedia, session: async () => ({ state: "playing" }) },
  } as unknown as ServiceMap;
  const router = createMemoryRouter(buildRoutes(modules), { initialEntries: ["/journey"] });
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ServicesProvider services={services}>
        <SlotProvider registry={buildSlotRegistry(modules.flatMap((m) => m.slots ?? []))}>
          <RouterProvider router={router} />
        </SlotProvider>
      </ServicesProvider>
    </QueryClientProvider>,
  );
}

const iconPath = (name: "cup" | "pin") => {
  const { container, unmount } = render(<Icon name={name} />);
  const d = container.querySelector("path")!.getAttribute("d");
  unmount();
  return d;
};

/* ---------------- 1. 附近走走不写“在店里” ---------------- */

describe("旅途页：只有门店才说“在店里”", () => {
  it("tripState：到访中，门店说“在店里”；户外、其他、不知道都说“到了”", () => {
    const snap = snapshotAt("destination", "vs-t");
    const now = Date.now();
    expect(tripState(snap, now, "shop")).toMatchObject({ visiting: true, atShop: true, state: "在店里" });
    for (const setting of ["outdoor", "other", null] as const) expect(tripState(snap, now, setting)).toMatchObject({ visiting: true, atShop: false, state: "到了" });
    expect(tripState(snap, now)).toMatchObject({ atShop: false, state: "到了" });
    // 不在到访里：给了“门店”也不算在店里
    expect(tripState(snapshotAt("origin"), now, "shop")).toMatchObject({ visiting: false, atShop: false });
  });

  it("家附近的星球小路（park）：状态签、状态卡都写“到了”，图标是定位针不是杯子", async () => {
    renderJourney(snapshotAt("destination", "vs-t"), async () => visitWith("park"));
    const chip = await screen.findByTestId("trip-chip");
    await waitFor(() => expect(chip.textContent).toMatch(/在家附近走走 · 到了/));
    const card = screen.getByRole("region", { name: "TA 此刻的旅途" });
    expect(card.querySelector(".ps-trip-card__eyebrow")!.textContent).toMatch(/^TA 到了/);
    expect(`${chip.textContent}${card.textContent}`).not.toMatch(/店/);
    expect(card.querySelector(".ps-trip-card__icon path")!.getAttribute("d")).toBe(iconPath("pin"));
  });

  it("咖啡馆（cafe）：写“在店里”，图标是杯子", async () => {
    renderJourney(snapshotAt("destination", "vs-t"), async () => visitWith("cafe"));
    const chip = await screen.findByTestId("trip-chip");
    await waitFor(() => expect(chip.textContent).toMatch(/在家附近走走 · 在店里/));
    const card = screen.getByRole("region", { name: "TA 此刻的旅途" });
    expect(card.querySelector(".ps-trip-card__eyebrow")!.textContent).toMatch(/^TA 在店里/);
    expect(card.querySelector(".ps-trip-card__icon path")!.getAttribute("d")).toBe(iconPath("cup"));
  });

  it("到访还没读到：先说“到了”，不先写“在店里”", async () => {
    renderJourney(snapshotAt("destination", "vs-t"), () => new Promise<never>(() => undefined));
    const chip = await screen.findByTestId("trip-chip");
    expect(chip.textContent).toMatch(/在家附近走走 · 到了/);
    expect(chip.textContent).not.toMatch(/店/);
  });

  it("旅途状态卡（home.panels，目前小窝不显示）：小路写“TA 到了，去看看”，咖啡馆写“TA 在店里，进去看看”", async () => {
    const home = (visitId: string) => ({ ...fixtureHomeSnapshot(), journey: { journey_id: "jn-t", itinerary_version: 1, headline: "TA 在家附近走走", current_visit_id: visitId, current_leg_id: null } }) as HomeSnapshot;
    for (const [template, text] of [["park", "TA 到了，去看看"], ["cafe", "TA 在店里，进去看看"]] as const) {
      const services = { visits: { visit: async () => visitWith(template) } } as unknown as ServiceMap;
      render(
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <ServicesProvider services={services}>
            <MemoryRouter>
              <JourneyStatusPanel snapshot={home("vs-t")} />
            </MemoryRouter>
          </ServicesProvider>
        </QueryClientProvider>,
      );
      const link = await screen.findByRole("link", { name: text });
      expect(link.getAttribute("href")).toBe("/visits/vs-t");
      cleanup();
    }
  });
});

/* ---------------- 2. 徽标不压地名 ---------------- */

type Box = { left: number; right: number; top: number; bottom: number };
const overlap = (a: Box, b: Box) => Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) * Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
const translateOf = (value: string | null) => {
  const m = (value ?? "").match(/translate\((-?[\d.]+)(?:px)?,\s*(-?[\d.]+)(?:px)?\)/);
  if (!m) throw new Error(`读不出位置：${value}`);
  return { x: Number(m[1]), y: Number(m[2]) };
};

function geometry() {
  // 样式里的尺寸：徽标（companion.css）、小音符、地名（MapSurface 字号 12、描边 4，旅途页 journey.css 再上移）、车身（transport.css）
  const companion = css("features/companion_media/companion.css");
  const badge = rule(companion, ".ps-badge");
  const bw = px(badge, "width"), bh = px(badge, "height"), bl = px(badge, "left"), bt = px(badge, "top");
  const ring = Number(badge.match(/0 0 0 (\d+)px/)?.[1] ?? NaN);
  const notes = rule(companion, ".ps-badge__notes i");
  const noteLefts = [px(notes, "left"), px(rule(companion, ".ps-badge__notes i:nth-child(2)"), "left")];
  const noteTop = px(notes, "top"), noteSize = px(notes, "font-size");
  // 飘动终点：关键帧里带 px 的那个 translateY（起点是 translateY(0)）
  const float = Math.abs(Number(companion.match(/@keyframes ps-note-float[\s\S]*?translateY\((-?[\d.]+)px\)/)?.[1] ?? NaN));
  const lift = Number(css("features/journey/journey.css").match(/\.ps-journey-map \.ps-map__base text\s*\{[^}]*translateY\((-?[\d.]+)px\)/)?.[1] ?? 0);
  const vehicle = px(rule(css("features/transport/transport.css"), ".ps-vehicle"), "width") / 2;
  const numbers = { bw, bh, bl, bt, ring, noteTop, noteSize, float, vehicle, lift };
  expect(Object.entries(numbers).filter(([, value]) => !Number.isFinite(value)).map(([key]) => key), `样式数字都要读到：${JSON.stringify(numbers)}`).toEqual([]);

  const anchorOf = (testId: string) => translateOf(document.querySelector(`[data-testid="${testId}"]`)!.closest<HTMLElement>(".ps-map__anchor")!.style.transform);
  const b = anchorOf("activity-badge-music");
  const v = anchorOf("vehicle-marker");
  const badgeBody: Box = { left: b.x + bl, right: b.x + bl + bw, top: b.y + bt, bottom: b.y + bt + bh };
  const badgeRing: Box = { left: badgeBody.left - ring, right: badgeBody.right + ring, top: badgeBody.top - ring, bottom: badgeBody.bottom + ring };
  const notesBand: Box = { left: badgeBody.left + Math.min(...noteLefts), right: badgeBody.left + Math.max(...noteLefts) + noteSize, top: badgeBody.top + noteTop - float, bottom: badgeBody.top + noteTop + noteSize };
  // 地名：文字基线在 y=-12 再加上旅途页的上移；按每字 12px（中文全角，最宽）、上 12 下 3、四周描边 2 算，只会算大不会算小
  const labels = [...document.querySelectorAll<SVGGElement>(".ps-map__base g[transform]")].flatMap((g) => {
    const text = g.querySelector("text");
    if (!text) return [];
    const at = translateOf(g.getAttribute("transform"));
    const baseline = at.y + Number(text.getAttribute("y")) + lift;
    const half = ([...(text.textContent ?? "")].length * 12) / 2 + 2;
    return [{ name: text.textContent, box: { left: at.x - half, right: at.x + half, top: baseline - 12 - 2, bottom: baseline + 3 + 2 } as Box }];
  });
  // 车身是圆：徽标矩形离圆心最近的点要在半径以外
  const nearX = Math.max(badgeBody.left, Math.min(v.x, badgeBody.right)) - v.x;
  const nearY = Math.max(badgeBody.top, Math.min(v.y, badgeBody.bottom)) - v.y;
  return { labels, badgeRing, notesBand, gapToVehicle: Math.hypot(nearX, nearY) - vehicle, vehicleAt: v };
}

describe("旅途图：一起听的徽标不压地名、不压车身", () => {
  for (const [where, place] of [["destination", PATH.name], ["origin", HOME.name]] as const) {
    it(`车在${where === "destination" ? "目的地上（家附近的星球小路）" : "起点（家）"}：徽标和小音符都不碰任何地名`, async () => {
      renderJourney(snapshotAt(where), async () => visitWith("park"));
      await screen.findByTestId("activity-badge-music");
      const g = geometry();
      const here = g.labels.find((l) => l.name === place)!;
      expect(here, "车所在地点的地名要画出来").toBeTruthy();
      // 前提：车确实压在这个地点上（地名就在车正上方）
      expect(Math.abs((here.box.left + here.box.right) / 2 - g.vehicleAt.x)).toBeLessThan(1);
      for (const label of g.labels) {
        expect(overlap(g.badgeRing, label.box), `徽标（含外圈）压到“${label.name}”`).toBe(0);
        expect(overlap(g.notesBand, label.box), `小音符飘进“${label.name}”`).toBe(0);
      }
      expect(g.gapToVehicle, "徽标不压车身").toBeGreaterThanOrEqual(0);
    });
  }
});

/* ---------------- 3. 推荐详情页：资料来源不露版本号和状态代码 ---------------- */

function renderDetail(rec: FoodRecommendation) {
  const modules = loadFeatureModules();
  const base = buildServices(modules, { mode: "fixture", api: createApiClient("/api/v1/web") });
  const services = { ...base, food: { ...base.food, recommendation: async () => rec } } as unknown as ServiceMap;
  const router = createMemoryRouter([{ path: "/journey/food/:recommendationId", element: <HouseholdProvider userId={null}><RecommendationDetailPage /></HouseholdProvider> }], { initialEntries: [`/journey/food/${rec.recommendation_id}`] });
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ServicesProvider services={services}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
}

describe("推荐详情页：资料来源只写人话", () => {
  const sourceCard = async () => (await screen.findByText("资料来源")).closest(".ps-card") as HTMLElement;

  it("演示推荐：写覆盖范围、“资料状态：演示资料 · 整理于 …”，不写版本号、不写 fixture", async () => {
    const rec = structuredClone(fixtureRecommendation("fx-rec-rich-1"));
    rec.provenance = { ...rec.provenance, generated_at: "2026-09-24T07:10:00Z", fact_version: "facts-2026.09", rule_version: "rules-3", preference_version: 7 };
    renderDetail(rec);
    const card = await sourceCard();
    expect(within(card).getByText(rec.provenance.coverage_note)).toBeTruthy();
    const when = new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date("2026-09-24T07:10:00Z"));
    // 状态和整理时间各占一行
    expect(within(card).getByText("资料状态：演示资料").tagName).toBe("DIV");
    expect(within(card).getByText(`整理于 ${when}`).tagName).toBe("DIV");
    expect(card.textContent).not.toMatch(/版本|第\s*\d+\s*版|facts-2026|rules-3|fixture|live_/);
    expect(document.body.textContent).not.toMatch(/来源与版本/);
  });

  it("核实过一部分的资料：状态写中文；没有平台评分时不再说“演示资料没有”", async () => {
    const rec = structuredClone(fixtureRecommendation("fx-rec-rich-1"));
    rec.provenance = { ...rec.provenance, data_status: "live_partial" };
    rec.branch = { ...rec.branch, ratings: [] };
    renderDetail(rec);
    const card = await sourceCard();
    expect(card.textContent).toMatch(/资料状态：只有一部分资料核实过/);
    expect(card.textContent).toMatch(/平台评分：没有/);
    expect(card.textContent).not.toMatch(/演示资料没有平台评分|live_partial/);
  });

  it("认不出的状态代码：整条状态不显示，不把代码露出来", async () => {
    const rec = structuredClone(fixtureRecommendation("fx-rec-rich-1"));
    rec.provenance = { ...rec.provenance, data_status: "live_unknown_new" as never, generated_at: "not-a-date" };
    renderDetail(rec);
    const card = await sourceCard();
    expect(card.textContent).not.toMatch(/资料状态|整理于|live_unknown_new/);
  });
});

describe("推荐详情页：分店和依据只写人话（主窗口 2026-09-25 追加）", () => {
  const local = (iso: string) => new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(iso));

  it("不露分店编号和内部规则说明；资料里有品牌才写“品牌：…”", async () => {
    const rec = structuredClone(fixtureRecommendation("fx-rec-rich-1"));
    renderDetail(rec);
    const head = (await screen.findByRole("heading", { name: rec.branch.name })).closest(".ps-card") as HTMLElement;
    expect(document.body.textContent).not.toContain(rec.branch.branch_id);
    expect(document.body.textContent).not.toMatch(/分店 ID|命名空间|总店证据/);
    expect(head.textContent).not.toMatch(/品牌：/);
    cleanup();
    renderDetail({ ...rec, branch: { ...rec.branch, brand: "示例清汤面馆" } });
    const withBrand = (await screen.findByRole("heading", { name: rec.branch.name })).closest(".ps-card") as HTMLElement;
    expect(within(withBrand).getByText("品牌：示例清汤面馆")).toBeTruthy();
  });

  it("观察时间按看的人所在时区写“几月几日 几点”；没有时间就整行不显示，不写“未知”", async () => {
    const rec = structuredClone(fixtureRecommendation("fx-rec-rich-1"));
    const [first] = rec.dishes[0].evidence;
    expect(first, "前提：演示推荐的第一道菜有依据").toBeTruthy();
    rec.dishes[0].evidence = [{ ...first, observed_at: "2026-09-20T02:30:00Z", sample_count: 12 }, { ...first, evidence_id: `${first.evidence_id}-b`, observed_at: null }];
    renderDetail(rec);
    await screen.findByText("资料来源");
    const blocks = [...document.querySelectorAll<HTMLElement>(".ps-evidence")];
    expect(blocks).toHaveLength(2);
    expect(within(blocks[0]).getByText(`观察时间 ${local("2026-09-20T02:30:00Z")}`)).toBeTruthy();
    expect(within(blocks[0]).getByText("实际取得样本 12 条")).toBeTruthy();
    expect(blocks[0].textContent).not.toContain("2026-09-20T02:30:00Z");
    // 没有观察时间：样本数照写，时间那一行整行不显示
    expect(within(blocks[1]).getByText("实际取得样本 0 条")).toBeTruthy();
    expect(blocks[1].textContent).not.toMatch(/观察时间|未知/);
  });
});

/* ---------------- 4. 底图：量到小于 64 的尺寸时不请求 ---------------- */

describe("底图请求：容器一时量出过小的尺寸不发请求", () => {
  it("先量到 32×340（整页截图时视口被压成 1px 宽的实测值），再量到 390×540：只请求 384×544，从不请求小于 64 的尺寸", async () => {
    mode.dataMode = "live";
    class SequenceResizeObserver {
      constructor(private readonly callback: ResizeObserverCallback) {}
      observe() {
        this.callback([{ contentRect: { width: 32, height: 340 } } as ResizeObserverEntry], this as unknown as ResizeObserver);
        setTimeout(() => this.callback([{ contentRect: { width: 390, height: 540 } } as ResizeObserverEntry], this as unknown as ResizeObserver), 30);
      }
      unobserve() {}
      disconnect() {}
    }
    vi.stubGlobal("ResizeObserver", SequenceResizeObserver);
    const unavailable: BasemapView = { available: false, reason: "not_configured", provider: null, image_url: null, center: null, zoom: null, width: null, height: null, attribution: null, expires_at: null } as BasemapView;
    const basemap = vi.fn(async (_req: { width: number; height: number }) => unavailable);
    const services = { platform: { meta: vi.fn(), basemap } } as unknown as ServiceMap;
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ServicesProvider services={services}>
          <SchematicMapSurface bounds={[HOME, PATH]} routes={[{ id: "r", points: [HOME, PATH] }]} places={[{ id: "p", at: PATH, name: PATH.name }]} />
        </ServicesProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(basemap).toHaveBeenCalledWith(expect.objectContaining({ width: 384, height: 544 })));
    await new Promise((r) => setTimeout(r, 60));
    const sizes = basemap.mock.calls.map(([req]) => [req.width, req.height]);
    expect(sizes).toEqual([[384, 544]]);
  });
});
