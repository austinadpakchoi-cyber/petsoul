/**
 * claude-6c2b · 小窝 / 菜园第 3 轮：
 * 1. 种下时先倒种子、再出苗（样式契约；逐帧时间线看演示站实拍 output/playwright/claude-6c2b/home-r3/）；
 * 2. 庭院最底下长图渐变到地面色的那一段拉长、两头缓（逐档钉）；
 * 3. 小窝“‹ 地图”不多压一条历史：从地图进来（from=map 且站内有来路）就后退；否则 replace 去 /map?focus=。
 * “我出门啦”便笺照旧压一条去 /map?focus=（它的意思是“去看 TA 走到哪了”）。
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { HomeSnapshot, PetPresence } from "@/shared/contracts";
import { HomeScene } from "@/features/home/HomeScene";
import { fixtureHomeSnapshot } from "@/fixtures/home";

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "");
});

const ROOT = process.cwd();
const read = (rel: string) => readFileSync(resolve(ROOT, rel), "utf8");
const FARM_CSS = read("src/features/farm/farm.css");
const HOME_CSS = read("src/features/home/home.css");

/** 去掉注释后的所有规则（@media 里的按最里层选择器算）。 */
function rules(css: string): Array<{ selector: string; body: string }> {
  const bare = css.replace(/\/\*[\s\S]*?\*\//g, "");
  return [...bare.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({ selector: m[1].trim().replace(/\s+/g, " "), body: m[2] }));
}
function ruleBody(css: string, selector: string): string {
  const found = rules(css).filter((r) => r.selector === selector);
  expect(found.length, `找不到规则 ${selector}`).toBeGreaterThan(0);
  return found.map((r) => r.body).join(";");
}
/** 规则里某个属性的值；没有这个属性时返回空串（由用例自己断言，不在收集阶段抛错——那样整个文件“0 条用例”，报不出是哪一条）。 */
function value(body: string, prop: string): string {
  const m = body.match(new RegExp(`(?:^|[;\\s])${prop.replace(/-/g, "\\-")}\\s*:\\s*([^;]+);?`));
  return m ? m[1].trim().replace(/\s+/g, " ") : "";
}
/** “0.45s” / “1400ms” → 毫秒。 */
const ms = (t: string) => (t.endsWith("ms") ? Number(t.slice(0, -2)) : Number(t.slice(0, -1)) * 1000);
/** animation 简写里某个名字那一段的时长与延迟（第一个时间是时长，第二个是延迟）；找不到这一段时 found 为 false。 */
function timing(shorthand: string, name: string): { found: boolean; duration: number; delay: number; fill: string | null } {
  const part = shorthand.split(",").map((s) => s.trim()).find((s) => s.startsWith(name + " "));
  if (!part) return { found: false, duration: NaN, delay: NaN, fill: null };
  const times = [...part.matchAll(/(?:^|\s)(\d+(?:\.\d+)?m?s)(?=\s|$)/g)].map((m) => ms(m[1]));
  const fill = part.match(/\b(both|forwards|backwards)\b/)?.[1] ?? null;
  return { found: true, duration: times[0], delay: times[1] ?? 0, fill };
}
/** 某个 @media 条件下的整块内容。 */
function mediaBlock(css: string, query: string): string {
  const at = css.indexOf(query);
  expect(at).toBeGreaterThan(-1);
  const open = css.indexOf("{", at);
  let depth = 0;
  let end = open;
  for (; end < css.length; end++) {
    if (css[end] === "{") depth++;
    else if (css[end] === "}" && --depth === 0) break;
  }
  return css.slice(open + 1, end);
}
function keyframes(css: string, name: string): string {
  const at = css.indexOf(`@keyframes ${name} {`);
  expect(at, `没有 @keyframes ${name}`).toBeGreaterThan(-1);
  return mediaBlock(css.slice(at), `@keyframes ${name}`);
}

describe("1 · 种下：先倒种子，倒完再出苗", () => {
  const CROP = ".ps-garden-slot .ps-garden-bed.is-just-planted .ps-garden-bed__crop";
  const crop = value(ruleBody(FARM_CSS, CROP), "animation");
  const pop = timing(crop, "ps-crop-pop");
  const sway = timing(crop, "ps-garden-sway");
  const pourOut = timing(value(ruleBody(FARM_CSS, ".ps-seed-pour"), "animation"), "ps-seed-pour-out");
  const tilt = timing(value(ruleBody(FARM_CSS, ".ps-seed-pour__bag"), "animation"), "ps-seed-tilt");
  const fall = timing(value(ruleBody(FARM_CSS, ".ps-seed-pour i"), "animation"), "ps-seed-fall");
  const seedDelays = [fall.delay, ...[3, 4, 5].map((n) => ms(value(ruleBody(FARM_CSS, `.ps-seed-pour i:nth-child(${n})`), "animation-delay")))];
  const pourGone = pourOut.delay + pourOut.duration;

  it("四段动画都在：作物冒芽与摇摆、倒种子一组淡出、袋子倾倒、种子落下", () => {
    expect(pop.found, crop).toBe(true);
    expect(sway.found, crop).toBe(true);
    expect(pourOut.found, "倒种子这一组要在倒完后淡出（ps-seed-pour-out）").toBe(true);
    expect(tilt.found).toBe(true);
    expect(fall.found).toBe(true);
  });

  it("时间线：种子都落地后整组倒种子才淡出；作物即使和袋子同一刻挂上，冒芽也在袋子完全消失、倾倒做完之后", () => {
    expect(pourOut.found, "倒种子这一组要在倒完后淡出（ps-seed-pour-out）").toBe(true);
    expect(Math.max(...seedDelays) + fall.duration, "最后一粒种子落地").toBeLessThanOrEqual(pourGone);
    expect(pop.delay, "冒芽开始 ≥ 袋子完全消失").toBeGreaterThanOrEqual(pourGone);
    expect(pop.delay, "冒芽开始 ≥ 倾倒做完").toBeGreaterThanOrEqual(tilt.duration);
    expect(sway.delay, "冒完芽才接着摇摆").toBe(pop.delay + pop.duration);
    expect(pop.duration).toBe(800); // 原有的出现动画，不改
  });

  it("等待期间作物是隐形的：冒芽第一帧透明、并且用 both 保持；淡出最后一帧透明、并且保持", () => {
    expect(pop.fill).toBe("both");
    expect(keyframes(FARM_CSS, "ps-crop-pop")).toMatch(/0%\s*\{[^}]*opacity:\s*0/);
    expect(pourOut.fill).toBe("both");
    expect(keyframes(FARM_CSS, "ps-seed-pour-out")).toMatch(/to\s*\{[^}]*opacity:\s*0/);
  });

  it("冒芽在页面撤掉 is-just-planted 之前做完：延迟 + 时长 + 演示接口的等待 ≤ GardenPage 的收尾时间", () => {
    const clear = Number(read("src/features/farm/GardenPage.tsx").match(/setPlanted\(null\),\s*(\d+)\)/)?.[1]);
    const fixtureDelay = Number(read("src/fixtures/world.ts").match(/function delay<T>\(value: T, ms = (\d+)\)/)?.[1]);
    expect(clear).toBeGreaterThan(0);
    expect(fixtureDelay).toBeGreaterThan(0);
    expect(pop.delay + pop.duration + fixtureDelay).toBeLessThanOrEqual(clear);
  });

  it("减少动态效果：作物不等、直接显示（animation: none），倒种子这一整组不出现", () => {
    const reduce = mediaBlock(FARM_CSS, "@media (prefers-reduced-motion: reduce)");
    const none = rules(reduce).filter((r) => /animation:\s*none/.test(r.body)).flatMap((r) => r.selector.split(",").map((s) => s.trim()));
    expect(none).toContain(CROP);
    const hidden = rules(reduce).filter((r) => /display:\s*none/.test(r.body)).flatMap((r) => r.selector.split(",").map((s) => s.trim()));
    expect(hidden).toContain(".ps-seed-pour");
  });
});

describe("2 · 庭院最底下：长图渐变到地面色的一段拉长、两头缓", () => {
  const bg = value(ruleBody(HOME_CSS, ".ps-living-ground::before"), "background");
  const gradient = bg.match(/linear-gradient\((.*?)\)\s*,\s*var\(--ground-src\)/)?.[1] ?? "";
  const stops = gradient.split(/,(?![^(]*\))/).map((s) => s.trim()).slice(1);

  it("从距底 ≥ 56px 处开始（原来是 24px），到底边正好是地面色 #8c7e39", () => {
    expect(gradient, `解析不出长图上的渐变：${bg}`).not.toBe("");
    expect(stops[0]).toMatch(/^transparent calc\(100% - (\d+)px\)$/);
    const start = Number(stops[0].match(/(\d+)px/)![1]);
    expect(start).toBeGreaterThanOrEqual(56);
    expect(start).toBeLessThanOrEqual(80);
    expect(stops[stops.length - 1]).toBe("#8c7e39");
    expect(value(ruleBody(HOME_CSS, ".ps-living-ground"), "background")).toBe("#8c7e39");
  });

  it("中间几档都是同一个地面色（rgb 140, 126, 57）只调透明度，透明度一路变大、位置一路往下，头尾两段比中间缓", () => {
    const mid = stops.slice(1, -1).map((s) => s.match(/^rgba\(140, 126, 57, ([\d.]+)\) calc\(100% - (\d+)px\)$/));
    expect(mid.length).toBeGreaterThanOrEqual(2);
    expect(mid.every(Boolean)).toBe(true);
    const start = Number(stops[0].match(/(\d+)px/)![1]);
    const points = [[0, start], ...mid.map((m) => [Number(m![1]), Number(m![2])]), [1, 0]];
    for (let i = 1; i < points.length; i++) {
      expect(points[i][0]).toBeGreaterThan(points[i - 1][0]);
      expect(points[i][1]).toBeLessThan(points[i - 1][1]);
    }
    const slope = (i: number) => (points[i + 1][0] - points[i][0]) / (points[i][1] - points[i + 1][1]);
    const slopes = points.slice(0, -1).map((_, i) => slope(i));
    expect(slopes[0]).toBeLessThan(Math.max(...slopes));
    expect(slopes[slopes.length - 1]).toBeLessThan(Math.max(...slopes));
  });
});

/* ---------------- 3 · 小窝“‹ 地图” ---------------- */

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>;
}

function snapshot(presence: PetPresence = "at_home"): HomeSnapshot {
  const base = fixtureHomeSnapshot();
  return { ...base, presence, pet: { ...base.pet, pet_id: "pet-r3" } } as HomeSnapshot;
}

function renderHome(entries: string[], presence: PetPresence = "at_home") {
  const router = createMemoryRouter(
    [
      { path: "/home", element: <HomeScene snapshot={snapshot(presence)} /> },
      { path: "*", element: <LocationProbe /> },
    ],
    { initialEntries: entries, initialIndex: entries.length - 1 },
  );
  render(<RouterProvider router={router} />);
  return router;
}
const back = () => screen.getByRole("link", { name: "回到地图" });

describe("3 · 小窝“‹ 地图”不多压一条历史", () => {
  it("从地图进来（/map → /home?from=map）：点它是后退，回到原来那条 /map；历史条数不变（往前还是那条小窝）", async () => {
    const router = renderHome(["/map", "/home?from=map"]);
    const home = router.state.location.key;
    expect(back().getAttribute("href")).toBe("/map?focus=pet-r3");
    await act(async () => {
      fireEvent.click(back());
    });
    expect(router.state.historyAction).toBe("POP");
    expect(router.state.location.key).toBe("default"); // 原来那条（第一条）
    expect(screen.getByTestId("location").textContent).toBe("/map");
    await act(async () => {
      await router.navigate(1);
    });
    expect(router.state.location.key).toBe(home);
    expect(router.state.location.search).toBe("?from=map");
  });

  it("从地图进来、换过房间（replace）：照样后退回到地图", async () => {
    const router = renderHome(["/map", "/home?from=map"]);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "屋内" }));
    });
    expect(router.state.location.search).toBe("?from=map&room=inside");
    await act(async () => {
      fireEvent.click(back());
    });
    expect(router.state.historyAction).toBe("POP");
    expect(screen.getByTestId("location").textContent).toBe("/map");
  });

  it.each([
    ["直接打开 /home", ["/home"]],
    ["直接打开 /home?from=map（带参数但没有站内来路）", ["/home?from=map"]],
    ["站内有来路、但不是从地图来的", ["/garden", "/home"]],
  ])("%s：用 replace 去 /map?focus=<当前宠物>，历史条数不变", async (_why, entries) => {
    const router = renderHome(entries);
    await act(async () => {
      fireEvent.click(back());
    });
    expect(router.state.historyAction).toBe("REPLACE");
    expect(screen.getByTestId("location").textContent).toBe("/map?focus=pet-r3");
    // 小窝那一条被换掉：往回退不会回到小窝
    await act(async () => {
      await router.navigate(-1);
    });
    expect(router.state.location.pathname).not.toBe("/home");
  });

  it("浏览器里再核 history.state.idx：直接打开后换过房间（key 不再是 default，idx 仍是 0）不算有来路；idx > 0 才后退", async () => {
    window.history.replaceState({ idx: 0, key: "k0" }, "");
    let router = renderHome(["/map", "/home?from=map"]);
    await act(async () => {
      fireEvent.click(back());
    });
    expect(router.state.historyAction).toBe("REPLACE");
    expect(screen.getByTestId("location").textContent).toBe("/map?focus=pet-r3");
    cleanup();
    window.history.replaceState({ idx: 1, key: "k1" }, "");
    router = renderHome(["/map", "/home?from=map"]);
    await act(async () => {
      fireEvent.click(back());
    });
    expect(router.state.historyAction).toBe("POP");
    expect(screen.getByTestId("location").textContent).toBe("/map");
  });

  it("带修饰键（新标签页打开）的点按不拦，交给浏览器：页面自己不跳", async () => {
    const router = renderHome(["/map", "/home?from=map"]);
    const before = router.state.location.key;
    await act(async () => {
      fireEvent.click(back(), { ctrlKey: true });
    });
    expect(router.state.location.key).toBe(before);
    expect(router.state.location.pathname).toBe("/home");
  });

  it("“我出门啦”便笺不变：从地图进来也照旧压一条去 /map?focus=（去看 TA 走到哪了）", async () => {
    const router = renderHome(["/map", "/home?from=map"], "in_transit");
    await act(async () => {
      fireEvent.click(screen.getByTestId("home-away-note"));
    });
    expect(router.state.historyAction).toBe("PUSH");
    expect(screen.getByTestId("location").textContent).toBe("/map?focus=pet-r3");
  });
});
