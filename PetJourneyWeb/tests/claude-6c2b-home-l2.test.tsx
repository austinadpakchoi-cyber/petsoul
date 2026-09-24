/**
 * claude-6c2b · 小窝改成地图下面的二级页（方案 2.2 页面层级、第 5 节小窝）：
 * - 左上角始终能回到地图（不再依赖 ?from=map）；二级页不挂底栏（bareRoutes），仍过登录与入住守卫（WorldGate）；
 * - 庭院 / 屋内切换不加浏览器历史（replace），在地图上按返回不会回到小窝的某个房间；
 * - “生活与回忆”那排入口与管理员“给这个家添伙伴”不在小窝了，换成场景左侧的小图标（拍一张；信箱只在屋内，
 *   院子里场景自己有信箱；未读只挂小红点）；
 * - “此刻 · 一起生活”面板已退役（与地图首页主状态面板重复，用户 2026-09-24 要求旧 UI 退役）；home.panels 一张都不放（驾校提醒已按方案 8.2 挪到地图主状态面板）；
 * - 场景里的东西平时不写字，点到才冒出名字和能做的事，再点或点别处收起，每件都有无障碍名称；
 * - 第一次进来，可点的东西依次轻闪一次，按宠物记在本机（本机存储读写失败时当第一次，不崩）；
 * - TA 不在家：窝是空的，窝边一张“我出门啦”，点它回到地图；在家时没有这张便笺；
 * - [过渡方案] 场景自然淡进地面：遮罩只在底图那一层，地面层是场景外的独立装饰元素，样式集中在一段里、删掉即回原样。
 * 这里只证明页面的呈现与跳转地址：回地图的链接带 ?focus=<当前宠物 id>，地图页据此对准 TA（对准本身在 map-panel 测试里验）。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, MemoryRouter, Route, RouterProvider, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { HomeSnapshot, HouseholdBrief, OnboardingState, PetPresence, PlotSummary, SessionState } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { slot } from "@/shared/modules/types";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { buildSlotRegistry, SlotProvider } from "@/shared/slots/Slot";
import { createFixtureDrivingService } from "@/features/driving_school/service";
import { HomeBody, HomePage } from "@/features/home/HomePage";
import { HomeScene } from "@/features/home/HomeScene";
import { fixtureHomeSnapshot } from "@/fixtures/home";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "live", isDev: false, apiBase: "/api/v1/web" } }));

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const RIPE: PlotSummary = { plot_id: "p-ripe", cycle_id: "c-1", crop_key: "star_tomato", crop_label: "星星番茄", stage: "ripe", ripe_at: null, steal_total: 3, steal_remaining: 3 };
const GROWING: PlotSummary = { plot_id: "p-grow", cycle_id: "c-2", crop_key: "moon_radish", crop_label: "月光萝卜", stage: "growing", ripe_at: null, steal_total: 3, steal_remaining: 3 };

function snapshot({
  petId,
  presence = "at_home",
  unread = 2,
  favorite = "窗台上的软垫",
  journey = presence !== "at_home",
}: { petId: string; presence?: PetPresence; unread?: number; favorite?: string | null; journey?: boolean }): HomeSnapshot {
  const base = fixtureHomeSnapshot();
  return {
    ...base,
    data_origin: "live",
    presence,
    journey: journey ? { journey_id: "j-1", itinerary_version: 1, headline: "栗子 出门走走", current_visit_id: null, current_leg_id: null } : null,
    pet: { ...base.pet, pet_id: petId, name: "栗子", photo_url: null, photo_generated: false, presence },
    plots: [RIPE, GROWING],
    unread: { messages: unread, circle: 0 },
    welcome: favorite
      ? { pet_id: petId, confirmation_id: "cf-1", projection_version: 1, greeting: "我到家啦。", details: [{ kind: "favorite_object", text: favorite, note_id: "n-1", note_version: 1 }] }
      : null,
    catching_up: false,
  } as HomeSnapshot;
}

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
}

function renderScene(home: HomeSnapshot, entry = "/home") {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/home" element={<HomeScene snapshot={home} />} />
        <Route path="*" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

function householdFor(petId: string): HouseholdBrief {
  return {
    household_id: "house-l2", name: "栗子的家", home_id: "home-1", role: "admin", home_activated: true, member_count: 1,
    pets: [{ pet_id: petId, name: "栗子", species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-23T00:00:00Z", added_by_you: true }],
  } as HouseholdBrief;
}

/** 与应用同一套外围：家庭上下文、角色能力开关（后端报 not_implemented，不会去读角色）。管理员身份。 */
function renderPage({ petId, home, entry = "/home", state = null }: { petId: string; home: () => Promise<HomeSnapshot>; entry?: string; state?: unknown }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const meta = async () => ({ api_prefix: "/api/v1/web", contract_version: "0.4.5", server_time: "2026-09-24T00:00:00Z", backend_version: "test", data_origin: "live", auth_methods_available: [], applied_migrations: [], capabilities: [{ key: "character.state", module: "character", status: "not_implemented", note: null }] });
  const services = {
    households: { list: async () => [householdFor(petId)] },
    world: { home: vi.fn(home) },
    transport: { journeyMap: vi.fn(async () => { throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有行程" }); }) },
    platform: { meta },
    pets: { character: vi.fn() },
  } as unknown as ServiceMap;
  const [pathname, search = ""] = entry.split("?");
  return render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <MemoryRouter initialEntries={[{ pathname, search: search ? `?${search}` : "", state }]}>
          <HouseholdProvider userId="u-1">
            <Routes>
              <Route path="/home" element={<HomePage />} />
              <Route path="*" element={<LocationProbe />} />
            </Routes>
          </HouseholdProvider>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
}

const hinting = () => document.querySelectorAll(".is-hinting").length;

describe("小窝是地图下面的二级页：左上角始终能回到地图", () => {
  it.each(["/home", "/home?from=map", "/home?room=inside"])("从 %s 进来都有“‹ 地图”，点它回到 /map", async (entry) => {
    renderPage({ petId: "pet-back", home: async () => snapshot({ petId: "pet-back" }), entry });
    await screen.findByRole("region", { name: /共同的家/ });
    const back = screen.getAllByRole("link", { name: "回到地图" });
    expect(back).toHaveLength(1);
    expect(back[0].getAttribute("href")).toBe("/map?focus=pet-back");
    expect(back[0].textContent).toBe("地图");
    fireEvent.click(back[0]);
    expect(screen.getByTestId("location").textContent).toBe("/map?focus=pet-back");
  });

  it("小窝还没读出来、或读取失败时，也给同一个出口", async () => {
    renderPage({ petId: "pet-wait", home: () => new Promise<HomeSnapshot>(() => undefined) });
    expect((await screen.findByRole("link", { name: "回到地图" })).getAttribute("href")).toBe("/map?focus=pet-wait");
    expect(screen.queryByRole("region", { name: /共同的家/ })).toBeNull();
    cleanup();
    renderPage({ petId: "pet-fail", home: async () => { throw new ApiError({ kind: "http", status: 500, code: "INTERNAL_ERROR", message: "家园暂时读不出来" }); } });
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("link", { name: "回到地图" }).getAttribute("href")).toBe("/map?focus=pet-fail");
  });
});

describe("“生活与回忆”那排入口不在小窝了", () => {
  it("没有那排入口，也没有管理员的“给这个家添伙伴”（已搬去“回忆”“我的”）", async () => {
    const view = renderPage({ petId: "pet-life", home: async () => snapshot({ petId: "pet-life" }) });
    await screen.findByRole("region", { name: "共同的家·庭院" });
    expect(screen.queryByRole("navigation", { name: "生活与回忆" })).toBeNull();
    for (const text of ["生活与回忆", "我们的家", "工作与证件", "我的收藏", "生活叮嘱", "给这个家添伙伴"]) {
      expect(view.container.textContent, text).not.toContain(text);
    }
    for (const href of ["/households/manage", "/life", "/collection", "/onboarding/reception?mode=supplement", "/pets/new"]) {
      expect(view.container.querySelector(`a[href="${href}"]`), href).toBeNull();
    }
  });
});

describe("“此刻 · 一起生活”面板已退役（与地图首页的主状态面板重复）", () => {
  it.each([
    ["在家、菜熟了、有未读", "at_home"],
    ["出门在外", "in_transit"],
  ] as const)("%s：页面上没有这块面板，也没有它的几个按钮", async (_label, presence) => {
    const view = renderPage({ petId: `pet-panel-${presence}`, home: async () => snapshot({ petId: `pet-panel-${presence}`, presence }) });
    await screen.findByRole("region", { name: /共同的家/ });
    expect(screen.queryByRole("region", { name: "此刻可以做的事" })).toBeNull();
    for (const text of ["此刻 · 一起生活", "去陪 TA", "给 TA 提个出行建议", "去菜园收菜", "块菜地成熟了", "信箱里有新消息", "打开看看"]) {
      expect(view.container.textContent, text).not.toContain(text);
    }
    expect(view.container.querySelector('a[href="/journey"]')).toBeNull();
  });

  it("它原来说的几件事换了地方：菜熟了菜园门发光，未读在院子信箱探出的信封 / 屋内信箱小图标的小红点，出门了看便笺回地图", () => {
    renderScene(snapshot({ petId: "pet-panel-moved", presence: "in_transit", unread: 3 }));
    const gate = screen.getByRole("button", { name: "菜园，1 块熟了" });
    expect(gate.className).toContain("is-ready");
    expect(gate.querySelector(".ps-living-garden-gate__ripe")).toBeTruthy();
    // 院子：场景里的信箱带着未读数（无障碍名称）与探出来的信封
    const mailbox = screen.getByRole("button", { name: "信箱，3 条未读" });
    expect(mailbox.querySelector(".ps-home-envelope")).toBeTruthy();
    expect(screen.getByRole("link", { name: /^我出门啦/ }).getAttribute("href")).toBe("/map?focus=pet-panel-moved");
    // 屋内：没有场景信箱，左侧信箱小图标挂小红点
    cleanup();
    renderScene(snapshot({ petId: "pet-panel-moved-in", presence: "in_transit", unread: 3 }), "/home?room=inside");
    const mail = within(screen.getByRole("navigation", { name: "快捷入口" })).getByRole("link", { name: "信箱，3 条未读" });
    expect(within(mail).getByTestId("home-rail-dot")).toBeTruthy();
  });
});

describe("左侧小图标：小窝自己的几件事", () => {
  it("屋内：有地址、有无障碍名称；平时一个字都不写（未读只挂小红点），不重复菜园门", () => {
    renderScene(snapshot({ petId: "pet-rail", unread: 2 }), "/home?room=inside");
    const rail = screen.getByRole("navigation", { name: "快捷入口" });
    const links = within(rail).getAllByRole("link");
    expect(links.map((link) => [link.getAttribute("aria-label"), link.getAttribute("href")])).toEqual([
      ["给 TA 拍一张", "/photos?scene=home"],
      ["信箱，2 条未读", "/communicator"],
    ]);
    expect(rail.textContent).toBe("");
    expect(within(links[1]).getByTestId("home-rail-dot").getAttribute("aria-hidden")).toBe("true");
    expect(within(links[0]).queryByTestId("home-rail-dot")).toBeNull();
    expect(links.map((link) => link.getAttribute("data-name"))).toEqual(["给 TA 拍一张", "信箱"]);
    expect(within(rail).queryByRole("link", { name: /菜园/ })).toBeNull();
    // 没有未读时不挂红点
    cleanup();
    renderScene(snapshot({ petId: "pet-rail-0", unread: 0 }), "/home?room=inside");
    const quiet = screen.getByRole("navigation", { name: "快捷入口" });
    expect(quiet.textContent).toBe("");
    expect(within(quiet).queryByTestId("home-rail-dot")).toBeNull();
    expect(within(quiet).getByRole("link", { name: "信箱" }).getAttribute("href")).toBe("/communicator");
  });

  it("庭院：场景里已经有信箱，左侧不再放信箱小图标（只剩拍一张）；换到屋内它才出现，换回来又收起", async () => {
    renderScene(snapshot({ petId: "pet-rail-court", unread: 2 }));
    const rail = screen.getByRole("navigation", { name: "快捷入口" });
    expect(within(rail).getAllByRole("link").map((link) => link.getAttribute("aria-label"))).toEqual(["给 TA 拍一张"]);
    expect(within(rail).queryByTestId("home-rail-dot")).toBeNull();
    // 院子里的信箱还在场景里，并带着未读
    expect(screen.getByRole("button", { name: "信箱，2 条未读" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "屋内" }));
    await waitFor(() => expect(within(screen.getByRole("navigation", { name: "快捷入口" })).getByRole("link", { name: "信箱，2 条未读" })).toBeTruthy());
    expect(screen.queryByRole("button", { name: /^信箱/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "庭院" }));
    await waitFor(() => expect(within(screen.getByRole("navigation", { name: "快捷入口" })).queryByRole("link", { name: /信箱/ })).toBeNull());
  });

  it("触屏：第一下只冒出写着名字的小气泡，点别处收起；再点一下才去", () => {
    renderScene(snapshot({ petId: "pet-rail-touch" }));
    const photo = screen.getByRole("link", { name: "给 TA 拍一张" });
    fireEvent.pointerDown(photo, { pointerType: "touch" });
    fireEvent.click(photo);
    expect(screen.queryByTestId("location")).toBeNull();
    const bubble = screen.getAllByRole("link", { name: "给 TA 拍一张" }).find((el) => el !== photo);
    expect(bubble?.textContent).toBe("给 TA 拍一张");
    expect(bubble?.getAttribute("href")).toBe("/photos?scene=home");
    fireEvent.pointerDown(document.body, { pointerType: "touch" });
    expect(screen.getAllByRole("link", { name: "给 TA 拍一张" })).toHaveLength(1);
    fireEvent.pointerDown(photo, { pointerType: "touch" });
    fireEvent.click(photo);
    fireEvent.pointerDown(photo, { pointerType: "touch" });
    fireEvent.click(photo);
    expect(screen.getByTestId("location").textContent).toBe("/photos?scene=home");
  });

  it("鼠标（悬停已经看得到名字）与键盘：点一下直接去", () => {
    renderScene(snapshot({ petId: "pet-rail-mouse" }), "/home?room=inside");
    const mail = screen.getByRole("link", { name: "信箱，2 条未读" });
    fireEvent.pointerDown(mail, { pointerType: "mouse" });
    fireEvent.click(mail);
    expect(screen.getByTestId("location").textContent).toBe("/communicator");
    cleanup();
    renderScene(snapshot({ petId: "pet-rail-key" }));
    fireEvent.click(screen.getByRole("link", { name: "给 TA 拍一张" }));
    expect(screen.getByTestId("location").textContent).toBe("/photos?scene=home");
  });
});

describe("场景里的东西平时不写字，点到才冒出名字和能做的事", () => {
  it("默认没有任何物件名字在页面上，每件都有无障碍名称", () => {
    renderScene(snapshot({ petId: "pet-words" }));
    const scene = screen.getByRole("region", { name: "共同的家·庭院" });
    for (const word of ["屋门", "进屋", "信箱", "菜园", "熟了", "窗台上的软垫", "叮嘱", "陪 TA", "我出门啦"]) {
      expect(scene.textContent, word).not.toContain(word);
    }
    for (const name of ["屋门", "看看 栗子", "你留下的叮嘱：窗台上的软垫", "信箱，2 条未读", "菜园，1 块熟了"]) {
      expect(screen.getByRole("button", { name }).getAttribute("aria-expanded"), name).toBe("false");
    }
    expect(screen.queryByRole("group")).toBeNull();
  });

  it("点一下冒出名字与能做的事，再点收起；点别处收起；点在气泡里不收；同一时间只开一个", () => {
    renderScene(snapshot({ petId: "pet-tap" }));
    const garden = screen.getByRole("button", { name: "菜园，1 块熟了" });
    fireEvent.click(garden);
    expect(garden.getAttribute("aria-expanded")).toBe("true");
    const bubble = screen.getByRole("group", { name: "菜园" });
    expect(garden.getAttribute("aria-controls")).toBe(bubble.id);
    expect(bubble.textContent).toContain("1 块熟了");
    expect(within(bubble).getByRole("link", { name: "去菜园" }).getAttribute("href")).toBe("/garden");
    fireEvent.click(garden);
    expect(screen.queryByRole("group", { name: "菜园" })).toBeNull();
    expect(garden.getAttribute("aria-expanded")).toBe("false");

    const mail = screen.getByRole("button", { name: "信箱，2 条未读" });
    fireEvent.click(mail);
    const mailBubble = screen.getByRole("group", { name: "信箱" });
    expect(mailBubble.textContent).toContain("2 条新消息");
    expect(within(mailBubble).getByRole("link", { name: "打开信箱" }).getAttribute("href")).toBe("/communicator");
    fireEvent.pointerDown(within(mailBubble).getByRole("link", { name: "打开信箱" }));
    expect(screen.getByRole("group", { name: "信箱" })).toBeTruthy();
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("group", { name: "信箱" })).toBeNull();

    fireEvent.click(mail);
    fireEvent.click(garden);
    expect(screen.queryByRole("group", { name: "信箱" })).toBeNull();
    expect(screen.getByRole("group", { name: "菜园" })).toBeTruthy();
    expect(screen.getAllByRole("group")).toHaveLength(1);
  });

  it("Esc 收起气泡，焦点回到那件东西上", () => {
    renderScene(snapshot({ petId: "pet-esc" }));
    const memento = screen.getByRole("button", { name: "你留下的叮嘱：窗台上的软垫" });
    memento.focus();
    fireEvent.click(memento);
    const bubble = screen.getByRole("group", { name: "窗台上的软垫" });
    expect(bubble.textContent).toContain("你为 TA 留下的生活叮嘱");
    const more = within(bubble).getByRole("link", { name: "补充叮嘱" });
    expect(more.getAttribute("href")).toBe("/onboarding/reception?mode=supplement");
    more.focus();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("group", { name: "窗台上的软垫" })).toBeNull();
    expect(document.activeElement).toBe(memento);
  });

  it("屋门带你进屋；屋里的收藏柜通向收藏；换了房间，原来的气泡跟着消失", () => {
    renderScene(snapshot({ petId: "pet-door" }));
    fireEvent.click(screen.getByRole("button", { name: "屋门" }));
    fireEvent.click(within(screen.getByRole("group", { name: "屋门" })).getByRole("button", { name: "进屋看看" }));
    expect(screen.getByRole("region", { name: "共同的家·屋内" })).toBeTruthy();
    expect(screen.queryByRole("group")).toBeNull();
    expect(screen.queryByRole("button", { name: "屋门" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "收藏柜" }));
    expect(within(screen.getByRole("group", { name: "收藏柜" })).getByRole("link", { name: "看看收藏" }).getAttribute("href")).toBe("/collection");
    fireEvent.click(screen.getByRole("button", { name: "庭院" }));
    expect(screen.getByRole("region", { name: "共同的家·庭院" })).toBeTruthy();
    expect(screen.queryByRole("group")).toBeNull();
  });

  it("TA：点一下冒出名字，“陪 TA 待一会儿”打开面板，面板收起后焦点回到 TA", () => {
    renderScene(snapshot({ petId: "pet-sheet" }));
    const pet = screen.getByRole("button", { name: "看看 栗子" });
    fireEvent.click(pet);
    const bubble = screen.getByRole("group", { name: "栗子" });
    expect(bubble.textContent).toContain("在家");
    fireEvent.click(within(bubble).getByRole("button", { name: "陪 TA 待一会儿" }));
    expect(screen.getByRole("dialog", { name: /陪 栗子 待一会儿/ }).parentElement).toBe(document.body);
    expect(screen.queryByRole("group", { name: "栗子" })).toBeNull();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(pet);
  });
});

describe("第一次进来：可点的东西依次轻闪一次，之后不再打扰", () => {
  it("按从上到下的顺序依次亮；按宠物记在本机，第二次进来不再出现，换一只宠物照常提示", () => {
    const first = renderScene(snapshot({ petId: "pet-hint-a" }));
    expect(screen.getByRole("region", { name: "共同的家·庭院" }).getAttribute("data-hint")).toBe("on");
    const things = ["屋门", "看看 栗子", "你留下的叮嘱：窗台上的软垫", "信箱，2 条未读", "菜园，1 块熟了"].map((name) => screen.getByRole("button", { name }));
    for (const thing of things) expect(thing.className).toContain("is-hinting");
    const delays = things.map((thing) => Number.parseInt(thing.style.getPropertyValue("--hint-delay"), 10));
    expect(delays.every(Number.isFinite)).toBe(true);
    expect(delays).toEqual([...delays].sort((a, b) => a - b));
    expect(new Set(delays).size).toBe(delays.length);
    // 小图标不在提示之列
    expect(within(screen.getByRole("navigation", { name: "快捷入口" })).queryAllByRole("link").some((link) => link.className.includes("is-hinting"))).toBe(false);
    expect(localStorage.getItem("petsoul:home-intro:pet-hint-a")).toBe("1");

    first.unmount();
    renderScene(snapshot({ petId: "pet-hint-a" }));
    expect(hinting()).toBe(0);
    expect(screen.getByRole("region", { name: "共同的家·庭院" }).getAttribute("data-hint")).toBeNull();

    cleanup();
    renderScene(snapshot({ petId: "pet-hint-b" }));
    expect(hinting()).toBeGreaterThan(0);
  });

  it("TA 不在家时，便笺也在提示之列", () => {
    renderScene(snapshot({ petId: "pet-hint-away", presence: "in_transit" }));
    expect(screen.getByRole("link", { name: /^我出门啦/ }).className).toContain("is-hinting");
  });

  it("闪完一轮就安静下来", () => {
    vi.useFakeTimers();
    try {
      renderScene(snapshot({ petId: "pet-hint-quiet" }));
      expect(hinting()).toBeGreaterThan(0);
      act(() => {
        vi.advanceTimersByTime(10_000);
      });
      expect(hinting()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it("本机存储读写都抛错时不崩，当作第一次", () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("denied", "SecurityError");
    });
    renderScene(snapshot({ petId: "pet-storage-throws" }));
    expect(screen.getByRole("region", { name: "共同的家·庭院" })).toBeTruthy();
    expect(hinting()).toBeGreaterThan(0);
    expect(getItem).toHaveBeenCalled();
    expect(setItem).toHaveBeenCalled();
  });

  it("连 localStorage 本身都拿不到（隐私模式、被禁用）时也不崩", () => {
    const own = Object.getOwnPropertyDescriptor(window, "localStorage");
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new DOMException("denied", "SecurityError");
      },
    });
    try {
      renderScene(snapshot({ petId: "pet-storage-gone" }));
      expect(screen.getByRole("region", { name: "共同的家·庭院" })).toBeTruthy();
      expect(hinting()).toBeGreaterThan(0);
    } finally {
      if (own) Object.defineProperty(window, "localStorage", own);
      else delete (window as unknown as { localStorage?: Storage }).localStorage;
    }
    expect(() => window.localStorage.getItem("x")).not.toThrow();
  });

  it("到家时刻的卡片还开着时先不提示、也不记；关掉以后才依次亮", async () => {
    renderPage({ petId: "pet-arrive", home: async () => snapshot({ petId: "pet-arrive" }), state: { arrival: "pet-arrive" } });
    const dialog = await screen.findByRole("dialog", { name: "栗子 到家了" });
    expect(hinting()).toBe(0);
    expect(localStorage.getItem("petsoul:home-intro:pet-arrive")).toBeNull();
    fireEvent.click(within(dialog).getByRole("button", { name: "进家看看" }));
    await waitFor(() => expect(hinting()).toBeGreaterThan(0));
    expect(localStorage.getItem("petsoul:home-intro:pet-arrive")).toBe("1");
  });
});

describe("TA 不在家：窝是空的，窝边一张“我出门啦”", () => {
  it.each(["in_transit", "at_destination", "visiting", "returning"] as const)("%s：没有 TA，便笺点开回到地图", (presence) => {
    renderScene(snapshot({ petId: `pet-away-${presence}`, presence }));
    expect(screen.queryByTestId("home-pet")).toBeNull();
    const note = screen.getByRole("link", { name: /^我出门啦/ });
    expect(note.getAttribute("href")).toBe(`/map?focus=pet-away-${presence}`);
    expect(note.textContent).toContain("我出门啦");
    fireEvent.click(note);
    expect(screen.getByTestId("location").textContent).toBe(`/map?focus=pet-away-${presence}`);
  });

  it("屋里也一样；便笺只看 TA 在不在家这件事，不依赖有没有行程摘要", () => {
    renderScene(snapshot({ petId: "pet-away-inside", presence: "in_transit", journey: false }), "/home?room=inside");
    expect(screen.getByRole("region", { name: "共同的家·屋内" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /^我出门啦/ }).getAttribute("href")).toBe("/map?focus=pet-away-inside");
    expect(screen.queryByTestId("home-pet")).toBeNull();
  });

  it("在家时照常有 TA、没有便笺；不知道 TA 在哪（unknown）时不替 TA 写“出门啦”", () => {
    renderScene(snapshot({ petId: "pet-at-home" }));
    expect(screen.getByTestId("home-pet")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /我出门啦/ })).toBeNull();
    expect(screen.queryByText(/我出门啦/)).toBeNull();
    cleanup();
    renderScene(snapshot({ petId: "pet-unknown", presence: "unknown" }));
    expect(screen.queryByTestId("home-pet")).toBeNull();
    expect(screen.queryByRole("link", { name: /我出门啦/ })).toBeNull();
  });
});

describe("庭院 / 屋内切换不加浏览器历史（replace）", () => {
  function renderFromMap(home: HomeSnapshot) {
    const router = createMemoryRouter(
      [
        { path: "/home", element: <HomeScene snapshot={home} /> },
        { path: "*", element: <LocationProbe /> },
      ],
      { initialEntries: ["/map", "/home?from=map"], initialIndex: 1 },
    );
    render(<RouterProvider router={router} />);
    return router;
  }

  it("用切换键来回换房间，再按返回：直接回到地图，不会回到小窝的某个房间", async () => {
    const router = renderFromMap(snapshot({ petId: "pet-room-switch" }));
    fireEvent.click(screen.getByRole("button", { name: "屋内" }));
    await waitFor(() => expect(router.state.location.search).toBe("?from=map&room=inside"));
    expect(router.state.historyAction).toBe("REPLACE");
    fireEvent.click(screen.getByRole("button", { name: "庭院" }));
    await waitFor(() => expect(router.state.location.search).toBe("?from=map"));
    fireEvent.click(screen.getByRole("button", { name: "屋内" }));
    await waitFor(() => expect(router.state.location.search).toBe("?from=map&room=inside"));
    await act(async () => {
      await router.navigate(-1);
    });
    expect(router.state.location.pathname).toBe("/map");
  });

  it("从屋门进屋也一样", async () => {
    const router = renderFromMap(snapshot({ petId: "pet-room-door" }));
    fireEvent.click(screen.getByRole("button", { name: "屋门" }));
    fireEvent.click(within(screen.getByRole("group", { name: "屋门" })).getByRole("button", { name: "进屋看看" }));
    await waitFor(() => expect(screen.getByRole("region", { name: "共同的家·屋内" })).toBeTruthy());
    expect(router.state.historyAction).toBe("REPLACE");
    await act(async () => {
      await router.navigate(-1);
    });
    expect(router.state.location.pathname).toBe("/map");
  });
});

describe("home.panels 在小窝里一张都不放（白名单已清空；驾校提醒在地图主状态面板，方案 8.2）", () => {
  it("驾校卡、旅途状态卡与其他模块新加的卡都不渲染；入住欢迎（home.welcome）照旧", () => {
    const registry = buildSlotRegistry([
      slot("home.panels", "journey.status", () => <p>旅途状态卡</p>, 5),
      slot("home.panels", "driving_school.progress", () => <p>驾校卡</p>, 40),
      slot("home.panels", "someone.else", () => <p>别的模块的卡</p>, 50),
      slot("home.welcome", "home.welcome-banner", () => <p>入住欢迎</p>, 10),
    ]);
    const view = render(
      <SlotProvider registry={registry}>
        <MemoryRouter initialEntries={["/home"]}>
          <HomeBody snapshot={snapshot({ petId: "pet-panels" })} />
        </MemoryRouter>
      </SlotProvider>,
    );
    expect(view.container.textContent).not.toContain("驾校卡");
    expect(screen.getByText("入住欢迎")).toBeTruthy();
    expect(view.container.textContent).not.toContain("旅途状态卡");
    expect(view.container.textContent).not.toContain("别的模块的卡");
  });
});

/* ---------------- 真实路由表（所有模块、live）：二级页不挂底栏，但守卫照旧 ---------------- */

const modules = loadFeatureModules();
const never = () => new Promise<never>(() => undefined);

function onboarding(step: OnboardingState["step"]): OnboardingState {
  return { step, pet_id: "pet-route", home_id: "home-1", reception_session_id: "rs-1", reception_skipped: false, home_activated_at: step === "active" ? "2026-09-23T00:00:00Z" : null, pet_origin: "own_pet" };
}
function sessionAt(step: OnboardingState["step"]): SessionState {
  return { authenticated: true, user: { user_id: "u-1", username: "owner", display_name: null, auth_method: "web_password" }, csrf_required: false, expires_at: null, onboarding: onboarding(step) };
}
const anonymous: SessionState = { authenticated: false, user: null, csrf_required: false, expires_at: null, onboarding: null };

/** 只给这一页真用到的服务；其余一律“还在读”（不会去碰任何别的接口，只看路由和这一页）。 */
function appServices(session: SessionState, extra: Record<string, Record<string, unknown>> = {}): ServiceMap {
  const stub = new Proxy({}, { get: (_t, prop) => (prop === "then" ? undefined : prop === "fixtureScenarios" || prop === "fixtureVariants" ? () => [] : never) });
  const meta = async () => ({ api_prefix: "/api/v1/web", contract_version: "0.4.5", server_time: "2026-09-24T00:00:00Z", backend_version: "test", data_origin: "live", auth_methods_available: [], applied_migrations: [], capabilities: [{ key: "character.state", module: "character", status: "not_implemented", note: null }] });
  const own: Record<string, Record<string, unknown>> = {
    session: { current: async () => session },
    platform: { meta },
    households: { list: async () => [householdFor("pet-route")] },
    world: { home: async () => snapshot({ petId: "pet-route", presence: "in_transit" }) },
    ...extra,
  };
  return new Proxy({} as ServiceMap, {
    get: (_t, key) => {
      const table = typeof key === "string" ? own[key] : undefined;
      if (!table) return stub;
      return new Proxy(stub, { get: (t, p) => (typeof p === "string" && p in table ? table[p] : Reflect.get(t, p)) });
    },
  });
}

function renderApp(path: string, services: ServiceMap) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(buildRoutes(modules), { initialEntries: [path] });
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <SlotProvider registry={buildSlotRegistry(modules.flatMap((m) => m.slots ?? []))}>
          <RouterProvider router={router} />
        </SlotProvider>
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return router;
}

describe("小窝挂在不带底栏的布局下，登录与入住守卫照旧（真实路由表、live）", () => {
  // 主布局现在也只在三个标签页显示底栏，所以“没有主导航”这一条靠两道机制都能成立、分不出是哪一道；
  // 方案 2.2 定的是“二级页挂 bareRoutes”，这里直接钉路由表：/home 挪回带底栏的主布局会红。
  it("路由表里 /home 登记在不带底栏的 bareRoutes（二级页），不在主布局里", () => {
    const [tabbed, bare] = buildRoutes(modules);
    expect((bare.children ?? []).map((c) => c.path)).toContain("home");
    expect((tabbed.children ?? []).map((c) => c.path)).not.toContain("home");
  });

  it("已登录、已入住：打开 /home 是小窝，没有任何底栏（主布局的“主导航”与新版预览底栏都没有）", async () => {
    const router = renderApp("/home?from=map", appServices(sessionAt("active")));
    expect(await screen.findByRole("region", { name: "共同的家·庭院" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/home");
    expect(screen.queryByRole("navigation", { name: "主导航" })).toBeNull();
    expect(screen.queryByRole("navigation", { name: "主导航（新版预览）" })).toBeNull();
    expect(document.querySelector(".ps-tabbar")).toBeNull();
    // 渲染在不带底栏的外壳里
    expect(document.querySelector(".ps-shell--bare")).toBeTruthy();
    expect(screen.getByRole("link", { name: "回到地图" }).getAttribute("href")).toBe("/map?focus=pet-route");
  });

  it("未登录打开 /home：去欢迎页，并记下是从小窝来的", async () => {
    const router = renderApp("/home", appServices(anonymous));
    await waitFor(() => expect(router.state.location.pathname).toBe("/welcome"));
    expect(router.state.location.state).toEqual({ from: "/home" });
  });

  it.each([
    ["reception_optional", "/onboarding/reception"],
    ["ready_to_move_in", "/onboarding/move-in"],
  ] as const)("入住还没完成（%s）打开 /home：回到对应的入住步骤 %s", async (step, target) => {
    const router = renderApp("/home", appServices(sessionAt(step)));
    await waitFor(() => expect(router.state.location.pathname).toBe(target));
  });

  it("真实插槽里：驾校卡（已挪到地图主状态面板，方案 8.2）与旅途状态卡（链到 /journey）都不出现", async () => {
    const view = { driving: createFixtureDrivingService({ stage: "enrolled", latency: 0 }) as unknown as Record<string, unknown> };
    renderApp("/home", appServices(sessionAt("active"), view));
    expect(await screen.findByRole("region", { name: "共同的家·庭院" })).toBeTruthy();
    // 学车中（enrolled）按旧规矩本该有驾校卡；等它有机会出现再断言没有。
    await act(async () => {
      await new Promise((r) => setTimeout(r, 150));
    });
    expect(screen.queryByRole("link", { name: /爪爪驾校/ })).toBeNull();
    expect(document.body.textContent).not.toContain("点开地图看 TA 在哪");
    expect(document.body.textContent).not.toContain("出不出门由 TA 决定");
    expect(document.querySelector('a[href="/journey"]')).toBeNull();
  });
});

/* ---------------- [过渡方案] 场景自然淡进地面 ---------------- */

const HOME_CSS = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "..", "src", "features", "home", "home.css"), "utf8");
const FADE = "linear-gradient(to bottom, #000 86%, transparent)";

/** 带某条声明的所有规则（先去掉注释；@media 里的规则按最里层的选择器算）。 */
function rulesWith(css: string, declaration: RegExp): Array<{ selector: string; body: string }> {
  const bare = css.replace(/\/\*[\s\S]*?\*\//g, "");
  return [...bare.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter((m) => declaration.test(m[2])).map((m) => ({ selector: m[1].trim(), body: m[2] }));
}

/** 只有屋内还用过渡方案（庭院已换 UI-ASSET-008 长图）：屋内底图这一层的选择器。 */
const INSIDE_BG = ".ps-living-scene.is-inside .ps-living-background";

/** 遮罩只许在屋内底图这一层，并且带 -webkit- 前缀；返回发现的问题（空数组 = 没问题）。 */
function maskProblems(css: string): string[] {
  const problems: string[] = [];
  const masked = rulesWith(css, /(^|[;\s])(-webkit-)?mask(-image)?\s*:/);
  for (const rule of masked) if (rule.selector !== INSIDE_BG) problems.push(`遮罩加在了 ${rule.selector}`);
  const own = masked.filter((rule) => rule.selector === INSIDE_BG).map((rule) => rule.body).join(";");
  if (!own.includes(`-webkit-mask-image: ${FADE}`)) problems.push("底图缺 -webkit-mask-image");
  if (!new RegExp(`(^|[;\\s])mask-image: ${FADE.replace(/[()%#]/g, "\\$&")}`).test(own)) problems.push("底图缺 mask-image");
  return problems;
}

describe("[过渡方案] 场景自然淡进地面（庭院已换长图；屋内底图往下延伸的真图到了整段删掉）", () => {
  it("遮罩只加在屋内底图这一层（带 -webkit- 前缀）；庭院底图、装热区的 section、TA、便笺、菜园门、地面层都不加", () => {
    expect(maskProblems(HOME_CSS)).toEqual([]);
  });

  it("这项检查自己会红：遮罩挪到 section 上、挪到所有底图上（庭院也淡出）、或少了 -webkit- 前缀，都查得出来", () => {
    const onSection = HOME_CSS.replace(/\.ps-living-scene\.is-inside \.ps-living-background \{(\r?\n) {2}-webkit-mask-image/, ".ps-living-scene {$1  -webkit-mask-image");
    expect(onSection).not.toBe(HOME_CSS);
    expect(maskProblems(onSection)).toContain("遮罩加在了 .ps-living-scene");
    const onBoth = HOME_CSS.replace(/\.ps-living-scene\.is-inside \.ps-living-background \{(\r?\n) {2}-webkit-mask-image/, ".ps-living-background {$1  -webkit-mask-image");
    expect(onBoth).not.toBe(HOME_CSS);
    expect(maskProblems(onBoth)).toContain("遮罩加在了 .ps-living-background");
    const noPrefix = HOME_CSS.replace(/-webkit-mask-image:[^;]*;/, "");
    expect(noPrefix).not.toBe(HOME_CSS);
    expect(maskProblems(noPrefix)).toEqual(["底图缺 -webkit-mask-image"]);
  });

  it("过渡层的样式都在标了 [过渡方案] 的一段里：删掉这一段，遮罩与地面层一起没了，section 回到纯色占位", () => {
    const start = HOME_CSS.indexOf("[过渡方案] 场景自然淡进地面 · 开始");
    const end = HOME_CSS.indexOf("[过渡方案] 场景自然淡进地面 · 结束");
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
    const outside = HOME_CSS.slice(0, start) + HOME_CSS.slice(end);
    expect(outside).not.toMatch(/ps-living-extend|mask-image/);
    expect(outside).toMatch(/\.ps-living-scene \{[^}]*background: #dec79e;/);
    expect(HOME_CSS.slice(start, end)).toMatch(/\.ps-living-extend \{/);
  });

  it("地面层是场景外面的一个独立装饰元素：庭院是长图地面层、屋内是过渡垫层，都不在 section 里、对读屏隐藏、里面没有东西", async () => {
    renderScene(snapshot({ petId: "pet-extend" }));
    const courtyardScene = screen.getByRole("region", { name: "共同的家·庭院" });
    // 庭院：长图地面层，没有过渡垫层
    const ground = screen.getByTestId("home-scene-ground");
    expect(screen.queryByTestId("home-scene-extend")).toBeNull();
    expect(courtyardScene.contains(ground)).toBe(false);
    expect(ground.getAttribute("aria-hidden")).toBe("true");
    expect(ground.childElementCount).toBe(0);
    expect(courtyardScene.querySelector(".ps-living-background")?.tagName).toBe("IMG");
    fireEvent.click(screen.getByRole("button", { name: "屋内" }));
    // 屋内：过渡垫层（遮罩所在的底图是一张图片，里面装不下任何可点的东西），没有长图地面层
    await waitFor(() => expect(screen.getByTestId("home-scene-extend").className).toContain("is-inside"));
    const extend = screen.getByTestId("home-scene-extend");
    expect(screen.queryByTestId("home-scene-ground")).toBeNull();
    const insideScene = screen.getByRole("region", { name: "共同的家·屋内" });
    expect(insideScene.contains(extend)).toBe(false);
    expect(extend.getAttribute("aria-hidden")).toBe("true");
    expect(extend.childElementCount).toBe(0);
    expect(insideScene.querySelector(".ps-living-background")?.tagName).toBe("IMG");
  });
});
