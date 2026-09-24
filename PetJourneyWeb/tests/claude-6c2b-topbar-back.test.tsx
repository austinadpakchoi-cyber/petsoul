/**
 * claude-6c2b · 顶栏返回“从哪来回哪去”（用户 2026-09-24 同意）：
 * 有站内上一页时退回上一页；直接打开链接进来时回上级页（back 字符串），back 为 true 时回地图首页。
 * href 始终是上级页。
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, Link, RouterProvider } from "react-router";
import { TopBar } from "@/shared/ui";

afterEach(() => cleanup());

function Page({ name, back }: { name: string; back?: string | boolean }) {
  return (
    <div>
      <TopBar title={name} back={back} />
      <p data-testid="where">{name}</p>
      <Link to="/garden">去菜园</Link>
    </div>
  );
}

function renderAt(entries: string[], index = entries.length - 1) {
  const router = createMemoryRouter(
    [
      { path: "/map", element: <Page name="地图" /> },
      { path: "/home", element: <Page name="小窝" /> },
      { path: "/garden", element: <Page name="菜园" back="/map" /> },
      { path: "/pets/:id", element: <Page name="宠物主页" back /> },
    ],
    { initialEntries: entries, initialIndex: index },
  );
  render(<RouterProvider router={router} />);
  return router;
}

describe("顶栏返回：从哪来回哪去", () => {
  it("直接打开链接进来（没有站内历史）：回上级页", async () => {
    const router = renderAt(["/garden"]);
    const back = screen.getByRole("link", { name: "返回" });
    expect(back.getAttribute("href")).toBe("/map");
    fireEvent.click(back);
    expect((await screen.findByTestId("where")).textContent).toBe("地图");
    expect(router.state.location.pathname).toBe("/map");
  });

  it("从小窝点进菜园：返回回到小窝，不跳过它回地图；href 仍是上级页", async () => {
    const router = renderAt(["/home"]);
    fireEvent.click(screen.getByRole("link", { name: "去菜园" }));
    expect((await screen.findByTestId("where")).textContent).toBe("菜园");
    const back = screen.getByRole("link", { name: "返回" });
    expect(back.getAttribute("href")).toBe("/map");
    fireEvent.click(back);
    expect((await screen.findByTestId("where")).textContent).toBe("小窝");
    expect(router.state.location.pathname).toBe("/home");
  });

  it("修饰键点击交给浏览器，不在当前页退回上一页", async () => {
    const router = renderAt(["/home"]);
    fireEvent.click(screen.getByRole("link", { name: "去菜园" }));
    await screen.findByText("菜园", { selector: "[data-testid=where]" });
    fireEvent.click(screen.getByRole("link", { name: "返回" }), { ctrlKey: true });
    expect(router.state.location.pathname).toBe("/garden");
  });

  it("back 为 true、直接打开时：回地图首页，不再是点了没反应", async () => {
    const router = renderAt(["/pets/p-1"]);
    const back = screen.getByRole("link", { name: "返回" });
    expect(back.getAttribute("href")).toBe("/map");
    fireEvent.click(back);
    expect((await screen.findByTestId("where")).textContent).toBe("地图");
    expect(router.state.location.pathname).toBe("/map");
  });
});
