/**
 * claude-6c2b · 新版导航（用户 2026-09-24 采纳地图首页方案，旧四栏退役）：
 * “/” 进地图首页；深链一律按原路径打开，不被首页规则吞掉；底栏只剩“地图 · 通讯器 · 回忆”。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import { createApiClient } from "@/shared/api/client";
import { loadFeatureModules } from "@/app/modules";
import { buildRoutes } from "@/app/router";
import { RouteErrorPage } from "@/app/RouteErrorPage";
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

  it("找不到的地址：“回到家”回地图首页，不再回旧的 /home", async () => {
    renderApp("/no-such-place");
    const back = await screen.findByRole("link", { name: "回到家" });
    expect(back.getAttribute("href")).toBe("/map");
  });

  it("页面出错：“回到家”回地图首页，不再回旧的 /home", async () => {
    const quiet = vi.spyOn(console, "error").mockImplementation(() => undefined);
    function Boom(): never {
      throw new Error("测试用的页面错误");
    }
    const router = createMemoryRouter([{ path: "/", element: <Boom />, errorElement: <RouteErrorPage /> }], { initialEntries: ["/"] });
    render(<RouterProvider router={router} />);
    const back = await screen.findByRole("link", { name: "回到家" });
    expect(back.getAttribute("href")).toBe("/map");
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
