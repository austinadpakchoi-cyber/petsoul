/**
 * claude-6c2b · 地图第 0b 步（主窗口 2026-09-24 定，第 1 条随后更正）。同一家两只：栗子 p-1（当前宠物）、豆包 p-2。
 * 1. W1 加可选 petId（I 批准）：前端知道当前宠物就总带上（跨家时靠它指明哪个家）；不知道就不带，同一个家由后端自己定位。
 *    钉住：服务层给了 id 才有 pet_id、没给就只有 scope=household；地图带当前宠物的 id；跨家切到另一个家的宠物后按它重新请求、不报 409
 *    （查询键没变，是切换清了缓存才重读）。唯一还会报错的“跨家又没带”（409 pet_required）不能是死胡同：说人话、给去选的入口，
 *    原话和错误码收进“技术信息”；其他错误照旧能重试；读取中、读不到都留着底部三栏和右上“我的”。
 * 3. 左上角“进小窝”跟着面板上那只：先把当前宠物换成它再跳；面板本来就是当前宠物时不换。
 * 4. 同一个家只画一个小窝标记（名字跟着面板上那只）；在家的几只围着它错开——谁也不盖住谁、不盖住小窝，一只在家也一样；
 *    出门在外的不挪。jsdom 没有排版：这里按标记的实际尺寸（HOME_MARKER_SIZE / 宠物 52×62）和锚点平移算盒子，浏览器里另外实测。
 * （第 2 条“世界正在更新按面板上那只”写在 claude-6c2b-map-mail-scope 里，替换原来“全家通用”那一条。）
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, Link, RouterProvider } from "react-router";
import type { DrivingSchoolStatus, HomeSnapshot, HouseholdBrief, SessionState, WorldPetState, WorldState } from "@/shared/contracts";
import { createApiClient } from "@/shared/api/client";
import { ApiError } from "@/shared/api/errors";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceContext, ServiceMap } from "@/shared/services/types";
import { HouseholdProvider, useCurrentHousehold } from "@/shared/session/householdContext";
import { createLiveWorldService } from "@/features/home/service";
import type { AMapNamespace } from "@/features/world_map/amapLoader";
import { HOME_MARKER_SIZE, homeMarkerShift } from "@/features/world_map/markers";
import { MapHomePage } from "@/features/world_map/MapHomePage";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "live", isDev: false, apiBase: "/api/v1/web" } }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  delete window.AMap;
  FakeMap.all = [];
  window.sessionStorage.clear();
});

/* ---------------- 高德替身：标记内容挂进容器（与真实高德一样在页面里） ---------------- */

class FakeMarker {
  content: HTMLElement;
  constructor(options: Record<string, unknown>) {
    this.content = options.content as HTMLElement;
  }
  setPosition() {}
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
  static all: FakeMap[] = [];
  zoom: number;
  center: [number, number];
  constructor(
    public container: HTMLElement,
    public options: Record<string, unknown>,
  ) {
    this.zoom = options.zoom as number;
    this.center = options.center as [number, number];
    FakeMap.all.push(this);
  }
  add(overlay: unknown) {
    if (overlay instanceof FakeMarker) this.container.appendChild(overlay.content);
  }
  remove(overlay: unknown) {
    if (overlay instanceof FakeMarker) overlay.content.remove();
  }
  destroy() {}
  on() {}
  setZoomAndCenter(zoom: number, center: [number, number]) {
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

function installFakeAmap() {
  window.AMap = { Map: FakeMap, Marker: FakeMarker, Polyline: FakeShape, Circle: FakeShape, Pixel: class {} } as unknown as AMapNamespace;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/map/config")) {
        return Response.json({ provider: "amap", available: true, js_key: "test-only", service_host: "/_AMapService", style: null, style_dark: null, overseas_tiles: false, unavailable_reason: null });
      }
      return new Response("", { status: 404 });
    }),
  );
}

/* ---------------- 同一家两只宠物（live） ---------------- */

const HOME_POINT = { lat: 24.441642, lng: 118.112039 };
const CAFE = { name: "街角的咖啡馆", lat: 24.4452, lng: 118.1063 };

function w1Pet(petId: string, name: string, relation: "mine" | "household", where: "home" | "cafe" = "home"): WorldPetState {
  const out = where === "cafe";
  return {
    pet_id: petId,
    name,
    species: "cat",
    avatar_url: null,
    relation,
    home: { center: HOME_POINT, precision_m: 900, label: "环岛路附近的海边" },
    leg: null,
    position: out ? { lat: CAFE.lat, lng: CAFE.lng, basis: "place", precision_m: 50 } : { ...HOME_POINT, basis: "home_area", precision_m: 900 },
    version: 1,
    activity: out
      ? { kind: "cafe", phase: "there", pose: "cafe", title: "去附近喝一杯", doing: null, place: CAFE, since: null, until: null, job: null, journey_id: null, visit_id: null }
      : { kind: "home", phase: "home", pose: "idle", title: "在小窝", doing: null, place: null, since: null, until: null, job: null, journey_id: null, visit_id: null },
  } as unknown as WorldPetState;
}

const LIZI = { pet_id: "p-1", name: "栗子", species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true };
const DOUBAO = { pet_id: "p-2", name: "豆包", species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-21T00:00:00Z", added_by_you: true };
const householdOf = (pets: unknown[]) => ({ household_id: "hh-1", name: "我们的家", role: "admin", home_activated: true, pets }) as unknown as HouseholdBrief;

const signedIn = { authenticated: true, user: { user_id: "u-1" }, csrf_required: false, expires_at: null, onboarding: { step: "active" } } as unknown as SessionState;

const NO_SCHOOL = {
  stage: "none",
  wish_text: null,
  enrolled_at: null,
  coach: { name: "龟教练·慢慢", line: "", intro: "" },
  subjects: [],
  open_session: null,
  license: null,
  voucher_available: false,
  ceremony_done: false,
  temperament: "steady",
  rules_version: "v1",
  server_time: new Date().toISOString(),
} as unknown as DrivingSchoolStatus;

/** 只放行给定的服务；读到别的服务就抛错。 */
function strictServices(provided: Record<string, unknown>): ServiceMap {
  return new Proxy(provided as unknown as ServiceMap, {
    get: (target, key) => {
      if (typeof key === "string" && key in target) return (target as unknown as Record<string, unknown>)[key];
      throw new Error(`unexpected service ${String(key)}`);
    },
  });
}

/** 目标页：另一个家庭上下文实例里的“当前宠物”。 */
function CurrentPet({ page }: { page: string }) {
  const { pet } = useCurrentHousehold();
  return <output data-testid="current-pet">{`${page}:${pet?.pet_id ?? "-"}`}</output>;
}

/** 后端（I 改后）跨多个家、又没指明宠物时的 409：错误码 CONFLICT，details.reason = pet_required。 */
const PET_REQUIRED = new ApiError({
  kind: "http",
  status: 409,
  code: "CONFLICT",
  message: "你照顾的宠物不止一只，请指明是哪一只（pet_id）。",
  requestId: "req-409",
  details: { reason: "pet_required", pets: [{ pet_id: "p-1", household_id: "hh-1" }, { pet_id: "p-9", household_id: "hh-2" }] },
});
const SERVER_DOWN = new ApiError({ kind: "http", status: 500, code: "INTERNAL_ERROR", message: "服务器出了点问题。", retryable: true });

const worldOf = (pets: WorldPetState[]): WorldState => ({ server_time: new Date().toISOString(), coord_system: "wgs84", cache_seconds: 15, pets }) as WorldState;

interface Setup {
  /** 世界状态里的宠物（默认两只都在家）。 */
  w1?: WorldPetState[];
  /** 家庭名单（默认一个家：栗子、豆包都已入住）。 */
  members?: unknown[];
  /** 跨家时直接给出几个家（给了就不用 members）。 */
  households?: HouseholdBrief[];
  /** 世界状态替身（第一个参数是宠物 id，第二个是 signal）：默认不看参数、200 给出 w1；给 error 就一直失败；pending 就一直在读；也可以自己写。 */
  worldState?: { error: ApiError } | "pending" | ((petId: unknown) => Promise<WorldState>);
}

function renderMapApp({ w1 = [w1Pet("p-1", "栗子", "mine"), w1Pet("p-2", "豆包", "household")], members = [LIZI, DOUBAO], households, worldState }: Setup = {}) {
  installFakeAmap();
  const state = vi.fn(async (petId?: string, _signal?: AbortSignal): Promise<WorldState> => {
    if (worldState === "pending") return new Promise<WorldState>(() => undefined);
    if (typeof worldState === "function") return worldState(petId);
    if (worldState) throw worldState.error;
    return worldOf(w1);
  });
  const home = vi.fn(async (_petId?: string | null, _signal?: AbortSignal) => ({ unread: { messages: 0, circle: 0 }, catching_up: false }) as unknown as HomeSnapshot);
  const services = strictServices({
    session: { current: async () => signedIn },
    households: { list: async () => households ?? [householdOf(members)] },
    world: { state, home },
    driving: { status: async () => NO_SCHOOL },
    visits: { travelWish: async () => null },
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const target = (page: string) => (
    <HouseholdProvider userId="u-1">
      <CurrentPet page={page} />
      <Link to="/map">回到地图</Link>
    </HouseholdProvider>
  );
  const router = createMemoryRouter(
    [
      { path: "/map", element: <MapHomePage /> },
      { path: "/communicator", element: target("通讯器") },
      { path: "/home", element: target("小窝") },
    ],
    { initialEntries: ["/map"] },
  );
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { router, state };
}

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50));
  });

async function showDoubao(): Promise<HTMLElement> {
  await screen.findByRole("region", { name: "栗子此刻" });
  fireEvent.click(await screen.findByRole("button", { name: /^豆包在/ }));
  return screen.findByRole("region", { name: "豆包此刻" });
}

/* ---------------- 标记的盒子（相对各自的坐标点，px；高德按内容盒底边中点对准坐标） ---------------- */

interface Box {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

const PET_W = 52;
const PET_H = 62;

function translateOf(el: HTMLElement): { x: number; y: number } {
  const m = /translate\((-?[\d.]+)px,\s*(-?[\d.]+)px\)/.exec(el.style.transform);
  return m ? { x: Number(m[1]), y: Number(m[2]) } : { x: 0, y: 0 };
}

/** 宠物标记（52×62）底边中点在坐标上，再按锚点上的平移挪开。 */
function petBox(name: string): Box {
  const button = screen.getByRole("button", { name: new RegExp(`^${name}在`) });
  const anchor = button.closest<HTMLElement>(".ps-wmap-anchor--pet");
  if (!anchor) throw new Error(`${name} 的标记不在锚点里`);
  const { x, y } = translateOf(anchor);
  return { left: x - PET_W / 2, right: x + PET_W / 2, top: y - PET_H, bottom: y };
}

/** 小窝按钮（HOME_MARKER_SIZE 见方）底边中点在坐标上，再按交付单锚点平移 --home-dx / --home-dy。 */
function homeBox(): Box {
  const { x, y } = homeMarkerShift();
  return { left: x - HOME_MARKER_SIZE / 2, right: x + HOME_MARKER_SIZE / 2, top: y - HOME_MARKER_SIZE, bottom: y };
}

function overlaps(a: Box, b: Box): boolean {
  return Math.min(a.right, b.right) - Math.max(a.left, b.left) > 0 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 0;
}

const homeButtons = () => [...document.querySelectorAll<HTMLButtonElement>("button.ps-wmap-home")];

/* ---------------- 1. 两只宠物：按当前宠物读世界状态 ---------------- */

/** 真的 API 客户端（假 fetch 记下网址）：看 GET /world/state 实际发出去的查询串。 */
function liveWorldOverFetch() {
  const urls: string[] = [];
  const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
    urls.push(String(input));
    return Response.json(worldOf([]));
  });
  const service = createLiveWorldService({ mode: "live", api: createApiClient("/api/v1/web", fetchImpl as unknown as typeof fetch) } as ServiceContext);
  // 签名改成 state(petId?, signal?) 前后都能编译：按新约定调用。
  const state = service.state as unknown as (petId?: string, signal?: AbortSignal) => Promise<WorldState>;
  return { urls, state };
}

/** 跨两个家：栗子在“我们的家”（hh-1），豆豆在“第二个家”（hh-2）。与后端一致：给了 pet_id 按它定位那个家；没给就 409 pet_required。 */
const DOUDOU = { ...LIZI, pet_id: "p-9", name: "豆豆" };
const TWO_HOUSEHOLDS = [householdOf([LIZI]), { ...householdOf([DOUDOU]), household_id: "hh-2", name: "第二个家" } as unknown as HouseholdBrief];
async function crossHouseholdWorld(petId: unknown): Promise<WorldState> {
  if (petId === "p-1") return worldOf([w1Pet("p-1", "栗子", "mine")]);
  if (petId === "p-9") return worldOf([w1Pet("p-9", "豆豆", "mine")]);
  throw PET_REQUIRED;
}

describe("第 0b 步 · 1：W1 带上当前宠物（可选 petId）；唯一还会报错的跨家不带 pet_id 有出路", () => {
  it("服务层：给了宠物 id，GET /world/state?scope=household&pet_id=…", async () => {
    const { urls, state } = liveWorldOverFetch();
    await state("p-2", new AbortController().signal);
    expect(urls).toEqual(["/api/v1/web/world/state?scope=household&pet_id=p-2"]);
  });

  it("服务层：当前宠物未知（没给宠物 id）就不带 pet_id，照常能读（同一个家由后端自己定位）", async () => {
    const { urls, state } = liveWorldOverFetch();
    await expect(state(undefined, new AbortController().signal)).resolves.toMatchObject({ pets: [] });
    await expect(state()).resolves.toMatchObject({ pets: [] });
    expect(urls).toEqual(["/api/v1/web/world/state?scope=household", "/api/v1/web/world/state?scope=household"]);
  });

  it("地图：知道当前宠物（栗子）就带上它的 id；同一家两只都画出来", async () => {
    const { state } = renderMapApp();
    await screen.findByRole("region", { name: "栗子此刻" });
    expect(await screen.findByRole("button", { name: /^栗子在/ })).toBeTruthy();
    expect(await screen.findByRole("button", { name: /^豆包在/ })).toBeTruthy();
    expect(state.mock.calls.length).toBeGreaterThan(0);
    expect(state.mock.calls.map((call) => call[0])).toEqual(state.mock.calls.map(() => "p-1"));
  });

  it("跨家：先按栗子（我们的家）读；切到第二个家的豆豆后按豆豆重新请求（查询键没变，是切换清了缓存才重读），不报 409", async () => {
    const { state } = renderMapApp({ households: TWO_HOUSEHOLDS, worldState: crossHouseholdWorld });
    await screen.findByRole("region", { name: "栗子此刻" });
    const before = state.mock.calls.length;
    // 地图上不切宠物，宠物分在两个家时只给一个切家的小控件（2026-09-24）：切到“第二个家”，换成那个家里的豆豆。
    fireEvent.click(within(screen.getByRole("group", { name: "切换当前的家" })).getByRole("button", { name: /第二个家/ }));
    expect(await screen.findByRole("region", { name: "豆豆此刻" })).toBeTruthy();
    expect(state.mock.calls.slice(before).map((call) => call[0])).toContain("p-9");
    expect(screen.queryByText(/不止一个家/)).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("跨家又没带 pet_id（后端 409 pet_required）：说人话、给去选的入口，原话和错误码收进“技术信息”；底部三栏和“我的”都在，不给“重试”", async () => {
    renderMapApp({ households: TWO_HOUSEHOLDS, worldState: { error: PET_REQUIRED } });
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("你在不止一个家里照顾伙伴，先选一只再看地图。")).toBeTruthy();
    expect(within(alert).getByRole("link", { name: /选一只/ }).getAttribute("href")).toBe("/me");
    expect(within(alert).queryByRole("button", { name: "重试" })).toBeNull();
    const tech = within(alert).getByText("技术信息").closest("details");
    expect(tech?.textContent ?? "").toContain("CONFLICT");
    expect(tech?.textContent ?? "").toContain("你照顾的宠物不止一只，请指明是哪一只（pet_id）。");
    expect(alert.textContent?.replace(tech?.textContent ?? "", "") ?? "").not.toContain("pet_id");
    const nav = screen.getByRole("navigation", { name: /主导航/ });
    expect(within(nav).getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual(["/map", "/communicator", "/memories"]);
    expect(screen.getByRole("link", { name: "我的" }).getAttribute("href")).toBe("/me");
  });

  it("其他错误（例如 500）：照旧能重试，也留着底部三栏和“我的”", async () => {
    const { state } = renderMapApp({ worldState: { error: SERVER_DOWN } });
    const alert = await screen.findByRole("alert");
    expect(within(alert).queryByText(/不止一个家/)).toBeNull();
    const reads = state.mock.calls.length;
    fireEvent.click(within(alert).getByRole("button", { name: "重试" }));
    await waitFor(() => expect(state.mock.calls.length).toBe(reads + 1));
    expect(within(screen.getByRole("navigation", { name: /主导航/ })).getAllByRole("link")).toHaveLength(3);
    expect(screen.getByRole("link", { name: "我的" }).getAttribute("href")).toBe("/me");
  });

  it("读取中（一直没回来）：同样留着底部三栏和“我的”，不困在加载页", async () => {
    renderMapApp({ worldState: "pending" });
    await screen.findByText("正在找 TA 在哪…");
    expect(within(screen.getByRole("navigation", { name: /主导航/ })).getAllByRole("link")).toHaveLength(3);
    expect(screen.getByRole("link", { name: "我的" }).getAttribute("href")).toBe("/me");
  });
});

/* ---------------- 3. 左上角“进小窝”跟着面板上那只 ---------------- */

describe("第 0b 步 · 3：左上角“进小窝”跟着面板上那只", () => {
  it("面板是豆包时点左上角“进小窝”：到了小窝，当前宠物是豆包（另一个家庭上下文靠 sessionStorage 接上）", async () => {
    renderMapApp();
    await showDoubao();
    fireEvent.click(screen.getByRole("link", { name: "进小窝" }));
    expect((await screen.findByTestId("current-pet")).textContent).toBe("小窝:p-2");
    expect(window.sessionStorage.getItem("petsoul:current-pet:u-1")).toBe("p-2");
  });

  it("从豆包的面板进小窝再回来：接着这一眼（镜头接着上次、仍看豆包），不当成换了宠物从头对准", async () => {
    renderMapApp();
    await showDoubao();
    await waitFor(() => expect(FakeMap.all[0]?.zoom).toBe(16));
    fireEvent.click(screen.getByRole("link", { name: "进小窝" }));
    expect((await screen.findByTestId("current-pet")).textContent).toBe("小窝:p-2");
    fireEvent.click(screen.getByRole("link", { name: "回到地图" }));
    expect(await screen.findByRole("region", { name: "豆包此刻" })).toBeTruthy();
    await waitFor(() => expect(FakeMap.all).toHaveLength(2));
    // 从头对准时新地图从全国视图（zoom 4）推近；接着看时直接用离开时的镜头。
    expect(FakeMap.all[1].options).toMatchObject({ zoom: 16 });
  });

  it("对照：面板就是当前宠物栗子时点“进小窝”：还是栗子，不写当前宠物", async () => {
    renderMapApp();
    await screen.findByRole("region", { name: "栗子此刻" });
    fireEvent.click(screen.getByRole("link", { name: "进小窝" }));
    expect((await screen.findByTestId("current-pet")).textContent).toBe("小窝:p-1");
    expect(window.sessionStorage.getItem("petsoul:current-pet:u-1")).toBeNull();
  });
});

/* ---------------- 4. 一个家一个小窝标记；在家的围着它错开 ---------------- */

describe("第 0b 步 · 4：同一个家只画一个小窝标记，在家的几只围着它错开", () => {
  it("两只都在家：只有一个小窝标记，名字跟着面板上那只（栗子 → 点豆包后是豆包）", async () => {
    renderMapApp();
    await screen.findByRole("region", { name: "栗子此刻" });
    await waitFor(() => expect(homeButtons().length).toBeGreaterThan(0));
    await settle();
    expect(homeButtons().map((b) => b.getAttribute("aria-label"))).toEqual(["栗子的小窝，TA 在家，进去看看"]);
    await showDoubao();
    await settle();
    expect(homeButtons().map((b) => b.getAttribute("aria-label"))).toEqual(["豆包的小窝，TA 在家，进去看看"]);
  });

  it("两只都在家：围着小窝错开——两只谁也不盖住谁，也不盖住小窝", async () => {
    renderMapApp();
    await screen.findByRole("button", { name: /^豆包在/ });
    await settle();
    const lizi = petBox("栗子");
    const doubao = petBox("豆包");
    const house = homeBox();
    expect(overlaps(lizi, doubao)).toBe(false);
    expect(overlaps(lizi, house)).toBe(false);
    expect(overlaps(doubao, house)).toBe(false);
  });

  it("只有一只在家：也不压住小窝（原来头像压住小窝一半）", async () => {
    renderMapApp({ w1: [w1Pet("p-1", "栗子", "mine")], members: [LIZI] });
    await screen.findByRole("button", { name: /^栗子在/ });
    await settle();
    expect(homeButtons()).toHaveLength(1);
    expect(overlaps(petBox("栗子"), homeBox())).toBe(false);
  });

  it("出门在外的不挪：豆包在咖啡馆，不参与围坐；栗子在家照样让开小窝；小窝标记仍只有一个，面板是豆包时说 TA 出门了", async () => {
    renderMapApp({ w1: [w1Pet("p-1", "栗子", "mine"), w1Pet("p-2", "豆包", "household", "cafe")] });
    await screen.findByRole("button", { name: /^豆包在/ });
    await settle();
    const doubaoAnchor = screen.getByRole("button", { name: /^豆包在/ }).closest<HTMLElement>(".ps-wmap-anchor--pet");
    expect(doubaoAnchor?.style.transform ?? "").toBe("");
    expect(overlaps(petBox("栗子"), homeBox())).toBe(false);
    expect(homeButtons()).toHaveLength(1);
    const panel = await showDoubao();
    expect(within(panel).queryByRole("link", { name: /进小窝看看/ })).toBeNull();
    await settle();
    expect(homeButtons().map((b) => b.getAttribute("aria-label"))).toEqual(["豆包的小窝，TA 出门了，进去看看"]);
  });
});

/* ---------------- 5. 深色地图：zzz 与高德 Logo（样式规则；实际渲染的对比度在浏览器里另量） ---------------- */

// 不用 new URL(相对路径, import.meta.url)：Vite 会把它当资源地址改写。
const CSS = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "..", "src/features/world_map/world-map.css"), "utf8");

/** 所有 `@media (prefers-color-scheme: dark) { … }` 块的内容（按花括号配对取）。 */
function darkBlocks(css: string): string[] {
  const blocks: string[] = [];
  const re = /@media\s*\(prefers-color-scheme:\s*dark\)\s*\{/g;
  for (let m = re.exec(css); m; m = re.exec(css)) {
    let depth = 1;
    let i = re.lastIndex;
    for (; i < css.length && depth > 0; i += 1) depth += css[i] === "{" ? 1 : css[i] === "}" ? -1 : 0;
    blocks.push(css.slice(re.lastIndex, i - 1));
  }
  return blocks;
}

/** 深色块里某个选择器的声明（selector 要逐字一致）。 */
function darkRule(selector: string): Record<string, string> {
  for (const block of darkBlocks(CSS)) {
    const at = block.indexOf(`${selector} {`);
    if (at < 0) continue;
    const body = block.slice(block.indexOf("{", at) + 1, block.indexOf("}", at));
    return Object.fromEntries(
      body
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .split(";")
        .map((d) => d.split(":").map((s) => s.trim()))
        .filter(([k, v]) => k && v)
        .map(([k, ...v]) => [k, v.join(":")]),
    );
  }
  return {};
}

function rgbOf(color: string): { rgb: [number, number, number]; alpha: number } {
  const hex = /^#([0-9a-f]{6})$/i.exec(color);
  if (hex) return { rgb: [0, 2, 4].map((i) => parseInt(hex[1].slice(i, i + 2), 16)) as [number, number, number], alpha: 1 };
  const nums = (color.match(/[\d.]+/g) ?? []).map(Number);
  return { rgb: [nums[0], nums[1], nums[2]], alpha: nums[3] ?? 1 };
}
const channel = (v: number) => {
  const c = v / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
};
const luminance = ([r, g, b]: [number, number, number]) => 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
const contrast = (a: [number, number, number], b: [number, number, number]) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};
const over = (top: { rgb: [number, number, number]; alpha: number }, under: [number, number, number]) => top.rgb.map((c, i) => c * top.alpha + under[i] * (1 - top.alpha)) as [number, number, number];

/** 浏览器里量到的深色底：高德深色底图（zzz 周围的中位色）与深色主状态面板（巡检量 2.18 时的底）。 */
const DARK_MAP: [number, number, number] = [0x07, 0x17, 0x38];
const DARK_PANEL: [number, number, number] = [0x23, 0x2d, 0x26];
/** 高德 Logo 图里“高德地图”几个字的颜色（按实测亮度取的近似深色）。 */
const LOGO_TEXT: [number, number, number] = [0x1a, 0x1a, 0x1a];

describe("第 0b 步 · 5：深色地图上的 zzz 与高德 Logo（样式规则）", () => {
  it("zzz：地图页里（标记和主状态面板的头像都算）换成浅色字，对深色底图和深色面板都 ≥ 3:1", () => {
    const rule = darkRule(".ps-wmap .ps-mood__zzz i");
    expect(rule.color, "深色下地图页里 zzz 的颜色规则").toBeTruthy();
    const zzz = rgbOf(rule.color).rgb;
    expect(contrast(zzz, DARK_MAP)).toBeGreaterThanOrEqual(3);
    expect(contrast(zzz, DARK_PANEL)).toBeGreaterThanOrEqual(3);
  });

  it("高德 Logo：深色下垫浅色衬底，“高德地图”几个字对衬底 ≥ 4.5:1；衬底不压住右边的版权文字（版权往右让开得比衬底多出来的还多）", () => {
    const logo = darkRule(".ps-wmap .amap-logo");
    expect(logo.background, "深色下 Logo 的衬底").toBeTruthy();
    expect(contrast(LOGO_TEXT, over(rgbOf(logo.background), DARK_MAP))).toBeGreaterThanOrEqual(4.5);
    const px = (v: string | undefined) => Number(/(-?[\d.]+)px/.exec(v ?? "")?.[1] ?? 0);
    const [padY, padX] = (logo.padding ?? "0 0").split(/\s+/);
    expect(padY).toBeTruthy();
    const overhang = px(logo["margin-left"]) + 2 * px(padX ?? padY);
    const copyright = darkRule(".ps-wmap .amap-copyright");
    expect(px(copyright["margin-left"])).toBeGreaterThan(overhang);
  });
});
