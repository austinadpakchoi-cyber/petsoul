/**
 * claude-6c2b · C84A-MAP-MAIL-SCOPE-01（c84a 报的 P1）：地图主状态面板的信箱提醒属于面板上显示的那只宠物。
 * 同一家两只：栗子 p-1（当前宠物）、豆包 p-2。地图上点哪只，面板就显示哪只——这只是本页的选择，不改当前宠物。
 * - 栗子自己的未读只在栗子的面板出现（对照：当前宠物自己的有效提醒照常）；点豆包后不再出现，改读豆包自己的家园快照（请求用 p-2）；
 *   豆包 0 条、或它的家园快照还在读 / 读不到时，没有信箱这一行，绝不拿栗子的数顶替；
 * - 点标记只是换看哪只：当前宠物不变、世界状态不重读、地图不重挂；
 * - 从面板进按宠物区分的页面（信箱提醒、捎句话、进小窝看看、家的标记），到了目标页当前宠物就是面板上那只。
 *   这里的目标页是另一个家庭上下文实例（与实际应用一致），只能靠 sessionStorage 的 petsoul:current-pet:<用户> 接上；
 *   离开之前地图不按清空的缓存再画一次（不闪“正在找 TA 在哪…”、世界状态与家园快照不多读）；
 *   面板本来就是当前宠物（对照）：进页面不切换（不写当前宠物、缓存不清）；家的标记也按面板上那只进（同一家只画一个小窝标记，名字跟着面板上那只）；
 * - “世界正在更新”按面板上那只（第 0b 步改：后端 catching_up 按宠物算），读它自己的家园快照，换宠物就跟着换；
 * - 收起、展开两种状态下，提醒都能点进去、去向正确（jsdom 只证明可点与去向；短屏上不被遮挡由浏览器实测另证）。
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import type { DrivingSchoolStatus, HomeSnapshot, HouseholdBrief, SessionState, WorldPetState, WorldState } from "@/shared/contracts";
import { queryKeys } from "@/shared/query/queryClient";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider, useCurrentHousehold } from "@/shared/session/householdContext";
import type { AMapNamespace } from "@/features/world_map/amapLoader";
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

/* ---------------- 高德替身：只记录镜头与覆盖物，标记内容挂进容器（与真实高德一样在页面里） ---------------- */

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
  private handlers = new Map<string, Array<() => void>>();
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
  on(event: string, handler: () => void) {
    this.handlers.set(event, [...(this.handlers.get(event) ?? []), handler]);
  }
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

function w1Pet(petId: string, name: string, relation: "mine" | "household"): WorldPetState {
  return {
    pet_id: petId,
    name,
    species: "cat",
    avatar_url: null,
    relation,
    home: { center: HOME_POINT, precision_m: 900, label: "环岛路附近的海边" },
    leg: null,
    position: { ...HOME_POINT, basis: "home_area", precision_m: 900 },
    version: 1,
    activity: { kind: "home", phase: "home", pose: "idle", title: "在小窝", doing: null, place: null, since: null, until: null, job: null, journey_id: null, visit_id: null },
  };
}

const household = {
  household_id: "hh-1",
  name: "我们的家",
  role: "admin",
  home_activated: true,
  pets: [
    { pet_id: "p-1", name: "栗子", species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true },
    { pet_id: "p-2", name: "豆包", species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-21T00:00:00Z", added_by_you: true },
  ],
} as unknown as HouseholdBrief;

const signedIn = { authenticated: true, user: { user_id: "u-1" }, csrf_required: false, expires_at: null, onboarding: { step: "active" } } as unknown as SessionState;

/** 驾校还没开始：面板里没有驾校那一行，只看信箱与系统提示。 */
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

type PetId = "p-1" | "p-2";
const snapshotFor = (unread: number, catchingUp: boolean) => ({ unread: { messages: unread, circle: 0 }, catching_up: catchingUp }) as unknown as HomeSnapshot;

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

interface Setup {
  unread?: Partial<Record<PetId, number>>;
  catchingUp?: Partial<Record<PetId, boolean>>;
  /** 自己写家园快照（例如豆包的一直在读 / 读不到）。 */
  home?: (petId: string | null) => Promise<HomeSnapshot>;
}

function renderMapApp({ unread = {}, catchingUp = {}, home }: Setup = {}) {
  installFakeAmap();
  const homeFn = vi.fn<(petId: string | null, signal?: AbortSignal) => Promise<HomeSnapshot>>(
    home ?? (async (petId) => snapshotFor(unread[petId as PetId] ?? 0, catchingUp[petId as PetId] ?? false)),
  );
  const worldState: WorldState = { server_time: new Date().toISOString(), coord_system: "wgs84", cache_seconds: 15, pets: [w1Pet("p-1", "栗子", "mine"), w1Pet("p-2", "豆包", "household")] };
  const state = vi.fn(async (_petId?: string, _signal?: AbortSignal) => worldState);
  const services = strictServices({
    session: { current: async () => signedIn },
    households: { list: async () => [household] },
    world: { state, home: homeFn },
    driving: { status: async () => NO_SCHOOL },
    // 旅行心愿那一行（journey/travelPlan/wishNote）在 live 下读 visits.travelWish：这里没有活动心愿。
    visits: { travelWish: async () => null },
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/map", element: <MapHomePage /> },
      {
        path: "/communicator",
        element: (
          <HouseholdProvider userId="u-1">
            <CurrentPet page="通讯器" />
          </HouseholdProvider>
        ),
      },
      {
        path: "/home",
        element: (
          <HouseholdProvider userId="u-1">
            <CurrentPet page="小窝" />
          </HouseholdProvider>
        ),
      },
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
  return { router, home: homeFn, state, client };
}

const requestedPets = (home: ReturnType<typeof renderMapApp>["home"]) => home.mock.calls.map((call) => call[0]);
const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50));
  });

/** 记下从现在起页面里有没有冒出过某段文字（地图按清空的缓存重画时会出“正在找 TA 在哪…”）；调用返回值即停止并给出结果。 */
function watchInserted(text: string): () => boolean {
  let seen = false;
  const scan = (records: MutationRecord[]) => {
    for (const record of records) for (const node of Array.from(record.addedNodes)) if (node.textContent?.includes(text)) seen = true;
  };
  const observer = new MutationObserver(scan);
  observer.observe(document.body, { childList: true, subtree: true });
  return () => {
    scan(observer.takeRecords());
    observer.disconnect();
    return seen;
  };
}

/** 先确认栗子的面板出来了，再点地图上豆包的标记，返回豆包的面板。 */
async function showDoubao(): Promise<HTMLElement> {
  await screen.findByRole("region", { name: "栗子此刻" });
  fireEvent.click(await screen.findByRole("button", { name: /^豆包在/ }));
  return screen.findByRole("region", { name: "豆包此刻" });
}

describe("C84A-MAP-MAIL-SCOPE-01：信箱提醒属于面板上显示的那只宠物", () => {
  it("对照：当前宠物栗子的 7 条在栗子的面板出现，请求用的是 p-1，点它去通讯器", async () => {
    const { home } = renderMapApp({ unread: { "p-1": 7 } });
    const mine = await screen.findByRole("region", { name: "栗子此刻" });
    expect((await within(mine).findByRole("link", { name: "TA 发来 7 条消息" })).getAttribute("href")).toBe("/communicator");
    expect(requestedPets(home)).toContain("p-1");
  });

  it("点豆包的标记：面板换成豆包，不再说栗子的 7 条；改读豆包自己的家园快照（p-2），它 0 条就没有信箱这一行", async () => {
    const { home } = renderMapApp({ unread: { "p-1": 7, "p-2": 0 } });
    const other = await showDoubao();
    await settle();
    expect(within(other).queryByRole("link", { name: "TA 发来 7 条消息" })).toBeNull();
    await waitFor(() => expect(requestedPets(home)).toContain("p-2"));
    await settle();
    expect(within(other).queryByRole("link", { name: /^TA 发来/ })).toBeNull();
  });

  it("豆包有自己的未读：显示豆包自己的 3 条，请求用的是 p-2；切回栗子又是栗子的 7 条", async () => {
    const { home } = renderMapApp({ unread: { "p-1": 7, "p-2": 3 } });
    const other = await showDoubao();
    expect(await within(other).findByRole("link", { name: "TA 发来 3 条消息" })).toBeTruthy();
    expect(within(other).queryByRole("link", { name: "TA 发来 7 条消息" })).toBeNull();
    expect(requestedPets(home)).toContain("p-2");
    fireEvent.click(screen.getByRole("button", { name: /^栗子在/ }));
    const mine = await screen.findByRole("region", { name: "栗子此刻" });
    expect(await within(mine).findByRole("link", { name: "TA 发来 7 条消息" })).toBeTruthy();
    expect(within(mine).queryByRole("link", { name: "TA 发来 3 条消息" })).toBeNull();
  });

  it.each([
    ["还在读", () => new Promise<HomeSnapshot>(() => undefined)],
    ["读不到", () => Promise.reject(new Error("家园快照读不到"))],
  ])("豆包的家园快照%s：没有信箱这一行，也不拿栗子的 7 条顶替", async (_label, doubaoHome) => {
    const { home } = renderMapApp({ home: (petId) => (petId === "p-1" ? Promise.resolve(snapshotFor(7, false)) : doubaoHome()) });
    const other = await showDoubao();
    await settle();
    expect(within(other).queryByRole("link", { name: "TA 发来 7 条消息" })).toBeNull();
    await waitFor(() => expect(requestedPets(home)).toContain("p-2"));
    await settle();
    expect(within(other).queryByRole("link", { name: /^TA 发来/ })).toBeNull();
  });

  it("护栏：点标记只是换看哪只——当前宠物还是栗子、没写当前宠物、世界状态不重读、地图不重挂", async () => {
    const { state, router } = renderMapApp({ unread: { "p-1": 7 } });
    await screen.findByRole("region", { name: "栗子此刻" });
    await waitFor(() => expect(FakeMap.all).toHaveLength(1));
    const reads = state.mock.calls.length;
    fireEvent.click(await screen.findByRole("button", { name: /^豆包在/ }));
    await screen.findByRole("region", { name: "豆包此刻" });
    await settle();
    expect(state.mock.calls.length).toBe(reads);
    expect(FakeMap.all).toHaveLength(1);
    expect(window.sessionStorage.getItem("petsoul:current-pet:u-1")).toBeNull();
    // 地图上不再有按宠物的切换栏（2026-09-24：一个家的几只画在同一张图上，只有分在不止一个家时才有切家的小控件）。
    // 断言不变，只换找按钮的地方：到同一张路由表里有切换栏的小窝，“查看 栗子”仍是按下的——点标记没有改当前宠物。
    expect(screen.queryByRole("group", { name: "切换当前宠物" })).toBeNull();
    await act(async () => { await router.navigate("/home"); });
    expect((await screen.findByRole("button", { name: /^查看 栗子/ })).getAttribute("aria-pressed")).toBe("true");
  });

  it.each([
    ["栗子的快照标着、豆包的没有", { "p-1": true }, true, false],
    ["豆包的快照标着、栗子的没有", { "p-2": true }, false, true],
  ] as const)("“世界正在更新”按面板上那只（后端 catching_up 按宠物算）：%s", async (_label, catchingUp, onLizi, onDoubao) => {
    const CATCHING_UP = "世界正在更新，工钱和来信稍后出现。";
    const { home } = renderMapApp({ catchingUp });
    const mine = await screen.findByRole("region", { name: "栗子此刻" });
    await waitFor(() => expect(requestedPets(home)).toContain("p-1"));
    await settle();
    if (onLizi) expect(await within(mine).findByText(CATCHING_UP)).toBeTruthy();
    else expect(within(mine).queryByText(CATCHING_UP)).toBeNull();
    const other = await showDoubao();
    await waitFor(() => expect(requestedPets(home)).toContain("p-2"));
    await settle();
    if (onDoubao) expect(await within(other).findByText(CATCHING_UP)).toBeTruthy();
    else expect(within(other).queryByText(CATCHING_UP)).toBeNull();
  });

  it.each([
    ["信箱提醒", "通讯器", async (panel: HTMLElement) => fireEvent.click(await within(panel).findByRole("link", { name: "TA 发来 3 条消息" }))],
    ["捎句话", "通讯器", async (panel: HTMLElement) => fireEvent.click(within(panel).getByRole("link", { name: /捎句话/ }))],
    ["进小窝看看", "小窝", async (panel: HTMLElement) => fireEvent.click(within(panel).getByRole("link", { name: /进小窝看看/ }))],
    ["家的标记", "小窝", async (_panel: HTMLElement) => fireEvent.click(await screen.findByRole("button", { name: "豆包的小窝，TA 在家，进去看看" }))],
  ])("从豆包的面板点%s：到了%s，当前宠物是豆包（另一个家庭上下文靠 sessionStorage 接上）；离开前地图不按清空的缓存重画", async (_what, page, press) => {
    const { state, home } = renderMapApp({ unread: { "p-1": 7, "p-2": 3 } });
    const other = await showDoubao();
    // 等豆包自己的家园快照读到（没有在途请求），再记下点之前各读了几次。
    await within(other).findByRole("link", { name: "TA 发来 3 条消息" });
    const reads = { state: state.mock.calls.length, home: home.mock.calls.length };
    const flashed = watchInserted("正在找 TA 在哪");
    await press(other);
    expect((await screen.findByTestId("current-pet")).textContent).toBe(`${page}:p-2`);
    expect(window.sessionStorage.getItem("petsoul:current-pet:u-1")).toBe("p-2");
    await settle();
    expect(flashed()).toBe(false);
    expect({ state: state.mock.calls.length, home: home.mock.calls.length }).toEqual(reads);
  });

  it.each([
    ["信箱提醒", "通讯器", async (panel: HTMLElement) => fireEvent.click(await within(panel).findByRole("link", { name: "TA 发来 7 条消息" }))],
    ["捎句话", "通讯器", async (panel: HTMLElement) => fireEvent.click(within(panel).getByRole("link", { name: /捎句话/ }))],
    ["进小窝看看", "小窝", async (panel: HTMLElement) => fireEvent.click(within(panel).getByRole("link", { name: /进小窝看看/ }))],
    // 这里没点过地图上的标记，得等地图（和标记）挂上来再点。
    ["家的标记", "小窝", async (_panel: HTMLElement) => fireEvent.click(await screen.findByRole("button", { name: "栗子的小窝，TA 在家，进去看看" }))],
  ])("对照：面板就是当前宠物栗子时点%s：到了%s还是栗子，不切换（没写当前宠物、栗子的家园快照缓存还在）", async (_what, page, press) => {
    const { client } = renderMapApp({ unread: { "p-1": 7, "p-2": 3 } });
    const mine = await screen.findByRole("region", { name: "栗子此刻" });
    await within(mine).findByRole("link", { name: "TA 发来 7 条消息" });
    await press(mine);
    expect((await screen.findByTestId("current-pet")).textContent).toBe(`${page}:p-1`);
    expect(window.sessionStorage.getItem("petsoul:current-pet:u-1")).toBeNull();
    expect(client.getQueryData(queryKeys.homeFor("u-1", "p-1"))).toBeTruthy();
  });

  it.each([
    ["面板是豆包", true, "豆包的小窝，TA 在家，进去看看", "小窝:p-2", "p-2"],
    ["面板是栗子", false, "栗子的小窝，TA 在家，进去看看", "小窝:p-1", null],
  ])("家的标记按面板上那只进（同一家只画一个小窝标记，名字跟着面板上那只）：%s", async (_label, toDoubao, marker, arrived, stored) => {
    renderMapApp({ unread: { "p-1": 7, "p-2": 3 } });
    if (toDoubao) await showDoubao();
    else await screen.findByRole("region", { name: "栗子此刻" });
    await waitFor(() => expect(document.querySelectorAll("button.ps-wmap-home")).toHaveLength(1));
    const only = await screen.findByRole("button", { name: /的小窝，/ });
    expect(only.getAttribute("aria-label")).toBe(marker);
    fireEvent.click(only);
    expect((await screen.findByTestId("current-pet")).textContent).toBe(arrived);
    expect(window.sessionStorage.getItem("petsoul:current-pet:u-1")).toBe(stored);
  });

  it("收起、展开两种状态下，豆包面板的信箱提醒都能点进去，到了通讯器当前宠物是豆包", async () => {
    const setup = { unread: { "p-1": 7, "p-2": 3 }, catchingUp: { "p-1": true, "p-2": true } } satisfies Setup;
    // 收起：只露第一条（来信）和“还有 1 条”
    renderMapApp(setup);
    let other = await showDoubao();
    let group = await within(other).findByRole("group", { name: "提醒，共 2 条" });
    expect(within(group).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["TA 发来 3 条消息"]);
    fireEvent.click(within(group).getByRole("link", { name: "TA 发来 3 条消息" }));
    expect((await screen.findByTestId("current-pet")).textContent).toBe("通讯器:p-2");
    cleanup();
    FakeMap.all = [];
    window.sessionStorage.clear();
    // 展开：两条都在，来信仍能点
    renderMapApp(setup);
    other = await showDoubao();
    group = await within(other).findByRole("group", { name: "提醒，共 2 条" });
    fireEvent.click(within(group).getByRole("button", { name: "还有 1 条" }));
    expect(within(group).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["TA 发来 3 条消息", "世界正在更新，工钱和来信稍后出现。"]);
    fireEvent.click(within(group).getByRole("link", { name: "TA 发来 3 条消息" }));
    expect((await screen.findByTestId("current-pet")).textContent).toBe("通讯器:p-2");
  });
});
