/**
 * claude-6c2b（分身）· 二级页的出口（用户 2026-09-24：“老的那些 ui 记得要退役掉的，不要干扰到我们新的 ui ux”）。
 * 新导航下二级页全屏、不显示底栏（方案 2.2），每一页都得自己带出口；返回去向按方案 2.3 的层级写死上级，不做历史后退。
 * - 没有死胡同：主布局下的二级页逐个经真实路由表（fixture）打开，都只有一个“返回”；本次定了去向的页，href 等于定的上级。
 * - 旅途页两条分支都有出口：fixture 走“旅途中”分支（地图贴边，原本连顶栏都没有），live 且 TA 在家走“在家”分支。
 * - 不再有散落的 "/home" 路由字面量：只剩白名单，每条写理由；接口路径（api.request("/home…")、契约表 path）不算路由。
 * - 不靠顶栏的出口（接受邀请、入住守卫、接待 / 叮嘱的“先回去”“先去地图看看”、叮嘱存好后的去向）逐条按行为测：
 *   补充叮嘱（已入住后再来改）回“我的”，演示模式回地图首页，入住中的流程照旧（去入住）。
 *   按钮文字跟着去向走（补充：“先回去”“完成”；演示：“先去地图看看”“回地图”）；live 入住中的文字不动，由 claude-6c2b-entry-flow.test.tsx 钉着。
 *   图标也跟着走（“先回去”返回箭头 back、“先去地图看看”地图图钉 pin，live 入住中仍是房子）；叮嘱存好后的说明写“在‘我的’里补充”，失败说明与按钮同一套条件。
 * - “我们的家”的称呼：输入上限与后端 PetRelationshipRequest / InviteCreateRequest 一致（12）；保存后 TA 的档案（/me/dna）缓存一起失效。
 */
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import * as ts from "typescript";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, MemoryRouter, Route, RouterProvider, Routes, useLocation } from "react-router";
import type {
  HomeSnapshot,
  HouseholdBrief,
  HouseholdDetail,
  IntakeCandidate,
  IntakeConfirmationResult,
  InvitePreview,
  OnboardingState,
  PetPublicProfile,
  PetRelationship,
  PetRelationshipRequestInput,
  ReceptionSession,
  SessionState,
} from "@/shared/contracts";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { queryKeys } from "@/shared/query/queryClient";
import { buildServices, ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider } from "@/shared/session/householdContext";
import { Icon, type IconName } from "@/shared/ui";
import { fixtureHomeSnapshot } from "@/fixtures/home";
import { HouseholdPage } from "@/features/household/HouseholdPage";
import { JoinPage } from "@/features/household/JoinPage";
import { MoveInPage } from "@/features/identity/pages";
import { JourneyPage } from "@/features/journey/JourneyPage";
import { PendingEntryPage } from "@/features/pets/PendingEntryPage";
import { CareNotesPage } from "@/features/reception/CareNotesPage";
import { ReceptionPage } from "@/features/reception/ReceptionPage";

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
  // 主布局里有滚动恢复；jsdom 没有 scrollTo。示意地图量尺寸用 ResizeObserver，jsdom 也没有：没有它旅途地图会在挂载时崩到错误页。
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/* ---------------- 渲染 ---------------- */

const modules = loadFeatureModules();

/** 整个应用（真实路由表 + 主布局），fixture 服务。 */
function renderApp(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const services = buildServices(modules, { mode: "fixture", api: createApiClient("/api/v1/web") });
  const router = createMemoryRouter(buildRoutes(modules), { initialEntries: [path] });
  render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return router;
}

/** 只放页面该用的服务；读到没给的服务就算失败（证明页面没偷偷请求别的）。 */
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
  return <output data-testid="location">{location.pathname}</output>;
}

/** 单页渲染：页面挂在自己的路径上，别的路径一律是“落点探针”，用来读跳去了哪里。from：站内上一页（有它就不是“直接打开”）。 */
function renderPage(element: ReactElement, entry: string, services: Record<string, unknown>, options: { userId?: string; from?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const page = options.userId ? <HouseholdProvider userId={options.userId}>{element}</HouseholdProvider> : element;
  const view = render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={strictServices(services)}>
        <MemoryRouter initialEntries={options.from ? [options.from, entry] : [entry]}>
          <Routes>
            <Route path={entry.split("?")[0]} element={page} />
            <Route path="*" element={<LocationProbe />} />
          </Routes>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { ...view, client };
}

const landedAt = () => screen.queryByTestId("location")?.textContent ?? null;

/** 页面上所有叫“返回”的控件：写死上级的是链接，历史后退是按钮。 */
function backControls(): HTMLElement[] {
  return [...screen.queryAllByRole("link", { name: "返回" }), ...screen.queryAllByRole("button", { name: "返回" })];
}

/**
 * 按钮上画的是哪个图标：拿 Icon 自己画出来的路径来比。
 * Icon 的名字现在是实际图标名的联合类型（shared/ui/Icon.tsx 已收紧），写错名字 tsc 会报；运行时仍先确认参照图标的路径不是空的。
 */
function iconPath(name: IconName): string {
  const { container } = render(<Icon name={name} />, { container: document.createElement("div") });
  const d = container.querySelector("path")?.getAttribute("d") ?? "";
  expect(d, `Icon 里没有叫 ${name} 的图标`).not.toBe("");
  return d;
}
const iconOf = (button: HTMLElement) => button.querySelector("svg path")?.getAttribute("d") ?? "";

/* ---------------- 测试数据 ---------------- */

const onboardingAt = (step: OnboardingState["step"]): OnboardingState => ({
  step,
  pet_id: "pet-a",
  home_id: "home-1",
  reception_session_id: "rs-1",
  reception_skipped: false,
  home_activated_at: null,
  pet_origin: "own_pet",
});

const signedIn = (step: OnboardingState["step"]): SessionState => ({
  authenticated: true,
  user: { user_id: "owner-1", username: "lin", display_name: null, auth_method: "web_password" },
  csrf_required: false,
  expires_at: null,
  onboarding: onboardingAt(step),
});

/** 演示世界的会话：没有账号、没有入住阶段（identity 模块的 fixture 会话就是这样）。 */
const fixtureSession: SessionState = { authenticated: false, user: null, csrf_required: false, expires_at: null, onboarding: null };

const profile = { pet_id: "pet-a", display_name: "奶茶", species: "cat", avatar_url: null } as unknown as PetPublicProfile;

const candidate = {
  candidate_id: "c-1",
  kind: "habit",
  subject: "pet",
  text: "喜欢窗台晒太阳",
  source_turn_id: "t-2",
  source_excerpt: "它最喜欢在窗台晒太阳",
  needs_clarification: false,
  suggested_slot: null,
  suggested_slot_value: null,
  state: "unconfirmed",
} as IntakeCandidate;

function receptionSession(candidates: IntakeCandidate[]): ReceptionSession {
  return {
    session_id: "rs-1",
    pet_id: "pet-a",
    branch: "own_pet",
    mode: "guided_notes",
    status: "active",
    host: { host_id: "h", display_name: "星球接待员", role_label: "PetSoul 的 AI 接待角色", avatar_url: null, is_ai: true, disclosure: "我是 AI 接待角色。" },
    turns: [{ turn_id: "t-1", seq: 1, speaker: "host", text: "有什么想交代的吗？", created_at: "2026-09-23T00:00:00Z" }],
    candidates,
    draft_revision: 1,
    draft_expires_at: null,
    data_origin: "live",
  };
}

const brief: HouseholdBrief = {
  household_id: "house-1",
  name: "海边的家",
  home_id: "home-1",
  role: "admin",
  home_activated: true,
  member_count: 1,
  pets: [{ pet_id: "pet-a", name: "奶茶", species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step: "moved_in", joined_at: "2026-09-20T00:00:00Z", added_by_you: true }],
};

/* ---------------- 1. 没有死胡同 ---------------- */

// 方案 2.3 的层级：写死上级，不做历史后退。null = 不是本次定的去向（别的模块在管），这里只要求“有且只有一个返回”。
const SECONDARY: Array<[path: string, parent: string | null]> = [
  ["/collection", "/memories"], // 回忆与收藏属于回忆
  ["/market", "/garden"], // 集市属于菜园体系
  ["/garden", "/map"], // 菜园是从地图进的二级页
  ["/neighbors", null], // 菜园下的三级页（回菜园）
  ["/journey", "/map"], // 旅途并入地图主状态面板；fixture 下是“旅途中”分支
  ["/journey/food", "/map"], // 从主状态面板“TA 在哪”进入
  ["/guides", "/memories"], // 攻略手账属于回忆
  ["/school", "/map"], // 爪爪驾校：从地图进入
  ["/households/manage", "/me"], // 我们的家：入口在“我的”
  ["/settings", "/me"],
  ["/pets/new", "/me"],
  ["/photos", "/memories"], // 相册属于回忆
  ["/circle", null], // 朋友圈归通讯器（另一个分身）
  // 带参数、fixture 里找得到真实 id 的（攻略 fixture 为空、驾考成绩单的 id 是运行时生成的，这两类没有）：
  ["/homes/fx-home-lizi", null],
  ["/journey/food/fx-rec-rich-1", null],
  ["/visits/fx-visit-001", "/map"], // 到店：从主状态面板“TA 在哪”进入
  ["/posts/fx-post-1", null],
  ["/pets/fx-pet-001", null],
  ["/school/subject/s1", null],
];

describe("没有死胡同：主布局下的二级页都有“返回”（fixture，真实路由表）", () => {
  it.each(SECONDARY)("%s", async (path, parent) => {
    const router = renderApp(path);
    await waitFor(() => expect(backControls().length).toBeGreaterThan(0), { timeout: 4000 });
    // 顶栏先于数据出现：等演示数据（每段约 220ms，旅途要串两段）和挂载后的副作用落定。
    // 页面若在那之后崩成错误页 / 找不到页，刚才那一瞬间的“返回”不算数。
    await new Promise((resolve) => setTimeout(resolve, 600));
    expect(document.body.textContent).not.toMatch(/这一页没能打开|这里还没有路/);
    // 没被重定向到别处：否则“有返回”说的是另一页。
    expect(router.state.location.pathname).toBe(path);
    const backs = backControls();
    expect(backs).toHaveLength(1);
    if (parent) expect(backs[0].getAttribute("href")).toBe(parent);
  });
});

describe("旅途页两条分支都有出口", () => {
  it("fixture · 旅途中（地图贴边、原本没有顶栏）：左上角回地图首页；读屏标题仍只有那一个 h1，顶栏同名标题不重复朗读", async () => {
    renderApp("/journey");
    expect(await screen.findByTestId("journey-map", {}, { timeout: 4000 })).toBeTruthy();
    const topbar = document.querySelector<HTMLElement>(".ps-topbar");
    expect(topbar).toBeTruthy();
    expect(within(topbar!).getByRole("link", { name: "返回" }).getAttribute("href")).toBe("/map");
    const h1 = screen.getAllByRole("heading", { level: 1 });
    expect(h1).toHaveLength(1);
    const shown = topbar!.querySelector('.ps-topbar__title [aria-hidden="true"]');
    expect(shown?.textContent).toBe(h1[0].textContent);
  });

  it("live · TA 在家（在家分支）：左上角同样回地图首页", async () => {
    mode.dataMode = "live";
    const base = fixtureHomeSnapshot();
    const home = { ...base, presence: "at_home", journey: null, pet: { ...base.pet, pet_id: "pet-a", name: "奶茶" } } as HomeSnapshot;
    const pending = () => new Promise<never>(() => undefined);
    const transport = new Proxy({}, { get: (_t, prop) => (prop === "then" ? undefined : prop === "fixtureScenarios" ? () => [] : pending) });
    renderPage(<JourneyPage />, "/journey", { households: { list: async () => [brief] }, world: { home: async () => home }, transport }, { userId: "owner-1" });
    expect(await screen.findByText("出不出门由 TA 决定")).toBeTruthy();
    expect(screen.queryByTestId("journey-map")).toBeNull();
    expect(backControls().map((el) => el.getAttribute("href"))).toEqual(["/map"]);
  });
});

/* ---------------- 2. 不再有散落的 "/home" ---------------- */

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

type Hit = { file: string; line: number; text: string; lineText: string; api: boolean };

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    return /\.tsx?$/.test(entry.name) ? [full] : [];
  });
}

/** 路由 /home 本身或带查询、锚点、子路径；"/homes/…" 是邻居家，不算。 */
const HOME_ROUTE = /^\/home(?=$|[?#/])/;

/** 接口路径不是路由：api.request("/home…") 的第一个参数，或契约表 generated.ts 里的 path: "/home…"。 */
function isApiPath(node: ts.Node, file: string): boolean {
  const parent = node.parent;
  if (ts.isCallExpression(parent) && parent.arguments[0] === node) {
    const callee = parent.expression;
    return ts.isPropertyAccessExpression(callee) && callee.name.text === "request";
  }
  return file === "src/shared/contracts/generated.ts" && ts.isPropertyAssignment(parent) && parent.initializer === node && ts.isIdentifier(parent.name) && parent.name.text === "path";
}

/** 用语法树找字面量：注释不算，字符串、模板字符串（取 ${} 之前那段）、JSX 属性都算。 */
function homeLiterals(full: string): Hit[] {
  const code = readFileSync(full, "utf8");
  const file = relative(ROOT, full).split(sep).join("/");
  const source = ts.createSourceFile(full, code, ts.ScriptTarget.Latest, true, full.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const lines = code.split(/\r?\n/);
  const hits: Hit[] = [];
  const visit = (node: ts.Node) => {
    const text = ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) ? node.text : ts.isTemplateExpression(node) ? node.head.text : null;
    if (text !== null && HOME_ROUTE.test(text)) {
      const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line;
      hits.push({ file, line: line + 1, text, lineText: lines[line] ?? "", api: isApiPath(node, file) });
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return hits;
}

/** 允许留下的 "/home" 路由：每条写理由。mustExist 的两条是逐行点名的例外，用法没了就该删掉白名单。 */
const ALLOWED: Array<{ why: string; match: (hit: Hit) => boolean; mustExist?: boolean }> = [
  { why: "地图进小窝的入口（/home?from=map）", match: (h) => h.file.startsWith("src/features/world_map/") && h.text === "/home?from=map" },
  { why: "小窝自身（src/features/home/**）", match: (h) => h.file.startsWith("src/features/home/") },
  {
    why: "入住成功的“到家时刻”：第一次进小窝、带 arrival 状态，有意保留",
    match: (h) => h.file === "src/features/identity/pages.tsx" && h.text === "/home" && h.lineText.includes("arrival"),
    mustExist: true,
  },
  {
    why: "“我们的家 · 住在这里”的“回家看看 →”：去小窝的正向入口，不是返回；小窝左上角自己回地图",
    match: (h) => h.file === "src/features/household/HouseholdPage.tsx" && h.text === "/home" && h.lineText.includes("回家看看"),
    mustExist: true,
  },
];

describe("不再有散落的 \"/home\" 路由字面量（静态扫描 src 下 .ts/.tsx）", () => {
  const files = sourceFiles(join(ROOT, "src"));
  const hits = files.flatMap(homeLiterals);

  it("前提：扫到了源码，也认得出接口路径（否则“0 条”什么都不说明）", () => {
    expect(files.length).toBeGreaterThan(100);
    const api = hits.filter((h) => h.api).map((h) => `${h.file} ${h.text}`);
    expect(api).toEqual(expect.arrayContaining(["src/features/home/service.ts /home", "src/features/identity/module.tsx /home/place", "src/shared/contracts/generated.ts /home"]));
  });

  it("\"/home\" 路由字面量只剩白名单里的", () => {
    const stray = hits.filter((h) => !h.api && !ALLOWED.some((allowed) => allowed.match(h)));
    expect(stray.map((h) => `${h.file}:${h.line} ${h.text}`)).toEqual([]);
  });

  it("逐行点名的白名单确实还有对应用法（白名单不留空条目）", () => {
    for (const allowed of ALLOWED.filter((a) => a.mustExist)) {
      expect(hits.some((h) => !h.api && allowed.match(h)), allowed.why).toBe(true);
    }
  });
});

/* ---------------- 3. 不靠顶栏的出口 ---------------- */

describe("接待：补充叮嘱回“我的”，演示模式的入住接待回地图首页，入住中照旧", () => {
  // 2026-09-24：“先回去”改成和左上角返回同一条规矩（站内有来路就回来路，直接打开时回上级页）。
  // 这一条钉“直接打开”：没有站内上一页，两个出口都去上级页“我的”。补充时要读当前宠物，所以给家庭列表。
  it("live · 已入住后来补充、直接打开（没有站内上一页）：左上角回“我的”；“先回去”（返回箭头）也回上级页“我的”", async () => {
    mode.dataMode = "live";
    const skip = vi.fn(async () => receptionSession([]));
    renderPage(<ReceptionPage />, "/onboarding/reception?mode=supplement", {
      session: { current: async () => signedIn("active") },
      households: { list: async () => [brief] },
      pets: { publicProfile: async () => profile },
      reception: { start: async () => receptionSession([]), get: async () => receptionSession([]), skip },
      world: { home: vi.fn() },
    });
    const dock = await screen.findByRole("group", { name: "补充叮嘱的下一步" });
    expect(backControls().map((el) => el.getAttribute("href"))).toEqual(["/me"]);
    const leave = within(dock).getByRole("button", { name: "先回去" });
    expect(iconOf(leave)).toBe(iconPath("back"));
    fireEvent.click(leave);
    await waitFor(() => expect(skip).toHaveBeenCalledWith("rs-1"));
    await waitFor(() => expect(landedAt()).toBe("/me"));
  });

  it("fixture · 入住接待（不是补充）：左上角照旧回 /onboarding；“先去地图看看”（地图图钉）回地图首页", async () => {
    const skip = vi.fn(async () => receptionSession([]));
    renderPage(<ReceptionPage />, "/onboarding/reception", {
      session: { current: async () => fixtureSession },
      pets: { publicProfile: async () => profile },
      reception: { start: async () => receptionSession([]), get: async () => receptionSession([]), skip },
      world: { home: async () => fixtureHomeSnapshot() },
    });
    const dock = await screen.findByRole("group", { name: "接待的下一步" });
    expect(backControls().map((el) => el.getAttribute("href"))).toEqual(["/onboarding"]);
    const toMap = within(dock).getByRole("button", { name: "先去地图看看" });
    expect(iconOf(toMap)).toBe(iconPath("pin"));
    fireEvent.click(toMap);
    await waitFor(() => expect(landedAt()).toBe("/map"));
  });

  it("live · 入住中（不是补充）：主按钮文字和房子图标都照旧", async () => {
    mode.dataMode = "live";
    renderPage(<ReceptionPage />, "/onboarding/reception", {
      session: { current: async () => signedIn("reception_optional") },
      pets: { publicProfile: async () => profile },
      reception: { start: async () => receptionSession([]), get: async () => receptionSession([]), skip: vi.fn() },
      world: { home: vi.fn() },
    });
    const dock = await screen.findByRole("group", { name: "接待的下一步" });
    expect(iconOf(within(dock).getByRole("button", { name: "先带 奶茶 去入住" }))).toBe(iconPath("home"));
  });

  // 这一条钉“站内有来路”：从通讯器进来的补充，“先回去”退回通讯器（不再写死去“我的”），也不去演示模式的地图首页；
  // 左上角返回的链接地址仍是上级页“我的”（点它同样退回来路，由 TopBar 自己的测试钉着）。
  it("fixture · 从通讯器进来的补充（?mode=supplement，站内有来路）：“先回去”（返回箭头）退回通讯器", async () => {
    const skip = vi.fn(async () => receptionSession([]));
    renderPage(<ReceptionPage />, "/onboarding/reception?mode=supplement", {
      session: { current: async () => fixtureSession },
      pets: { publicProfile: async () => profile },
      reception: { start: async () => receptionSession([]), get: async () => receptionSession([]), skip },
      world: { home: async () => fixtureHomeSnapshot() },
    }, { from: "/communicator" });
    const dock = await screen.findByRole("group", { name: "补充叮嘱的下一步" });
    expect(backControls().map((el) => el.getAttribute("href"))).toEqual(["/me"]);
    const leave = within(dock).getByRole("button", { name: "先回去" });
    expect(iconOf(leave)).toBe(iconPath("back"));
    fireEvent.click(leave);
    await waitFor(() => expect(landedAt()).toBe("/communicator"));
  });

  // 有待整理的叮嘱时，“整理”是主按钮，旁边的次要按钮同样按去向写字；live 入住中的“跳过，直接去入住（以后还能补充）”由 entry-flow 测试钉着。
  it.each([
    ["live", "先回去（以后还能补充）", "/me", "/onboarding/reception?mode=supplement", "补充叮嘱的下一步"],
    ["fixture", "先去地图看看（以后还能补充）", "/map", "/onboarding/reception", "接待的下一步"],
  ] as const)("%s · 有待整理的叮嘱时，次要按钮“%s”去 %s", async (dataMode, label, expected, entry, dockName) => {
    mode.dataMode = dataMode;
    const skip = vi.fn(async () => receptionSession([candidate]));
    renderPage(<ReceptionPage />, entry, {
      session: { current: async () => (dataMode === "live" ? signedIn("active") : fixtureSession) },
      households: { list: async () => [brief] },
      pets: { publicProfile: async () => profile },
      reception: { start: async () => receptionSession([candidate]), get: async () => receptionSession([candidate]), skip },
      world: { home: async () => fixtureHomeSnapshot() },
    });
    const dock = await screen.findByRole("group", { name: dockName });
    expect(within(dock).getAllByRole("button").map((button) => button.textContent)).toEqual(["整理这 1 条叮嘱", label]);
    fireEvent.click(within(dock).getByRole("button", { name: label }));
    await waitFor(() => expect(landedAt()).toBe(expected));
  });
});

describe("入住叮嘱：同一套规则", () => {
  it("live · 已入住后来补充、一句都没说：“先回去”（返回箭头）回“我的”", async () => {
    mode.dataMode = "live";
    const skip = vi.fn(async () => receptionSession([]));
    renderPage(<CareNotesPage />, "/onboarding/notes?session=rs-1", {
      session: { current: async () => signedIn("active") },
      reception: { get: async () => receptionSession([]), skip },
    });
    const leave = await screen.findByRole("button", { name: "先回去" });
    expect(iconOf(leave)).toBe(iconPath("back"));
    fireEvent.click(leave);
    await waitFor(() => expect(skip).toHaveBeenCalledWith("rs-1"));
    await waitFor(() => expect(landedAt()).toBe("/me"));
  });

  it("fixture · 一句都没说：“先去地图看看”（地图图钉）回地图首页", async () => {
    const skip = vi.fn(async () => receptionSession([]));
    renderPage(<CareNotesPage />, "/onboarding/notes?session=rs-1", {
      session: { current: async () => fixtureSession },
      reception: { get: async () => receptionSession([]), skip },
    });
    const toMap = await screen.findByRole("button", { name: "先去地图看看" });
    expect(iconOf(toMap)).toBe(iconPath("pin"));
    fireEvent.click(toMap);
    await waitFor(() => expect(skip).toHaveBeenCalledWith("rs-1"));
    await waitFor(() => expect(landedAt()).toBe("/map"));
  });

  it("live · 入住中一句都没说：“先去入住”和房子图标都照旧", async () => {
    mode.dataMode = "live";
    renderPage(<CareNotesPage />, "/onboarding/notes?session=rs-1", {
      session: { current: async () => signedIn("reception_optional") },
      reception: { get: async () => receptionSession([]), skip: vi.fn() },
    });
    expect(iconOf(await screen.findByRole("button", { name: "先去入住" }))).toBe(iconPath("home"));
  });

  it("fixture · 有待确认的便笺：“先去地图看看”回地图首页", async () => {
    renderPage(<CareNotesPage />, "/onboarding/notes?session=rs-1", {
      session: { current: async () => fixtureSession },
      reception: { get: async () => receptionSession([candidate]) },
    });
    fireEvent.click(await screen.findByRole("button", { name: "先去地图看看" }));
    await waitFor(() => expect(landedAt()).toBe("/map"));
  });

  // 入住中（保存后进入 ready_to_move_in）的去向由 claude-6c2b-entry-flow.test.tsx 钉着：“带 TA 去新家”→ /onboarding/move-in。
  it.each([
    ["live", "完成", "/me"],
    ["fixture", "回地图", "/map"],
  ] as const)("%s · 已入住状态下存好叮嘱：“%s”去 %s", async (dataMode, label, expected) => {
    mode.dataMode = dataMode;
    const result = {
      confirmation_id: "cf-1",
      session_id: "rs-1",
      draft_revision: 1,
      persist_state: "persisted",
      notes: [],
      grants: [],
      onboarding: onboardingAt("active"),
      data_origin: dataMode,
    } as IntakeConfirmationResult;
    const confirm = vi.fn(async () => result);
    renderPage(<CareNotesPage />, "/onboarding/notes?session=rs-1", {
      session: { current: async () => (dataMode === "live" ? signedIn("active") : fixtureSession) },
      reception: { get: async () => receptionSession([candidate]), confirm },
    });
    fireEvent.click(await screen.findByRole("radio", { name: "只留在这里" }));
    fireEvent.click(screen.getByRole("button", { name: "这样记就对了" }));
    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
    expect((await screen.findByRole("link", { name: label })).getAttribute("href")).toBe(expected);
    // 补充的入口在“我的”，不再说“在家里补充”。
    expect(document.querySelector(".ps-notes-saved p")?.textContent).toBe("交给 TA 0 条 · 只留在这里 0 条。以后还能在“我的”里补充。");
  });

  // 契约允许 persist_state = failed，但目前后端只回 persisted（PetJourneyBackend/app/reception/store.py:223），
  // 演示的保存失败是直接报错（显示另一张“保存没有成功”卡片），所以这个分支今天走不到。
  // 这里直接喂 failed，只为钉住“失败说明与按钮同一套条件”，不代表现实里会出现这个组合。
  it.each([
    ["live", "active", "完成", "/me", "先回“我的”"],
    ["fixture", "active", "回地图", "/map", "先回地图"],
    ["live", "ready_to_move_in", "带 TA 去新家", "/onboarding/move-in", "先去入住"],
  ] as const)("%s · %s · 没写进去：按钮“%s”去 %s，说明写“或%s”", async (dataMode, step, label, expected, tail) => {
    mode.dataMode = dataMode;
    const result = {
      confirmation_id: "cf-2",
      session_id: "rs-1",
      draft_revision: 1,
      persist_state: "failed",
      notes: [],
      grants: [],
      onboarding: onboardingAt(step),
      data_origin: dataMode,
    } as IntakeConfirmationResult;
    const confirm = vi.fn(async () => result);
    renderPage(<CareNotesPage />, "/onboarding/notes?session=rs-1", {
      session: { current: async () => (dataMode === "live" ? signedIn(step === "active" ? "active" : "reception_optional") : fixtureSession) },
      reception: { get: async () => receptionSession([candidate]), confirm },
    });
    fireEvent.click(await screen.findByRole("radio", { name: "只留在这里" }));
    fireEvent.click(screen.getByRole("button", { name: "这样记就对了" }));
    expect(await screen.findByRole("heading", { name: "这次没有保存成功" })).toBeTruthy();
    expect(screen.getByRole("link", { name: label }).getAttribute("href")).toBe(expected);
    expect(document.querySelector(".ps-notes-saved p")?.textContent).toBe(`便笺没有写进去。可以回到接待再试一次，或${tail}。`);
  });
});

describe("入住与邀请的落点：地图首页（小窝只在第一次入住的“到家时刻”进）", () => {
  it("fixture · 入住页：演示世界视为已入住，直接去地图首页", async () => {
    renderPage(<MoveInPage />, "/onboarding/move-in", {
      session: { current: async () => fixtureSession, homePlace: vi.fn(), moveIn: vi.fn() },
      pets: { publicProfile: vi.fn() },
    });
    await waitFor(() => expect(landedAt()).toBe("/map"));
  });

  it.each([
    ["active", "/map"],
    ["reception_optional", "/onboarding/reception"],
    ["ready_to_move_in", "/onboarding/move-in"],
  ] as const)("live · 领养选择页已不在“挑伙伴”这一步（%s）：按入住阶段去 %s", async (step, expected) => {
    mode.dataMode = "live";
    renderPage(<PendingEntryPage />, "/onboarding/choice", {
      session: { current: async () => signedIn(step) },
      pets: { publicPet: vi.fn(), adopt: vi.fn() },
    });
    await waitFor(() => expect(landedAt()).toBe(expected));
  });

  it("live · 确认加入家人的家：去地图首页", async () => {
    mode.dataMode = "live";
    const invite: InvitePreview = {
      invite_id: "inv-1",
      status: "pending",
      role: "caregiver",
      relation_hint: null,
      expires_at: "2026-09-30T00:00:00Z",
      household_name: "海边的家",
      inviter_name: "小林",
      pet_names: ["奶茶"],
      already_member: false,
    };
    const acceptInvite = vi.fn(async () => ({}) as HouseholdDetail);
    renderPage(<JoinPage />, "/join?invite=tok-0123456789abcdef", {
      households: { previewInvite: async () => invite, acceptInvite },
      session: { current: async () => signedIn("active") },
    });
    fireEvent.click(await screen.findByRole("button", { name: "我想加入这个家" }));
    fireEvent.click(screen.getByRole("button", { name: "确认加入" }));
    await waitFor(() => expect(acceptInvite).toHaveBeenCalledWith("tok-0123456789abcdef"));
    await waitFor(() => expect(landedAt()).toBe("/map"));
  });
});

describe("我们的家：返回“我的”；称呼上限与后端一致；保存后 TA 的档案一起失效", () => {
  const detail: HouseholdDetail = {
    household: brief,
    members: [{ user_id: "owner-1", display_name: "小林", role: "admin", joined_at: "2026-09-20T00:00:00Z", is_you: true }],
    settings: { name: "海边的家", caregivers_can_spend: false, generated_photos: false, pet_messages: true, public_posts: false },
    your_permissions: ["view", "care", "spend", "manage"],
    version: 1,
  };
  const relationship: PetRelationship = { pet_id: "pet-a", owner_title: "妈妈", relation_label: null, updated_at: null };

  it("live · 管理员", async () => {
    mode.dataMode = "live";
    const saveRelationship = vi.fn(async (_petId: string, body: PetRelationshipRequestInput) => ({ ...relationship, ...body }));
    const { client } = renderPage(<HouseholdPage />, "/households/manage", {
      households: { list: async () => [brief], detail: async () => detail, invites: async () => [], relationship: async () => relationship, saveRelationship },
    }, { userId: "owner-1" });
    // “TA 的档案”（/me/dna）先前读过一份：保存称呼后它必须失效（两边是同一份称呼）。
    const dnaKey = queryKeys.dnaFor("owner-1", "pet-a");
    client.setQueryData(dnaKey, { pet_id: "pet-a" });

    const ownerTitle = (await screen.findByLabelText("TA 对你的称呼")) as HTMLInputElement;
    expect(backControls().map((el) => el.getAttribute("href"))).toEqual(["/me"]);
    // 后端 PetRelationshipRequest.owner_title / relation_label 与 InviteCreateRequest.relation_hint 都是 max_length=12。
    expect(ownerTitle.maxLength).toBe(12);
    expect((screen.getByLabelText("你们的关系") as HTMLInputElement).maxLength).toBe(12);
    expect((screen.getByLabelText("给家人的称呼提示") as HTMLInputElement).maxLength).toBe(12);

    await waitFor(() => expect(ownerTitle.value).toBe("妈妈"));
    expect(client.getQueryState(dnaKey)?.isInvalidated).toBe(false);
    fireEvent.change(ownerTitle, { target: { value: "姐姐" } });
    fireEvent.click(screen.getByRole("button", { name: "保存称呼" }));
    expect(await screen.findByText("称呼已保存，只用于你与 TA 的关系。")).toBeTruthy();
    expect(saveRelationship).toHaveBeenCalledWith("pet-a", { owner_title: "姐姐", relation_label: null });
    await waitFor(() => expect(client.getQueryState(dnaKey)?.isInvalidated).toBe(true));
  });
});
