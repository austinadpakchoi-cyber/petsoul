/**
 * claude-6c2b · 新版导航（用户 2026-09-24 采纳地图首页方案，旧四栏退役）：
 * “/” 进地图首页；深链一律按原路径打开，不被首页规则吞掉；底栏只剩“地图 · 通讯器 · 回忆”。
 */
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { ROUTE_ERROR_HINT, RouteErrorPage } from "@/app/RouteErrorPage";
import { buildServices, ServicesProvider } from "@/shared/services/registry";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "fixture", isDev: false, apiBase: "/api/v1/web" } }));

afterEach(() => cleanup());

const modules = loadFeatureModules();

function renderAppWithContainer(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const services = buildServices(modules, { mode: "fixture", api: createApiClient("/api/v1/web") });
  const router = createMemoryRouter(buildRoutes(modules), { initialEntries: [path] });
  const { container } = render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <RouterProvider router={router} />
      </ServicesProvider>
    </QueryClientProvider>,
  );
  return { router, container };
}

function renderApp(path: string) {
  return renderAppWithContainer(path).router;
}

describe("新版导航（fixture）", () => {
  it("“/” 进地图首页", async () => {
    const router = renderApp("/");
    await waitFor(() => expect(router.state.location.pathname).toBe("/map"));
  });

  // 会红的保护：以后谁把首页规则写宽（例如一律跳 /map），这些深链会被吞掉。
  it.each(["/map", "/communicator", "/memories", "/me", "/home", "/garden", "/journey", "/circle", "/world", "/life", "/collection", "/settings", "/guides", "/school"])(
    "深链 %s 按原路径打开",
    async (path) => {
      const router = renderApp(path);
      // 给重定向一个机会发生；深链不应被改写。
      await new Promise((resolve) => setTimeout(resolve, 30));
      expect(router.state.location.pathname).toBe(path);
    },
  );

  it("找不到的地址：“回到地图”回地图首页，不再回旧的 /home（按钮名和去处一致）", async () => {
    renderApp("/no-such-place");
    const back = await screen.findByRole("link", { name: "回到地图" });
    expect(back.getAttribute("href")).toBe("/map");
  });

  it("页面出错：“回到地图”回地图首页，不再回旧的 /home（按钮名和去处一致）", async () => {
    const quiet = vi.spyOn(console, "error").mockImplementation(() => undefined);
    function Boom(): never {
      throw new Error("测试用的页面错误");
    }
    const router = createMemoryRouter([{ path: "/", element: <Boom />, errorElement: <RouteErrorPage /> }], { initialEntries: ["/"] });
    render(<RouterProvider router={router} />);
    const back = await screen.findByRole("link", { name: "回到地图" });
    expect(back.getAttribute("href")).toBe("/map");
    quiet.mockRestore();
  });

  // 2026-09-24 巡检：崩溃页原来把 JS 报错原文直接写给玩家。现在只写一句人话，原文收进默认收起的“技术信息”。
  it("页面出错：玩家看到的是一句人话，报错原文只在收起的“技术信息”里", async () => {
    const quiet = vi.spyOn(console, "error").mockImplementation(() => undefined);
    function Boom(): never {
      throw new Error("Cannot read properties of undefined (reading 'pet_id')");
    }
    const router = createMemoryRouter([{ path: "/", element: <Boom />, errorElement: <RouteErrorPage /> }], { initialEntries: ["/"] });
    render(<RouterProvider router={router} />);
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(ROUTE_ERROR_HINT)).toBeTruthy();
    const raw = within(alert).getByText("Cannot read properties of undefined (reading 'pet_id')");
    const details = raw.closest("details");
    expect(details).toBeTruthy();
    expect(details?.open).toBe(false);
    expect(within(details as HTMLElement).getByText("技术信息").tagName).toBe("SUMMARY");
    quiet.mockRestore();
  });

  it("主布局底栏只剩“地图 · 通讯器 · 回忆”，旧的“家 / 旅途 / 星球”不再出现", async () => {
    renderApp("/communicator");
    const nav = await screen.findByRole("navigation", { name: "主导航" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((a) => a.textContent)).toEqual(["地图", "通讯器", "回忆"]);
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["/map", "/communicator", "/memories"]);
    expect(nav.textContent).not.toMatch(/家|旅途|星球/);
  });

  // 方案 2.2：二级页全屏、不显示底栏；底栏高度按 0 算（layout.css 的 .ps-shell--no-tabs）。
  it.each(["/circle", "/collection", "/garden", "/settings", "/guides", "/school", "/no-such-place"])("二级页 %s 不显示底栏", async (path) => {
    const { container } = renderAppWithContainer(path);
    await waitFor(() => expect(container.querySelector(".ps-shell")).toBeTruthy());
    expect(screen.queryByRole("navigation", { name: "主导航" })).toBeNull();
    expect(container.querySelector(".ps-shell")?.className).toContain("ps-shell--no-tabs");
  });

  // 全屏页（bareRoutes）：地图、回忆自带新版底栏，保留底栏高度；其余全屏页底栏高度按 0 算，不多留 64px 空白。
  it.each([
    ["/life", true],
    ["/me", true],
    ["/home", true],
    ["/map", false],
    ["/memories", false],
  ])("全屏页 %s 外壳 no-tabs = %s", async (path, noTabs) => {
    const { container } = renderAppWithContainer(path);
    await waitFor(() => expect(container.querySelector(".ps-shell--bare")).toBeTruthy());
    expect(container.querySelector(".ps-shell--bare")?.className.includes("ps-shell--no-tabs")).toBe(noTabs);
  });

  it("标签页（通讯器，含带参数的深链）照常显示底栏，外壳不带 no-tabs", async () => {
    const { container } = renderAppWithContainer("/communicator?channel=friends");
    expect(await screen.findByRole("navigation", { name: "主导航" })).toBeTruthy();
    expect(container.querySelector(".ps-shell")?.className).not.toContain("ps-shell--no-tabs");
  });
});

describe("底栏样式（layout.css）", () => {
  // 去掉注释再查：注释里提到旧写法不算。
  const css = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "..", "src", "app", "layout.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

  it("有几个标签就平分几列，不再写死四列（否则三栏底栏右边空四分之一）", () => {
    expect(css).not.toMatch(/repeat\(\s*4\s*,/);
    expect(css).toMatch(/grid-auto-flow:\s*column/);
    expect(css).toMatch(/grid-auto-columns:\s*minmax\(0,\s*1fr\)/);
  });

  it("二级页外壳把底栏高度按 0 算", () => {
    expect(css).toMatch(/\.ps-shell--no-tabs\s*\{[^}]*--tabbar-h:\s*0px/);
  });
});

/*
 * 外壳底栏 = 地图胶囊（用户 2026-09-25 同意改外壳底栏；驾校·页面分身）：
 * 通讯器等标签页的底栏（app/layout.css 的 .ps-tabbar）在视觉上要和地图、回忆页的胶囊（world_map/world-map.css 的 .ps-wmap-tabs）完全一样。
 * 两套组件合并前是两份样式，这里逐项比对（只读地图那份，不改它）；--tabbar-h 要等于胶囊占高；深色下的字实算对比度。
 */
describe("外壳底栏和地图胶囊一模一样", () => {
  const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  const read = (...parts: string[]) => readFileSync(resolve(ROOT, "src", ...parts), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const layout = read("app", "layout.css");
  const wmap = read("features", "world_map", "world-map.css");
  const rule = (text: string, selector: string): Map<string, string> => {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+");
    const m = text.match(new RegExp(`(?:^|\\})\\s*${escaped}\\s*\\{([^}]*)\\}`));
    if (!m) throw new Error(`找不到 ${selector}`);
    return new Map(
      m[1].split(";").map((d) => d.trim()).filter(Boolean).map((d) => {
        const i = d.indexOf(":");
        return [d.slice(0, i).trim(), d.slice(i + 1).trim().replace(/\s+/g, " ")] as [string, string];
      }),
    );
  };
  const iconSize = (file: string) => Number(readFileSync(resolve(ROOT, "src", file), "utf8").match(/<Icon name=\{tab\.icon\} size=\{(\d+)\} \/>/)?.[1]);

  it("胶囊本身：内边距、圆角、底色、阴影、最宽都照 .ps-wmap-tabs；有几个标签就平分几列", () => {
    const shell = rule(layout, ".ps-tabbar");
    const map = rule(wmap, ".ps-wmap-tabs");
    for (const prop of ["padding", "border-radius", "background", "box-shadow", "max-width"]) expect(shell.get(prop), `.ps-tabbar 的 ${prop}`).toBe(map.get(prop));
    expect(shell.get("grid-auto-flow")).toBe("column");
    expect(shell.get("grid-auto-columns")).toBe("minmax(0, 1fr)");
    // 旧的通栏写法不能留：顶边线、毛玻璃、按变量写死的高度
    for (const prop of ["border-top", "backdrop-filter", "height"]) expect(shell.has(prop), `.ps-tabbar 不该再有 ${prop}`).toBe(false);
  });

  it("位置：左右各 12px、离底 10px + 安全区、最宽居中——和地图外层 .ps-wmap-bottom 给胶囊留的一样", () => {
    const shell = rule(layout, ".ps-tabbar");
    const dock = rule(wmap, ".ps-wmap-bottom");
    const [, sides, bottom] = dock.get("padding")!.match(/^0 (\S+) (calc\(.*\))$/) ?? [];
    expect(sides, "地图外层的左右留白").toBe("12px");
    expect(shell.get("position")).toBe("fixed");
    expect(shell.get("left")).toBe(sides);
    expect(shell.get("right")).toBe(sides);
    expect(shell.get("bottom")).toBe(bottom);
    expect(shell.get("margin")).toBe("0 auto");
  });

  it("标签：内边距、圆角、字色、字号、图文间距、图标大小、选中态都照 .ps-wmap-tab", () => {
    const tab = rule(layout, ".ps-tab");
    const mapTab = rule(wmap, ".ps-wmap-tab");
    for (const prop of ["display", "flex-direction", "align-items", "gap", "padding", "border-radius", "color", "font-size", "text-decoration"]) expect(tab.get(prop), `.ps-tab 的 ${prop}`).toBe(mapTab.get(prop));
    // 未选中不加粗（地图那份没写字重）；也不再有旧的最小高度（地图那份靠内容撑高）
    expect(tab.has("font-weight")).toBe(mapTab.has("font-weight"));
    expect(tab.has("min-height")).toBe(mapTab.has("min-height"));
    const active = rule(layout, ".ps-tab.is-active");
    const mapActive = rule(wmap, ".ps-wmap-tab.is-active");
    for (const prop of ["background", "color", "font-weight"]) expect(active.get(prop), `选中态的 ${prop}`).toBe(mapActive.get(prop));
    expect(iconSize("app/RootLayout.tsx"), "图标大小").toBe(iconSize("features/world_map/PreviewTabBar.tsx"));
  });

  it("--tabbar-h 等于胶囊占高（胶囊 + 离底 10px）；用它的地方都另加安全区，合起来就是胶囊加离底加安全区", () => {
    const tabbar = rule(layout, ".ps-tabbar");
    const tab = rule(layout, ".ps-tab");
    const px = (v: string | undefined) => Number(v?.match(/(-?[\d.]+)px/)?.[1]);
    const [tabTop, , tabBottom] = tab.get("padding")!.split(" ").map((v) => Number(v.replace("px", "")));
    const bodyLineHeight = Number(read("shared", "theme", "global.css").match(/html,\s*body\s*\{[^}]*line-height:\s*([\d.]+)/)?.[1]);
    const offset = px(tabbar.get("bottom"));
    const capsule = px(tabbar.get("padding")) * 2 + tabTop + tabBottom + iconSize("app/RootLayout.tsx") + px(tab.get("gap")) + px(tab.get("font-size")) * bodyLineHeight;
    expect(capsule, "胶囊高（与浏览器实测 62.05 一致）").toBeCloseTo(62.05, 2);
    const expr = rule(layout, ".ps-shell").get("--tabbar-h")!;
    expect(expr).toMatch(/^calc\([\d.px+*\s]+\)$/);
    const value = Number(new Function(`return ${expr.slice(5, -1).replace(/px/g, "")};`)());
    expect(value).toBeCloseTo(capsule + offset, 2);
    expect(rule(layout, ".ps-shell--no-tabs").get("--tabbar-h")).toBe("0px");

    // 所有用 --tabbar-h 的 calc 里都同时加（减）了 --safe-bottom
    const walk = (dir: string): string[] => readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(join(dir, e.name)) : e.name.endsWith(".css") ? [join(dir, e.name)] : []));
    const uses: string[] = [];
    for (const file of walk(resolve(ROOT, "src"))) {
      const text = readFileSync(file, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
      for (let i = text.indexOf("calc("); i >= 0; i = text.indexOf("calc(", i + 1)) {
        let depth = 0, j = i + 4;
        for (; j < text.length; j++) { if (text[j] === "(") depth++; else if (text[j] === ")" && --depth === 0) break; }
        const group = text.slice(i, j + 1);
        if (group.includes("var(--tabbar-h)")) uses.push(`${file.replace(ROOT, "")}: ${group}`);
      }
    }
    expect(uses.length, "至少找到页面留白、输入框、播放条、菜园这几处").toBeGreaterThanOrEqual(4);
    expect(uses.filter((u) => !u.includes("var(--safe-bottom)"))).toEqual([]);
  });

  it("深色下：未选中的字对胶囊底 ≥ 4.5，选中的 ≥ 7（胶囊是 0.93 不透明，按身后最亮的情况也要够）", () => {
    const rgba = (v: string): [number, number, number, number] => {
      if (v.startsWith("#")) { const h = v.slice(1).length === 3 ? v.slice(1).split("").map((c) => c + c).join("") : v.slice(1); return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)).concat(1) as [number, number, number, number]; }
      const n = v.match(/[\d.]+/g)!.map(Number);
      return [n[0], n[1], n[2], n[3] ?? 1];
    };
    const over = (top: number[], below: number[]) => [0, 1, 2].map((i) => top[i] * top[3] + below[i] * (1 - top[3]));
    const lin = (c: number) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
    const lum = (c: number[]) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
    const ratio = (a: number[], b: number[]) => { const [x, y] = [lum(a), lum(b)]; return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
    const capsule = rgba(rule(layout, ".ps-tabbar").get("background")!);
    const idle = rgba(rule(layout, ".ps-tab").get("color")!);
    const active = rule(layout, ".ps-tab.is-active");
    const activeBg = rgba(active.get("background")!);
    const activeInk = rgba(active.get("color")!);
    // 身后可能是：深色页底、深色卡面、深色下的浅色正文字，外加最坏的纯白（例如照片）
    const tokens = readFileSync(resolve(ROOT, "src", "shared", "theme", "tokens.css"), "utf8");
    const dark = tokens.slice(tokens.indexOf("prefers-color-scheme: dark"));
    const token = (name: string) => rgba(dark.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{3,6})`))![1]);
    const results = [["深色页底", token("c-bg")], ["深色卡面", token("c-surface")], ["深色正文字", token("c-ink")], ["纯白", [255, 255, 255, 1]]].map(([name, backdrop]) => {
      const bg = over(capsule, backdrop as number[]);
      return { name, idle: ratio(over(idle, bg), bg), active: ratio(over(activeInk, over(activeBg, bg)), over(activeBg, bg)) };
    });
    for (const r of results) {
      expect(r.idle, `${r.name}：未选中 ${r.idle.toFixed(2)}`).toBeGreaterThanOrEqual(4.5);
      expect(r.active, `${r.name}：选中 ${r.active.toFixed(2)}`).toBeGreaterThanOrEqual(7);
    }
    // 实算值（2026-09-25）：深色页底 6.57 / 9.07，纯白 5.53 / 7.34
    expect(results[0].idle).toBeCloseTo(6.57, 1);
    expect(results[3].active).toBeCloseTo(7.34, 1);
  });

  it("通讯器页的底栏：还是那三格、图标 20px，选中“通讯器”", async () => {
    renderApp("/communicator");
    const nav = await screen.findByRole("navigation", { name: "主导航" });
    expect(nav.className).toBe("ps-tabbar");
    const links = within(nav).getAllByRole("link");
    expect(links.map((a) => a.className)).toEqual(["ps-tab", "ps-tab is-active", "ps-tab"]);
    expect(links.map((a) => a.querySelector("svg")?.getAttribute("width"))).toEqual(["20", "20", "20"]);
  });
});
