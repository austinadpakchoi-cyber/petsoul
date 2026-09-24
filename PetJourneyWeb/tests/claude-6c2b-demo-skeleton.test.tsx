/**
 * claude-6c2b（分身）· 演示站不再停在骨架屏：照片页 /photos 的照片许可（家庭详情）与申请记录、我们的家 /households/manage。
 * 原因：这几处查询都要求 userId 才启用，演示模式下 HouseholdProvider 给的 userId 是 null，查询永远不启用、一直 pending。
 * 修法照 useActiveHome：演示下不因 userId 为空而停用（键的账号位是 "-"），照样问演示服务——
 * - 演示服务有数据就显示；
 * - 演示服务答“能力未接入”：给一句明确的说明（演示模式没有……），不转骨架屏、不说“这里暂时还没开放”（旧说法“这里还在搭建中”）、也不误说“还没有家庭”；
 * - live 的键、请求与启用条件一点不变：仍按 userId 分键；live 的“能力未接入”照旧走统一错误态。
 */
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router";
import type { HomeSnapshot, HouseholdBrief, HouseholdDetail, PhotoRequestView } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { queryKeys } from "@/shared/query/queryClient";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import { PhotoRequestsPage } from "@/features/pets/PhotoRequestsPage";
import { HouseholdPage } from "@/features/household/HouseholdPage";

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
  vi.stubGlobal("scrollTo", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/* ---------------- 测试数据 ---------------- */

const DEMO_PET = fixtureHomeSnapshot().pet.pet_id; // 演示家园快照里的那只宠物

const BRIEF: HouseholdBrief = {
  household_id: "house-1",
  name: "海边的家",
  home_id: "home-1",
  role: "admin",
  home_activated: true,
  member_count: 1,
  pets: [{ pet_id: "pet-a", name: "奶茶", species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true }],
};

const DETAIL: HouseholdDetail = {
  household: BRIEF,
  members: [{ user_id: "owner-1", display_name: "小林", role: "admin", joined_at: "2026-09-20T00:00:00Z", is_you: true }],
  settings: { name: "海边的家", caregivers_can_spend: false, generated_photos: true, pet_messages: true, public_posts: false },
  your_permissions: ["view", "care", "spend", "manage"],
  version: 1,
};

const READY_ROW: PhotoRequestView = {
  request_id: "pr-1",
  task_id: "task-1",
  scene: "home",
  narrative: "daily_life",
  fictional: false,
  captured_at: "2026-09-23T08:00:00Z",
  place: "家",
  city: "厦门",
  photo_status: "ready",
  image_url: "/media/photo-1.jpg",
  can_retry: false,
};

/** live 家里那只宠物在家（不在路上，不去读行程地图）。 */
const liveHome = (): HomeSnapshot => {
  const base = fixtureHomeSnapshot();
  return { ...base, data_origin: "live", presence: "at_home", journey: null, pet: { ...base.pet, pet_id: "pet-a", name: "奶茶" } } as HomeSnapshot;
};

const capability = (name: string) => ApiError.capability(name, "这项在这里没有。");

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

/** 页面挂在家庭上下文里（演示模式 userId 为 null；live 给账号）。 */
function renderPage(element: ReactElement, path: string, services: Record<string, unknown>, userId: string | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={strictServices(services)}>
        <MemoryRouter initialEntries={[path]}>
          <HouseholdProvider userId={userId}>{element}</HouseholdProvider>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return client;
}

/** 演示站原样：真实路由表 + 真实演示服务。 */
function renderDemo(path: string) {
  const modules = loadFeatureModules();
  const services = buildServices(modules, { mode: "fixture", api: createApiClient("/api/v1/web") });
  const router = createMemoryRouter(buildRoutes(modules), { initialEntries: [path] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { client, router };
}

const busy = () => [...document.querySelectorAll("[aria-busy='true'] .visually-hidden")].map((node) => node.textContent);
const hasKey = (client: QueryClient, key: readonly unknown[]) => client.getQueryCache().findAll({ queryKey: key, exact: true }).length === 1;

/* ---------------- 演示站原样 ---------------- */

describe("演示站：不再停在骨架屏", () => {
  it("/photos：照片许可与申请记录都问了演示服务（账号位 \"-\"，记录按演示宠物），答“能力未接入”就明说演示里没有；没有在转的读取", async () => {
    const { client, router } = renderDemo("/photos");
    expect(await screen.findByText("演示模式没有照片记录", {}, { timeout: 4000 })).toBeTruthy();
    await waitFor(() => expect(busy()).toEqual([]));
    expect(router.state.location.pathname).toBe("/photos");
    expect(screen.getByText("演示模式里拍不了真实照片，这里先看看有哪些拍法。")).toBeTruthy();
    expect(screen.getByText("住进来以后，给 TA 拍的照片会在这里。")).toBeTruthy();
    // 不当成出错：没有“这里暂时还没开放”（旧说法“这里还在搭建中”）、没有重试，也不说“暂时读不到照片许可”。
    expect(document.body.textContent).not.toMatch(/这里暂时还没开放|这里还在搭建中|暂时读不到照片许可|正在读取照片结果|正在确认这个家的照片许可/);
    expect(screen.queryByRole("button", { name: "重试" })).toBeNull();
    expect((screen.getByRole("button", { name: "给我拍一张" }) as HTMLButtonElement).disabled).toBe(true);
    // 键：演示没有账号（账号位 "-"）；照片记录按演示家园快照里的那只宠物（与“回忆”页同一个键）。
    expect(hasKey(client, queryKeys.householdDetail("-", ""))).toBe(true);
    expect(hasKey(client, queryKeys.photoRequestsFor("-", DEMO_PET))).toBe(true);
    expect(client.getQueryState(queryKeys.photoRequestsFor("-", DEMO_PET))?.status).toBe("error");
  });

  it("/households/manage：不再误说“还没有家庭”；演示服务答“能力未接入”，明说演示模式没有真实的家庭资料；返回照旧回“我的”", async () => {
    const { client } = renderDemo("/households/manage");
    expect(await screen.findByText("演示模式没有真实的家庭资料", {}, { timeout: 4000 })).toBeTruthy();
    expect(screen.getByText("住进来以后，家人、邀请和约定都在这里。")).toBeTruthy();
    await waitFor(() => expect(busy()).toEqual([]));
    expect(document.body.textContent).not.toMatch(/还没有家庭|这里暂时还没开放|这里还在搭建中|正在翻开家庭档案/);
    expect(screen.getByRole("link", { name: "返回" }).getAttribute("href")).toBe("/me");
    expect(hasKey(client, queryKeys.householdDetail("-", ""))).toBe(true);
  });
});

/* ---------------- 演示服务有数据就显示 ---------------- */

describe("演示模式：演示服务有数据就显示", () => {
  it("/photos：家庭许可开着、有一张照片——许可按数据走，记录显示出来；照片记录按演示宠物去读", async () => {
    const detail = vi.fn(async () => DETAIL);
    const photoRequests = vi.fn(async () => [READY_ROW]);
    renderPage(<PhotoRequestsPage />, "/photos", {
      households: { list: vi.fn(), detail },
      world: { home: async () => fixtureHomeSnapshot() },
      pets: { photoRequests },
      transport: {},
    }, null);
    expect(await screen.findByRole("img", { name: "动物世界生成照片" })).toBeTruthy();
    await waitFor(() => expect(busy()).toEqual([]));
    expect(photoRequests).toHaveBeenCalledWith(DEMO_PET, expect.anything());
    expect(detail).toHaveBeenCalledWith("", expect.anything());
    expect(screen.queryByText("演示模式没有照片记录")).toBeNull();
    expect(screen.queryByText(/演示模式里拍不了/)).toBeNull();
    expect(screen.queryByText("这个家还没开启 AI 照片")).toBeNull();
  });
});

/* ---------------- live 一点不变 ---------------- */

describe("live：键、请求与启用条件照旧（按 userId 分键）", () => {
  it("/photos：许可按 (owner-1, house-1)、记录按 (owner-1, pet-a) 分键与请求；不出现账号位为 \"-\" 的键", async () => {
    mode.dataMode = "live";
    const detail = vi.fn(async () => DETAIL);
    const photoRequests = vi.fn(async () => [READY_ROW]);
    const client = renderPage(<PhotoRequestsPage />, "/photos", {
      households: { list: async () => [BRIEF], detail },
      world: { home: async () => liveHome() },
      pets: { photoRequests },
      transport: {},
    }, "owner-1");
    expect(await screen.findByRole("img", { name: "动物世界生成照片" })).toBeTruthy();
    expect(photoRequests).toHaveBeenCalledWith("pet-a", expect.anything());
    expect(detail).toHaveBeenCalledWith("house-1", expect.anything());
    expect(hasKey(client, queryKeys.photoRequestsFor("owner-1", "pet-a"))).toBe(true);
    expect(hasKey(client, queryKeys.householdDetail("owner-1", "house-1"))).toBe(true);
    const anonymous = client.getQueryCache().getAll().filter((query) => ["pets", "households"].includes(String(query.queryKey[0])) && query.queryKey[2] === "-");
    expect(anonymous).toEqual([]);
  });

  it("/photos：live 的“能力未接入”照旧走统一错误态（这里暂时还没开放），不冒充演示说明", async () => {
    mode.dataMode = "live";
    renderPage(<PhotoRequestsPage />, "/photos", {
      households: { list: async () => [BRIEF], detail: async () => DETAIL },
      world: { home: async () => liveHome() },
      pets: { photoRequests: async () => { throw capability("pets.photo-requests"); } },
      transport: {},
    }, "owner-1");
    const list = await screen.findByText("申请记录");
    await waitFor(() => expect(document.body.textContent).toContain("这里暂时还没开放"));
    expect(list).toBeTruthy();
    expect(screen.queryByText("演示模式没有照片记录")).toBeNull();
  });

  it("/households/manage：详情按 (owner-1, house-1) 分键；live 的“能力未接入”照旧走统一错误态", async () => {
    mode.dataMode = "live";
    const client = renderPage(<HouseholdPage />, "/households/manage", {
      households: { list: async () => [BRIEF], detail: async () => { throw capability("households.detail"); }, invites: async () => [] },
    }, "owner-1");
    expect(await screen.findByText("这里暂时还没开放")).toBeTruthy();
    expect(screen.queryByText("演示模式没有真实的家庭资料")).toBeNull();
    expect(hasKey(client, queryKeys.householdDetail("owner-1", "house-1"))).toBe(true);
    expect(within(document.body).queryByText("还没有家庭")).toBeNull();
  });
});
