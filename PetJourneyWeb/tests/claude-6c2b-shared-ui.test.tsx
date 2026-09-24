/**
 * claude-6c2b · shared/ui 两处（用户 2026-09-24 同意“按你的推荐来做”）：
 * 1) PetAvatar 永远是 TA 自己的样子：有照片用照片；演示模式用演示小灰猫；live 没有照片是爪印——任何情况下都不写名字首字。
 * 2) ErrorState 的错误码、request_id、能力名默认收进“技术信息”，玩家平时只见一句人话。
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { ApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { ErrorState, PetAvatar, petPortraitUrl, type IconName } from "@/shared/ui";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "live", isDev: false, apiBase: "/api/v1/web" } }));

const mode = env as { dataMode: "live" | "fixture" };

afterEach(() => {
  cleanup();
  mode.dataMode = "live";
});

describe("PetAvatar：不写名字首字", () => {
  it("live 没有照片：中性爪印占位，读屏说“暂无照片”，画面上没有任何文字", () => {
    render(<PetAvatar petId="p-1" name="栗子" species="cat" photoUrl={null} size={40} />);
    const avatar = screen.getByRole("img", { name: "栗子，暂无照片" });
    expect(avatar.className).toContain("is-placeholder");
    expect(avatar.querySelector("svg.ps-paw-mark")).toBeTruthy();
    expect(avatar.querySelector("img")).toBeNull();
    expect(avatar.textContent).toBe("");
  });

  it("有照片：只用这张照片", () => {
    render(<PetAvatar petId="p-1" name="栗子" species="cat" photoUrl="/media/pets/p-1.jpg" />);
    const avatar = screen.getByRole("img", { name: "栗子" });
    expect(avatar.querySelector("img")?.getAttribute("src")).toBe("/media/pets/p-1.jpg");
    expect(avatar.className).not.toContain("is-placeholder");
    expect(avatar.textContent).toBe("");
  });

  it("演示模式没有照片：用演示小灰猫；live 下同样的数据绝不借演示猫", () => {
    mode.dataMode = "fixture";
    render(<PetAvatar petId="demo" name="团子" species="dog" photoUrl={null} />);
    const img = screen.getByRole("img", { name: "团子，暂无照片" }).querySelector("img");
    expect(img?.getAttribute("src")).toMatch(/demo-cat-portrait/);
    expect(petPortraitUrl(null)).toMatch(/demo-cat-portrait/);
    mode.dataMode = "live";
    expect(petPortraitUrl(null)).toBeNull();
  });

  it("空白名字也不会露出占位字符", () => {
    render(<PetAvatar petId="p-9" name=" " species="cat" photoUrl={null} />);
    expect(screen.getByRole("img").textContent).toBe("");
  });
});

function renderError(error: unknown, onRetry?: () => void) {
  return render(
    <MemoryRouter>
      <ErrorState error={error} onRetry={onRetry} />
    </MemoryRouter>,
  );
}

/** 断言某段技术文字只出现在收起的“技术信息”里。 */
function expectFoldedTech(container: HTMLElement, text: string) {
  const details = container.querySelector("details.ps-state__tech") as HTMLDetailsElement | null;
  expect(details).toBeTruthy();
  expect(details!.open).toBe(false);
  expect(details!.querySelector("summary")?.textContent).toBe("技术信息");
  expect(details!.textContent).toContain(text);
  // 拿掉“技术信息”之后，页面其余地方都不应再出现这段文字。
  const rest = container.cloneNode(true) as HTMLElement;
  rest.querySelectorAll("details").forEach((node) => node.remove());
  expect(rest.textContent).not.toContain(text);
}

describe("图标名是实际图标的联合类型（shared/ui/Icon.tsx）", () => {
  it("写一个不存在的图标名，tsc 就报错；把类型改回任意字符串时，下面的 @ts-expect-error 失效，tsc 会红", () => {
    // @ts-expect-error "map" 不是图标名（地图用的是 "pin"）
    const wrong: IconName = "map";
    const right: IconName = "pin";
    expect([wrong, right]).toEqual(["map", "pin"]);
  });
});

describe("切换宠物栏的颜色跟主题走（householdContext.css，I 放行只换颜色）", () => {
  // 去掉注释再查；white-space 之类的属性名不算颜色。SHARED_UI_PETBAR_CSS 只给变异对照指到副本用。
  const cssFile = process.env.SHARED_UI_PETBAR_CSS ?? resolve(dirname(fileURLToPath(import.meta.url)), "..", "src", "shared", "session", "householdContext.css");
  const css = readFileSync(cssFile, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const values = [...css.matchAll(/(?:^|[;{\s])(color|background(?:-color)?|border(?:-[a-z]+)*-?color|border(?:-bottom)?|outline)\s*:\s*([^;]+);/g)].map((m) => m[2].trim());

  it("没有写死的颜色（十六进制、rgb、white/black），深色模式下不再是一条亮条", () => {
    expect(values.length).toBeGreaterThan(5);
    for (const value of values) {
      expect(value, value).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(|\bwhite\b|\bblack\b/);
    }
  });

  it("底色、文字、边框、选中态都用主题变量", () => {
    for (const token of ["--c-surface", "--c-surface-2", "--c-surface-stroke", "--c-ink", "--c-ink-2", "--c-sun", "--c-sun-soft"]) {
      expect(css).toContain(`var(${token})`);
    }
  });
});

describe("ErrorState：错误码默认收起", () => {
  it("网络错误：标题说人话、给重试，NETWORK_ERROR 与 request_id 只在收起的“技术信息”里", () => {
    const { container } = renderError(new ApiError({ kind: "network", code: "NETWORK_ERROR", message: "网络连接失败", retryable: true, requestId: "req_abc12345" }), () => undefined);
    expect(screen.getByRole("alert").textContent).toContain("信号暂时中断");
    expect(screen.getByRole("button", { name: /重试/ })).toBeTruthy();
    expectFoldedTech(container, "NETWORK_ERROR");
    expectFoldedTech(container, "request_id req_abc12345");
  });

  it("能力未接入：能力名只在收起的“技术信息”里", () => {
    const { container } = renderError(ApiError.capability("social.friends", "这项能力尚未接入。"));
    expect(container.textContent).toContain("这里暂时还没开放");
    expectFoldedTech(container, "social.friends");
  });

  it("未登录：request_id 只在收起的“技术信息”里；没有编号时不出现空的“技术信息”", () => {
    const withId = renderError(new ApiError({ kind: "http", status: 401, code: "AUTH_REQUIRED", message: "需要登录后才能继续。", retryable: false, requestId: "req_x1" }));
    expectFoldedTech(withId.container, "request_id req_x1");
    cleanup();
    const without = renderError(new ApiError({ kind: "http", status: 401, code: "AUTH_REQUIRED", message: "需要登录后才能继续。", retryable: false }));
    expect(without.container.querySelector("details")).toBeNull();
  });
});
