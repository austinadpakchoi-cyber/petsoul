/**
 * claude-6c2b · 小窝庭院接入 UI-ASSET-008 v1 长底图（r7k）与 UI-ASSET-006 开垦土块 / 作物；
 * 顺带：菜园飞进篮子的那颗菜、种子袋看不见的两处原有问题，菜园门牌副标题深色对比度（CSS 巡检转来）。
 * jsdom 不排版：这里钉结构、数据和样式契约；位置、接缝、像素结论看演示站实拍
 * （PetJourneyWeb/output/playwright/claude-6c2b/courtyard-008/，含改前改后的热点位置表）。
 * 屋内的长图接缝没过审，本轮不接：屋内仍是原图 + [过渡方案] 垫层（那一段由 claude-6c2b-home-l2 的 [过渡方案] 用例钉）。
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import type { HomeSnapshot, PlotStage, PlotSummary } from "@/shared/contracts";
import { HomeScene } from "@/features/home/HomeScene";
import { KNOWN_CROPS, cropArt, cropVisual, produceVisual } from "@/features/farm/cropVisual";
import { fixtureHomeSnapshot } from "@/fixtures/home";

afterEach(() => cleanup());

const ROOT = process.cwd();
const read = (rel: string) => readFileSync(resolve(ROOT, rel), "utf8");
const TALL = "/ui-assets/UI-ASSET-008/v1/courtyard-base-tall.webp";
/** 交付单 docs/coordination/ui-assets/deliveries/UI-ASSET-008-v1.md 登记的 SHA-256：页面只引用，不改图。 */
const TALL_SHA256 = "87ead92b8e6d4adadbe2b79c9a975c274c7cc6f4a4e7e60c4e4c91ecc4adc809";
/** 长图最底 8 行整幅平均（courtyard-base-tall.webp 解码像素，rgb 140, 126, 57）：矮屏以外、图下面还空着的地方补这个地面色。 */
const GROUND = "#8c7e39";
const OLD_ART = /plot-soil|crop-sprouts|crop-pea-v1|crop-radish-v1|crop-tomato\.webp|courtyard-base\.webp/;
const HOME_CSS = read("src/features/home/home.css");
const FARM_CSS = read("src/features/farm/farm.css");

/** 去掉注释后的所有规则（@media 里的按最里层选择器算）。 */
function rules(css: string): Array<{ selector: string; body: string }> {
  const bare = css.replace(/\/\*[\s\S]*?\*\//g, "");
  return [...bare.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({ selector: m[1].trim(), body: m[2] }));
}
function ruleBody(css: string, selector: string): string {
  const found = rules(css).filter((r) => r.selector === selector);
  expect(found.length, `找不到规则 ${selector}`).toBeGreaterThan(0);
  return found.map((r) => r.body).join(";");
}
function value(body: string, prop: string): string | null {
  const m = body.match(new RegExp(`(?:^|[;\\s])${prop.replace(/-/g, "\\-")}\\s*:\\s*([^;]+);?`));
  return m ? m[1].trim() : null;
}
/** 某个 @media 条件下的整块内容（按花括号配对取出）。 */
function mediaBlocks(css: string, query: string): string[] {
  const out: string[] = [];
  let at = css.indexOf(query);
  while (at >= 0) {
    const open = css.indexOf("{", at);
    let depth = 0;
    let end = open;
    for (; end < css.length; end++) {
      if (css[end] === "{") depth++;
      else if (css[end] === "}" && --depth === 0) break;
    }
    out.push(css.slice(open + 1, end));
    at = css.indexOf(query, end);
  }
  return out;
}
/** WebP 画布尺寸（RIFF 头里的 VP8X / VP8 / VP8L 块）。 */
function webpSize(buf: Buffer): { w: number; h: number } {
  expect(buf.toString("ascii", 0, 4) + buf.toString("ascii", 8, 12)).toBe("RIFFWEBP");
  let off = 12;
  while (off + 8 <= buf.length) {
    const tag = buf.toString("ascii", off, off + 4);
    const size = buf.readUInt32LE(off + 4);
    const data = off + 8;
    if (tag === "VP8X") return { w: 1 + buf.readUIntLE(data + 4, 3), h: 1 + buf.readUIntLE(data + 7, 3) };
    if (tag === "VP8 ") return { w: buf.readUInt16LE(data + 6) & 0x3fff, h: buf.readUInt16LE(data + 8) & 0x3fff };
    if (tag === "VP8L") {
      const bits = buf.readUInt32LE(data + 1);
      return { w: (bits & 0x3fff) + 1, h: ((bits >> 14) & 0x3fff) + 1 };
    }
    off = data + size + (size & 1);
  }
  throw new Error("WebP 里没有图像块");
}

let seq = 0;
function plot(cropKey: string | null, stage: PlotStage): PlotSummary {
  seq += 1;
  const planted = stage === "growing" || stage === "ripe";
  return { plot_id: `c${seq}`, cycle_id: planted ? `cc${seq}` : null, crop_key: cropKey, crop_label: cropKey ? "作物" : null, stage, ripe_at: null, steal_total: planted ? 2 : null, steal_remaining: planted ? 2 : null };
}
function renderYard(plots: PlotSummary[]) {
  const snapshot: HomeSnapshot = { ...fixtureHomeSnapshot(), plots };
  return render(
    <MemoryRouter initialEntries={["/home"]}>
      <HomeScene snapshot={snapshot} />
    </MemoryRouter>,
  );
}
const yard = () => screen.getByRole("region", { name: "共同的家·庭院" });
const artRefs = (root: Element) =>
  [...root.querySelectorAll("img")].map((i) => i.getAttribute("src") ?? "").concat([...root.querySelectorAll("[style]")].map((e) => e.getAttribute("style") ?? ""));

describe("庭院换 UI-ASSET-008 长底图，坐标框照旧是原来的 780×1320", () => {
  const tallBytes = readFileSync(resolve(ROOT, `public${TALL}`));
  const tall = webpSize(tallBytes);

  it("庭院底图是长图、屋内仍是原图；长图字节与交付单一致，780×1690", () => {
    renderYard([plot("star_tomato", "ripe")]);
    expect(yard().querySelector(".ps-living-background")?.getAttribute("src")).toBe(TALL);
    fireEvent.click(screen.getByRole("button", { name: "屋内" }));
    const inside = screen.getByRole("region", { name: "共同的家·屋内" }).querySelector(".ps-living-background")?.getAttribute("src") ?? "";
    expect(inside).toContain("room-base.webp");
    expect(inside).not.toContain("UI-ASSET-008");
    expect(createHash("sha256").update(tallBytes).digest("hex")).toBe(TALL_SHA256);
    expect(tall).toEqual({ w: 780, h: 1690 });
  });

  it("盒子仍是 390:610；长图 cover 后，任何宽度下盒子上沿都对着第 50 行、下沿对着第 1270 行（和原图 780×1320 cover 居中一样）", () => {
    expect(value(ruleBody(HOME_CSS, ".ps-living-scene"), "aspect-ratio")).toBe("390 / 610");
    const position = value(ruleBody(HOME_CSS, ".ps-living-scene.is-courtyard .ps-living-background"), "object-position") ?? "";
    const m = position.match(/^50% calc\((\d+(?:\.\d+)?) \/ (\d+(?:\.\d+)?) \* 100%\)$/);
    expect(m, position).toBeTruthy();
    const p = Number(m![1]) / Number(m![2]);
    for (const width of [320, 375, 390, 430, 560]) {
      const boxH = (width * 610) / 390;
      // 原图：780×1320，object-position 居中（50%）
      const s0 = Math.max(width / 780, boxH / 1320);
      const top0 = -((boxH - 1320 * s0) * 0.5) / s0;
      // 长图：cover 同样按宽度铺满，纵向按 p
      const s = Math.max(width / tall.w, boxH / tall.h);
      expect(s).toBeCloseTo(width / tall.w, 10);
      const offY = (boxH - tall.h * s) * p;
      expect(-offY / s, `${width}px 宽：盒子上沿`).toBeCloseTo(top0, 6);
      expect(-offY / s).toBeCloseTo(50, 6);
      expect((boxH - offY) / s, `${width}px 宽：盒子下沿`).toBeCloseTo(1270, 6);
    }
  });

  it("盒子下面接着铺长图第 1270–1690 行：地面层从盒子底边起，下半截与盒子里同一张图、同一个缩放；再往下补底边地面色，浅深都一样", () => {
    const ground = ruleBody(HOME_CSS, ".ps-living-ground");
    expect(value(ground, "margin-top")).toBe("calc(610 / 390 * 100%)");
    expect(value(ground, "background")).toBe(GROUND);
    expect(value(ground, "overflow")).toBe("hidden");
    expect(value(ground, "pointer-events")).toBe("none");
    const before = ruleBody(HOME_CSS, ".ps-living-ground::before");
    // 420 = 1690 − 1270：盒子下沿以下剩下的行数
    expect(value(before, "aspect-ratio")).toBe(`${tall.w} / ${tall.h - 1270}`);
    expect(before).toMatch(/var\(--ground-src\) 50% 100% \/ 100% auto no-repeat/);
    // 图的最后一段渐变到底边地面色（第 3 轮从 24px 拉长到 64px；逐档细节在 claude-6c2b-home-r3 里钉）
    expect(before).toMatch(/linear-gradient\(\s*to bottom,\s*transparent calc\(100% - \d+px\),[\s\S]*#8c7e39\s*\)/);
    for (const dark of mediaBlocks(HOME_CSS, "@media (prefers-color-scheme: dark)")) expect(dark).not.toContain("ps-living-ground");
    renderYard([plot("star_tomato", "ripe")]);
    const layer = screen.getByTestId("home-scene-ground");
    expect(layer.style.getPropertyValue("--ground-src")).toBe(`url("${TALL}")`);
    expect(yard().contains(layer)).toBe(false);
  });
});

describe("院子里的菜园入口：和菜园页同一块开垦土块，作物种在地里", () => {
  it("熟了：开垦土块 + 这一种的成熟图 + 前景土层 + 代码加的光；入口还是同一个按钮，名字不变；场景里没有旧木框和旧作物图", () => {
    renderYard([plot("star_tomato", "ripe"), plot("moon_radish", "growing")]);
    const gate = screen.getByRole("button", { name: "菜园，1 块熟了" });
    expect(gate.getAttribute("data-testid")).toBe("home-garden-gate");
    const bed = gate.querySelector<HTMLElement>(".ps-living-plot-art > .ps-garden-bed.is-tilled.is-ripe");
    expect(bed).toBeTruthy();
    expect(bed!.querySelector(".ps-garden-bed__soil")).toBeTruthy();
    expect(bed!.querySelector(".ps-garden-bed__crop")?.getAttribute("src")).toBe(cropArt("star_tomato", "ripe").src);
    expect(Number(bed!.style.getPropertyValue("--crop-ay"))).toBe(cropArt("star_tomato", "ripe").anchorY);
    expect(bed!.querySelector(".ps-garden-bed__front")).toBeTruthy();
    expect(bed!.querySelector(".ps-garden-bed__glow")).toBeTruthy();
    expect(within(gate).queryAllByRole("button")).toHaveLength(0);
    expect(artRefs(yard()).filter((s) => OLD_ART.test(s))).toEqual([]);
  });

  it("只有正在长的：这一种的生长中图，根茎作物有前景土层，不发光", () => {
    renderYard([plot("sakura_radish", "growing")]);
    const gate = screen.getByRole("button", { name: "菜园，都在长" });
    const bed = gate.querySelector<HTMLElement>(".ps-garden-bed.is-tilled.is-growing")!;
    expect(bed.querySelector(".ps-garden-bed__crop")?.getAttribute("src")).toBe(cropArt("sakura_radish", "growing").src);
    expect(bed.querySelector(".ps-garden-bed__crop")?.className).toContain("is-root");
    expect(bed.querySelector(".ps-garden-bed__front")).toBeTruthy();
    expect(bed.querySelector(".ps-garden-bed__glow")).toBeNull();
  });

  it("空地、收获后：只有土，没有作物和光", () => {
    for (const stage of ["empty", "harvested"] as const) {
      renderYard([plot(stage === "empty" ? null : "sun_pea", stage)]);
      const gate = screen.getByRole("button", { name: "菜园，有空地可以种" });
      const bed = gate.querySelector<HTMLElement>(`.ps-garden-bed.is-tilled.is-${stage}`)!;
      expect(bed.querySelector(".ps-garden-bed__soil"), stage).toBeTruthy();
      for (const part of ["crop", "front", "glow", "shade", "reach"]) expect(bed.querySelector(`.ps-garden-bed__${part}`), `${stage}/${part}`).toBeNull();
      cleanup();
    }
  });

  it("源码里不再引用旧木框、旧作物图和旧庭院底图", () => {
    expect(read("src/features/home/HomeScene.tsx")).not.toMatch(OLD_ART);
    expect(read("src/features/farm/cropVisual.ts")).not.toMatch(/assets\/living\/crop-/);
  });
});

describe("cropVisual / produceVisual 统一到 cropArt", () => {
  it("cropVisual 就是 cropArt(...).src：五种两档、表外作物都一样", () => {
    for (const crop of [...KNOWN_CROPS, "pumpkin", null]) {
      for (const stage of ["growing", "ripe"] as const) expect(cropVisual(crop, stage), `${crop}/${stage}`).toBe(cropArt(crop, stage).src);
    }
  });

  it("produceVisual：五种用收成小图；表外作物退回 cropArt 的中性图（和地里一致），不是旧的嫩芽图", () => {
    for (const crop of KNOWN_CROPS) expect(produceVisual(crop)).toBe(`/ui-assets/UI-ASSET-003/v1/produce-${crop}.webp`);
    for (const crop of ["pumpkin", "", null]) {
      expect(produceVisual(crop), String(crop)).toBe(cropArt(crop, "ripe").src);
      expect(produceVisual(crop)).not.toMatch(OLD_ART);
    }
  });
});

describe("菜园两处原有问题：飞进篮子的那颗菜、种下时的种子袋", () => {
  it("飞行的那颗菜：外框是 0×0 的定位点，图放开 max-width（全局 img 的 max-width: 100% 会把它压成 0 宽）", () => {
    const flyer = ruleBody(FARM_CSS, ".ps-garden-flyer");
    expect(value(flyer, "width")).toBe("0");
    const img = ruleBody(FARM_CSS, ".ps-garden-flyer img");
    expect(value(img, "max-width")).toBe("none");
    expect(value(img, "width")).toBe("48px");
  });

  it("种子袋：外框改成块级、袋子图放开 max-width；落点按种植点（--plant-x / --plant-y）定位，不再按木框写死", () => {
    expect(value(ruleBody(FARM_CSS, ".ps-seed-pour"), "display")).toBe("block");
    expect(value(ruleBody(FARM_CSS, ".ps-seed-pour__bag"), "max-width")).toBe("none");
    const pour = ruleBody(FARM_CSS, ".ps-garden-slot__pour");
    expect(value(pour, "left")).toMatch(/var\(--plant-x/);
    expect(value(pour, "margin-bottom")).toMatch(/var\(--plant-y/);
    expect(value(pour, "right")).toBeNull();
  });
});

describe("菜园门牌副标题（“没人看着”这一行）：深色下也看得清", () => {
  const tokens = read("src/shared/theme/tokens.css");
  const vars = (block: string) => Object.fromEntries([...block.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
  const light = vars(tokens.slice(tokens.indexOf(":root {"), tokens.indexOf("}")));
  const dark = { ...light, ...vars(mediaBlocks(tokens, "@media (prefers-color-scheme: dark)")[0]) };
  const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const lum = (c: number[]) => {
    const [r, g, b] = c.map((v) => (v / 255 <= 0.03928 ? v / 255 / 12.92 : ((v / 255 + 0.055) / 1.055) ** 2.4));
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const ratio = (a: string, b: string) => {
    const [x, y] = [lum(rgb(a)), lum(rgb(b))].sort((m, n) => n - m);
    return (x + 0.05) / (y + 0.05);
  };

  it("用纸质固定色，门牌暖纸底上浅色、深色对比度都 ≥ 4.5", () => {
    const color = value(ruleBody(FARM_CSS, ".ps-garden-scene__sign small"), "color") ?? "";
    const token = color.match(/^var\((--[\w-]+)\)$/)?.[1];
    expect(token, color).toBe("--paper-secondary-ink");
    const bg = value(ruleBody(FARM_CSS, ".ps-garden-scene__sign"), "background") ?? "";
    expect(bg).toMatch(/^#[0-9a-f]{8}$/i);
    expect(parseInt(bg.slice(7, 9), 16) / 255).toBeGreaterThan(0.9); // 门牌几乎不透明，按不透明底色算
    const paper = bg.slice(0, 7);
    for (const [scheme, map] of [["light", light], ["dark", dark]] as const) {
      expect(ratio(map[token!], paper), `${scheme} ${map[token!]} on ${paper}`).toBeGreaterThanOrEqual(4.5);
    }
  });
});
