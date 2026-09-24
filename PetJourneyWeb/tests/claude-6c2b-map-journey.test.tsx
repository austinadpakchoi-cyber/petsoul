/**
 * claude-6c2b · 地图第 1 步：地图接上“这趟旅途”（只做 live）。同一家两只：栗子 p-1（当前宠物、在家）、豆包 p-2（出门喝一杯，jn-1）。
 * - 行程快照只为面板上显示的那只读、只读自己家的、W1 journey_id 不为空才读（在家不读）；键 queryKeys.journeyMap(petId)。
 * - 对齐：W1 journey_id 等于快照 journey_id 且快照 lifecycle === "active" 才用；对不上什么都不出，并只重读一次。
 * - W1 这只的 (journey_id, phase, version, until) 一变就让快照失效；保底刷新只在对齐时开。
 * - 提醒：一起听用服务端 entry.label；你已经在一起听时不出现；这趟旅途“到{city}后，让 TA 挑一家”→ /journey/food；
 *   顺序 mail, listen, trip, school, wish, system。
 * - “这趟旅途”面板（?sheet=trip）：路线（“正在走”只认 current_leg_id）、四个链接、journey.cards 插槽整块、数据来源；
 *   ?sheet= 打开用 push、返回键关；和 ?focus= 同时出现时只删 focus；journey.sheet / journey.dock 插槽只在对齐时拿到快照、时间是校准过的真实时间。
 * - 主按钮：在店里（there + visit_id）进店看看；其余看看 TA（只对准，不弹面板）；捎句话一直在。
 * - 演示条控件放大到 40px 后窄屏折两行：镜头把 TA 放在演示条下沿与底部面板之间的正中（AmapView topInset）；live 没有演示条，照旧。
 * 验收后追加（主窗口 2026-09-24）：
 * - 只读自己家的：不在当前家庭名单里的宠物（例如跨家切换时 W1 还没换过来）点了也不读快照。
 * - “进店看看”只在地点确实是店时出现：按这次到访的场景模板（cafe / restaurant），不按名字猜；小路、公园是“看看 TA”。
 * - 高德 Logo 与版权：窄屏时高德不写版权文字，按它的写法补上；两者抬到底部一叠和打开着的底部面板更高的那个之上；
 *   版权字号 ≥ 10px、衬底对比 ≥ 4.5（浅色深色都算）。
 * - 底图没画出来时顶部提示“地图加载中…”，第一块底图图块回来（高德的 complete 在图块到之前就发，不能用）才撤；
 *   超过 15 秒换成“地图还没加载出来”+ 重试（重建地图、重新计时）；减少动态效果不转圈；提示的下沿算进镜头的顶部让位，不压 TA。
 * - 寻味那一行改用 food_discovery 的 foodCardTitle / useFoodPicksAvailable（同城、异地、不知道家在哪、推荐没开）。
 * 第 2 步：标记上的交通方式角标（W1 leg.mode，走路没有）；一起听 / 一起看徽标（companion_media 的 ActivityBadgeFor，只给面板上那只、只在对齐时）。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import type { CompanionSession, DrivingSchoolStatus, HomeSnapshot, HouseholdBrief, JourneyMapSnapshot, SessionState, Visit, WebMeta, WorldPetState, WorldState } from "@/shared/contracts";
import { slot } from "@/shared/modules/types";
import { queryKeys } from "@/shared/query/queryClient";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider, useCurrentHousehold } from "@/shared/session/householdContext";
import { buildSlotRegistry, SlotProvider } from "@/shared/slots/Slot";
import type { JourneyOverlayProps, JourneySheetProps } from "@/shared/slots/names";
import { serverNow } from "@/shared/time/clock";
import type { AMapNamespace } from "@/features/world_map/amapLoader";
import { copyrightText, ensureCopyright } from "@/features/world_map/attribution";
import { isBasemapTile } from "@/features/world_map/basemapReady";
import { MAP_SLOW_MS, MapLoadingHint } from "@/features/world_map/MapLoadingHint";
import { modeBadgeOf } from "@/features/world_map/markers";
import { isAligned, journeyRefetchInterval, JOURNEY_FALLBACK_MS, worldJourneyKey } from "@/features/world_map/journeyDetails";
import { MapHomePage } from "@/features/world_map/MapHomePage";
import { arrangeNotes, type PanelNote } from "@/features/world_map/panelNotes";
import { worldPetFromState } from "@/features/world_map/worldState";

// 默认 live；只有“演示条不压住标记”那条改成 fixture（afterEach 换回）。
const mode = vi.hoisted(() => ({ env: { dataMode: "live" as "live" | "fixture", isDev: false, apiBase: "/api/v1/web" } }));
vi.mock("@/shared/config/env", () => mode);
const player = vi.hoisted(() => ({ current: { sessionId: null as string | null, mode: "not_joined" } }));
vi.mock("@/features/companion_media/playerStore", () => ({ usePlayer: () => player.current }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  delete window.AMap;
  window.sessionStorage.clear();
  player.current = { sessionId: null, mode: "not_joined" };
  mode.env.dataMode = "live";
  FakeMap.framed = [];
  FakeMap.all = [];
  FakeMap.copyright = "";
  vi.useRealTimers();
});

/* ---------------- 高德替身 ---------------- */

class FakeMarker {
  content: HTMLElement;
  position: [number, number] | null = null;
  constructor(options: Record<string, unknown>) {
    this.content = options.content as HTMLElement;
  }
  setPosition(position: [number, number]) {
    this.position = position;
  }
  setzIndex() {}
  show() {}
  hide() {}
}
class FakeShape {
  setPath() {}
  setCenter() {}
  setRadius() {}
  show() {}
  hide() {}
}
class FakeMap {
  /** 每次“对准”时记下：对准前的缩放、给的中心、那一刻各只宠物标记的位置（标记里的名字事后再读：第一次对准时标记内容可能还没渲染进去）。 */
  static framed: Array<{ zoomBefore: number; center: [number, number]; pets: Array<{ marker: FakeMarker; position: [number, number] | null }> }> = [];
  /** 建过的每一张地图（重试会重建）。 */
  static all: FakeMap[] = [];
  /** 高德建地图时往版权里写的字：窄于 350px 时是空的（默认），宽屏时是这一句。 */
  static copyright = "";
  zoom: number;
  center: [number, number];
  markers: FakeMarker[] = [];
  handlers = new Map<string, Array<() => void>>();
  destroyed = false;
  constructor(
    public container: HTMLElement,
    options: Record<string, unknown>,
  ) {
    this.zoom = options.zoom as number;
    this.center = options.center as [number, number];
    // 和高德一样在容器里放 Logo 与版权（版权写不写字看 FakeMap.copyright）。
    const logo = document.createElement("a");
    logo.className = "amap-logo";
    const copyright = document.createElement("div");
    copyright.className = "amap-copyright";
    copyright.style.display = "none";
    if (FakeMap.copyright) copyright.innerHTML = FakeMap.copyright;
    container.append(logo, copyright);
    FakeMap.all.push(this);
  }
  on(event: string, handler: () => void) {
    this.handlers.set(event, [...(this.handlers.get(event) ?? []), handler]);
  }
  emit(event: string) {
    for (const handler of this.handlers.get(event) ?? []) handler();
  }
  add(overlay: unknown) {
    if (overlay instanceof FakeMarker) {
      this.markers.push(overlay);
      this.container.appendChild(overlay.content);
    }
  }
  remove(overlay: unknown) {
    if (overlay instanceof FakeMarker) overlay.content.remove();
  }
  destroy() {
    this.destroyed = true;
    this.container.querySelectorAll(".amap-logo, .amap-copyright").forEach((el) => el.remove());
  }
  setZoomAndCenter(zoom: number, center: [number, number]) {
    const pets = this.markers.filter((m) => m.content.classList.contains("ps-wmap-anchor--pet")).map((marker) => ({ marker, position: marker.position }));
    FakeMap.framed.push({ zoomBefore: this.zoom, center, pets });
    this.zoom = zoom;
    this.center = center;
  }
  panTo(center: [number, number]) {
    this.center = center;
  }
  getZoom() {
    return this.zoom;
  }
  getCenter() {
    return { lng: this.center[0], lat: this.center[1] };
  }
  getResolution() {
    return 1;
  }
  setFitView() {}
  setMapStyle() {}
}
/** 浏览器的 PerformanceObserver 替身：地图靠它看第一块底图图块回来（./basemapReady）；用例用 emit 放一条资源记录进去。 */
class FakePerfObserver {
  static supportedEntryTypes = ["resource"];
  static live = new Set<FakePerfObserver>();
  constructor(private callback: (list: { getEntries(): Array<{ name: string; responseStatus?: number }> }) => void) {}
  observe() {
    FakePerfObserver.live.add(this);
  }
  disconnect() {
    FakePerfObserver.live.delete(this);
  }
  static emit(name: string, responseStatus = 200) {
    for (const observer of [...FakePerfObserver.live]) observer.callback({ getEntries: () => [{ name, responseStatus }] });
  }
}
const TILE = "https://jsapi.amap.com/web_map/get_tile?t=1";
const STYLE = "https://custyle.amap.com/web/rendering/vdata/getMergedStyleData?id=1";

function installFakeAmap() {
  FakePerfObserver.live.clear();
  vi.stubGlobal("PerformanceObserver", FakePerfObserver);
  window.AMap = { Map: FakeMap, Marker: FakeMarker, Polyline: FakeShape, Circle: FakeShape, Pixel: class {} } as unknown as AMapNamespace;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) =>
      String(input).endsWith("/map/config")
        ? Response.json({ provider: "amap", available: true, js_key: "test-only", service_host: "/_AMapService", style: null, style_dark: null, overseas_tiles: false, unavailable_reason: null })
        : new Response("", { status: 404 }),
    ),
  );
}

/* ---------------- 数据 ---------------- */

const HOME = { lat: 24.441642, lng: 118.112039 };
const CAFE = { lat: 24.4452, lng: 118.1063, name: "星球居民开的小咖啡馆" };
const at = (minutes: number) => new Date(Date.now() + minutes * 60_000).toISOString();

type Where = "home" | "going" | "there";
function w1(petId: string, name: string, where: Where, over: { journeyId?: string | null; visitId?: string | null; version?: number; activity?: Record<string, unknown>; legMode?: string } = {}): WorldPetState {
  const home = where === "home";
  return {
    pet_id: petId,
    name,
    species: "cat",
    avatar_url: null,
    relation: petId === "p-1" ? "mine" : "household",
    home: { center: HOME, precision_m: 900, label: "海边" },
    leg: where === "going" ? { mode: over.legMode ?? "walk", route: [HOME, CAFE], departs_at: at(-3), arrives_at: at(5) } : null,
    position: home ? { ...HOME, basis: "home_area", precision_m: 900 } : where === "there" ? { lat: CAFE.lat, lng: CAFE.lng, basis: "place", precision_m: 30 } : { lat: 24.443, lng: 118.109, basis: "route", precision_m: 30 },
    version: over.version ?? 1,
    activity: {
      kind: home ? "home" : "cafe",
      phase: where,
      pose: home ? "idle" : where === "going" ? "walking" : "cafe",
      title: home ? "在小窝" : "去附近喝一杯",
      doing: null,
      place: home ? null : { name: CAFE.name, lat: CAFE.lat, lng: CAFE.lng, attribution: null },
      since: home ? null : at(-3),
      until: home ? null : at(5),
      job: null,
      journey_id: home ? null : over.journeyId === undefined ? "jn-1" : over.journeyId,
      visit_id: home ? null : over.visitId === undefined ? "vs-1" : over.visitId,
      ...over.activity,
    },
  } as unknown as WorldPetState;
}

function leg(id: string, sequence: number, phase: string, from: string, to: string, departMin: number, arriveMin: number) {
  const node = (name: string) => ({ name, lat: HOME.lat, lng: HOME.lng, timezone: "Asia/Hong_Kong", kind: "place" });
  return {
    leg_id: id,
    journey_id: "jn-1",
    sequence,
    kind: "main",
    mode: "walk",
    role: "passenger",
    world_service: null,
    origin: node(from),
    destination: node(to),
    times: { origin_timezone: "Asia/Hong_Kong", destination_timezone: "Asia/Hong_Kong", planned_departure_utc: at(departMin), planned_arrival_utc: at(arriveMin) },
    time_basis: "routed_estimate",
    freshness: "live",
    position_basis: "route",
    phase,
    itinerary_version: 1,
    route: [],
    reference: null,
    rescheduled_reason: null,
  };
}

function snapshot(over: Partial<JourneyMapSnapshot> = {}): JourneyMapSnapshot {
  return {
    journey_id: "jn-1",
    pet_id: "p-2",
    itinerary_version: 1,
    lifecycle: "active",
    destination_title: "星球居民开的小咖啡馆",
    current_visit_id: null,
    planned_visit_id: "vs-1",
    server_time: new Date().toISOString(),
    // 当前段是第二段（快照 current_leg_id）；W1 的 leg 是主段，面板不拿它判断在哪一段。
    legs: [leg("lg-1", 1, "arrived", "家", "星球居民开的小咖啡馆", -20, -10), leg("lg-2", 2, "in_transit", "星球居民开的小咖啡馆", "家", -3, 5)],
    current_leg_id: "lg-2",
    vehicle: null,
    activities: [],
    activity_entries: [
      { entry_id: "e-old", leg_id: "lg-1", activity_id: "a-old", badge: "music", badge_state: "active", media_session_id: "ms-old", label: "TA 在听《上一段的歌》", actions: ["join", "solo", "open_leg_card"] },
      { entry_id: "e-2", leg_id: "lg-2", activity_id: "a-2", badge: "music", badge_state: "active", media_session_id: "ms-2", label: "TA 在听《窗边的小调》", actions: ["join", "solo", "open_leg_card"] },
    ],
    arrival_context: { journey_id: "jn-1", itinerary_version: 1, leg_id: "lg-2", city: "香港", destination_timezone: "Asia/Hong_Kong", feasible_arrival_utc: at(5), stay_window_start_utc: at(5), stay_window_end_utc: at(30) },
    data_origin: "live",
    catching_up: false,
    ...over,
  } as unknown as JourneyMapSnapshot;
}

const household = {
  household_id: "hh-1",
  name: "我们的家",
  role: "admin",
  home_activated: true,
  pets: [
    { pet_id: "p-1", name: "栗子", species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true },
    { pet_id: "p-2", name: "豆包", species: "cat", photo_url: null, origin: "own_pet", presence: "traveling", join_step: "moved_in", joined_at: "2026-09-21T00:00:00Z", added_by_you: true },
  ],
} as unknown as HouseholdBrief;
const signedIn = { authenticated: true, user: { user_id: "u-1" }, csrf_required: false, expires_at: null, onboarding: { step: "active" } } as unknown as SessionState;
const NO_SCHOOL = { stage: "none", wish_text: null, enrolled_at: null, coach: { name: "", line: "", intro: "" }, subjects: [], open_session: null, license: null, voucher_available: false, ceremony_done: false, temperament: "steady", rules_version: "v1", server_time: new Date().toISOString() } as unknown as DrivingSchoolStatus;

function strictServices(provided: Record<string, unknown>): ServiceMap {
  return new Proxy(provided as unknown as ServiceMap, {
    get: (target, key) => {
      if (typeof key === "string" && key in target) return (target as unknown as Record<string, unknown>)[key];
      throw new Error(`unexpected service ${String(key)}`);
    },
  });
}

function CurrentPet({ page }: { page: string }) {
  const { pet } = useCurrentHousehold();
  return <output data-testid="current-pet">{`${page}:${pet?.pet_id ?? "-"}`}</output>;
}

/** 插槽替身：记下拿到的 props（只在对齐时才该被渲染）。 */
const seen = { sheet: [] as JourneySheetProps[], dock: [] as JourneyOverlayProps[], cards: [] as JourneyOverlayProps[] };
function FakeSheet(props: JourneySheetProps) {
  seen.sheet.push(props);
  return (
    <section role="dialog" aria-label={`插槽面板 ${props.kind}:${props.targetId}`}>
      <button type="button" onClick={props.close}>
        收起插槽面板
      </button>
    </section>
  );
}
function FakeDock(props: JourneyOverlayProps) {
  seen.dock.push(props);
  return <div data-testid="fake-dock">播放条</div>;
}
function FakeCards(props: JourneyOverlayProps) {
  seen.cards.push(props);
  return <div data-testid="fake-cards">卡片区（{props.snapshot.journey_id}）</div>;
}

interface Setup {
  doubao?: Where;
  doubaoOver?: Parameters<typeof w1>[3];
  map?: (petId: string) => Promise<JourneyMapSnapshot>;
  entry?: string;
  /** W1 里另外的宠物（不在当前家庭名单里）。 */
  extra?: WorldPetState[];
  /** 到访（GET /visits/:id）：默认场景模板是 cafe。 */
  visit?: (visitId: string) => Promise<Visit>;
  /** 面板上这只的家在哪座城市（家园快照 place.city）：默认厦门（替身的 HOME 坐标就在厦门）；null = 家园快照里没有 place。 */
  homeCity?: string | null;
  /** /meta 里 food.recommendations 的状态：默认 available。 */
  food?: "available" | "not_configured";
  /** 媒体会话此刻的状态（GET /media/sessions/:id，徽标读）：默认 playing。 */
  mediaState?: "playing" | "paused" | "interrupted" | "ended";
}

function visitOf(visitId: string, template: Visit["template"], name: string): Visit {
  return {
    visit_id: visitId,
    journey_id: "jn-1",
    pet_id: "p-2",
    place: { provider: "world", place_id: `pl-${visitId}`, name, address: null, lat: CAFE.lat, lng: CAFE.lng, coord_system: "wgs84", category: null, source_updated_at: null, attribution: null, data_origin: "live" },
    state: "active",
    template,
    planned_arrival_utc: null,
    arrived_at: at(-2),
    leaving_at: at(20),
    recommendation_id: null,
    activities: [],
    interior_is_original: true,
    data_origin: "live",
  } as unknown as Visit;
}

function renderMapApp({ doubao = "going", doubaoOver = {}, map, entry = "/map", extra = [], visit, homeCity = "厦门", food = "available", mediaState = "playing" }: Setup = {}) {
  installFakeAmap();
  seen.sheet = [];
  seen.dock = [];
  seen.cards = [];
  const pets = { current: [w1("p-1", "栗子", "home"), w1("p-2", "豆包", doubao, doubaoOver), ...extra] };
  const state = vi.fn(async (_petId?: string, _signal?: AbortSignal): Promise<WorldState> => ({ server_time: new Date().toISOString(), coord_system: "wgs84", cache_seconds: 15, pets: pets.current }) as WorldState);
  const journeyMap = vi.fn(map ?? (async (_petId: string) => snapshot()));
  const visitRead = vi.fn(visit ?? (async (visitId: string) => visitOf(visitId, "cafe", CAFE.name)));
  const home = vi.fn(async (_petId?: string | null, _signal?: AbortSignal) => ({ unread: { messages: 0, circle: 0 }, catching_up: false, place: homeCity ? { city: homeCity } : null }) as unknown as HomeSnapshot);
  const meta = vi.fn(async () => ({ capabilities: [{ key: "food.recommendations", status: food, module: "food_discovery", note: null }] }) as unknown as WebMeta);
  const session = vi.fn(async (sessionId: string) => ({ session_id: sessionId, state: mediaState }) as unknown as CompanionSession);
  const services = strictServices({
    session: { current: async () => signedIn },
    households: { list: async () => [household] },
    world: { state, home },
    driving: { status: async () => NO_SCHOOL },
    visits: { travelWish: async () => null, visit: visitRead },
    transport: { journeyMap },
    platform: { meta },
    companionMedia: { session },
  });
  const registry = buildSlotRegistry([slot("journey.sheet", "fake.sheet", FakeSheet), slot("journey.dock", "fake.dock", FakeDock), slot("journey.cards", "fake.cards", FakeCards)]);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const target = (page: string) => (
    <HouseholdProvider userId="u-1">
      <CurrentPet page={page} />
    </HouseholdProvider>
  );
  const router = createMemoryRouter(
    [
      { path: "/map", element: <MapHomePage /> },
      { path: "/home", element: target("小窝") },
      { path: "/communicator", element: target("通讯器") },
      { path: "/collection", element: target("收藏") },
      { path: "/journey/food", element: target("寻味") },
      { path: "/visits/:visitId", element: target("到访") },
    ],
    { initialEntries: [entry] },
  );
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <SlotProvider registry={registry}>
          <RouterProvider router={router} />
        </SlotProvider>
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { router, client, state, journeyMap, pets, visitRead, meta, session };
}

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 60));
  });
const itemsOf = (group: HTMLElement) => within(group).getAllByRole("listitem").map((li) => li.textContent);

async function showDoubao(): Promise<HTMLElement> {
  await screen.findByRole("region", { name: "栗子此刻" });
  fireEvent.click(await screen.findByRole("button", { name: /^豆包/ }));
  return screen.findByRole("region", { name: "豆包此刻" });
}

/* ---------------- 规则（纯函数） ---------------- */

describe("第 1 步 · 对齐与刷新的规则", () => {
  it("对齐 = journey_id 相同且 lifecycle 是 active；保底刷新只在对齐时开（45 秒）", () => {
    expect(isAligned(snapshot(), "jn-1")).toBe(true);
    expect(isAligned(snapshot(), "jn-2")).toBe(false);
    expect(isAligned(snapshot({ lifecycle: "completed" }), "jn-1")).toBe(false);
    expect(isAligned(snapshot(), null)).toBe(false);
    expect(isAligned(undefined, "jn-1")).toBe(false);
    expect(journeyRefetchInterval(snapshot(), "jn-1")).toBe(JOURNEY_FALLBACK_MS);
    expect(JOURNEY_FALLBACK_MS).toBeGreaterThanOrEqual(30_000);
    expect(JOURNEY_FALLBACK_MS).toBeLessThanOrEqual(60_000);
    expect(journeyRefetchInterval(snapshot(), "jn-2")).toBe(false);
    expect(journeyRefetchInterval(undefined, "jn-1")).toBe(false);
  });

  it("W1 这只的 (journey_id, phase, version, until) 四样任一变了，键就变", () => {
    const base = worldPetFromState(w1("p-2", "豆包", "going"));
    const key = worldJourneyKey(base);
    expect(worldJourneyKey(worldPetFromState(w1("p-2", "豆包", "going", { version: 2 })))).not.toBe(key);
    expect(worldJourneyKey(worldPetFromState(w1("p-2", "豆包", "there")))).not.toBe(key);
    expect(worldJourneyKey(worldPetFromState(w1("p-2", "豆包", "going", { journeyId: "jn-9" })))).not.toBe(key);
    expect(worldJourneyKey({ ...base, activity: { ...base.activity, until: (base.activity.until ?? 0) + 60_000 } })).not.toBe(key);
  });

  it("提醒顺序：mail, listen, trip, school, wish, system", () => {
    const kinds = ["system", "wish", "school", "trip", "listen", "mail"] as const;
    const notes: PanelNote[] = kinds.map((kind) => ({ id: kind, kind, text: kind }));
    expect(arrangeNotes(notes, null).map((n) => n.kind)).toEqual(["mail", "listen", "trip", "school", "wish", "system"]);
  });
});

/* ---------------- 什么时候读快照 ---------------- */

describe("第 1 步 · 什么时候读行程快照", () => {
  it("面板是在家的栗子：不读；点出门的豆包（自家）才按豆包读，键是 journeyMap(p-2)", async () => {
    const { journeyMap, client } = renderMapApp();
    await screen.findByRole("region", { name: "栗子此刻" });
    await settle();
    expect(journeyMap).not.toHaveBeenCalled();
    await showDoubao();
    await waitFor(() => expect(journeyMap).toHaveBeenCalled());
    expect(journeyMap.mock.calls.map((c) => c[0])).toEqual(["p-2"]);
    expect(client.getQueryData(queryKeys.journeyMap("p-2"))).toBeTruthy();
  });

  it("豆包也在家：谁都不读（也不为寻味那一行去问 /meta：没有到达上下文就用不着）", async () => {
    const { journeyMap, meta } = renderMapApp({ doubao: "home" });
    await showDoubao();
    await settle();
    expect(journeyMap).not.toHaveBeenCalled();
    expect(meta).not.toHaveBeenCalled();
  });

  it("只读自己家的：不在当前家庭名单里的小橘（例如跨家切换时 W1 还没换过来）出门在外，点它也不读、不出这趟旅途；点自家的豆包照常读", async () => {
    const { journeyMap } = renderMapApp({ extra: [w1("p-3", "小橘", "going", { journeyId: "jn-3" })] });
    await screen.findByRole("region", { name: "栗子此刻" });
    fireEvent.click(await screen.findByRole("button", { name: /^小橘/ }));
    const panel = await screen.findByRole("region", { name: "小橘此刻" });
    await settle();
    await settle();
    expect(journeyMap).not.toHaveBeenCalled();
    expect(within(panel).queryByRole("button", { name: /这趟旅途/ })).toBeNull();
    // 对照：同样出门在外、在家庭名单里的豆包，点它就按它读（证明上面不读不是因为点不到）。
    fireEvent.click(await screen.findByRole("button", { name: /^豆包/ }));
    await screen.findByRole("region", { name: "豆包此刻" });
    await waitFor(() => expect(journeyMap).toHaveBeenCalled());
    expect(journeyMap.mock.calls.map((c) => c[0])).toEqual(["p-2"]);
  });

  it.each([
    ["journey_id 不同（快照还是上一趟）", () => snapshot({ journey_id: "jn-0" })],
    ["lifecycle 不是 active（已经结束）", () => snapshot({ lifecycle: "completed" })],
  ])("对不上：%s——不出现任何快照派生的东西，并且只重读一次", async (_label, make) => {
    const { journeyMap } = renderMapApp({ map: async () => make() });
    const panel = await showDoubao();
    await waitFor(() => expect(journeyMap).toHaveBeenCalledTimes(2));
    await settle();
    await settle();
    expect(journeyMap).toHaveBeenCalledTimes(2);
    expect(within(panel).queryByRole("button", { name: /这趟旅途/ })).toBeNull();
    expect(within(panel).queryByText(/一起听|挑一家/)).toBeNull();
    expect(screen.queryByTestId("fake-dock")).toBeNull();
  });

  it("W1 这只的 version 变了：让快照失效、重读（查询键不变）", async () => {
    const { journeyMap, client, pets } = renderMapApp();
    await showDoubao();
    await waitFor(() => expect(journeyMap).toHaveBeenCalledTimes(1));
    pets.current = [w1("p-1", "栗子", "home"), w1("p-2", "豆包", "going", { version: 2 })];
    await act(async () => {
      await client.refetchQueries({ queryKey: queryKeys.worldStateFor("u-1") });
    });
    await waitFor(() => expect(journeyMap).toHaveBeenCalledTimes(2));
  });
});

/* ---------------- 提醒、按钮、面板 ---------------- */

describe("第 1 步 · 对齐后的提醒、按钮与“这趟旅途”面板", () => {
  it("对齐：一起听（服务端 label，只看 current_leg_id 那一段）排在这趟旅途前面；面板多一行“这趟旅途”；播放条在底部那一叠里、面板上方", async () => {
    renderMapApp();
    const panel = await showDoubao();
    const group = await within(panel).findByRole("group", { name: "提醒，共 2 条" });
    fireEvent.click(within(group).getByRole("button", { name: "还有 1 条" }));
    // 验收追加（寻味标题改用 food_discovery 的 foodCardTitle）：改前这一句“到香港后，让 TA 挑一家”是 journeyNotes 写死的；
    // 改后按家所在的城市算——替身的家在厦门（家园快照 place.city），这趟去香港，是“异地”，所以还是这一句。
    // 同城、不知道家在哪、推荐没开，见下面“验收追加 · 寻味那一行”。
    expect(itemsOf(group)).toEqual(["TA 在听《窗边的小调》 · 一起听", "到香港后，让 TA 挑一家"]);
    expect(within(group).getByRole("link", { name: /挑一家/ }).getAttribute("href")).toBe("/journey/food");
    // 说明只用服务端的 destination_title 原样（live 里它本身就是“去附近喝一杯”这类说法，不再加“去”）。
    expect(within(panel).getByRole("button", { name: /这趟旅途/ }).textContent).toBe("这趟旅途星球居民开的小咖啡馆");
    const dock = screen.getByTestId("fake-dock");
    const bottom = dock.closest(".ps-wmap-bottom");
    expect(bottom).toBeTruthy();
    expect(dock.compareDocumentPosition(panel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(seen.dock.at(-1)?.snapshot.journey_id).toBe("jn-1");
  });

  it("你已经在一起听这一段：一起听那一行不出现（这趟旅途照常）", async () => {
    player.current = { sessionId: "ms-2", mode: "synced" };
    renderMapApp();
    const panel = await showDoubao();
    const group = await within(panel).findByRole("group", { name: "提醒，共 1 条" });
    // 改前改后同上一条：家在厦门、这趟去香港（异地），标题由 foodCardTitle 算出来还是这一句。
    expect(itemsOf(group)).toEqual(["到香港后，让 TA 挑一家"]);
  });

  it("一起听点开：地图上打开播放面板（journey.sheet 插槽：media、会话 id、对齐的快照、校准过的真实时间），不换当前宠物；收起就关", async () => {
    const { router } = renderMapApp();
    const panel = await showDoubao();
    fireEvent.click(await within(panel).findByRole("link", { name: /一起听/ }));
    expect(await screen.findByRole("dialog", { name: "插槽面板 media:ms-2" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/map");
    const props = seen.sheet.at(-1)!;
    expect([props.kind, props.targetId, props.snapshot.journey_id]).toEqual(["media", "ms-2", "jn-1"]);
    expect(Math.abs(props.nowMs - serverNow())).toBeLessThan(5_000);
    expect(window.sessionStorage.getItem("petsoul:current-pet:u-1")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "收起插槽面板" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: /插槽面板/ })).toBeNull());
    expect(router.state.location.search).toBe("");
  });

  it("这趟旅途：按钮用 push 打开 ?sheet=trip；路线“正在走”只认 current_leg_id；四个链接；卡片插槽整块在里面；点一段看行程卡；返回键关掉", async () => {
    const { router } = renderMapApp();
    const panel = await showDoubao();
    fireEvent.click(await within(panel).findByRole("button", { name: /这趟旅途/ }));
    const sheet = await screen.findByRole("dialog", { name: /这趟旅途/ });
    expect(router.state.location.search).toBe("?sheet=trip");
    expect(router.state.historyAction).toBe("PUSH");
    const legs = within(sheet).getAllByRole("listitem").map((li) => li.textContent ?? "");
    expect(legs[0]).toContain("走过了");
    expect(legs[1]).toContain("正在走");
    const links = within(within(sheet).getByRole("navigation", { name: "这趟旅途的记录" }).parentElement!).getAllByRole("link").map((a) => `${a.textContent}→${a.getAttribute("href")}`);
    expect(links).toEqual(["手账→/guides?journey=jn-1", "旅途来信→/communicator?channel=family", "带回的收藏→/collection", "照片→/photos?scene=train"]);
    expect(within(sheet).getByTestId("fake-cards").textContent).toContain("jn-1");
    fireEvent.click(within(sheet).getByRole("button", { name: /星球居民开的小咖啡馆 → 家/ }));
    expect(await screen.findByRole("dialog", { name: "插槽面板 leg:lg-2" })).toBeTruthy();
    await act(async () => {
      await router.navigate(-1);
    });
    expect(await screen.findByRole("dialog", { name: /这趟旅途/ })).toBeTruthy();
    await act(async () => {
      await router.navigate(-1);
    });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: /这趟旅途/ })).toBeNull());
    expect(router.state.location.search).toBe("");
  });

  it("这趟旅途面板里去别的页面：先把当前宠物换成豆包（带回的收藏 → /collection 时当前宠物是豆包）", async () => {
    renderMapApp();
    const panel = await showDoubao();
    fireEvent.click(await within(panel).findByRole("button", { name: /这趟旅途/ }));
    const sheet = await screen.findByRole("dialog", { name: /这趟旅途/ });
    fireEvent.click(within(sheet).getByRole("link", { name: /带回的收藏/ }));
    expect((await screen.findByTestId("current-pet")).textContent).toBe("收藏:p-2");
  });

  it("?focus= 和 ?sheet= 同时：只删 focus，面板保留（刷新 / 深链也能打开）", async () => {
    const { router } = renderMapApp({ entry: "/map?focus=p-2&sheet=trip" });
    expect(await screen.findByRole("dialog", { name: /这趟旅途/ })).toBeTruthy();
    await waitFor(() => expect(router.state.location.search).toBe("?sheet=trip"));
    expect(await screen.findByRole("region", { name: "豆包此刻" })).toBeTruthy();
  });

  it("没对齐时地址里的 sheet 不出任何面板（也不把快照交给插槽）", async () => {
    renderMapApp({ entry: "/map?focus=p-2&sheet=media:ms-2", map: async () => snapshot({ journey_id: "jn-0" }) });
    await screen.findByRole("region", { name: "豆包此刻" });
    await settle();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(seen.sheet).toHaveLength(0);
    expect(seen.dock).toHaveLength(0);
  });
});

describe("第 1 步 · 主按钮随 W1", () => {
  it("在店里（there + visit_id，这次到访的场景模板是 cafe）：进店看看 → /visits/vs-1，先把当前宠物换成豆包；捎句话还在", async () => {
    const { visitRead } = renderMapApp({ doubao: "there" });
    const panel = await showDoubao();
    expect(within(panel).getByRole("link", { name: /捎句话/ })).toBeTruthy();
    fireEvent.click(await within(panel).findByRole("link", { name: /进店看看/ }));
    expect((await screen.findByTestId("current-pet")).textContent).toBe("到访:p-2");
    expect(visitRead.mock.calls.map((c) => c[0])).toEqual(["vs-1"]);
  });

  it.each([
    ["小路（park）：W1 说在“家附近的星球小路”", "park", { kind: "stroll", place: { name: "家附近的星球小路", lat: CAFE.lat, lng: CAFE.lng, attribution: null } }],
    ["名字像店也不算（park）：W1 的地名是“星球居民开的小咖啡馆”、kind 是 cafe", "park", {}],
    ["打工的地方（generic）", "generic", { kind: "job" }],
  ] as const)("不是店：%s——看看 TA，没有进店看看（按到访的场景模板，不按名字、不按 kind）", async (_label, template, activity) => {
    const { visitRead } = renderMapApp({ doubao: "there", doubaoOver: { activity }, visit: async (id) => visitOf(id, template, "随便什么名字") });
    const panel = await showDoubao();
    await waitFor(() => expect(visitRead).toHaveBeenCalled());
    await settle();
    expect(within(panel).queryByRole("link", { name: /进店看看/ })).toBeNull();
    expect(within(panel).getByRole("button", { name: /看看 TA/ })).toBeTruthy();
  });

  it("是店（cafe）哪怕 W1 把它报成散步（kind = stroll，后端 local:cafe 的现状）、地名也不像店：进店看看", async () => {
    renderMapApp({ doubao: "there", doubaoOver: { activity: { kind: "stroll", place: { name: "家附近的星球小路", lat: CAFE.lat, lng: CAFE.lng, attribution: null } } } });
    const panel = await showDoubao();
    expect(await within(panel).findByRole("link", { name: /进店看看/ })).toBeTruthy();
  });

  it("只读自己家的：不在当前家庭名单里的小橘在店里（there + visit_id），点它不读到访、不出进店看看", async () => {
    const { visitRead } = renderMapApp({ doubao: "home", extra: [w1("p-3", "小橘", "there", { journeyId: "jn-3", visitId: "vs-3" })] });
    await screen.findByRole("region", { name: "栗子此刻" });
    fireEvent.click(await screen.findByRole("button", { name: /^小橘/ }));
    const panel = await screen.findByRole("region", { name: "小橘此刻" });
    await settle();
    await settle();
    expect(visitRead).not.toHaveBeenCalled();
    expect(within(panel).queryByRole("link", { name: /进店看看/ })).toBeNull();
  });

  it("到访读不到：按不是店处理（看看 TA），面板照常", async () => {
    renderMapApp({ doubao: "there", visit: async () => Promise.reject(new Error("boom")) });
    const panel = await showDoubao();
    await settle();
    expect(within(panel).queryByRole("link", { name: /进店看看/ })).toBeNull();
    expect(within(panel).getByRole("button", { name: /看看 TA/ })).toBeTruthy();
  });

  it("在路上（visit_id 只是计划）：看看 TA（只对准，不弹面板）；没有进店看看，也不去读到访", async () => {
    const { router, visitRead } = renderMapApp({ doubao: "going" });
    const panel = await showDoubao();
    expect(within(panel).queryByRole("link", { name: /进店看看/ })).toBeNull();
    fireEvent.click(within(panel).getByRole("button", { name: /看看 TA/ }));
    await settle();
    expect(router.state.location.search).toBe("");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(visitRead).not.toHaveBeenCalled();
  });

  it("在店外的地方（there 但没有 visit_id）：看看 TA", async () => {
    renderMapApp({ doubao: "there", doubaoOver: { visitId: null } });
    const panel = await showDoubao();
    expect(within(panel).queryByRole("link", { name: /进店看看/ })).toBeNull();
    expect(within(panel).getByRole("button", { name: /看看 TA/ })).toBeTruthy();
  });
});

describe("第 1 步 · 演示条不压住 TA 的标记", () => {
  /**
   * 320×568 的版面：演示条控件放大到 40px 后折成两行（下沿 131）；底部面板 + 标签栏一叠 300 高。
   * hint：底图加载提示的上下沿（验收追加；不给就当它不占位——下面两条第 1 步的用例是这种情况）。
   */
  function stubLayout(hint: [number, number] | null = null) {
    const rects: Array<[string, number, number]> = [
      ["ps-wmap", 0, 568],
      ["ps-wmap-demo", 10, 131],
      ["ps-wmap-bottom", 268, 568],
      ...(hint ? [["ps-wmap-loading", hint[0], hint[1]] as [string, number, number]] : []),
    ];
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      const hit = rects.find(([cls]) => this.classList.contains(cls));
      const [top, bottom] = hit ? [hit[1], hit[2]] : [0, 0];
      return { x: 0, y: top, top, bottom, left: 0, right: 320, width: 320, height: bottom - top, toJSON: () => ({}) } as DOMRect;
    });
  }
  /** 像素换成纬度差（FakeMap.getResolution() = 1 米/像素，按目标缩放 16 折算）。 */
  const shiftDeg = (px: number, zoomBefore: number) => (px * 2 ** (zoomBefore - 16)) / 111_320;
  const framedOn = (name: string, index = 0) => {
    const call = FakeMap.framed[index];
    const labelOf = (marker: FakeMarker) => marker.content.querySelector("[aria-label]")?.getAttribute("aria-label") ?? "";
    const pet = call.pets.find(({ marker }) => labelOf(marker).startsWith(name))?.position ?? null;
    return { ...call, pet };
  };
  /** 第 index 次对准时，镜头中心在 TA 南边 px 像素。 */
  const expectShift = (name: string, index: number, px: number) => {
    const { zoomBefore, center, pet } = framedOn(name, index);
    expect(pet).not.toBeNull();
    expect(center[0]).toBeCloseTo(pet![0], 12);
    expect(center[1]).toBeCloseTo(pet![1] - shiftDeg(px, zoomBefore), 12);
  };

  it("验收追加 · live：底图加载提示在的时候（上下沿 16–62）镜头也让开它——TA 落在提示下沿与底部面板之间（(300 − 62)/2）；图块回来提示撤掉后再对准，照旧按 300/2", async () => {
    stubLayout([16, 62]);
    renderMapApp();
    await screen.findByText("地图加载中…");
    await waitFor(() => expect(FakeMap.framed.length > 0 && framedOn("栗子").pet).toBeTruthy());
    expectShift("栗子", 0, (300 - 62) / 2);
    act(() => FakePerfObserver.emit(TILE));
    await waitFor(() => expect(screen.queryByText("地图加载中…")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "定位 TA" }));
    await waitFor(() => expect(FakeMap.framed.length).toBe(2));
    expectShift("栗子", 1, 300 / 2);
  });

  it("验收追加 · 演示：提示在演示条下面（139–171）——两者取更低的那条下沿（(300 − 171)/2）；提示撤掉后按演示条（(300 − 131)/2）", async () => {
    mode.env.dataMode = "fixture";
    stubLayout([139, 171]);
    renderMapApp();
    await screen.findByText("演示剧本 · 不是真实数据");
    await screen.findByText("地图加载中…");
    await waitFor(() => expect(FakeMap.framed.length > 0 && framedOn("团子").pet).toBeTruthy());
    expectShift("团子", 0, (300 - 171) / 2);
    act(() => FakePerfObserver.emit(TILE));
    await waitFor(() => expect(screen.queryByText("地图加载中…")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "定位 TA" }));
    await waitFor(() => expect(FakeMap.framed.length).toBe(2));
    expectShift("团子", 1, (300 - 131) / 2);
  });

  it("演示：镜头中心在 TA 南边 (300 − 131)/2 像素——TA 落在演示条下沿与底部面板上沿之间那块地图的正中", async () => {
    mode.env.dataMode = "fixture";
    stubLayout();
    renderMapApp();
    await screen.findByText("演示剧本 · 不是真实数据");
    await waitFor(() => expect(FakeMap.framed.length > 0 && framedOn("团子").pet).toBeTruthy());
    const { zoomBefore, center, pet } = framedOn("团子");
    expect(pet).not.toBeNull();
    expect(center[0]).toBeCloseTo(pet![0], 12);
    expect(center[1]).toBeCloseTo(pet![1] - shiftDeg((300 - 131) / 2, zoomBefore), 12);
  });

  it("live 没有演示条：照旧只按底部一叠的一半偏（300/2 像素）", async () => {
    stubLayout();
    renderMapApp();
    await screen.findByRole("region", { name: "栗子此刻" });
    await waitFor(() => expect(FakeMap.framed.length > 0 && framedOn("栗子").pet).toBeTruthy());
    const { zoomBefore, center, pet } = framedOn("栗子");
    expect(pet).not.toBeNull();
    expect(center[0]).toBeCloseTo(pet![0], 12);
    expect(center[1]).toBeCloseTo(pet![1] - shiftDeg(300 / 2, zoomBefore), 12);
  });
});

/* ---------------- 验收追加：寻味那一行 ---------------- */

describe("验收追加 · 寻味那一行（food_discovery 的 foodCardTitle / useFoodPicksAvailable）", () => {
  it.each([
    ["同城：家在香港、这趟也在香港", "香港", "让 TA 在附近挑一家"],
    ["异地：家在厦门、这趟去香港", "厦门", "到香港后，让 TA 挑一家"],
    ["不知道家在哪座城市（家园快照没有 place）", null, "让 TA 在香港挑一家"],
  ] as const)("%s → “%s”那一行写“%s”，点它去 /journey/food", async (_label, homeCity, text) => {
    const { meta } = renderMapApp({ homeCity });
    const panel = await showDoubao();
    const group = await within(panel).findByRole("group", { name: "提醒，共 2 条" });
    fireEvent.click(within(group).getByRole("button", { name: "还有 1 条" }));
    await waitFor(() => expect(itemsOf(group)).toEqual(["TA 在听《窗边的小调》 · 一起听", text]));
    expect(within(group).getByRole("link", { name: text }).getAttribute("href")).toBe("/journey/food");
    expect(meta).toHaveBeenCalled();
  });

  it("推荐没开（/meta 里 food.recommendations 不是 available）：寻味那一行不出现；一起听、“这趟旅途”按钮照常", async () => {
    const { meta } = renderMapApp({ food: "not_configured" });
    const panel = await showDoubao();
    await waitFor(() => expect(meta).toHaveBeenCalled());
    const group = await within(panel).findByRole("group", { name: "提醒，共 1 条" });
    await settle();
    expect(itemsOf(group)).toEqual(["TA 在听《窗边的小调》 · 一起听"]);
    expect(within(panel).queryByText(/挑一家/)).toBeNull();
    expect(within(panel).getByRole("button", { name: /这趟旅途/ })).toBeTruthy();
  });
});

/* ---------------- 验收追加：高德 Logo 与版权 ---------------- */

const SRC = resolve(dirname(fileURLToPath(import.meta.url)), "..", "src");
type CssRule = { selector: string; context: string; decls: Map<string, string> };

/** 去掉注释后逐条取规则：选择器（空白归一）、所在 @ 规则、声明。 */
function cssRules(rel: string): CssRule[] {
  const src = readFileSync(resolve(SRC, rel), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const rules: CssRule[] = [];
  const stack: string[] = [];
  let buf = "";
  for (const ch of src) {
    if (ch === "{") {
      stack.push(buf.trim().replace(/\s+/g, " "));
      buf = "";
    } else if (ch === "}") {
      const prelude = stack.pop() ?? "";
      if (!prelude.startsWith("@")) {
        const decls = new Map<string, string>();
        for (const part of buf.split(";")) {
          const at = part.indexOf(":");
          if (at > 0) decls.set(part.slice(0, at).trim(), part.slice(at + 1).trim());
        }
        rules.push({ selector: prelude, context: stack.filter((s) => s.startsWith("@")).join(" "), decls });
      }
      buf = "";
    } else {
      buf += ch;
    }
  }
  return rules;
}

const DARK = "@media (prefers-color-scheme: dark)";

/** 令牌的值：浅色取 :root；深色先看深色段里的 :root 有没有改。 */
function token(name: string, dark: boolean): string {
  const rules = cssRules("shared/theme/tokens.css").filter((r) => r.selector === ":root");
  const light = rules.find((r) => r.context === "" && r.decls.has(name))?.decls.get(name);
  const darkValue = rules.find((r) => r.context === DARK && r.decls.has(name))?.decls.get(name);
  const value = dark ? darkValue ?? light : light;
  if (!value) throw new Error(`令牌 ${name} 没有定义`);
  return value;
}

function colorOf(value: string, dark: boolean): [number, number, number] {
  const ref = /^var\((--[\w-]+)\)$/.exec(value.trim());
  const hex = ref ? token(ref[1], dark) : value.trim();
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex);
  if (!m) throw new Error(`算不了对比度的颜色：${value}（${hex}）`);
  const full = m[1].length === 3 ? [...m[1]].map((c) => c + c).join("") : m[1];
  return [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16)) as [number, number, number];
}

function contrast(a: [number, number, number], b: [number, number, number]): number {
  const lum = (rgb: [number, number, number]) => {
    const [r, g, bl] = rgb.map((c) => {
      const s = c / 255;
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** 某个选择器在浅色（或叠上深色段）下最终的声明。 */
function finalDecls(rel: string, selector: string, dark: boolean): Map<string, string> {
  const merged = new Map<string, string>();
  for (const rule of cssRules(rel)) {
    const hit = rule.selector.split(",").map((s) => s.trim()).includes(selector);
    if (hit && (rule.context === "" || (dark && rule.context === DARK))) for (const [k, v] of rule.decls) merged.set(k, v);
  }
  return merged;
}

describe("验收追加 · 高德 Logo 与版权一直完整可见", () => {
  it("ensureCopyright：高德没写字（窄于 350px）时按它的写法补上“© 年份 AutoNavi”并挂好审图号的位置；补一次就够（再调不重复）；高德写了字的不动", () => {
    const narrow = document.createElement("div");
    narrow.innerHTML = '<a class="amap-logo"></a><div class="amap-copyright" style="display: none;"></div>';
    ensureCopyright(narrow, 2026);
    ensureCopyright(narrow, 2026);
    const el = narrow.querySelector(".amap-copyright") as HTMLElement & { mapNumber?: HTMLElement };
    expect(el.textContent).toBe(copyrightText(2026));
    expect(copyrightText(2026)).toBe("© 2026 AutoNavi ");
    expect(el.querySelectorAll(".amap-mcode")).toHaveLength(1);
    expect(el.mapNumber).toBe(el.querySelector(".amap-mcode"));

    const wide = document.createElement("div");
    wide.innerHTML = '<div class="amap-copyright"><!--v2.0--> © 2026 AutoNavi <span class="amap-mcode">- GS(2025)1号</span></div>';
    const before = wide.innerHTML;
    ensureCopyright(wide, 2026);
    expect(wide.innerHTML).toBe(before);
  });

  it("地图页：窄屏上建好地图就补上版权文字（底图画完再补也不重复）", async () => {
    renderMapApp();
    await screen.findByRole("region", { name: "栗子此刻" });
    const el = await waitFor(() => {
      const found = document.querySelector(".ps-wmap .amap-copyright");
      expect(found?.textContent).toBe(copyrightText(new Date().getFullYear()));
      return found as HTMLElement;
    });
    act(() => FakeMap.all[0].emit("complete"));
    expect(el.textContent).toBe(copyrightText(new Date().getFullYear()));
    expect(el.querySelectorAll(".amap-mcode")).toHaveLength(1);
  });

  it.each([
    ["这趟旅途面板 341 高（比底部一叠高）：抬到面板上面", 341, "341px"],
    ["面板只有 200 高（比底部一叠矮）：还是按底部一叠", 200, "300px"],
  ])("Logo 与版权的高度跟着盖住地图的最高那层——%s；关掉面板回到底部一叠（300）", async (_label, sheetHeight, expected) => {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      const [top, bottom] = this.classList.contains("ps-wmap-bottom") ? [268, 568] : this.classList.contains("ps-wmap") ? [0, 568] : [0, 0];
      return { x: 0, y: top, top, bottom, left: 0, right: 320, width: 320, height: bottom - top, toJSON: () => ({}) } as DOMRect;
    });
    vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockImplementation(function (this: HTMLElement) {
      return this.classList.contains("ps-sheet") ? sheetHeight : 0;
    });
    renderMapApp();
    const panel = await showDoubao();
    const root = document.querySelector(".ps-wmap") as HTMLElement;
    await waitFor(() => expect(root.style.getPropertyValue("--wmap-attrib")).toBe("300px"));
    fireEvent.click(await within(panel).findByRole("button", { name: /这趟旅途/ }));
    await screen.findByRole("dialog", { name: /这趟旅途/ });
    await waitFor(() => expect(root.style.getPropertyValue("--wmap-attrib")).toBe(expected));
    fireEvent.click(screen.getByRole("button", { name: "收起面板" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: /这趟旅途/ })).toBeNull());
    await waitFor(() => expect(root.style.getPropertyValue("--wmap-attrib")).toBe("300px"));
  });

  it("样式：Logo 与版权都按 --wmap-attrib 摆；版权 11px（≥ 10px）、纸色衬底 + 纸墨色字，浅色深色对比都 ≥ 4.5；没有任何规则把它们藏起来", () => {
    const css = "features/world_map/world-map.css";
    for (const selector of [".ps-wmap .amap-logo", ".ps-wmap .amap-copyright"]) {
      expect(finalDecls(css, selector, false).get("bottom")).toMatch(/^calc\(var\(--wmap-attrib\b.*\) \+ \d+px\)/);
    }
    for (const dark of [false, true]) {
      const copyright = finalDecls(css, ".ps-wmap .amap-copyright", dark);
      expect(Number.parseFloat(copyright.get("font-size") ?? "0")).toBeGreaterThanOrEqual(10);
      const ratio = contrast(colorOf(copyright.get("color") ?? "", dark), colorOf(copyright.get("background") ?? "", dark));
      expect(ratio).toBeGreaterThanOrEqual(4.5);
    }
    const hiding = cssRules(css).filter(
      (r) =>
        /amap-(logo|copyright)/.test(r.selector) &&
        (r.decls.get("display")?.startsWith("none") || r.decls.get("visibility")?.startsWith("hidden") || /^0(\.0*)?$/.test(r.decls.get("opacity") ?? "") || Number.parseFloat(r.decls.get("font-size") ?? "99") < 10),
    );
    expect(hiding).toEqual([]);
  });
});

/* ---------------- 验收追加：底图加载提示 ---------------- */

describe("验收追加 · 底图没画出来时的提示", () => {
  it("isBasemapTile：只认高德域名下、路径带 tile、成功（或状态给不出）的请求；样式数据、图标、脚本、失败的、别家的都不算", () => {
    expect(isBasemapTile("https://jsapi.amap.com/web_map/get_tile?t=1", 200)).toBe(true);
    expect(isBasemapTile("https://webrd01.is.autonavi.com/appmaptile?x=1&y=2&z=3")).toBe(true);
    expect(isBasemapTile("https://jsapi.amap.com/web_map/get_tile?t=1", 0)).toBe(true);
    expect(isBasemapTile(STYLE, 200)).toBe(false);
    expect(isBasemapTile("https://o4.amap.com/icon/2.0.2.45/v1/1_0_s/icons_4", 200)).toBe(false);
    expect(isBasemapTile("https://webapi.amap.com/maps?v=2.0", 0)).toBe(false);
    expect(isBasemapTile("https://jsapi.amap.com/web_map/get_tile?t=1", 404)).toBe(false);
    expect(isBasemapTile("https://example.com/tile/1/2/3.png", 200)).toBe(false);
    expect(isBasemapTile("https://amap.com.example.net/tile/1", 200)).toBe(false);
    expect(isBasemapTile("不是地址", 200)).toBe(false);
  });

  it("顶部提示“地图加载中…”（不在底部面板那一叠里）；只有高德 complete、只有样式数据回来都不撤；第一块底图图块回来（再过两帧）才撤", async () => {
    renderMapApp();
    const hint = await screen.findByText("地图加载中…");
    expect(hint.closest(".ps-wmap-loading")?.getAttribute("role")).toBe("status");
    expect(hint.closest(".ps-wmap-bottom")).toBeNull();
    await waitFor(() => expect(FakeMap.all.length).toBe(1));
    // 高德的 complete 在图块到之前就发（实测）：不能撤。
    act(() => FakeMap.all[0].emit("complete"));
    act(() => FakePerfObserver.emit(STYLE));
    await settle();
    expect(screen.getByText("地图加载中…")).toBeTruthy();
    act(() => FakePerfObserver.emit(TILE));
    await waitFor(() => expect(screen.queryByText("地图加载中…")).toBeNull());
    expect(screen.queryByText("地图还没加载出来")).toBeNull();
  });

  it("浏览器看不了图块（没有 PerformanceObserver）：退回高德的 complete 撤提示", async () => {
    renderMapApp();
    vi.stubGlobal("PerformanceObserver", undefined);
    await screen.findByText("地图加载中…");
    await waitFor(() => expect(FakeMap.all.length).toBe(1));
    act(() => FakeMap.all[0].emit("complete"));
    await waitFor(() => expect(screen.queryByText("地图加载中…")).toBeNull());
  });

  it("15 秒整还没出来才换成“地图还没加载出来”+ 重试（14.9 秒还是加载中）；重试重建地图、重新计时，新地图画完就撤", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"], shouldAdvanceTime: true });
    expect(MAP_SLOW_MS).toBe(15_000);
    renderMapApp();
    await screen.findByText("地图加载中…");
    await waitFor(() => expect(FakeMap.all.length).toBe(1));
    act(() => vi.advanceTimersByTime(MAP_SLOW_MS - 100));
    expect(screen.getByText("地图加载中…")).toBeTruthy();
    act(() => vi.advanceTimersByTime(100));
    expect(await screen.findByText("地图还没加载出来")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    await waitFor(() => expect(FakeMap.all.length).toBe(2));
    expect(FakeMap.all[0].destroyed).toBe(true);
    expect(await screen.findByText("地图加载中…")).toBeTruthy();
    act(() => vi.advanceTimersByTime(MAP_SLOW_MS - 100));
    expect(screen.getByText("地图加载中…")).toBeTruthy();
    act(() => FakePerfObserver.emit(TILE));
    await waitFor(() => expect(screen.queryByText("地图加载中…")).toBeNull());
    expect(screen.queryByText("地图还没加载出来")).toBeNull();
  });

  it("减少动态效果不转圈（prefers-reduced-motion: reduce 下把转圈藏掉）；转圈只是装饰，读屏不读", () => {
    const reduce = cssRules("features/world_map/world-map.css").filter((r) => r.context === "@media (prefers-reduced-motion: reduce)" && r.selector.split(",").map((s) => s.trim()).includes(".ps-wmap-loading__spin"));
    expect(reduce.some((r) => r.decls.get("display") === "none")).toBe(true);
    render(<MapLoadingHint onRetry={() => undefined} />);
    const status = screen.getByRole("status");
    expect(status.textContent).toBe("地图加载中…");
    expect(status.querySelector(".ps-wmap-loading__spin")?.getAttribute("aria-hidden")).toBe("true");
  });
});

/* ---------------- 第 2 步：标记上的交通方式角标与一起听 / 一起看徽标 ---------------- */

describe("第 2 步 · 交通方式角标（W1 leg.mode）", () => {
  it("modeBadgeOf：只在路上（去 / 回）、交通方式已知且不是走路时有角标", () => {
    const going = (mode: string | undefined) => worldPetFromState(w1("p-2", "豆包", "going", { legMode: mode }));
    expect(modeBadgeOf(going("train"))).toBe("train");
    expect(modeBadgeOf(going("flight"))).toBe("flight");
    expect(modeBadgeOf(going("taxi"))).toBe("taxi");
    expect(modeBadgeOf(going("walk"))).toBeNull();
    expect(modeBadgeOf(going("rocket"))).toBeNull();
    expect(modeBadgeOf(worldPetFromState(w1("p-2", "豆包", "there")))).toBeNull();
    expect(modeBadgeOf(worldPetFromState(w1("p-1", "栗子", "home")))).toBeNull();
    const returning = worldPetFromState(w1("p-2", "豆包", "going", { legMode: "ferry", activity: { phase: "returning" } }));
    expect(modeBadgeOf(returning)).toBe("ferry");
    // W1 只在路上（去 / 回）才给 leg；万一“到了”“在家”却还带着交通方式（数据前后不一致），也不画角标——不在路上就没有“坐什么”。
    expect(modeBadgeOf({ ...worldPetFromState(w1("p-2", "豆包", "there")), legMode: "train" })).toBeNull();
    expect(modeBadgeOf({ ...worldPetFromState(w1("p-1", "栗子", "home")), legMode: "flight" })).toBeNull();
  });

  it("交通方式照 W1 原样带进来：路线不够两点（leg 为 null）也知道坐什么；认不出的是 null，不猜", () => {
    const flying = w1("p-2", "豆包", "going", { legMode: "flight" });
    const shortRoute = { ...flying, leg: { ...flying.leg!, route: [HOME] } } as WorldPetState;
    const pet = worldPetFromState(shortRoute);
    expect(pet.leg).toBeNull();
    expect(pet.legMode).toBe("flight");
    expect(worldPetFromState(w1("p-2", "豆包", "going", { legMode: "rocket" })).legMode).toBeNull();
    expect(worldPetFromState(w1("p-1", "栗子", "home")).legMode).toBeNull();
  });

  it("地图上：豆包坐火车——标记右下角是火车角标（顶替头像自己的小徽标），读屏名字后面加“，坐火车”；走路的、在家的都没有角标", async () => {
    renderMapApp({ doubaoOver: { legMode: "train" } });
    await screen.findByRole("region", { name: "栗子此刻" });
    const doubao = await screen.findByRole("button", { name: /^豆包.*，坐火车$/ });
    expect(doubao.querySelector(".ps-wmap-pet__mode")?.getAttribute("data-mode")).toBe("train");
    expect(doubao.querySelector(".ps-wmap-pet__mode")?.getAttribute("aria-hidden")).toBe("true");
    expect(doubao.querySelector(".ps-mood__badge")).toBeNull();
    const lizi = screen.getAllByRole("button", { name: /^栗子/ }).find((b) => b.classList.contains("ps-wmap-pet"))!;
    expect(lizi.querySelector(".ps-wmap-pet__mode")).toBeNull();
    expect(lizi.querySelector(".ps-mood__badge")).toBeTruthy();
    // 主状态面板的头像也一样：豆包的面板头像右下角是火车角标；栗子的面板是头像自己的小徽标。
    expect(screen.getByRole("region", { name: "栗子此刻" }).querySelector(".ps-wmap-pet__mode")).toBeNull();
    fireEvent.click(doubao);
    const panel = await screen.findByRole("region", { name: "豆包此刻" });
    expect(panel.querySelector(".ps-wmap-panel__avatar .ps-wmap-pet__mode")?.getAttribute("data-mode")).toBe("train");
    expect(panel.querySelector(".ps-wmap-panel__avatar .ps-mood__badge")).toBeNull();
  });

  it("走路（W1 leg.mode = walk）：没有角标，头像自己的小徽标照旧", async () => {
    renderMapApp();
    await screen.findByRole("region", { name: "栗子此刻" });
    const doubao = await screen.findByRole("button", { name: /^豆包/ });
    expect(doubao.getAttribute("aria-label")).not.toMatch(/，坐/);
    expect(doubao.querySelector(".ps-wmap-pet__mode")).toBeNull();
    expect(doubao.querySelector(".ps-mood__badge")).toBeTruthy();
  });
});

describe("第 2 步 · 一起听 / 一起看徽标（companion_media 的 ActivityBadgeFor）", () => {
  const anchorOf = (name: string) => screen.getAllByRole("button", { name: new RegExp(`^${name}`) }).find((b) => b.classList.contains("ps-wmap-pet"))!.closest(".ps-wmap-anchor--pet") as HTMLElement;

  it("对齐后，面板上的豆包的标记旁有“一起听”徽标（当前这一段的那条，按会话状态说“进行中”）；它在标记按钮外面，不是按钮套按钮；栗子的标记没有", async () => {
    const { session } = renderMapApp();
    await showDoubao();
    const badge = await screen.findByRole("button", { name: "一起听：TA 在听《窗边的小调》（进行中）" });
    expect(badge.closest(".ps-wmap-pet")).toBeNull();
    expect(badge.closest(".ps-wmap-anchor--pet")).toBe(anchorOf("豆包"));
    expect(badge.closest(".ps-wmap-pet__activity")).toBeTruthy();
    expect(within(anchorOf("栗子")).queryByRole("button", { name: /^一起/ })).toBeNull();
    await waitFor(() => expect(session).toHaveBeenCalledWith("ms-2"));
  });

  it("点徽标：地图上打开播放面板（?sheet=media:ms-2，push），不换当前宠物", async () => {
    const { router } = renderMapApp();
    await showDoubao();
    fireEvent.click(await screen.findByRole("button", { name: /^一起听：/ }));
    await screen.findByRole("dialog", { name: "插槽面板 media:ms-2" });
    expect(router.state.location.search).toBe("?sheet=media%3Ams-2");
    expect(router.state.historyAction).toBe("PUSH");
    expect(window.sessionStorage.getItem("petsoul:current-pet:u-1")).toBeNull();
  });

  it("会话已暂停：徽标跟着说“已暂停”", async () => {
    renderMapApp({ mediaState: "paused" });
    await showDoubao();
    expect(await screen.findByRole("button", { name: "一起听：TA 在听《窗边的小调》（已暂停）" })).toBeTruthy();
  });

  it("快照没对齐：不画徽标（也不读会话）", async () => {
    const { session, journeyMap } = renderMapApp({ map: async () => snapshot({ journey_id: "jn-0" }) });
    await showDoubao();
    await waitFor(() => expect(journeyMap).toHaveBeenCalledTimes(2));
    await settle();
    expect(screen.queryByRole("button", { name: /^一起听：/ })).toBeNull();
    expect(session).not.toHaveBeenCalled();
  });

  it("当前这一段上的活动已经结束：不画徽标（上一段的旧活动也不拿来顶）", async () => {
    const ended = snapshot();
    const entries = ended.activity_entries.map((e) => (e.leg_id === "lg-2" ? { ...e, badge_state: "ended" as const } : e));
    renderMapApp({ map: async () => ({ ...ended, activity_entries: entries }) });
    await showDoubao();
    await within(await screen.findByRole("region", { name: "豆包此刻" })).findByRole("button", { name: /这趟旅途/ });
    await settle();
    expect(screen.queryByRole("button", { name: /^一起听：/ })).toBeNull();
  });
});
