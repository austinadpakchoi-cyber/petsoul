/**
 * claude-6c2b · 共用的“迎接 TA”（features/pets/adoptFlow.tsx；领养页与居民主页都用它）。
 * 迎接 TA：点一下只打开确认，确认之后才领养；按此刻的家决定怎么迎——
 *   未登录去注册（沿用 entry=adopt&pet_id）；没有家就新建家庭（不带 household_id）；只管理一个家写“迎接 TA 到{家名}”并带上它；
 *   管理几个家先在确认框里选（只列管理员的家）；不是任何家的管理员就说清楚要管理员来迎接、不给按钮；演示模式照原来的演示领养。
 *   失败说人话，不把错误码与后端原话摆进正文；换了迎进的家换一把幂等键，同一个家重试沿用同一把。
 * live 服务：household_id 只在迎进已有的家时才带；传 null 时请求体仍是 {candidate_id}，与原来逐字相同。
 * 领养页本身（头像、物种、去掉“✧”、已有家收成一行、两个动作分开）在 tests/claude-6c2b-adopt-page.test.tsx。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import type { HouseholdBrief, HouseholdPetBrief, SessionState } from "@/shared/contracts";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { ApiError } from "@/shared/api/errors";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { AdoptFlow, adoptFailureText } from "@/features/pets/adoptFlow";
import { PendingEntryPage } from "@/features/pets/PendingEntryPage";

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
});
afterEach(() => cleanup());

const guest = { authenticated: false, user: null, csrf_required: false, expires_at: null, onboarding: null } as SessionState;
const signedIn = {
  authenticated: true,
  user: { user_id: "u-1", display_name: null, username: "tester", auth_method: "web_password" },
  csrf_required: true,
  expires_at: null,
  onboarding: { step: "needs_companion", pet_id: null, home_id: null, reception_session_id: null, reception_skipped: false, home_activated_at: null, pet_origin: null, entry: null },
} as unknown as SessionState;

const pet = (pet_id: string, name: string) =>
  ({ pet_id, name, species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true }) as unknown as HouseholdPetBrief;
const home = (household_id: string, name: string | null, role: "admin" | "caregiver", pets: HouseholdPetBrief[]) =>
  ({ household_id, name, role, home_activated: true, home_id: `home-${household_id}`, member_count: 1, pets }) as unknown as HouseholdBrief;

/** 严格服务：没给的服务一碰就抛（演示模式不许去读家庭）。 */
function strict(services: Record<string, unknown>): ServiceMap {
  return new Proxy(services as unknown as ServiceMap, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof ServiceMap];
      throw new Error(`unexpected service ${prop}`);
    },
  });
}

function Where() {
  const location = useLocation();
  return <p data-testid="where">{location.pathname + location.search}</p>;
}

function renderFlow(options: { session?: SessionState; households?: HouseholdBrief[]; adopt?: (...args: unknown[]) => Promise<unknown>; props?: Partial<Parameters<typeof AdoptFlow>[0]> } = {}) {
  const adopt = vi.fn(options.adopt ?? (async () => ({ pet_id: "PJ-NEW", candidate_id: "cand-1", adopted_at: "2026-09-24T00:00:00Z" })));
  const list = vi.fn(async () => options.households ?? []);
  const services: Record<string, unknown> = { session: { current: async () => options.session ?? signedIn }, pets: { adopt } };
  if (options.households !== undefined || mode.dataMode === "live") services.households = { list };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={strict(services)}>
        <MemoryRouter initialEntries={["/world/residents/PJ-1"]}>
          <Routes>
            <Route path="/world/residents/:petId" element={<><AdoptFlow candidateId="cand-1" petId="PJ-1" name="小岚" adoptable {...options.props} /><Where /></>} />
            <Route path="*" element={<Where />} />
          </Routes>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { adopt, list };
}

/** 家庭列表还在读时按钮是灰的（aria-busy）：等它能点了再点，不然点了等于没点。 */
async function ready(name: string): Promise<HTMLButtonElement> {
  const button = (await screen.findByRole("button", { name })) as HTMLButtonElement;
  await waitFor(() => expect(button.disabled).toBe(false));
  return button;
}

describe("共用的“迎接 TA”：按此刻的家决定怎么迎", () => {
  it("未登录：去注册，带上 entry=adopt&pet_id；不给确认、不领养", async () => {
    const { adopt } = renderFlow({ session: guest });
    const link = await screen.findByRole("link", { name: "迎接 TA：小岚" });
    expect(link.getAttribute("href")).toBe("/register?entry=adopt&pet_id=PJ-1");
    expect(screen.queryByRole("button", { name: /迎接 TA/ })).toBeNull();
    expect(adopt).not.toHaveBeenCalled();
  });

  it("未登录、没有 pet_id：去普通注册", async () => {
    renderFlow({ session: guest, props: { petId: null } });
    expect((await screen.findByRole("link", { name: "迎接 TA：小岚" })).getAttribute("href")).toBe("/register");
  });

  it("还没有家：点一下只打开原样的确认框；确认后新建家庭（household_id 传 null），去入住准备", async () => {
    const { adopt } = renderFlow({ households: [] });
    fireEvent.click(await ready("迎接 TA：小岚"));
    expect(adopt).not.toHaveBeenCalled();
    const box = screen.getByRole("group", { name: "确认领养 小岚" });
    expect(within(box).getByText("确定迎接 小岚 吗？")).toBeTruthy();
    expect(within(box).getByText("领养后 TA 会加入你的家，下一步可以先和接待员说说想交代的事。")).toBeTruthy();
    fireEvent.click(within(box).getByRole("button", { name: "确认领养" }));
    await waitFor(() => expect(adopt).toHaveBeenCalledTimes(1));
    expect(adopt.mock.calls[0][0]).toBe("cand-1");
    expect(adopt.mock.calls[0][2]).toBeNull();
    await waitFor(() => expect(screen.getByTestId("where").textContent).toBe("/onboarding/reception?branch=adopted"));
  });

  it("“再看看”收起确认，不领养", async () => {
    const { adopt } = renderFlow({ households: [] });
    fireEvent.click(await ready("迎接 TA：小岚"));
    fireEvent.click(screen.getByRole("button", { name: "再看看" }));
    expect(screen.queryByRole("group", { name: "确认领养 小岚" })).toBeNull();
    expect(screen.getByRole("button", { name: "迎接 TA：小岚" })).toBeTruthy();
    expect(adopt).not.toHaveBeenCalled();
  });

  it("只管理一个家：写“迎接 TA 到奶茶的家”（与切换栏同一套家名），确认后带上这个家", async () => {
    const { adopt } = renderFlow({ households: [home("h-1", null, "admin", [pet("p-1", "奶茶")])] });
    const button = await ready("迎接 TA 到奶茶的家：小岚");
    expect(button.textContent).toBe("迎接 TA 到奶茶的家");
    fireEvent.click(button);
    const box = screen.getByRole("group", { name: "确认领养 小岚" });
    expect(within(box).getByText("确定迎接 小岚 到奶茶的家吗？")).toBeTruthy();
    expect(within(box).getByText("领养后 TA 会住进奶茶的家，下一步可以先和接待员说说想交代的事。")).toBeTruthy();
    fireEvent.click(within(box).getByRole("button", { name: "确认领养" }));
    await waitFor(() => expect(adopt).toHaveBeenCalledTimes(1));
    expect(adopt.mock.calls[0][2]).toBe("h-1");
  });

  it("管理几个家：确认框里先选迎进哪个家，只列出是管理员的家；没选之前“确认领养”是灰的", async () => {
    const { adopt } = renderFlow({
      households: [home("h-1", null, "admin", [pet("p-1", "奶茶")]), home("h-2", "海边的家", "admin", [pet("p-2", "豆豆")]), home("h-3", null, "caregiver", [pet("p-3", "栗子")])],
    });
    fireEvent.click(await ready("迎接 TA：小岚"));
    const box = screen.getByRole("group", { name: "确认领养 小岚" });
    const choices = within(box).getAllByRole("radio");
    expect(choices.map((radio) => radio.closest("label")?.textContent)).toEqual(["奶茶的家", "海边的家"]);
    expect(within(box).queryByText("栗子的家")).toBeNull();
    const confirm = within(box).getByRole("button", { name: "确认领养" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    fireEvent.click(within(box).getByRole("radio", { name: "海边的家" }));
    expect(confirm.disabled).toBe(false);
    fireEvent.click(confirm);
    await waitFor(() => expect(adopt).toHaveBeenCalledTimes(1));
    expect(adopt.mock.calls[0][2]).toBe("h-2");
  });

  it("在家里但不是任何一个家的管理员：说清楚要家里的管理员来迎接，不给按钮", async () => {
    const { adopt } = renderFlow({ households: [home("h-3", null, "caregiver", [pet("p-3", "栗子")])] });
    expect((await screen.findByRole("note")).textContent).toContain("需要家里的管理员来迎接");
    expect(screen.queryByRole("button", { name: /迎接 TA/ })).toBeNull();
    expect(screen.queryByRole("link", { name: /迎接 TA/ })).toBeNull();
    expect(adopt).not.toHaveBeenCalled();
  });

  it("此刻不能领养：按钮是灰的，点不开确认", async () => {
    const { list } = renderFlow({ households: [], props: { adoptable: false } });
    const button = (await screen.findByRole("button", { name: "迎接 TA：小岚" })) as HTMLButtonElement;
    await waitFor(() => expect(list).toHaveBeenCalled());
    await waitFor(() => expect(button.getAttribute("aria-busy")).toBeNull());
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(screen.queryByRole("group", { name: "确认领养 小岚" })).toBeNull();
  });

  it("演示模式：不读账号与家庭（严格服务里没有 households），照原来的演示领养", async () => {
    mode.dataMode = "fixture";
    const { adopt } = renderFlow({ session: guest });
    fireEvent.click(await ready("迎接 TA：小岚"));
    fireEvent.click(within(screen.getByRole("group", { name: "确认领养 小岚" })).getByRole("button", { name: "确认领养" }));
    await waitFor(() => expect(adopt).toHaveBeenCalledTimes(1));
    expect(adopt.mock.calls[0][2]).toBeNull();
  });

  it("换了迎进的家就换一把幂等键；同一个家重试沿用同一把", async () => {
    let attempt = 0;
    const { adopt } = renderFlow({
      households: [home("h-1", null, "admin", [pet("p-1", "奶茶")]), home("h-2", "海边的家", "admin", [pet("p-2", "豆豆")])],
      adopt: async () => {
        attempt += 1;
        throw new ApiError({ kind: "network", code: "NETWORK_ERROR", message: "连不上服务", retryable: true });
      },
    });
    fireEvent.click(await ready("迎接 TA：小岚"));
    const box = screen.getByRole("group", { name: "确认领养 小岚" });
    fireEvent.click(within(box).getByRole("radio", { name: "奶茶的家" }));
    fireEvent.click(within(box).getByRole("button", { name: "确认领养" }));
    await waitFor(() => expect(adopt).toHaveBeenCalledTimes(1));
    await screen.findByRole("alert");
    fireEvent.click(within(box).getByRole("button", { name: "确认领养" }));
    await waitFor(() => expect(adopt).toHaveBeenCalledTimes(2));
    fireEvent.click(within(box).getByRole("radio", { name: "海边的家" }));
    fireEvent.click(within(box).getByRole("button", { name: "确认领养" }));
    await waitFor(() => expect(adopt).toHaveBeenCalledTimes(3));
    const keys = adopt.mock.calls.map((call) => call[1]);
    expect(keys[1]).toBe(keys[0]);
    expect(keys[2]).not.toBe(keys[0]);
    expect(adopt.mock.calls.map((call) => call[2])).toEqual(["h-1", "h-1", "h-2"]);
    expect(attempt).toBe(3);
  });
});

describe("迎接失败说人话（正文里没有错误码，也没有后端原话）", () => {
  const cases: Array<[string, ApiError, string]> = [
    ["ADOPTION_TAKEN", new ApiError({ kind: "http", status: 409, code: "ADOPTION_TAKEN", message: "后端原话" }), "TA 刚刚有了自己的家"],
    ["ALREADY_HAS_COMPANION", new ApiError({ kind: "http", status: 409, code: "ALREADY_HAS_COMPANION", message: "后端原话" }), "每个账号先陪伴一只专属伙伴。"],
    ["household_exists", new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "后端原话", details: { reason: "household_exists" } }), "你已经建立过一个家"],
    ["FORBIDDEN", new ApiError({ kind: "http", status: 403, code: "FORBIDDEN", message: "后端原话", details: { reason: "manage_required" } }), "需要家里的管理员来迎接 TA。"],
    ["NOT_FOUND", new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "后端原话" }), "没有找到这位伙伴"],
    ["network", new ApiError({ kind: "network", code: "NETWORK_ERROR", message: "后端原话", retryable: true }), "网络不太稳"],
    ["other", new ApiError({ kind: "http", status: 500, code: "INTERNAL_ERROR", message: "后端原话" }), "这次没有迎接成功，请稍后再试。"],
  ];
  it.each(cases)("%s", (_name, error, text) => expect(adoptFailureText(error)).toContain(text));

  it("确认框里显示的是人话：抢不到时写“TA 刚刚有了自己的家”", async () => {
    renderFlow({ households: [], adopt: async () => { throw new ApiError({ kind: "http", status: 409, code: "ADOPTION_TAKEN", message: "后端原话" }); } });
    fireEvent.click(await ready("迎接 TA：小岚"));
    fireEvent.click(screen.getByRole("button", { name: "确认领养" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("TA 刚刚有了自己的家");
    expect(alert.textContent).not.toMatch(/ADOPTION_TAKEN|后端原话/);
  });
});

describe("live 服务（I 批准的签名：householdId 必传，显式 null 表示新建家庭）", () => {
  function liveServices() {
    const sent: Array<{ path: string; method: string; body: string; key: string | null }> = [];
    const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const headers = (init?.headers ?? {}) as Record<string, string>;
      sent.push({ path: String(input), method: init?.method ?? "GET", body: String(init?.body), key: headers["Idempotency-Key"] ?? null });
      return new Response(JSON.stringify({ pet_id: "PJ-NEW", candidate_id: "cand-1", adopted_at: "2026-09-24T00:00:00Z" }), { status: 200, headers: { "Content-Type": "application/json" } });
    }) as typeof fetch;
    return { services: buildServices(loadFeatureModules(), { mode: "live", api: createApiClient("/api/v1/web", fetchImpl) }), sent };
  }

  it("householdId 为 null：请求体逐字就是 {\"candidate_id\":\"cand-1\"}，不带 household_id（新建家庭）", async () => {
    const { services, sent } = liveServices();
    await services.pets.adopt("cand-1", "key-1", null);
    expect(sent).toEqual([{ path: "/api/v1/web/adoption/adopt", method: "POST", body: '{"candidate_id":"cand-1"}', key: "key-1" }]);
  });

  it("给了 householdId：请求体带上 household_id（迎进那个家）", async () => {
    const { services, sent } = liveServices();
    await services.pets.adopt("cand-1", "key-2", "h-9");
    expect(sent).toEqual([{ path: "/api/v1/web/adoption/adopt", method: "POST", body: '{"candidate_id":"cand-1","household_id":"h-9"}', key: "key-2" }]);
  });
});

describe("入住流程的调用方显式传 null（还没有家，新建家庭）", () => {
  it("登录后找回之前选中的居民：确认迎接时 adopt 的第三个参数就是 null（不是省略、不是 undefined）", async () => {
    const adopt = vi.fn(async () => ({ pet_id: "PJ-1", candidate_id: "cand-9", adopted_at: "2026-09-24T00:00:00Z" }));
    const view = {
      profile: { pet_id: "PJ-1", display_name: "小岚", species: "cat", avatar_url: null, bio: null, origin_label: null, visibility: "public", follower_count: 0, post_count: 0, viewer_follows: false, is_own: false, data_origin: "live" },
      resident: { pet_id: "PJ-1", candidate_id: "cand-9", name: "小岚", species: "cat", doing: "在驿站晒太阳", residence: "星球居民驿站", city: "香港", dream: "看看海", presence: "at_home", recent_posts: [] },
      adoptable: true,
      posts: [],
    };
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ServicesProvider services={strict({ session: { current: async () => signedIn }, pets: { publicPet: async () => view, adopt } })}>
          <MemoryRouter initialEntries={["/onboarding/choice?pet_id=PJ-1"]}>
            <Routes>
              <Route path="/onboarding/choice" element={<PendingEntryPage />} />
              <Route path="*" element={<Where />} />
            </Routes>
          </MemoryRouter>
        </ServicesProvider>
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "我想迎接 小岚" }));
    expect(adopt).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole("group", { name: "确认迎接 小岚" })).getByRole("button", { name: "确认迎接 TA" }));
    await waitFor(() => expect(adopt).toHaveBeenCalledTimes(1));
    const call = adopt.mock.calls[0] as unknown[];
    expect(call).toHaveLength(3);
    expect(call[0]).toBe("cand-9");
    expect(call[2]).toBeNull();
  });
});
