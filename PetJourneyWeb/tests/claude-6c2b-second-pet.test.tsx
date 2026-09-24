/**
 * claude-6c2b · 2026-09-24 巡检 P1：第二只宠物还在接待 / 入住时，账号不再被锁在接待页。
 * - 主布局 SessionGate 与 WorldGate 的拦截收窄：会话里任何一个已启用的家有 moved_in 的宠物就不拦；一只都没住进来（第一次入住）照旧拦。
 * - 接待页、入住页在这种情况下有出口“先不加了，回到 {名字}”，去 /map；当前宠物还是原来那只（切换栏记住的那只），不会换成待入住的这只。
 * - “我的”页出现一行“{名字}还没住进来 · 继续入住”，去它的入住步骤。
 * - 接待页先接回这只宠物还没结束的接待（reception_session_id），没有、读不到或已结束才新开（原来每进一次就新开一次）。
 * - 到家时刻：不是家里第一只住进来的，说明入住欢迎星币每个家发一次、给了第一只（I 拍板：第二只起是 0，维持现状，由前端说明）。
 * - 整理页（主窗口 23:1x 批准）：这次接待的宠物不是入住阶段里那只（第二只待入住时给第一只补充）就是“补充”——
 *   不写“入住准备 · 03 / 04”，没有“带 TA 去新家”，不去第二只的入住页；以数据为准，?mode=supplement 只作辅助。
 * 路由用的是真的 RootLayout / WorldGate / 页面组件；“地图”“通讯器”的页面内容换成读当前宠物的探针（它们自己的内容由各自的测试管）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider, useLocation, type RouteObject } from "react-router";
import type { HomePlaceView, HomeSnapshot, HouseholdBrief, HouseholdPetBrief, IntakeCandidate, IntakeConfirmationResult, OnboardingState, PetPublicProfile, ReceptionSession, SessionState, WebMeta } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { useCurrentHousehold } from "@/shared/session/householdContext";
import { RootLayout } from "@/app/RootLayout";
import { WorldGate } from "@/features/world_map/WorldGate";
import { ReceptionPage } from "@/features/reception/ReceptionPage";
import { MoveInPage } from "@/features/identity/pages";
import { CareNotesPage } from "@/features/reception/CareNotesPage";
import { MePage } from "@/features/me/MePage";
import { ArrivalMoment } from "@/features/home/ArrivalMoment";
import { fixtureHomeSnapshot } from "@/fixtures/home";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "live", isDev: false, apiBase: "/api/v1/web" } }));

beforeEach(() => {
  sessionStorage.clear();
  // 主布局里有滚动恢复；jsdom 没有 scrollTo。
  vi.stubGlobal("scrollTo", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

/* ---------------- 数据 ---------------- */

const USER = "owner-1";
const MAIYA = "pet-maiya";
const DOUBAO = "pet-doubao";
const NAICHA = "pet-naicha";
const NAMES: Record<string, string> = { [MAIYA]: "麦芽", [DOUBAO]: "豆包", [NAICHA]: "奶茶" };

function petBrief(petId: string, step: HouseholdPetBrief["join_step"]): HouseholdPetBrief {
  return { pet_id: petId, name: NAMES[petId], species: "cat", photo_url: null, origin: "own_pet", presence: step === "moved_in" ? "at_home" : "not_activated", join_step: step, joined_at: "2026-09-24T00:00:00Z", added_by_you: true };
}

function home(activated: boolean, pets: HouseholdPetBrief[]): HouseholdBrief {
  return { household_id: "house-1", name: null, home_id: "home-1", role: "admin", home_activated: activated, member_count: 1, pets };
}

/** 账号的会话：step / pet_id 是入住阶段里记着的那只；households 是会话里带的家庭列表（不给就是旧后端，没有这一栏）。 */
function account(step: OnboardingState["step"], petId: string, households: HouseholdBrief[] | undefined, receptionSessionId: string | null = null): SessionState {
  const onboarding: OnboardingState = { step, pet_id: petId, home_id: "home-1", reception_session_id: receptionSessionId, reception_skipped: false, home_activated_at: null, pet_origin: "own_pet" };
  if (households) onboarding.households = households;
  return { authenticated: true, user: { user_id: USER, username: "lin", display_name: null, auth_method: "web_password" }, csrf_required: false, expires_at: null, onboarding };
}

/** 第一次入住：一只都没住进来（家也还没启用）。 */
const firstTime = (step: "reception_optional" | "ready_to_move_in" = "reception_optional", receptionSessionId: string | null = null) =>
  account(step, NAICHA, [home(false, [petBrief(NAICHA, step)])], receptionSessionId);
/** 麦芽已经住进来，第二只奶茶还在接待 / 入住（巡检复现的情形）。 */
const secondPet = (step: "reception_optional" | "ready_to_move_in" = "reception_optional") =>
  account(step, NAICHA, [home(true, [petBrief(MAIYA, "moved_in"), petBrief(NAICHA, step)])]);
/** 麦芽、豆包都住进来了，第三只奶茶还在接待。 */
const thirdPet = () => account("reception_optional", NAICHA, [home(true, [petBrief(MAIYA, "moved_in"), petBrief(DOUBAO, "moved_in"), petBrief(NAICHA, "reception_optional")])]);
/** 只有住进来的麦芽，没有待入住的。 */
const settledOnly = () => account("active", MAIYA, [home(true, [petBrief(MAIYA, "moved_in")])]);

const profileOf = (petId: string) => ({ pet_id: petId, display_name: NAMES[petId] ?? "TA", species: "cat", avatar_url: null }) as unknown as PetPublicProfile;

const candidate = {
  candidate_id: "c-1", kind: "habit", subject: "pet", text: "它听到零食袋的声音会跑过来", source_turn_id: "t-2", source_excerpt: "它听到零食袋的声音会跑过来",
  needs_clarification: false, suggested_slot: null, suggested_slot_value: null, state: "unconfirmed",
} as IntakeCandidate;

function receptionSession(sessionId: string, petId: string, status: ReceptionSession["status"] = "active", said = false): ReceptionSession {
  return {
    session_id: sessionId, pet_id: petId, branch: "own_pet", mode: "guided_notes", status,
    host: { host_id: "h", display_name: "星球接待员", role_label: "PetSoul 的 AI 接待角色", avatar_url: null, is_ai: true, disclosure: "我是 AI 接待角色。" },
    turns: said
      ? [
          { turn_id: "t-1", seq: 1, speaker: "host", text: "有什么想交代的吗？", created_at: "2026-09-24T00:00:00Z" },
          { turn_id: "t-2", seq: 2, speaker: "owner", text: "它听到零食袋的声音会跑过来", created_at: "2026-09-24T00:01:00Z" },
          { turn_id: "t-3", seq: 3, speaker: "host", text: "记下了，等你确认。", created_at: "2026-09-24T00:01:00Z" },
        ]
      : [{ turn_id: "t-1", seq: 1, speaker: "host", text: "有什么想交代的吗？", created_at: "2026-09-24T00:00:00Z" }],
    candidates: said ? [candidate] : [], draft_revision: said ? 2 : 1, draft_expires_at: null, data_origin: "live",
  };
}

const meta: WebMeta = { api_prefix: "/api/v1/web", contract_version: "0.4.5", server_time: "2026-09-24T00:00:00Z", backend_version: "test", data_origin: "live", auth_methods_available: [], applied_migrations: [], capabilities: [] } as unknown as WebMeta;

const place: HomePlaceView = {
  place: { habitat: "city", habitat_label: "城市", city: "香港", area_label: "中环", display: "香港·中环", timezone: "Asia/Hong_Kong", chosen: true },
  options: [],
  can_change: true,
};

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

/** 落在入住步骤（或别的没挂页面的路径）时读地址。 */
function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}</output>;
}

/** 放进了页面：哪一页、当前宠物是谁（在 HouseholdProvider 里读，和切换栏同一个来源）。 */
function Where({ page }: { page: string }) {
  const { pet } = useCurrentHousehold();
  return <output data-testid="where">{`${page}·${pet?.name ?? "-"}`}</output>;
}

const MAP_ROUTE: RouteObject = { path: "/map", element: <WorldGate><Where page="地图" /></WorldGate> };
/** 主布局（带底栏的页面走它的 SessionGate）与地图（全屏页走 WorldGate）。 */
const GATE_ROUTES: RouteObject[] = [{ element: <RootLayout />, children: [{ path: "/communicator", element: <Where page="通讯器" /> }] }, MAP_ROUTE];

function renderRoutes(path: string, routes: RouteObject[], services: Record<string, unknown>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter([...routes, { path: "*", element: <LocationProbe /> }], { initialEntries: [path] });
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={strictServices(services)}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return router;
}

function gateServices(session: SessionState) {
  return {
    session: { current: async () => session },
    households: { list: async () => session.onboarding?.households ?? [] },
    platform: { meta: async () => meta },
  };
}

function receptionServices(session: SessionState, sessions: Record<string, ReceptionSession | Error> = {}) {
  const start = vi.fn(async (body: { pet_id: string }) => receptionSession(`rs-new-${body.pet_id}`, body.pet_id));
  const get = vi.fn(async (id: string) => {
    if (id.startsWith("rs-new-")) return receptionSession(id, id.slice("rs-new-".length));
    const found = sessions[id];
    if (!found) throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有找到这次接待。" });
    if (found instanceof Error) throw found;
    return found;
  });
  const skip = vi.fn();
  return {
    start, get, skip,
    services: {
      session: { current: async () => session },
      households: { list: async () => session.onboarding?.households ?? [] },
      pets: { publicProfile: async (petId: string) => profileOf(petId) },
      reception: { start, get, skip },
      world: { home: vi.fn() },
    },
  };
}

const where = () => screen.findByTestId("where").then((el) => el.textContent);
const location = () => screen.findByTestId("location").then((el) => el.textContent);

/* ---------------- 1. 守卫 ---------------- */

describe("守卫：一只都没住进来才拦", () => {
  it.each([
    ["/communicator", "主布局"],
    ["/map", "WorldGate"],
  ])("第一次入住（一只都没住进来）：%s（%s）照旧带去接待", async (path) => {
    renderRoutes(path, GATE_ROUTES, gateServices(firstTime()));
    expect(await location()).toBe("/onboarding/reception");
    expect(screen.queryByTestId("where")).toBeNull();
  });

  it.each([
    ["/communicator", "主布局"],
    ["/map", "WorldGate"],
  ])("第一次入住、已经可以入住：%s（%s）照旧带去入住页", async (path) => {
    renderRoutes(path, GATE_ROUTES, gateServices(firstTime("ready_to_move_in")));
    expect(await location()).toBe("/onboarding/move-in");
  });

  it.each([
    ["/communicator", "主布局"],
    ["/map", "WorldGate"],
  ])("会话里没带家庭列表（旧后端）：%s（%s）照旧拦，不当成已住进来", async (path) => {
    renderRoutes(path, GATE_ROUTES, gateServices(account("reception_optional", NAICHA, undefined)));
    expect(await location()).toBe("/onboarding/reception");
  });

  it.each([
    ["/communicator", "通讯器"],
    ["/map", "地图"],
  ])("麦芽已住进来、第二只奶茶还在接待：%s 不拦，当前宠物是麦芽", async (path, page) => {
    renderRoutes(path, GATE_ROUTES, gateServices(secondPet()));
    expect(await where()).toBe(`${page}·麦芽`);
    expect(screen.queryByTestId("location")).toBeNull();
  });

  it("麦芽已住进来、奶茶已经可以入住：地图也不拦", async () => {
    renderRoutes("/map", GATE_ROUTES, gateServices(secondPet("ready_to_move_in")));
    expect(await where()).toBe("地图·麦芽");
  });
});

/* ---------------- 2. 出口 ---------------- */

describe("接待页、入住页的出口：先不加了，回到已经住进来的那只", () => {
  it("接待页：切换栏记着豆包、第三只奶茶在接待——出口写“回到 豆包”，点了去地图，当前宠物还是豆包；不跳过接待", async () => {
    sessionStorage.setItem(`petsoul:current-pet:${USER}`, DOUBAO);
    const api = receptionServices(thirdPet());
    renderRoutes("/onboarding/reception", [{ path: "/onboarding/reception", element: <ReceptionPage /> }, MAP_ROUTE], api.services);
    const dock = await screen.findByRole("group", { name: "接待的下一步" });
    expect(within(dock).getAllByRole("button").map((button) => button.textContent)).toEqual(["先带 奶茶 去入住", "先不加了，回到 豆包"]);
    fireEvent.click(within(dock).getByRole("button", { name: "先不加了，回到 豆包" }));
    expect(await where()).toBe("地图·豆包");
    expect(sessionStorage.getItem(`petsoul:current-pet:${USER}`)).toBe(DOUBAO);
    expect(api.skip).not.toHaveBeenCalled();
  });

  it("接待页：只有麦芽住进来——出口写“回到 麦芽”，点了去地图，当前宠物是麦芽（不是待入住的奶茶）", async () => {
    const api = receptionServices(secondPet());
    renderRoutes("/onboarding/reception", [{ path: "/onboarding/reception", element: <ReceptionPage /> }, MAP_ROUTE], api.services);
    const dock = await screen.findByRole("group", { name: "接待的下一步" });
    fireEvent.click(within(dock).getByRole("button", { name: "先不加了，回到 麦芽" }));
    expect(await where()).toBe("地图·麦芽");
  });

  it("入住页：奶茶已经可以入住——出口写“回到 麦芽”，点了去地图，当前宠物是麦芽；不入住", async () => {
    const moveIn = vi.fn();
    const session = secondPet("ready_to_move_in");
    renderRoutes("/onboarding/move-in", [{ path: "/onboarding/move-in", element: <MoveInPage /> }, MAP_ROUTE], {
      session: { current: async () => session, homePlace: async () => place, moveIn },
      households: { list: async () => session.onboarding?.households ?? [] },
      pets: { publicProfile: async (petId: string) => profileOf(petId) },
    });
    const dock = await screen.findByRole("group", { name: "入住" });
    expect(within(dock).getAllByRole("button").map((button) => button.textContent)).toEqual(["入住，一起开始生活", "先不加了，回到 麦芽"]);
    fireEvent.click(within(dock).getByRole("button", { name: "先不加了，回到 麦芽" }));
    expect(await where()).toBe("地图·麦芽");
    expect(moveIn).not.toHaveBeenCalled();
  });

  it("第一次入住（一只都没住进来）：接待页和入住页都没有这个出口", async () => {
    const api = receptionServices(firstTime());
    renderRoutes("/onboarding/reception", [{ path: "/onboarding/reception", element: <ReceptionPage /> }], api.services);
    const dock = await screen.findByRole("group", { name: "接待的下一步" });
    expect(within(dock).getAllByRole("button").map((button) => button.textContent)).toEqual(["先带 奶茶 去入住"]);
    cleanup();

    const session = firstTime("ready_to_move_in");
    renderRoutes("/onboarding/move-in", [{ path: "/onboarding/move-in", element: <MoveInPage /> }], {
      session: { current: async () => session, homePlace: async () => place, moveIn: vi.fn() },
      pets: { publicProfile: async (petId: string) => profileOf(petId) },
    });
    const moveInDock = await screen.findByRole("group", { name: "入住" });
    expect(within(moveInDock).getAllByRole("button").map((button) => button.textContent)).toEqual(["入住，一起开始生活"]);
  });
});

/* ---------------- 3. “我的”里续上的入口 ---------------- */

describe("我的：有宠物还没住进来时，给一行继续入住", () => {
  it.each([
    ["reception_optional", "/onboarding/reception"],
    ["ready_to_move_in", "/onboarding/move-in"],
  ] as const)("奶茶停在 %s：出现“奶茶还没住进来 · 继续入住”，去 %s；页面上的当前宠物仍是麦芽", async (step, href) => {
    renderRoutes("/me", [{ path: "/me", element: <MePage /> }], gateServices(secondPet(step)));
    const row = await screen.findByRole("link", { name: /奶茶还没住进来 · 继续入住/ });
    expect(row.getAttribute("href")).toBe(href);
    expect(screen.getByRole("heading", { level: 2 }).textContent).toBe("麦芽");
  });

  it("没有待入住的宠物：不出现这一行", async () => {
    renderRoutes("/me", [{ path: "/me", element: <MePage /> }], gateServices(settledOnly()));
    expect((await screen.findByRole("heading", { level: 2 })).textContent).toBe("麦芽");
    expect(screen.queryByRole("link", { name: /还没住进来/ })).toBeNull();
  });
});

/* ---------------- 4. 接回没结束的接待 ---------------- */

describe("接待页先接回这只宠物还没结束的接待，不每次新开", () => {
  it("reception_session_id 指向的接待还开着（说过一句、待整理）：接着用它，不新开；说过的话和待整理的叮嘱都在", async () => {
    const api = receptionServices(firstTime("reception_optional", "rs-open"), { "rs-open": receptionSession("rs-open", NAICHA, "awaiting_confirmation", true) });
    renderRoutes("/onboarding/reception", [{ path: "/onboarding/reception", element: <ReceptionPage /> }], api.services);
    const dock = await screen.findByRole("group", { name: "接待的下一步" });
    expect(within(dock).getByRole("button", { name: "整理这 1 条叮嘱" })).toBeTruthy();
    expect(within(screen.getByRole("list", { name: "接待对话" })).getByText("它听到零食袋的声音会跑过来")).toBeTruthy();
    expect(api.get).toHaveBeenCalledWith("rs-open");
    expect(api.start).not.toHaveBeenCalled();
  });

  it.each([
    ["没有记着的接待", null, {}],
    ["记着的接待已跳过", "rs-old", { "rs-old": receptionSession("rs-old", NAICHA, "skipped") }],
    ["记着的接待已完成", "rs-old", { "rs-old": receptionSession("rs-old", NAICHA, "completed") }],
    ["记着的接待已过期", "rs-old", { "rs-old": receptionSession("rs-old", NAICHA, "expired") }],
    ["记着的接待读不到", "rs-gone", {}],
    ["记着的接待是别的宠物的", "rs-other", { "rs-other": receptionSession("rs-other", MAIYA, "active") }],
  ] as const)("%s：新开一次（只开一次）", async (_label, id, sessions) => {
    const api = receptionServices(firstTime("reception_optional", id), sessions as Record<string, ReceptionSession>);
    renderRoutes("/onboarding/reception", [{ path: "/onboarding/reception", element: <ReceptionPage /> }], api.services);
    await screen.findByRole("group", { name: "接待的下一步" });
    await waitFor(() => expect(api.start).toHaveBeenCalledTimes(1));
    expect((api.start.mock.calls[0] as unknown as [{ pet_id: string }])[0].pet_id).toBe(NAICHA);
  });
});

/* ---------------- 5. 到家时刻的入住欢迎星币说明 ---------------- */

describe("到家时刻：不是家里第一只住进来的，说明入住欢迎星币给了第一只", () => {
  const COINS = "入住欢迎星币每个家发一次，给了第一只住进来的伙伴。TA 可以去打工攒自己的星币。";

  /** 刚住进来的这一只（到家时刻只在这一刻出现）；pets / household.pets 是快照里这个家的宠物，不给就是快照没带这一栏。 */
  function arrivalOf(petId: string, pets?: HouseholdPetBrief[], householdPets?: HouseholdPetBrief[]): HomeSnapshot {
    const base = fixtureHomeSnapshot();
    const snapshot: HomeSnapshot = { ...base, presence: "at_home", welcome: null, pet: { ...base.pet, pet_id: petId, name: NAMES[petId], photo_url: null } };
    delete snapshot.pets;
    delete snapshot.household;
    if (pets) snapshot.pets = pets;
    if (householdPets) snapshot.household = home(true, householdPets);
    return snapshot;
  }

  it.each([
    ["第二只奶茶刚住进来，麦芽早就住进来了：说明", NAICHA, [petBrief(MAIYA, "moved_in"), petBrief(NAICHA, "moved_in")], undefined, true],
    ["第一只麦芽刚住进来，家里只有它：不说", MAIYA, [petBrief(MAIYA, "moved_in")], undefined, false],
    ["第一只麦芽刚住进来，奶茶还在接待（没住进来的不算）：不说", MAIYA, [petBrief(MAIYA, "moved_in"), petBrief(NAICHA, "reception_optional")], undefined, false],
    ["快照没带 pets、只带了 household.pets：照样认出是第二只", NAICHA, undefined, [petBrief(MAIYA, "moved_in"), petBrief(NAICHA, "moved_in")], true],
    ["快照里没有这个家的宠物数据：不说（不猜）", NAICHA, undefined, undefined, false],
  ] as const)("%s", (_label, petId, pets, householdPets, shown) => {
    render(<ArrivalMoment snapshot={arrivalOf(petId, pets ? [...pets] : undefined, householdPets ? [...householdPets] : undefined)} onClose={vi.fn()} />);
    const dialog = screen.getByRole("dialog", { name: `${NAMES[petId]} 到家了` });
    expect(within(dialog).queryByText(COINS) !== null).toBe(shown);
  });
});

/* ---------------- 6. 整理页：第二只待入住时给第一只补充 ---------------- */

describe("整理页：这次接待的宠物不是入住阶段那只，就是补充", () => {
  const KICKER = "入住准备 · 03 / 04";

  /** 整理页挂在真实路径上，别的路径是落点探针；confirm 回的入住阶段就是账号当前的阶段（补充不改变第二只的入住进度）。 */
  function renderNotes(entry: string, session: SessionState, receptionSessionData: ReceptionSession, afterConfirm: OnboardingState = session.onboarding!) {
    const skip = vi.fn(async () => ({ ...receptionSessionData, status: "skipped" as const }));
    const confirm = vi.fn(async () => ({
      confirmation_id: "cf-1", session_id: receptionSessionData.session_id, draft_revision: receptionSessionData.draft_revision, persist_state: "persisted",
      notes: [], grants: [], onboarding: afterConfirm, data_origin: "live",
    }) as unknown as IntakeConfirmationResult);
    renderRoutes(entry, [{ path: "/onboarding/notes", element: <CareNotesPage /> }], {
      session: { current: async () => session },
      reception: { get: async () => receptionSessionData, skip, confirm },
    });
    return { skip, confirm };
  }
  const backHref = () => screen.queryAllByRole("link", { name: "返回" }).map((el) => el.getAttribute("href"));

  it("奶茶待入住、给麦芽补充（有一条待整理，地址没带 mode）：补充模式——不写入住准备；存好后是“完成”回“我的”，没有“带 TA 去新家”", async () => {
    const api = renderNotes("/onboarding/notes?session=rs-maiya", secondPet(), receptionSession("rs-maiya", MAIYA, "awaiting_confirmation", true));
    await screen.findByRole("radio", { name: "交给 TA" });
    expect(document.body.textContent).not.toContain(KICKER);
    expect(document.body.textContent).toContain("再记下几件小事");
    expect(backHref()).toEqual(["/onboarding/reception?mode=supplement"]);
    fireEvent.click(screen.getByRole("radio", { name: "交给 TA" }));
    fireEvent.click(screen.getByRole("button", { name: "这样记就对了" }));
    await waitFor(() => expect(api.confirm).toHaveBeenCalledTimes(1));
    const done = await screen.findByRole("link", { name: "完成" });
    expect(done.getAttribute("href")).toBe("/me");
    expect(screen.queryByRole("link", { name: "带 TA 去新家" })).toBeNull();
    expect(document.body.textContent).not.toContain("先去入住");
  });

  it("奶茶待入住、给麦芽补充、一句都没说：是“先回去”（不是“先去入住”），点了回“我的”，不去奶茶的入住页；回接待回的是补充的接待", async () => {
    const api = renderNotes("/onboarding/notes?session=rs-maiya", secondPet(), receptionSession("rs-maiya", MAIYA));
    const leave = await screen.findByRole("button", { name: "先回去" });
    expect(screen.queryByRole("button", { name: "先去入住" })).toBeNull();
    expect(screen.getByRole("link", { name: "回到接待说一件小事" }).getAttribute("href")).toBe("/onboarding/reception?mode=supplement");
    fireEvent.click(leave);
    await waitFor(() => expect(api.skip).toHaveBeenCalledWith("rs-maiya"));
    expect(await location()).toBe("/me");
  });

  it("第一次入住的整理页照旧：写入住准备 · 03 / 04；存好后“带 TA 去新家”去入住页", async () => {
    const api = renderNotes("/onboarding/notes?session=rs-naicha", firstTime(), receptionSession("rs-naicha", NAICHA, "awaiting_confirmation", true), firstTime("ready_to_move_in").onboarding!);
    await screen.findByRole("radio", { name: "交给 TA" });
    expect(document.body.textContent).toContain(KICKER);
    expect(backHref()).toEqual(["/onboarding/reception"]);
    fireEvent.click(screen.getByRole("radio", { name: "交给 TA" }));
    fireEvent.click(screen.getByRole("button", { name: "这样记就对了" }));
    await waitFor(() => expect(api.confirm).toHaveBeenCalledTimes(1));
    expect((await screen.findByRole("link", { name: "带 TA 去新家" })).getAttribute("href")).toBe("/onboarding/move-in");
  });

  it("第一次入住、一句都没说：照旧是“先去入住”", async () => {
    renderNotes("/onboarding/notes?session=rs-naicha", firstTime(), receptionSession("rs-naicha", NAICHA));
    expect(await screen.findByRole("button", { name: "先去入住" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "先回去" })).toBeNull();
  });

  it("地址带着 mode=supplement、但这次接待就是入住阶段那只：以数据为准，照旧是入住流程", async () => {
    renderNotes("/onboarding/notes?session=rs-naicha&mode=supplement", firstTime(), receptionSession("rs-naicha", NAICHA, "awaiting_confirmation", true));
    await screen.findByRole("radio", { name: "交给 TA" });
    expect(document.body.textContent).toContain(KICKER);
    expect(backHref()).toEqual(["/onboarding/reception"]);
  });
});
