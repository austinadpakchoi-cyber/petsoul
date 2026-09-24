/**
 * claude-6c2b（分身）· 新版信息架构的两个全屏页：回忆（/memories）与我的（/me）。
 * - 两条路由经真实路由表在 fixture 下渲染：回忆底部是新版三栏且“回忆”为当前项、不挂旧四栏；我的左上角回地图、没有任何底栏。
 * - 各入口 href 正确；不出现还没接进前端服务的入口（隐私）。生活片段（/timeline）已接上，见 claude-6c2b-timeline.test.tsx；TA 的档案（/me/dna）已接上，见 claude-6c2b-dna.test.tsx；我的举报（/me/reports）已接上，见 claude-6c2b-my-reports.test.tsx。
 * - 入口上的数字只来自服务结果：有数据时显示；服务抛错（能力未接入、服务端出错）时只隐藏数字，入口照常，不出错误文字。
 * - 打工状态各说各的：going 是“去上班的路上”，不是在干活。
 * - “给这个家添伙伴”只对这个家的管理员出现；主人的显示名只认会话里的 user.display_name。
 * - 宠物头像一律是 TA 自己的样子（PetPortrait）：有照片用照片，演示模式用演示图，live 没照片是爪印，从不写名字首字。
 */
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, MemoryRouter, Route, RouterProvider, Routes } from "react-router";
import type { CredentialSummary, HouseholdBrief, JobRecord, PhotoRequestView, SessionState, TravelGuide } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import { fixtureCollection } from "@/fixtures/social";
import { MemoriesPage } from "@/features/memories/MemoriesPage";
import { heldCredentialCount, jobStatusText, latestJob, photoCounts } from "@/features/memories/facts";
import { MePage } from "@/features/me/MePage";

// 同一个文件里要切 fixture / live：env 用 getter 读一个可改的开关（页面在渲染时才读 env.dataMode）。
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
  // 全屏页的布局里有滚动恢复；jsdom 没有 scrollTo。
  vi.stubGlobal("scrollTo", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/* ---------------- 测试数据 ---------------- */

const FIXTURE_PET = fixtureHomeSnapshot().pet; // 演示世界的样板宠物（与地图演示剧本同一只）

const credential = (kind: CredentialSummary["kind"], status: CredentialSummary["status"]): CredentialSummary => ({
  credential_id: status === "not_obtained" ? null : `cred-${kind}`,
  kind,
  label: kind,
  status,
  number: status === "not_obtained" ? null : `PS-${kind}`,
  issued_at: null,
  title: null,
  condition: "条件",
  private: false,
  links: [],
});

const job = (status: string, startsAt: string, title: string): JobRecord => ({
  journey_id: `j-${title}`,
  job_key: "fishing_port",
  title,
  place: "渔港",
  starts_at: startsAt,
  ends_at: "2026-09-24T12:00:00Z",
  status,
  pay: 25,
  paid: status === "done",
});

let photoSeq = 0;
const photo = (status: PhotoRequestView["photo_status"]): PhotoRequestView => {
  photoSeq += 1;
  return {
    request_id: `photo-${photoSeq}`,
    task_id: `task-${photoSeq}`,
    scene: "home",
    narrative: "daily_life",
    fictional: false,
    captured_at: "2026-09-23T08:00:00Z",
    place: "家",
    city: "厦门",
    photo_status: status,
    image_url: status === "ready" ? `/media/photo-${photoSeq}.jpg` : null,
    can_retry: status === "failed" || status === "unknown",
  };
};

const guide = (id: string): TravelGuide => ({
  guide_id: id,
  journey_id: `j-${id}`,
  city: "厦门",
  destination_title: "海边",
  title: "海边的一天",
  summary: null,
  stops: [],
  owner_tips: [],
  composed_by: "template",
  image_status: null,
  image_url: null,
  created_at: "2026-09-22T08:00:00Z",
});

const householdPet = (petId: string, name: string): HouseholdBrief["pets"][number] => ({
  pet_id: petId,
  name,
  species: "cat",
  photo_url: null,
  origin: "own_pet",
  presence: "at_home",
  join_step: "moved_in",
  joined_at: "2026-09-20T00:00:00Z",
  added_by_you: true,
});

const household = (over: Partial<HouseholdBrief> = {}): HouseholdBrief => ({
  household_id: "house-1",
  name: "海边的家",
  home_id: "home-1",
  role: "admin",
  home_activated: true,
  member_count: 3,
  pets: [householdPet("pet-a", "奶茶")],
  ...over,
});

const signedIn = (displayName: string | null): SessionState => ({
  authenticated: true,
  user: { user_id: "owner-1", display_name: displayName, username: "lin", auth_method: "web_password" },
  csrf_required: false,
  expires_at: null,
  onboarding: { step: "active", pet_id: "pet-a", home_id: "home-1", reception_session_id: null, reception_skipped: false, home_activated_at: null, pet_origin: "own_pet" },
});

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

function renderPage(element: ReactElement, path: string, services: Record<string, unknown>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={strictServices(services)}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path={path.split("?")[0]} element={element} />
          </Routes>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { ...view, client };
}

/** fixture 下 WorldGate 会挂家庭上下文（它会读 households 服务，但 fixture 不调用）；当前宠物来自演示家园快照。 */
function fixtureBase() {
  return {
    households: { list: () => { throw new Error("fixture 不应请求家庭列表"); } },
    world: { home: async () => fixtureHomeSnapshot() },
  };
}

/** 回忆页的五个入口，按 href 取。 */
async function memoryEntries(): Promise<Record<string, HTMLElement>> {
  const nav = await screen.findByRole("navigation", { name: "回忆里的入口" });
  return Object.fromEntries(within(nav).getAllByRole("link").map((link) => [link.getAttribute("href") ?? "", link]));
}

const MEMORY_HREFS = ["/timeline", "/life", "/life?tab=jobs", "/collection", "/photos", "/guides"];
const ERROR_WORDS = /接入|出错|失败|重试|没能|能力|服务端|接口|fixture|模型/;

/** 宠物头像一律是 TA 自己的样子：有图就是图，没图是爪印；任何情况下都不写名字首字。 */
function portraitOf(name: string): { image: string | null; paw: boolean; text: string } {
  const portrait = screen.getByRole("img", { name });
  return { image: portrait.querySelector("img")?.getAttribute("src") ?? null, paw: Boolean(portrait.querySelector("svg")), text: portrait.textContent ?? "" };
}

/* ---------------- 纯函数 ---------------- */

describe("回忆页的事实：只数真实结果", () => {
  it("证件只数 active / used；not_obtained、in_progress、expired 都不算“已持有”", () => {
    const list = [
      credential("identity_card", "active"),
      credential("bank_card", "active"),
      credential("boarding_pass", "used"),
      credential("passport", "not_obtained"),
      credential("driver_license", "in_progress"),
      credential("hotel_key", "expired"),
    ];
    expect(heldCredentialCount(list)).toBe(3);
    expect(heldCredentialCount([])).toBe(0);
  });

  it("打工状态各说各的：going 是“去上班的路上”，不是在干活；不认识的状态不猜", () => {
    expect(jobStatusText("going")).toBe("去上班的路上");
    expect(jobStatusText("working")).toBe("在干活");
    expect(jobStatusText("done")).toBe("干完了");
    expect(jobStatusText("going")).not.toMatch(/在干活|打工中|正在/);
    expect(jobStatusText("going")).not.toBe(jobStatusText("working"));
    expect(jobStatusText("paused")).toBeNull();
    expect(jobStatusText("")).toBeNull();
  });

  it("最近一条打工 = 开始时间最晚的那条；时间读不出来的排最后；空列表没有", () => {
    const old = job("done", "2026-09-20T09:00:00Z", "在书店理书");
    const newest = job("going", "2026-09-24T09:00:00Z", "去渔港帮忙收网");
    const middle = job("done", "2026-09-22T09:00:00Z", "在花店帮忙");
    const broken = job("working", "不是时间", "时间坏了");
    expect(latestJob([old, newest, middle])).toBe(newest);
    expect(latestJob([broken, middle])).toBe(middle);
    expect(latestJob([broken])).toBe(broken);
    expect(latestJob([])).toBeNull();
  });

  it("相册只数画好的照片；还在画的单独数；没画成、结果未确认的不算照片", () => {
    expect(photoCounts([photo("ready"), photo("ready"), photo("processing"), photo("failed"), photo("unknown")])).toEqual({ ready: 2, drawing: 1 });
    expect(photoCounts([])).toEqual({ ready: 0, drawing: 0 });
  });
});

/* ---------------- 经真实路由表（fixture） ---------------- */

describe("两条路由（fixture，经真实路由表与演示服务）", () => {
  function renderApp(path: string) {
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
    return router;
  }

  it("/memories：全屏页，不挂旧四栏；底部是新版三栏，“回忆”是当前项", async () => {
    renderApp("/memories");
    expect(await screen.findByRole("heading", { level: 1, name: "回忆" })).toBeTruthy();
    expect(await screen.findByText(`${FIXTURE_PET.name}的日子，都攒在这里。`)).toBeTruthy();
    const tabs = screen.getByRole("navigation", { name: "主导航（新版预览）" });
    const current = within(tabs).getByRole("link", { name: "回忆" });
    expect(current.getAttribute("href")).toBe("/memories");
    expect(current.getAttribute("aria-current")).toBe("page");
    expect(within(tabs).getByRole("link", { name: "地图" }).getAttribute("aria-current")).toBeNull();
    expect(within(tabs).getByRole("link", { name: "通讯器" }).getAttribute("aria-current")).toBeNull();
    expect(screen.queryByRole("navigation", { name: "主导航" })).toBeNull();
    expect(Object.keys(await memoryEntries())).toEqual(MEMORY_HREFS);
  });

  it("/me：全屏页，没有任何底栏；左上角回地图；当前宠物是演示世界的样板宠物", async () => {
    renderApp("/me");
    expect(await screen.findByRole("heading", { level: 2, name: FIXTURE_PET.name })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1, name: "我的" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "返回地图" }).getAttribute("href")).toBe("/map");
    expect(screen.queryByRole("navigation", { name: "主导航（新版预览）" })).toBeNull();
    expect(screen.queryByRole("navigation", { name: "主导航" })).toBeNull();
    expect(screen.queryAllByRole("navigation")).toHaveLength(0);
  });
});

/* ---------------- 回忆（/memories） ---------------- */

describe("回忆：入口与数字", () => {
  it("有数据：证件已持有几张、最近一条打工、收藏件数、画好的照片、手账份数；都按当前宠物请求", async () => {
    const asked: string[] = [];
    renderPage(<MemoriesPage />, "/memories", {
      ...fixtureBase(),
      life: {
        credentials: async (petId: string) => {
          asked.push(`credentials:${petId}`);
          return [credential("identity_card", "active"), credential("bank_card", "active"), credential("boarding_pass", "used"), credential("passport", "not_obtained"), credential("hotel_key", "expired")];
        },
        jobs: async (petId: string) => {
          asked.push(`jobs:${petId}`);
          return [job("done", "2026-09-20T09:00:00Z", "在书店理书"), job("working", "2026-09-24T09:00:00Z", "去渔港帮忙收网")];
        },
      },
      economy: { collection: async () => fixtureCollection() },
      pets: {
        photoRequests: async (petId: string) => {
          asked.push(`photos:${petId}`);
          return [photo("ready"), photo("ready"), photo("processing"), photo("failed")];
        },
      },
      transport: { guides: async () => [guide("g-1")] },
    });
    const entries = await memoryEntries();
    expect(Object.keys(entries)).toEqual(MEMORY_HREFS);
    await waitFor(() => expect(entries["/guides"].textContent).toContain("1 份"));
    await waitFor(() => expect(entries["/life"].textContent).toContain("已持有 3 张"));
    expect(entries["/life"].querySelector(".ps-mem-wallet")?.getAttribute("data-cards")).toBe("3");
    expect(entries["/life?tab=jobs"].textContent).toContain("在干活");
    expect(entries["/life?tab=jobs"].textContent).toContain("去渔港帮忙收网");
    expect(entries["/life?tab=jobs"].textContent).not.toContain("在书店理书");
    expect(entries["/collection"].textContent).toContain(`${fixtureCollection().length} 件`);
    expect(entries["/photos"].textContent).toContain("2 张");
    expect(entries["/photos"].textContent).toContain("还有 1 张在画");
    expect(asked.sort()).toEqual([`credentials:${FIXTURE_PET.pet_id}`, `jobs:${FIXTURE_PET.pet_id}`, `photos:${FIXTURE_PET.pet_id}`]);
    expect(screen.getByText(`${FIXTURE_PET.name}的日子，都攒在这里。`)).toBeTruthy();
    // 演示宠物没有照片：头像用演示对象的图，不写首字。
    const portrait = portraitOf(FIXTURE_PET.name);
    expect(FIXTURE_PET.photo_url).toBeNull();
    expect(portrait.image).toBeTruthy();
    expect(portrait.text).toBe("");
    // 页面底部挂新版三栏，“回忆”为当前项。
    const tabs = screen.getByRole("navigation", { name: "主导航（新版预览）" });
    expect(within(tabs).getByRole("link", { name: "回忆" }).getAttribute("aria-current")).toBe("page");
  });

  it.each([
    ["going", "去上班的路上", /在干活|干完了|打工中|正在/],
    ["working", "在干活", /去上班的路上|干完了/],
    ["done", "干完了", /去上班的路上|在干活/],
    ["paused", "最近一份工", /去上班的路上|在干活|干完了/],
  ])("最近一条打工是 %s：写“%s”，不写成别的状态", async (status, text, forbidden) => {
    renderPage(<MemoriesPage />, "/memories", {
      ...fixtureBase(),
      life: { credentials: async () => [], jobs: async () => [job(status, "2026-09-24T09:00:00Z", "去渔港帮忙收网")] },
      economy: { collection: async () => [] },
      pets: { photoRequests: async () => [] },
      transport: { guides: async () => [] },
    });
    const entries = await memoryEntries();
    await waitFor(() => expect(entries["/life?tab=jobs"].querySelector(".ps-mem-card__main")?.textContent).toBe(text));
    expect(entries["/life?tab=jobs"].textContent).not.toMatch(forbidden);
  });

  it("都还没有：说“还没有……/还空着”，不编数字，也没有叠卡", async () => {
    renderPage(<MemoriesPage />, "/memories", {
      ...fixtureBase(),
      life: { credentials: async () => [credential("identity_card", "not_obtained")], jobs: async () => [] },
      economy: { collection: async () => [] },
      pets: { photoRequests: async () => [photo("failed")] },
      transport: { guides: async () => [] },
    });
    const entries = await memoryEntries();
    await waitFor(() => expect(entries["/guides"].textContent).toContain("还没有手账"));
    await waitFor(() => expect(entries["/life"].textContent).toContain("还没有拿到证件"));
    expect(entries["/life?tab=jobs"].textContent).toContain("还没有打工记录");
    expect(entries["/collection"].textContent).toContain("还空着");
    expect(entries["/photos"].textContent).toContain("还没有照片");
    expect(document.querySelector(".ps-mem-wallet")).toBeNull();
    expect(screen.getByRole("navigation", { name: "回忆里的入口" }).textContent).not.toMatch(/\d/);
  });

  it("服务抛错（能力未接入、服务端出错）：只隐藏数字，六个入口照常，不出现错误文字", async () => {
    const unavailable = () => Promise.reject(ApiError.capability("demo", "这项能力在 fixture 模式下尚未接入。"));
    const broken = () => Promise.reject(new ApiError({ kind: "http", status: 500, code: "INTERNAL_ERROR", message: "服务端出错了" }));
    const { client } = renderPage(<MemoriesPage />, "/memories", {
      ...fixtureBase(),
      life: { credentials: unavailable, jobs: broken },
      economy: { collection: broken },
      pets: { photoRequests: unavailable },
      transport: { guides: broken },
    });
    const entries = await memoryEntries();
    // 先确认五个计数请求都已经失败（不是还在读），再看页面。
    await waitFor(() => {
      // 证件列表与卡包共用 queryKeys.credentials 前缀（["credentials","list",…]），所以命名空间里多一个 "credentials"。
      const counted = client.getQueryCache().getAll().filter((query) => ["life", "credentials", "economy", "pets", "transport"].includes(String(query.queryKey[0])));
      expect(counted).toHaveLength(5);
      expect(counted.every((query) => query.state.status === "error")).toBe(true);
    });
    expect(Object.keys(entries)).toEqual(MEMORY_HREFS);
    for (const link of Object.values(entries)) expect(link.querySelector(".ps-mem-card__fact")).toBeNull();
    const nav = screen.getByRole("navigation", { name: "回忆里的入口" });
    expect(nav.textContent).toMatch(/证件卡包.*打工记录.*明信片与小收藏.*相册.*旅程与攻略手账/);
    expect(nav.textContent).not.toMatch(/\d/);
    expect(document.body.textContent).not.toMatch(ERROR_WORDS);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("生活片段已接上：入口排第一、指向 /timeline，不带数字；仍不放“即将开放”占位", async () => {
    renderPage(<MemoriesPage />, "/memories", {
      ...fixtureBase(),
      life: { credentials: async () => [], jobs: async () => [] },
      economy: { collection: async () => [] },
      pets: { photoRequests: async () => [] },
      transport: { guides: async () => [] },
    });
    const entries = await memoryEntries();
    expect(Object.keys(entries)[0]).toBe("/timeline");
    expect(entries["/timeline"].textContent).toContain("生活片段");
    expect(entries["/timeline"].textContent).not.toMatch(/\d/);
    expect(document.body.textContent).not.toMatch(/即将开放|敬请期待/);
  });

  it("live：当前宠物来自家庭上下文（不另取家园快照），计数按账号与这只宠物请求", async () => {
    mode.dataMode = "live";
    const asked: string[] = [];
    const record = (name: string) => async (petId: string | null) => {
      asked.push(`${name}:${petId}`);
      return [];
    };
    renderPage(<MemoriesPage />, "/memories", {
      session: { current: async () => signedIn("小林") },
      households: { list: async () => [household()] },
      life: { credentials: record("credentials"), jobs: record("jobs") },
      economy: { collection: record("collection") },
      pets: { photoRequests: record("photos") },
      transport: { guides: record("guides") },
    });
    expect(await screen.findByText("奶茶的日子，都攒在这里。")).toBeTruthy();
    const entries = await memoryEntries();
    await waitFor(() => expect(asked).toHaveLength(5));
    expect(asked.sort()).toEqual(["collection:pet-a", "credentials:pet-a", "guides:pet-a", "jobs:pet-a", "photos:pet-a"]);
    await waitFor(() => expect(entries["/guides"].textContent).toContain("还没有手账"));
  });
});

/* ---------------- 我的（/me） ---------------- */

describe("我的：TA、家与账号", () => {
  const ME_FIXED = ["/households/manage", "/me/dna", "/onboarding/reception?mode=supplement", "/me/look", "/me/reports", "/settings"];
  const entryHrefs = () => [...document.querySelectorAll("main ul a")].map((a) => a.getAttribute("href"));

  it("fixture：演示宠物；左上角回地图、没有底栏；演示世界没有家庭资料与账号，不显示添伙伴与主人名", async () => {
    const sessionCurrent = vi.fn();
    renderPage(<MePage />, "/me", { ...fixtureBase(), session: { current: sessionCurrent } });
    expect(await screen.findByRole("heading", { level: 2, name: FIXTURE_PET.name })).toBeTruthy();
    expect(screen.getByRole("link", { name: "返回地图" }).getAttribute("href")).toBe("/map");
    expect(screen.queryAllByRole("navigation")).toHaveLength(0);
    expect(entryHrefs()).toEqual(ME_FIXED);
    expect(screen.getByRole("link", { name: /^我们的家/ }).textContent).toContain("家人、伙伴与邀请");
    expect(screen.queryByRole("link", { name: /添伙伴/ })).toBeNull();
    expect(document.querySelector(".ps-me-hero p")).toBeNull();
    expect(sessionCurrent).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toMatch(/DNA|隐私|即将开放/);
    expect(screen.getByRole("link", { name: /^TA 的档案/ }).getAttribute("href")).toBe("/me/dna");
    const portrait = portraitOf(FIXTURE_PET.name);
    expect(portrait.image).toBeTruthy();
    expect(portrait.text).toBe("");
  });

  it("live · 管理员：写上主人的显示名、家名与成员数；出现“给这个家添伙伴”", async () => {
    mode.dataMode = "live";
    renderPage(<MePage />, "/me", {
      session: { current: async () => signedIn("小林") },
      households: { list: async () => [household({ role: "admin", pets: [{ ...householdPet("pet-a", "奶茶"), photo_url: "/media/pets/pet-a.jpg" }] })] },
    });
    expect(await screen.findByRole("heading", { level: 2, name: "奶茶" })).toBeTruthy();
    expect(portraitOf("奶茶")).toEqual({ image: "/media/pets/pet-a.jpg", paw: false, text: "" });
    expect(screen.getByText("小林的伙伴")).toBeTruthy();
    expect(screen.getByRole("link", { name: /^我们的家/ }).textContent).toContain("海边的家 · 3 位成员");
    const add = screen.getByRole("link", { name: /^给这个家添伙伴/ });
    expect(add.getAttribute("href")).toBe("/pets/new");
    expect(entryHrefs()).toEqual(["/households/manage", "/pets/new", "/me/dna", "/onboarding/reception?mode=supplement", "/me/look", "/me/reports", "/settings"]);
    expect(screen.getByRole("link", { name: "返回地图" }).getAttribute("href")).toBe("/map");
    expect(screen.queryAllByRole("navigation")).toHaveLength(0);
  });

  it("live · 共同照顾者：不出现添伙伴；没有显示名就不写主人那一行；家没起名只写成员数", async () => {
    mode.dataMode = "live";
    renderPage(<MePage />, "/me", {
      session: { current: async () => signedIn(null) },
      households: { list: async () => [household({ role: "caregiver", name: null, member_count: 2 })] },
    });
    expect(await screen.findByRole("heading", { level: 2, name: "奶茶" })).toBeTruthy();
    // live 没有照片：中性爪印，不借演示图，也不写首字。
    expect(portraitOf("奶茶")).toEqual({ image: null, paw: true, text: "" });
    expect(screen.queryByRole("link", { name: /添伙伴/ })).toBeNull();
    expect(document.querySelector('a[href="/pets/new"]')).toBeNull();
    expect(entryHrefs()).toEqual(ME_FIXED);
    expect(document.querySelector(".ps-me-hero p")).toBeNull();
    const home = screen.getByRole("link", { name: /^我们的家/ });
    expect(home.querySelector(".ps-me-row__meta")?.textContent).toBe("2 位成员");
  });
});
