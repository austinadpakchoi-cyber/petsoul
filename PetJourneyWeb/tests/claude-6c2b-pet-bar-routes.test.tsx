/**
 * claude-6c2b · 切换栏只在按宠物区分的页面出现（主窗口 2026-09-24，I 放行 householdContext.tsx / .css）。
 * - 显式清单：真实路由表里的每一条都必须归到 bar / capsule / household / none 之一，漏归类、归了两类、清单里有已不存在的路由都红；
 *   而且按清单里的样子运行时判出来的也是同一类（防两类的写法互相吞）。
 * - 设置、邻居家、朋友圈、公告不显示；地图只有宠物分在不止一个家时，才有一个只切家、不切宠物的小控件；
 *   小窝、菜园是浮在场景上方的小胶囊（零高度锚点，不把场景往下推）。
 * - 没起名的家叫“{第一只已入住宠物}的家”，家里还没有已入住的宠物才叫“家庭 N”。
 * - 每个按钮至少 40px 高、窄屏能横向滑到每一只：jsdom 不排版，这里钉住样式表里的声明；真浏览器的尺寸与可点到另有走查。
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, MemoryRouter, Route, RouterProvider, Routes, type RouteObject } from "react-router";
import type { HouseholdBrief, HouseholdDetail, HouseholdPetBrief } from "@/shared/contracts";
import { HouseholdPage } from "@/features/household/HouseholdPage";
import { loadFeatureModules } from "@/app/modules";
import { ApiError } from "@/shared/api/errors";
import { ErrorState } from "@/shared/ui";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { HouseholdProvider, householdLabel, householdLabels, PET_BAR_ROUTES, petBarModeFor, useCurrentHousehold, type PetBarMode } from "@/shared/session/householdContext";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "live", isDev: false, apiBase: "/api/v1/web" } }));

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

/** 与 app/router.tsx 的 collectPaths 同一套拼法：父子路径相接、index 取父路径。 */
function registeredPaths(): string[] {
  const out: string[] = [];
  const walk = (routes: RouteObject[], prefix = "") => {
    for (const route of routes) {
      const path = route.index ? prefix || "/" : route.path ? `${prefix}/${route.path}`.replace(/\/+/g, "/") : prefix;
      if (route.path || route.index) out.push(path);
      if (route.children) walk(route.children, path);
    }
  };
  for (const module of loadFeatureModules()) {
    walk(module.routes ?? []);
    walk(module.bareRoutes ?? []);
  }
  return out;
}

const MODES = Object.keys(PET_BAR_ROUTES) as PetBarMode[];
const declaredModes = (path: string) => MODES.filter((mode) => PET_BAR_ROUTES[mode].includes(path));
const sample = (pattern: string) => pattern.replace(/:[^/]+/g, "x-1");

describe("切换栏的显式清单", () => {
  const paths = registeredPaths();

  it("路由表不是空的（真实模块都加载到了）", () => {
    expect(paths.length).toBeGreaterThan(40);
    expect(paths).toEqual(expect.arrayContaining(["/map", "/home", "/garden", "/settings", "/circle", "/announcements", "/homes/:homeId"]));
  });

  it("每条已注册的路由都归了类，而且只归一类", () => {
    const unclassified = paths.filter((path) => declaredModes(path).length === 0);
    const doubled = paths.filter((path) => declaredModes(path).length > 1);
    expect({ unclassified, doubled }).toEqual({ unclassified: [], doubled: [] });
  });

  it("清单里没有已经不存在的路由", () => {
    const listed = MODES.flatMap((mode) => PET_BAR_ROUTES[mode]);
    expect(listed.filter((path) => !paths.includes(path))).toEqual([]);
  });

  it("运行时按路径判出来的，就是清单里写的那一类", () => {
    const mismatched = paths
      .map((path) => ({ path, declared: declaredModes(path)[0], runtime: petBarModeFor(sample(path)) }))
      .filter(({ declared, runtime }) => declared !== runtime);
    expect(mismatched).toEqual([]);
  });

  it.each([
    ["/settings", "none"], ["/homes/h-2", "none"], ["/neighbors", "none"], ["/circle", "none"], ["/announcements", "none"],
    ["/map", "household"], ["/home", "capsule"], ["/garden", "capsule"],
    ["/memories", "bar"], ["/households/manage", "bar"], ["/credentials/c-1", "bar"],
    ["/", "none"], ["/no-such-page", "none"],
  ] as const)("%s → %s", (path, mode) => expect(petBarModeFor(path)).toBe(mode));
});

const pet = (pet_id: string, name: string, join_step = "moved_in") =>
  ({ pet_id, name, species: "cat", photo_url: null, origin: "own_pet", presence: "at_home", join_step, joined_at: "2026-09-20T00:00:00Z", added_by_you: true }) as unknown as HouseholdPetBrief;
const household = (household_id: string, name: string | null, pets: HouseholdPetBrief[]) =>
  ({ household_id, name, role: "admin", home_activated: true, home_id: `home-${household_id}`, member_count: 1, pets }) as unknown as HouseholdBrief;

describe("家的称呼", () => {
  it("起了名就用名字（去掉首尾空白）", () => expect(householdLabel(household("h-1", "  海边的家 ", [pet("p-1", "奶茶")]), 0)).toBe("海边的家"));
  it("没起名：第一只已入住宠物的名字＋的家（还在入住中的不算）", () => {
    expect(householdLabel(household("h-1", null, [pet("p-0", "新来的", "reception"), pet("p-1", "栗子"), pet("p-2", "豆包")]), 0)).toBe("栗子的家");
    expect(householdLabel(household("h-1", "   ", [pet("p-1", "奶茶")]), 3)).toBe("奶茶的家");
  });
  it("同一个人的几个家叫出来撞了：撞名的都带上序号（与“家庭 N”同一套顺序），不撞的照旧", () => {
    const labels = householdLabels([
      household("h-1", null, [pet("p-1", "奶茶")]),
      household("h-2", null, [pet("p-2", "栗子")]),
      household("h-3", null, [pet("p-3", "奶茶")]),
      household("h-4", "海边的家", []),
      household("h-5", " 海边的家", []),
    ]);
    expect([...labels.values()]).toEqual(["奶茶的家（1）", "栗子的家", "奶茶的家（3）", "海边的家（4）", "海边的家（5）"]);
  });
  it("家里还没有已入住的宠物：按顺序叫“家庭 N”", () => {
    expect(householdLabel(household("h-1", null, []), 0)).toBe("家庭 1");
    expect(householdLabel(household("h-2", null, [pet("p-9", "路上的", "reception")]), 1)).toBe("家庭 2");
  });
});

function CurrentPet() {
  const { pet: current, household: home } = useCurrentHousehold();
  return <p data-testid="current">{current?.name}@{home?.household_id}</p>;
}

function renderAt(path: string, households: HouseholdBrief[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const services = { households: { list: async () => households } } as unknown as ServiceMap;
  const router = createMemoryRouter([{ path: "*", element: <HouseholdProvider userId="u-1"><CurrentPet /></HouseholdProvider> }], { initialEntries: [path] });
  const view = render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { router, container: view.container };
}

const oneHome = [household("h-1", null, [pet("p-1", "奶茶"), pet("p-2", "豆豆")])];
const twoHomes = [household("h-1", null, [pet("p-1", "奶茶")]), household("h-2", null, [pet("p-3", "栗子")])];

describe("切换栏出现在哪儿、长什么样", () => {
  it("按宠物区分的页面：一条切换栏；没起名的家显示“奶茶的家”，按钮说出是哪个家", async () => {
    renderAt("/memories", oneHome);
    const group = await screen.findByRole("group", { name: "切换当前宠物" });
    expect(within(group).getAllByRole("button")).toHaveLength(2);
    expect(within(group).getByRole("button", { name: "查看 豆豆，奶茶的家" })).toBeTruthy();
    expect(screen.getByText("奶茶的家")).toBeTruthy();
    expect(screen.queryByText("我们的家")).toBeNull();
  });

  it.each(["/settings", "/homes/h-9", "/circle", "/announcements", "/neighbors"])("%s 不显示", async (path) => {
    renderAt(path, oneHome);
    expect((await screen.findByTestId("current")).textContent).toBe("奶茶@h-1");
    expect(screen.queryByRole("group", { name: "切换当前宠物" })).toBeNull();
    expect(screen.queryByRole("group", { name: "切换当前的家" })).toBeNull();
  });

  it("地图：宠物都在一个家里时什么都不显示（一个家的几只本来就画在同一张图上）", async () => {
    renderAt("/map", oneHome);
    expect((await screen.findByTestId("current")).textContent).toBe("奶茶@h-1");
    expect(screen.queryByRole("group", { name: "切换当前宠物" })).toBeNull();
    expect(screen.queryByRole("group", { name: "切换当前的家" })).toBeNull();
  });

  it("地图：宠物分在两个家时，出现只切家的小控件（没有按宠物的按钮）；点另一个家就换到那个家", async () => {
    renderAt("/map", twoHomes);
    const group = await screen.findByRole("group", { name: "切换当前的家" });
    const buttons = within(group).getAllByRole("button");
    expect(buttons.map((button) => button.textContent)).toEqual(["奶茶的家", "栗子的家"]);
    expect(buttons.map((button) => button.getAttribute("aria-pressed"))).toEqual(["true", "false"]);
    expect(screen.queryByRole("group", { name: "切换当前宠物" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^查看 / })).toBeNull();

    fireEvent.click(buttons[1]);
    await waitFor(() => expect(screen.getByTestId("current").textContent).toBe("栗子@h-2"));
    expect(within(screen.getByRole("group", { name: "切换当前的家" })).getAllByRole("button").map((button) => button.getAttribute("aria-pressed"))).toEqual(["false", "true"]);
    expect(sessionStorage.getItem("petsoul:current-pet:u-1")).toBe("p-3");
  });

  it.each([["/home", "home"], ["/garden", "garden"]])("%s：浮在场景上方的小胶囊（挂在零高度锚点里），不是整条栏", async (path, placement) => {
    const { container } = renderAt(path, oneHome);
    const group = await screen.findByRole("group", { name: "切换当前宠物" });
    const capsule = group.closest(".ps-current-pet-bar");
    expect(capsule?.classList.contains("ps-current-pet-bar--capsule")).toBe(true);
    expect(capsule?.parentElement?.className).toBe(`ps-pet-capsule-anchor ps-pet-capsule-anchor--${placement}`);
    expect(container.querySelector(".ps-current-pet-bar:not(.ps-current-pet-bar--capsule)")).toBeNull();
    fireEvent.click(within(group).getByRole("button", { name: /^查看 豆豆/ }));
    await waitFor(() => expect(screen.getByTestId("current").textContent).toBe("豆豆@h-1"));
  });

  it("只有一只已入住的宠物时，按宠物区分的页面上也不显示", async () => {
    renderAt("/memories", [household("h-1", null, [pet("p-1", "奶茶"), pet("p-2", "还在接待", "reception")])]);
    expect((await screen.findByTestId("current")).textContent).toBe("奶茶@h-1");
    expect(screen.queryByRole("group", { name: "切换当前宠物" })).toBeNull();
  });
});

describe("样式表里的触控尺寸与窄屏滑动（jsdom 不排版，钉声明）", () => {
  const css = readFileSync(join(process.cwd(), "src/shared/session/householdContext.css"), "utf8");
  const rule = (selector: string) => {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const match = css.match(new RegExp(`(^|\\n)${escaped}\\s*\\{([^}]*)\\}`));
    if (!match) throw new Error(`样式表里没有 ${selector}`);
    return match[2];
  };
  const px = (body: string, prop: string) => Number(body.match(new RegExp(`(^|[;\\s])${prop}:\\s*(\\d+)px`))?.[2] ?? NaN);

  it.each([".ps-current-pet-bar button", ".ps-current-pet-bar--capsule button", ".ps-household-switch button"])("%s 至少 40px 高", (selector) => {
    expect(px(rule(selector), "min-height")).toBeGreaterThanOrEqual(40);
  });

  it("切换栏的按钮组可以横向滑（窄屏上第三只也点得到）", () => {
    expect(rule(".ps-current-pet-bar > div")).toMatch(/overflow-x:\s*auto/);
    expect(rule(".ps-current-pet-bar > div")).toMatch(/min-width:\s*0/);
  });

  it("胶囊的锚点零高度、胶囊绝对定位：不把场景往下推", () => {
    expect(rule(".ps-pet-capsule-anchor")).toMatch(/height:\s*0;/);
    expect(rule(".ps-current-pet-bar--capsule")).toMatch(/position:\s*absolute/);
  });
});

describe("household_required 说人话（后端原话、错误码与原因码收进“技术信息”）", () => {
  const MESSAGE = "你在不止一个家庭里，请指明是哪一个（household_id）。";
  it("正文是人话；技术信息里有 CONFLICT、household_required 与后端原话；正文不露参数名", () => {
    render(<ErrorState error={new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: MESSAGE, details: { reason: "household_required" } })} onRetry={() => undefined} />);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("你在不止一个家里，先选好是哪一个家再看。");
    const tech = alert.querySelector("details");
    expect(tech?.textContent).toContain("CONFLICT");
    expect(tech?.textContent).toContain("household_required");
    expect(tech?.textContent).toContain(MESSAGE);
    const outside = [...alert.childNodes].filter((node) => node !== tech).map((node) => node.textContent).join("");
    expect(outside).not.toMatch(/household_id|household_required|请指明/);
  });
});

describe("第二批 1：地图切家控件重挂时，把选中的那个家滚进来（与宠物栏同一个做法；jsdom 不排版，钉调用，320 宽的实际效果在真浏览器量）", () => {
  it("选的是第二个家：控件挂上时对按下的那一颗 scrollIntoView（nearest，不动页面纵向）；离开地图再回来重挂，再滚一次", async () => {
    const scrolled: Array<{ text: string | null; options: unknown }> = [];
    const proto = HTMLElement.prototype as unknown as { scrollIntoView?: (options?: unknown) => void };
    const original = proto.scrollIntoView;
    proto.scrollIntoView = function (this: HTMLElement, options?: unknown) { scrolled.push({ text: this.textContent, options }); };
    try {
      sessionStorage.setItem("petsoul:current-pet:u-1", "p-3");
      const { router } = renderAt("/map", twoHomes);
      const group = await screen.findByRole("group", { name: "切换当前的家" });
      expect(within(group).getAllByRole("button").map((button) => button.getAttribute("aria-pressed"))).toEqual(["false", "true"]);
      await waitFor(() => expect(scrolled).toEqual([{ text: "栗子的家", options: { block: "nearest", inline: "nearest" } }]));

      await act(async () => { await router.navigate("/settings"); });
      expect(screen.queryByRole("group", { name: "切换当前的家" })).toBeNull();
      await act(async () => { await router.navigate("/map"); });
      await screen.findByRole("group", { name: "切换当前的家" });
      await waitFor(() => expect(scrolled.map((item) => item.text)).toEqual(["栗子的家", "栗子的家"]));
    } finally {
      if (original) proto.scrollIntoView = original; else delete proto.scrollIntoView;
    }
  });
});

describe("第二批 2：“我们的家”没起名时，大标题与切换栏同一套说法", () => {
  const detailOf = (brief: HouseholdBrief): HouseholdDetail => ({
    household: brief,
    members: [{ user_id: "u-1", display_name: "小林", role: "admin", joined_at: "2026-09-20T00:00:00Z", is_you: true }],
    settings: { name: brief.name, caregivers_can_spend: false, generated_photos: false, pet_messages: true, public_posts: false },
    your_permissions: ["view", "care", "spend", "manage"],
    version: 1,
  }) as unknown as HouseholdDetail;

  function renderFamily(list: HouseholdBrief[]) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const households = {
      list: async () => list,
      detail: async (id: string) => detailOf(list.find((item) => item.household_id === id)!),
      invites: async () => [],
      relationship: async (petId: string) => ({ pet_id: petId, owner_title: null, relation_label: null, updated_at: null }),
    };
    render(
      <QueryClientProvider client={client}>
        <ServicesProvider services={{ households } as unknown as ServiceMap}>
          <MemoryRouter initialEntries={["/households/manage"]}>
            <Routes>
              <Route path="/households/manage" element={<HouseholdProvider userId="u-1"><HouseholdPage /></HouseholdProvider>} />
            </Routes>
          </MemoryRouter>
        </ServicesProvider>
      </QueryClientProvider>,
    );
  }
  const heroTitle = async () => (await waitFor(() => {
    const title = document.querySelector(".ps-family-hero h1");
    if (!title) throw new Error("还没渲染出家庭档案");
    return title;
  })).textContent;

  it("没起名：大标题是“奶茶的家”（不再是笼统的“我们的家”），与切换栏左边那格一样；页名仍叫“我们的家”", async () => {
    renderFamily(oneHome);
    expect(await heroTitle()).toBe("奶茶的家");
    expect(screen.getByRole("group", { name: "切换当前宠物" }).closest(".ps-current-pet-bar")?.querySelector(":scope > span")?.textContent).toBe("奶茶的家");
    expect(screen.getAllByText("我们的家").length).toBeGreaterThan(0);
  });

  it("起了名：用名字", async () => {
    renderFamily([household("h-1", " 海边的家 ", [pet("p-1", "奶茶"), pet("p-2", "豆豆")])]);
    expect(await heroTitle()).toBe("海边的家");
  });

  it("两个家叫出来撞名（第一只都叫奶茶）：当前是第二个家时，大标题和切换栏都是“奶茶的家（2）”", async () => {
    sessionStorage.setItem("petsoul:current-pet:u-1", "p-3");
    renderFamily([household("h-1", null, [pet("p-1", "奶茶")]), household("h-2", null, [pet("p-3", "奶茶")])]);
    expect(await heroTitle()).toBe("奶茶的家（2）");
    expect(screen.getByRole("group", { name: "切换当前宠物" }).closest(".ps-current-pet-bar")?.querySelector(":scope > span")?.textContent).toBe("奶茶的家（2）");
  });
});
