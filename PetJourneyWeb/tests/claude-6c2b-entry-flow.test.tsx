import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, MemoryRouter, Route, RouterProvider, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { HomePlaceView, HomeSnapshot, HouseholdBrief, IntakeCandidate, IntakeConfirmationResult, OnboardingState, PetPublicProfile, ReceptionSession, SessionState } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { MoveInPage } from "@/features/identity/pages";
import { ReceptionPage } from "@/features/reception/ReceptionPage";
import { CareNotesPage } from "@/features/reception/CareNotesPage";
import { HomePage } from "@/features/home/HomePage";
import { HomeScene } from "@/features/home/HomeScene";
import { fixtureHomeSnapshot } from "@/fixtures/home";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "live", isDev: false, apiBase: "/api/v1/web" } }));

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

function onboarding(step: OnboardingState["step"]): OnboardingState {
  return { step, pet_id: "pet-1", home_id: "home-1", reception_session_id: "rs-1", reception_skipped: false, home_activated_at: null, pet_origin: "own_pet" };
}
function session(step: OnboardingState["step"]): SessionState {
  return { authenticated: true, user: { user_id: "u-1", username: "owner", display_name: null, auth_method: "web_password" }, csrf_required: false, expires_at: null, onboarding: onboarding(step) };
}
const profile = { pet_id: "pet-1", display_name: "栗子", species: "cat", avatar_url: null } as unknown as PetPublicProfile;
const candidate: IntakeCandidate = {
  candidate_id: "c-1", kind: "habit", subject: "pet", text: "喜欢窗台晒太阳", source_turn_id: "t-2", source_excerpt: "它最喜欢在窗台晒太阳",
  needs_clarification: false, suggested_slot: null, suggested_slot_value: null, state: "unconfirmed",
} as IntakeCandidate;
function receptionSession(candidates: IntakeCandidate[]): ReceptionSession {
  return {
    session_id: "rs-1", pet_id: "pet-1", branch: "own_pet", mode: "guided_notes", status: "active",
    host: { host_id: "h", display_name: "星球接待员", role_label: "PetSoul 的 AI 接待角色", avatar_url: null, is_ai: true, disclosure: "我是 AI 接待角色。" },
    turns: [{ turn_id: "t-1", seq: 1, speaker: "host", text: "有什么想交代的吗？", created_at: "2026-09-23T00:00:00Z" }],
    candidates, draft_revision: 1, draft_expires_at: null, data_origin: "live",
  };
}

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
  return <output data-testid="location">{`${location.pathname}|${JSON.stringify(location.state)}`}</output>;
}

function renderAt(element: React.ReactNode, services: Record<string, unknown>, initialEntries: Parameters<typeof MemoryRouter>[0]["initialEntries"], path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={strictServices(services)}>
        <MemoryRouter initialEntries={initialEntries}>
          <Routes>
            <Route path={path} element={element} />
            <Route path="*" element={<LocationProbe />} />
          </Routes>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
}

describe("reception: the main action follows what was actually said", () => {
  it("with nothing said, offers moving in instead of an empty confirmation page", async () => {
    const skip = vi.fn(async () => receptionSession([]));
    renderAt(<ReceptionPage />, {
      session: { current: async () => session("reception_optional") },
      pets: { publicProfile: async () => profile },
      reception: { start: async () => receptionSession([]), get: async () => receptionSession([]), skip },
      world: { home: vi.fn() },
    }, ["/onboarding/reception"], "/onboarding/reception");
    const dock = await screen.findByRole("group", { name: "接待的下一步" });
    expect(screen.getByText("入住准备 · 03 / 04")).toBeTruthy();
    expect(within(dock).queryByRole("button", { name: /条叮嘱/ })).toBeNull();
    fireEvent.click(within(dock).getByRole("button", { name: "先带 栗子 去入住" }));
    await waitFor(() => expect(skip).toHaveBeenCalledWith("rs-1"));
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/onboarding/move-in|null"));
  });

  it("once a note is waiting, organising it becomes the primary action and skipping stays available", async () => {
    renderAt(<ReceptionPage />, {
      session: { current: async () => session("reception_optional") },
      pets: { publicProfile: async () => profile },
      reception: { start: async () => receptionSession([candidate]), get: async () => receptionSession([candidate]), skip: vi.fn() },
      world: { home: vi.fn() },
    }, ["/onboarding/reception"], "/onboarding/reception");
    const dock = await screen.findByRole("group", { name: "接待的下一步" });
    const buttons = within(dock).getAllByRole("button").map((button) => button.textContent);
    expect(buttons).toEqual(["整理这 1 条叮嘱", "跳过，直接去入住（以后还能补充）"]);
  });
});

describe("care notes: no dead end, no internal ids", () => {
  it("an empty draft gives two real ways forward instead of a permanently disabled confirm", async () => {
    const skip = vi.fn(async () => receptionSession([]));
    renderAt(<CareNotesPage />, {
      session: { current: async () => session("reception_optional") },
      reception: { get: async () => receptionSession([]), skip },
    }, ["/onboarding/notes?session=rs-1"], "/onboarding/notes");
    expect(await screen.findByRole("heading", { name: "还没有要确认的叮嘱" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "这样记就对了" })).toBeNull();
    expect(screen.getByRole("link", { name: "回到接待说一件小事" }).getAttribute("href")).toBe("/onboarding/reception");
    fireEvent.click(screen.getByRole("button", { name: "先去入住" }));
    await waitFor(() => expect(skip).toHaveBeenCalledWith("rs-1"));
  });

  it("confirms with the chosen target and reports destinations without exposing the confirmation id", async () => {
    const result: IntakeConfirmationResult = {
      confirmation_id: "cf-internal-7788", session_id: "rs-1", draft_revision: 1, persist_state: "persisted",
      notes: [{ note_id: "n-1", pet_id: "pet-1", kind: "habit", subject: "pet", text: "喜欢窗台晒太阳", target: "give_to_pet", purposes: ["home_interaction", "private_chat"], slot: null, slot_value: null, version: 1, confirmed_at: "2026-09-23T00:00:00Z", supersedes_note_id: null, revoked_at: null }],
      grants: [], onboarding: onboarding("ready_to_move_in"), data_origin: "live",
    } as IntakeConfirmationResult;
    const confirm = vi.fn(async () => result);
    const page = renderAt(<CareNotesPage />, {
      session: { current: async () => session("reception_optional") },
      reception: { get: async () => receptionSession([candidate]), confirm },
    }, ["/onboarding/notes?session=rs-1"], "/onboarding/notes");
    const confirmButton = await screen.findByRole("button", { name: "这样记就对了" });
    expect((confirmButton as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("还有 1 条没选怎么处理。")).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: "交给 TA" }));
    fireEvent.click(screen.getByRole("button", { name: "这样记就对了" }));
    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
    const decision = (confirm.mock.calls[0] as unknown as [{ decisions: Array<{ target: string; purposes: string[] }> }])[0].decisions[0];
    expect(decision.target).toBe("give_to_pet");
    expect(decision.purposes).toEqual(["home_interaction", "private_chat"]);
    expect(await screen.findByRole("heading", { name: "记下了" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "带 TA 去新家" }).getAttribute("href")).toBe("/onboarding/move-in");
    expect(page.container.textContent).not.toContain("cf-internal-7788");
    expect(page.container.querySelector("[data-confirmation-id='cf-internal-7788']")).toBeTruthy();
  });
});

const place: HomePlaceView = {
  place: { habitat: "city", habitat_label: "城市", city: "香港", area_label: "中环", display: "香港·中环", timezone: "Asia/Hong_Kong", chosen: false },
  options: [
    { habitat: "seaside", label: "海边", examples: ["香港"], open: true },
    { habitat: "city", label: "城市", examples: ["香港"], open: true },
    { habitat: "desert", label: "沙漠", examples: [], open: false },
  ],
  can_change: true,
};

describe("move-in: the last step reads as bringing TA home", () => {
  it("shows only open habitats as choices and sends the chosen one", async () => {
    const moveIn = vi.fn(async () => onboarding("active"));
    // 与应用相同的数据路由：跳转在 transition 中生效，才能暴露“守卫二次跳转覆盖到家状态”的竞态。
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const router = createMemoryRouter([
      { path: "/onboarding/move-in", element: <MoveInPage /> },
      { path: "*", element: <LocationProbe /> },
    ], { initialEntries: ["/onboarding/move-in"] });
    render(
      <QueryClientProvider client={client}>
        <ServicesProvider services={strictServices({ session: { current: async () => session("ready_to_move_in"), homePlace: async () => place, moveIn }, pets: { publicProfile: async () => profile } })}>
          <RouterProvider router={router} />
        </ServicesProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("heading", { name: "带 栗子 回家" })).toBeTruthy();
    const choices = await screen.findByRole("group", { name: "选择家的环境" });
    expect(within(choices).getAllByRole("button").map((b) => b.querySelector("strong")?.textContent)).toEqual(["海边", "城市"]);
    // 2026-09-24 巡检 P2（主窗口派单）：没开放的类型不再一一列出，只说一句“更多地方以后开放。”
    expect(screen.getByText("更多地方以后开放。")).toBeTruthy();
    expect(screen.queryByText(/沙漠/)).toBeNull();
    fireEvent.click(within(choices).getByRole("button", { name: /海边/ }));
    expect(within(choices).getByRole("button", { name: /海边/ }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "入住，一起开始生活" }));
    await waitFor(() => expect(moveIn).toHaveBeenCalledWith(false, "seaside", "pet-1"));
    // 成功后带着“到家时刻”状态去家园，且没有被守卫的第二次跳转覆盖。
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe('/home|{"arrival":"pet-1"}'));
  });

  it("treats pet_away as waiting for TA, not as a generic failure", async () => {
    const moveIn = vi.fn(async () => {
      throw new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "TA 还在外面，等 TA 回到驿站再接回家。", details: { reason: "pet_away", pet_id: "pet-1" } });
    });
    renderAt(<MoveInPage />, {
      session: { current: async () => session("ready_to_move_in"), homePlace: async () => place, moveIn },
      pets: { publicProfile: async () => profile },
    }, ["/onboarding/move-in"], "/onboarding/move-in");
    await screen.findByRole("group", { name: "选择家的环境" });
    fireEvent.click(screen.getByRole("button", { name: "入住，一起开始生活" }));
    expect(await screen.findByText("栗子 还在外面")).toBeTruthy();
    expect(screen.getByRole("button", { name: "再看看 TA 回来没有" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("re-reads the session when the move-in receipt is lost instead of claiming failure", async () => {
    const current = vi.fn(async () => session("ready_to_move_in"));
    const moveIn = vi.fn(async () => {
      throw new ApiError({ kind: "network", code: "NETWORK_ERROR", message: "网络连接失败", retryable: true });
    });
    renderAt(<MoveInPage />, {
      session: { current, homePlace: async () => place, moveIn },
      pets: { publicProfile: async () => profile },
    }, ["/onboarding/move-in"], "/onboarding/move-in");
    await screen.findByRole("group", { name: "选择家的环境" });
    fireEvent.click(screen.getByRole("button", { name: "入住，一起开始生活" }));
    expect((await screen.findByRole("alert")).textContent).toContain("入住结果还没确认");
    await waitFor(() => expect(current.mock.calls.length).toBeGreaterThanOrEqual(2));
  });
});

const household = {
  household_id: "house-1", name: "我们的家", home_id: "home-1", role: "admin", home_activated: true, member_count: 1,
  pets: [{ pet_id: "pet-1", name: "栗子", species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-23T00:00:00Z", added_by_you: true }],
} as HouseholdBrief;

function arrivalSnapshot(): HomeSnapshot {
  const base = fixtureHomeSnapshot();
  return {
    ...base,
    presence: "at_home",
    journey: null,
    catching_up: false,
    pet: { ...base.pet, pet_id: "pet-1", name: "栗子", photo_url: null, photo_generated: false },
    place: { habitat: "seaside", habitat_label: "海边", city: "香港", area_label: "西贡的海边", display: "香港·西贡的海边", timezone: "Asia/Hong_Kong", chosen: true },
    welcome: { pet_id: "pet-1", confirmation_id: "cf-1", projection_version: 1, greeting: "我到家啦，这里闻起来像你。", details: [{ kind: "favorite_object", text: "窗台上的软垫", note_id: "n-1", note_version: 1 }] },
  } as HomeSnapshot;
}

function renderHome(state: unknown) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // 家园会先看 meta 里角色能力；当前后端报 not_implemented，角色接口不应被调用。
  const character = vi.fn();
  const meta = async () => ({ api_prefix: "/api/v1/web", contract_version: "0.4.5", server_time: "2026-09-23T00:00:00Z", backend_version: "test", data_origin: "live", auth_methods_available: [], applied_migrations: [], capabilities: [{ key: "character.state", module: "character", status: "not_implemented", note: null }] });
  const services = strictServices({ households: { list: async () => [household] }, world: { home: async () => arrivalSnapshot() }, transport: { journeyMap: vi.fn() }, platform: { meta }, pets: { character } });
  return render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <MemoryRouter initialEntries={[{ pathname: "/home", state }]}>
          <HouseholdProvider userId="u-1"><HomePage /></HouseholdProvider>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
}

describe("first arrival at home", () => {
  it("plays once after move-in with the confirmed greeting, then goes away", async () => {
    renderHome({ arrival: "pet-1" });
    const dialog = await screen.findByRole("dialog", { name: "栗子 到家了" });
    expect(within(dialog).getByText("“我到家啦，这里闻起来像你。”")).toBeTruthy();
    expect(within(dialog).getByText("窗台上的软垫")).toBeTruthy();
    expect(within(dialog).getByText("新家 · 香港·西贡的海边")).toBeTruthy();
    expect(within(dialog).getByText("来自你确认过的生活叮嘱")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "进家看看" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "栗子 到家了" })).toBeNull());
  });

  it("does not appear on an ordinary visit or for another pet", async () => {
    renderHome(null);
    expect(await screen.findByRole("region", { name: "共同的家·庭院" })).toBeTruthy();
    expect(screen.queryByTestId("home-arrival")).toBeNull();
    cleanup();
    renderHome({ arrival: "someone-else" });
    expect(await screen.findByRole("region", { name: "共同的家·庭院" })).toBeTruthy();
    expect(screen.queryByTestId("home-arrival")).toBeNull();
  });
});

describe("home garden entrance speaks the garden's state in one line", () => {
  const growing = { plot_id: "p1", cycle_id: "c1", crop_key: "sun_pea", crop_label: "太阳豌豆", stage: "growing", ripe_at: null, steal_total: null, steal_remaining: null };
  const empty = { plot_id: "p2", cycle_id: null, crop_key: null, crop_label: null, stage: "empty", ripe_at: null, steal_total: null, steal_remaining: null };
  const ripe = { plot_id: "p3", cycle_id: "c3", crop_key: "moon_radish", crop_label: "月光萝卜", stage: "ripe", ripe_at: null, steal_total: 2, steal_remaining: 2 };
  it.each([
    [[growing, empty, ripe], "菜园，1 块熟了", "1 块熟了"],
    [[growing, empty], "菜园，有空地可以种", "有空地可以种"],
    [[growing], "菜园，都在长", "都在长"],
  ])("%#", (plots, spoken, shown) => {
    const base = fixtureHomeSnapshot();
    const page = render(<MemoryRouter><HomeScene snapshot={{ ...base, presence: "at_home", plots: plots as HomeSnapshot["plots"] }} /></MemoryRouter>);
    // 小窝里的东西平时不写字（claude-6c2b 小窝二级页）：这一句由入口的无障碍名称说出，点开才显示在气泡里，旁边是“去菜园”。
    const gate = screen.getByRole("button", { name: spoken });
    expect(page.container.querySelector("[data-testid='home-garden-gate']")?.textContent).toBe("");
    fireEvent.click(gate);
    const bubble = screen.getByRole("group", { name: "菜园" });
    expect(bubble.querySelector(".ps-home-bubble__detail")?.textContent).toBe(shown);
    expect(within(bubble).getByRole("link", { name: "去菜园" }).getAttribute("href")).toBe("/garden");
  });
});
