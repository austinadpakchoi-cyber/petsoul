/**
 * claude-6c2b（分身）· P0：一家有两只宠物时，按宠物分的接口必须显式带当前宠物（pet_id）。
 * 后端 require_pet：请求没带 pet_id、而这位家人能照顾的宠物不止一只时回 409（details.reason = pet_required）；
 * GET /settings 不报错，但没带 pet_id 时回的是“第一只”的简介与公开范围。
 *
 * 这里用“两只宠物”的 live 替身后端（假的 ApiClient，按上面的规矩回 409 / 回第一只），经真实路由表、真实 live 服务实现渲染：
 * - 集市：读、卖、交货都带当前宠物；显示的是当前宠物家的旅费；切宠物后按新宠物重读。
 * - 驾校：状态、历史、报名、开考 / 练习、考局读取、开始、放弃、领证都带当前宠物；历史不再因 409 不见。
 * - 设置：读、存都带当前宠物；显示当前宠物的简介（不是“第一只”的）；切宠物后表单换成新宠物的。
 * - 菜园的选种子：读收藏带当前宠物（原来不带，409 被吞掉，种子数当成 0）。
 * - 驾校 live 服务：除课程外每条都带 ?pet_id=。
 * - 统一错误态：pet_required 说人话，后端原话与原因码收进“技术信息”。
 * - 设置页“聊天时更懂你”：不露开发术语与原始模式代码。
 * - 点按区：欢迎页登录链接、登录 / 注册页底部链接、我们的家的复选框与“回家看看”至少 40px（样式规则；实际尺寸在截图脚本里量）。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import type { CollectionItem, HomeSnapshot, HouseholdBrief, MarketView, SessionBrief, SessionState, SettingsView } from "@/shared/contracts";
import type { ApiClient } from "@/shared/api/client";
import { ApiError } from "@/shared/api/errors";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import { ErrorState } from "@/shared/ui";
import { fixtureHomeSnapshot, fixtureMarket } from "@/fixtures/home";
import { FIXTURE_CROPS } from "@/fixtures/farm";
import { createFixtureDrivingService, createLiveDrivingService, type FixtureDrivingOptions } from "@/features/driving_school/service";

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

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

beforeEach(() => {
  mode.dataMode = "live";
  sessionStorage.clear();
  // 当前宠物先是第二只（豆豆）：后端“没带 pet_id 就回第一只”的读法会在这里露馅。
  sessionStorage.setItem("petsoul:current-pet:owner-1", "pet-b");
  vi.stubGlobal("scrollTo", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/* ---------------- 两只宠物的替身后端 ---------------- */

const PETS = [
  { id: "pet-a", name: "奶茶" },
  { id: "pet-b", name: "豆豆" },
] as const;
type PetId = (typeof PETS)[number]["id"];

const SIGNED_IN: SessionState = {
  authenticated: true,
  user: { user_id: "owner-1", display_name: "小林", username: "lin", auth_method: "web_password" },
  csrf_required: false,
  expires_at: null,
  onboarding: { step: "active", pet_id: "pet-a", home_id: "home-1", reception_session_id: null, reception_skipped: false, home_activated_at: null, pet_origin: "own_pet" },
};

const HOUSEHOLD: HouseholdBrief = {
  household_id: "house-1",
  name: "海边的家",
  home_id: "home-1",
  role: "admin",
  home_activated: true,
  member_count: 1,
  pets: PETS.map((p) => ({ pet_id: p.id, name: p.name, species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true })),
};

const PET_REQUIRED_MESSAGE = "你照顾的宠物不止一只，请指明是哪一只（pet_id）。";
const petRequired = () =>
  new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: PET_REQUIRED_MESSAGE, details: { reason: "pet_required", pets: PETS.map((p) => ({ pet_id: p.id, household_id: "house-1" })) } });

const homeFor = (pet: PetId): HomeSnapshot => {
  const base = fixtureHomeSnapshot();
  const name = PETS.find((p) => p.id === pet)!.name;
  return { ...base, data_origin: "live", presence: "at_home", journey: null, pet: { ...base.pet, pet_id: pet, name } } as HomeSnapshot;
};

const BALANCE: Record<PetId, number> = { "pet-a": 120, "pet-b": 45 };
const marketFor = (pet: PetId): MarketView => {
  const base = fixtureMarket();
  return { ...base, data_origin: "live", wallet: { ...base.wallet, balance: BALANCE[pet] }, orders: base.orders.map((o, i) => ({ ...o, fulfilled: false, can_fulfill: i === 0 })) };
};

const settingsFor = (pet: PetId): SettingsView => ({
  username: "lin",
  display_name: "小林",
  public_posts: false,
  profile_visibility: "public",
  bio: pet === "pet-a" ? "奶茶的简介" : "豆豆的简介",
  intent_layer_mode: "off",
});

const briefA: SessionBrief = { session_id: "s-a-1", subject: "s1", mode: "formal", item: null, attempt_kind: "first", state: "settled", passed: true, score: 96, created_at: "2026-09-23T08:00:00Z", settled_at: "2026-09-23T08:20:00Z" };

type Call = { method: string; path: string; petId: string | null; body?: unknown };

/** 按后端规矩回话：按宠物分的接口没带 pet_id → 409 pet_required；GET /settings 没带 → 回“第一只”。 */
function twoPetBackend(stages: Partial<Record<PetId, FixtureDrivingOptions["stage"]>> = {}) {
  const calls: Call[] = [];
  const school: Record<PetId, ReturnType<typeof createFixtureDrivingService>> = {
    "pet-a": createFixtureDrivingService({ stage: stages["pet-a"] ?? "enrolled", latency: 0 }),
    "pet-b": createFixtureDrivingService({ stage: stages["pet-b"] ?? "none", latency: 0 }),
  };
  const need = (petId: string | null): PetId => {
    if (!petId) throw petRequired();
    if (!PETS.some((p) => p.id === petId)) throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有这只宠物" });
    return petId as PetId;
  };
  const api: ApiClient = {
    base: "/api/v1/web",
    async request<T>(path: string, options: { method?: string; query?: Record<string, unknown>; body?: unknown } = {}): Promise<T> {
      const method = options.method ?? "GET";
      const raw = options.query?.pet_id;
      const petId = raw === undefined || raw === null || raw === "" ? null : String(raw);
      calls.push({ method, path, petId, body: options.body });
      const reply = async (): Promise<unknown> => {
        if (path === "/session") return SIGNED_IN;
        if (path === "/households") return [HOUSEHOLD];
        if (path === "/home") return homeFor(need(petId));
        if (path === "/market") return marketFor(need(petId));
        if (path === "/market/sell" || /^\/market\/orders\/[^/]+\/fulfill$/.test(path)) {
          const pet = need(petId);
          return { wallet: marketFor(pet).wallet, pantry: marketFor(pet).pantry, gained_coins: 10, message: "卖掉了" };
        }
        if (path === "/collection") {
          need(petId);
          return [] as CollectionItem[];
        }
        if (path === "/farm/crops") return FIXTURE_CROPS;
        if (path === "/settings") {
          if (method === "GET") return settingsFor((petId as PetId | null) ?? "pet-a");
          const body = (options.body ?? {}) as Partial<SettingsView>;
          const petFields = body.bio !== undefined || body.profile_visibility !== undefined || body.public_posts !== undefined || body.generated_photos !== undefined;
          const pet = petFields ? need(petId) : ((petId as PetId | null) ?? "pet-a");
          return { ...settingsFor(pet), ...body };
        }
        if (path === "/driving/curriculum") return school["pet-a"].curriculum();
        if (path === "/driving") return school[need(petId)].status();
        if (path === "/driving/history") return need(petId) === "pet-a" ? [briefA] : [];
        if (path === "/driving/enroll") {
          const pet = need(petId);
          school[pet] = createFixtureDrivingService({ stage: "enrolled", latency: 0 });
          return school[pet].status();
        }
        if (path === "/driving/ceremony") return school[need(petId)].ceremony();
        if (path === "/driving/sessions") return school[need(petId)].createSession(options.body as never, "k");
        const session = path.match(/^\/driving\/sessions\/([^/]+)(\/[a-z]+)?$/);
        if (session) {
          const svc = school[need(petId)];
          const [, id, tail] = session;
          if (!tail) return svc.session(id);
          if (tail === "/begin") return svc.begin(id);
          if (tail === "/abandon") return svc.abandon(id, true);
        }
        throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: `替身没有这条：${method} ${path}` });
      };
      return (await reply()) as T;
    },
  };
  return { api, calls };
}

function renderApp(path: string, api: ApiClient) {
  const modules = loadFeatureModules();
  const services = buildServices(modules, { mode: "live", api });
  const router = createMemoryRouter(buildRoutes(modules), { initialEntries: [path] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return Object.assign(router, { client });
}

const callsTo = (calls: Call[], method: string, path: string | RegExp) => calls.filter((c) => c.method === method && (typeof path === "string" ? c.path === path : path.test(c.path)));
const switchTo = (name: string) => fireEvent.click(screen.getByRole("button", { name: new RegExp(`^查看 ${name}`) }));

/* ---------------- 替身本身：不带 pet_id 真的会 409 ---------------- */

describe("两只宠物的替身后端（对照）", () => {
  it("按宠物分的接口不带 pet_id 就 409 pet_required；带了才回数据；GET /settings 不带时回第一只", async () => {
    const { api } = twoPetBackend();
    await expect(api.request("/market")).rejects.toMatchObject({ status: 409, details: { reason: "pet_required" } });
    await expect(api.request("/driving/history")).rejects.toMatchObject({ status: 409 });
    await expect(api.request("/settings", { method: "PATCH", body: { bio: "x" } })).rejects.toMatchObject({ status: 409 });
    expect(((await api.request("/market", { query: { pet_id: "pet-b" } })) as MarketView).wallet.balance).toBe(45);
    expect(((await api.request("/settings")) as SettingsView).bio).toBe("奶茶的简介");
  });
});

/* ---------------- 集市 ---------------- */

describe("集市：读、卖、交货都带当前宠物", () => {
  it("当前是豆豆：按 pet-b 读、显示豆豆家的旅费；卖与交货都带 pet-b；切到奶茶后按 pet-a 重读", async () => {
    const { api, calls } = twoPetBackend();
    const { client } = renderApp("/market", api);
    expect(await screen.findByText("45")).toBeTruthy();
    // live 的集市键按账号与宠物分（切宠物就是另一份）。
    expect(client.getQueryCache().findAll({ queryKey: ["economy", "market", "owner-1", "pet-b"], exact: true })).toHaveLength(1);
    expect(callsTo(calls, "GET", "/market").map((c) => c.petId)).toEqual(["pet-b"]);
    expect(screen.queryByRole("alert")).toBeNull();

    fireEvent.click(screen.getAllByRole("button", { name: /^全卖/ })[0]);
    await waitFor(() => expect(callsTo(calls, "POST", "/market/sell")).toHaveLength(1));
    expect(callsTo(calls, "POST", "/market/sell")[0].petId).toBe("pet-b");

    fireEvent.click(screen.getByRole("button", { name: "交货" }));
    await waitFor(() => expect(callsTo(calls, "POST", /^\/market\/orders\/.+\/fulfill$/)).toHaveLength(1));
    expect(callsTo(calls, "POST", /^\/market\/orders\/.+\/fulfill$/)[0].petId).toBe("pet-b");

    switchTo("奶茶");
    expect(await screen.findByText("120")).toBeTruthy();
    expect(callsTo(calls, "GET", "/market").at(-1)?.petId).toBe("pet-a");
    expect(calls.every((c) => !["/market", "/market/sell"].includes(c.path) || c.petId)).toBe(true);
  });
});

/* ---------------- 驾校 ---------------- */

describe("驾校：每条都带当前宠物", () => {
  it("首页：豆豆还没报名——报名带 pet-b；切到奶茶，历史按 pet-a 读出来（不再因 409 不见）", async () => {
    const { api, calls } = twoPetBackend();
    renderApp("/school", api);
    const enroll = await screen.findByRole("button", { name: /报名爪爪驾校/ });
    expect(callsTo(calls, "GET", "/driving").map((c) => c.petId)).toEqual(["pet-b"]);
    fireEvent.click(enroll);
    await waitFor(() => expect(callsTo(calls, "POST", "/driving/enroll")).toHaveLength(1));
    expect(callsTo(calls, "POST", "/driving/enroll")[0].petId).toBe("pet-b");
    await waitFor(() => expect(callsTo(calls, "GET", "/driving/history").some((c) => c.petId === "pet-b")).toBe(true));

    switchTo("奶茶");
    expect(await screen.findByText("最近的练习与考试（只有你能看到）")).toBeTruthy();
    expect(callsTo(calls, "GET", "/driving/history").at(-1)?.petId).toBe("pet-a");
    expect(callsTo(calls, "GET", "/driving/history").every((c) => c.petId)).toBe(true);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("科目页开练习、考局页读取与“不练了”都带 pet-b", async () => {
    const { api, calls } = twoPetBackend({ "pet-b": "enrolled" });
    const router = renderApp("/school/subject/s1", api);
    fireEvent.click(await screen.findByRole("button", { name: "做一套练习题" }));
    await waitFor(() => expect(router.state.location.pathname).toMatch(/^\/school\/session\//));
    expect(callsTo(calls, "POST", "/driving/sessions").map((c) => c.petId)).toEqual(["pet-b"]);
    const leave = await screen.findByRole("button", { name: "不练了" });
    expect(callsTo(calls, "GET", /^\/driving\/sessions\/[^/]+$/).every((c) => c.petId === "pet-b")).toBe(true);
    fireEvent.click(leave);
    await waitFor(() => expect(callsTo(calls, "POST", /\/abandon$/)).toHaveLength(1));
    expect(callsTo(calls, "POST", /\/abandon$/)[0].petId).toBe("pet-b");
  });

  it("考局页“开始练习”带 pet-b", async () => {
    const { api, calls } = twoPetBackend({ "pet-b": "enrolled" });
    renderApp("/school/subject/s1", api);
    fireEvent.click(await screen.findByRole("button", { name: "做一套练习题" }));
    const begin = await screen.findByRole("button", { name: "开始练习" });
    await waitFor(() => expect((begin as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(begin);
    await waitFor(() => expect(callsTo(calls, "POST", /\/begin$/)).toHaveLength(1));
    expect(callsTo(calls, "POST", /\/begin$/)[0].petId).toBe("pet-b");
  });

  it("成绩单读考局带 pet-b；领证带 pet-b", async () => {
    const first = twoPetBackend({ "pet-b": "enrolled" });
    renderApp("/school/result/any-session", first.api);
    await waitFor(() => expect(callsTo(first.calls, "GET", "/driving/sessions/any-session")).toHaveLength(1));
    expect(callsTo(first.calls, "GET", "/driving/sessions/any-session")[0].petId).toBe("pet-b");
    cleanup();

    const second = twoPetBackend({ "pet-b": "licensed" });
    renderApp("/school/ceremony", second.api);
    fireEvent.click(await screen.findByRole("button", { name: "开始领证" }));
    await waitFor(() => expect(callsTo(second.calls, "POST", "/driving/ceremony")).toHaveLength(1));
    expect(callsTo(second.calls, "POST", "/driving/ceremony")[0].petId).toBe("pet-b");
  });

  it("live 服务：除课程外每条都带 ?pet_id=", async () => {
    const seen: Array<[string, unknown]> = [];
    const api = { base: "/api/v1/web", request: async (path: string, options: { query?: Record<string, unknown> } = {}) => { seen.push([path, options.query?.pet_id]); return {}; } } as unknown as ApiClient;
    const driving = createLiveDrivingService({ api } as never);
    await driving.status("p");
    await driving.enroll("p");
    await driving.createSession({ subject: "s1", mode: "practice", item: null }, "k", "p");
    await driving.session("s", "p");
    await driving.begin("s", "p");
    await driving.answer("s", { question_id: "q", answer: "a" } as never, "p");
    await driving.inputs("s", {} as never, "p");
    await driving.pause("s", "p");
    await driving.submit("s", "p");
    await driving.abandon("s", true, "p");
    await driving.history("p");
    await driving.ceremony("p");
    await driving.curriculum();
    expect(seen.filter(([path]) => path !== "/driving/curriculum").map(([path, pet]) => `${path}=${pet}`)).toEqual([
      "/driving=p",
      "/driving/enroll=p",
      "/driving/sessions=p",
      "/driving/sessions/s=p",
      "/driving/sessions/s/begin=p",
      "/driving/sessions/s/answers=p",
      "/driving/sessions/s/inputs=p",
      "/driving/sessions/s/pause=p",
      "/driving/sessions/s/submit=p",
      "/driving/sessions/s/abandon=p",
      "/driving/history=p",
      "/driving/ceremony=p",
    ]);
  });
});

/* ---------------- 设置 ---------------- */

describe("设置：读、存都带当前宠物", () => {
  it("当前是豆豆：显示豆豆的简介（不是第一只的）；存简介带 pet-b；切到奶茶后表单换成奶茶的", async () => {
    const { api, calls } = twoPetBackend();
    renderApp("/settings", api);
    const bio = (await screen.findByLabelText("TA 的简介")) as HTMLInputElement;
    expect(bio.value).toBe("豆豆的简介");
    expect(callsTo(calls, "GET", "/settings").map((c) => c.petId)).toEqual(["pet-b"]);

    fireEvent.change(bio, { target: { value: "豆豆爱晒太阳" } });
    fireEvent.click(screen.getByRole("button", { name: "保存简介" }));
    await waitFor(() => expect(callsTo(calls, "PATCH", "/settings")).toHaveLength(1));
    expect(callsTo(calls, "PATCH", "/settings")[0]).toMatchObject({ petId: "pet-b", body: { bio: "豆豆爱晒太阳" } });
    expect(screen.queryByRole("alert")).toBeNull();

    switchTo("奶茶");
    await waitFor(() => expect((screen.getByLabelText("TA 的简介") as HTMLInputElement).value).toBe("奶茶的简介"));
    expect(callsTo(calls, "GET", "/settings").at(-1)?.petId).toBe("pet-a");
    fireEvent.click(screen.getByRole("button", { name: "只有我" }));
    await waitFor(() => expect(callsTo(calls, "PATCH", "/settings")).toHaveLength(2));
    expect(callsTo(calls, "PATCH", "/settings")[1]).toMatchObject({ petId: "pet-a", body: { profile_visibility: "private" } });

    // 再切回豆豆：豆豆那份已经在缓存里（切宠物时“identity”前缀的缓存不清），表单也要换回豆豆的，不能留着奶茶的简介。
    switchTo("豆豆");
    await waitFor(() => expect((screen.getByLabelText("TA 的简介") as HTMLInputElement).value).toBe("豆豆爱晒太阳"));
  });

  it("“聊天时更懂你”说人话：不出现开发术语与原始模式代码", async () => {
    const { api } = twoPetBackend();
    renderApp("/settings", api);
    expect(await screen.findByText("聊天时更懂你")).toBeTruthy();
    expect(screen.getByText("未开启")).toBeTruthy();
    expect(document.body.textContent).toContain("开启后，TA 回你消息时会更贴着你的意思");
    expect(document.body.textContent).not.toMatch(/意图判断层|可选控件|回应措辞|关闭（默认）|\boff\b|\bshadow\b|\bassist\b/);
  });
});

/* ---------------- 菜园选种子 ---------------- */

describe("菜园：选种子时读收藏带当前宠物", () => {
  it("点空地打开选种子：GET /collection 带 pet-b", async () => {
    const { api, calls } = twoPetBackend();
    renderApp("/garden", api);
    fireEvent.click(await screen.findByRole("button", { name: /^在第 \d+ 块地种点什么$/ }));
    await waitFor(() => expect(callsTo(calls, "GET", "/collection")).toHaveLength(1));
    expect(callsTo(calls, "GET", "/collection")[0].petId).toBe("pet-b");
  });
});

/* ---------------- 统一错误态 ---------------- */

describe("统一错误态：pet_required 说人话", () => {
  it("正文是人话；后端原话、错误码与原因码收进“技术信息”；别的错误照旧显示原话", () => {
    const view = render(<ErrorState error={petRequired()} onRetry={() => undefined} />);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("家里有不止一只伙伴，先选一只再看。");
    const tech = alert.querySelector("details");
    expect(tech?.textContent).toContain("CONFLICT");
    expect(tech?.textContent).toContain("pet_required");
    expect(tech?.textContent).toContain(PET_REQUIRED_MESSAGE);
    // 技术信息之外不露参数名与原话
    const outside = [...alert.childNodes].filter((node) => node !== tech).map((node) => node.textContent).join("");
    expect(outside).not.toMatch(/pet_id|pet_required|请指明/);
    view.unmount();

    render(<ErrorState error={new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "还没成熟。", details: { reason: "not_ripe" } })} />);
    expect(screen.getByRole("alert").textContent).toContain("还没成熟。");
    expect(screen.getByRole("alert").textContent).not.toContain("家里有不止一只伙伴");
  });
});

/* ---------------- 点按区（样式规则） ---------------- */

describe("点按区至少 40px（样式规则；实际尺寸由截图脚本在浏览器里量）", () => {
  const css = (rel: string) => readFileSync(resolve(ROOT, rel), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const minHeightOf = (text: string, selector: string) => {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const blocks = [...text.matchAll(new RegExp(`(?:^|[}\\s,])${escaped}\\s*\\{([^}]*)\\}`, "g"))].map((m) => m[1]);
    const values = blocks.flatMap((b) => [...b.matchAll(/min-height:\s*(\d+)px/g)].map((m) => Number(m[1])));
    return values.length ? Math.max(...values) : 0;
  };
  it("欢迎页登录链接、登录 / 注册页底部链接", () => {
    const identity = css("src/features/identity/identity.css");
    expect(minHeightOf(identity, ".ps-welcome-login")).toBeGreaterThanOrEqual(40);
    expect(minHeightOf(identity, ".ps-auth-switch a")).toBeGreaterThanOrEqual(40);
  });
  it("我们的家：三个复选框所在的整行、“回家看看 →”", () => {
    const household = css("src/features/household/household.css");
    expect(minHeightOf(household, ".ps-family-switches label")).toBeGreaterThanOrEqual(40);
    expect(minHeightOf(household, ".ps-family-card a")).toBeGreaterThanOrEqual(40);
  });
});

