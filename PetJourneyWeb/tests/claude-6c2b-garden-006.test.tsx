/**
 * claude-6c2b · 菜园接入 UI-ASSET-006 v1（r7k）：三张开垦土块轮流用、五种作物各两档、作物“种在地里”。
 * jsdom 不排版：这里钉结构、数据和样式契约；“根部在不在土里”的像素结论看演示站实拍
 * （PetJourneyWeb/output/playwright/claude-6c2b/garden-006/，含每块地近景）。
 * 小窝院子的菜园入口这次不换图，仍走旧 cropVisual（另有 web-041-home 钉着），这里不测它。
 */
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import type { HomeSnapshot, NeighborHomeView, PlotStage, PlotSummary } from "@/shared/contracts";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { KNOWN_CROPS, cropArt } from "@/features/farm/cropVisual";
import { BED_SOILS, GARDEN_FIELD } from "@/features/farm/GardenScene";
import { MyGarden } from "@/features/farm/GardenPage";
import { NeighborHomePage } from "@/features/farm/NeighborPages";
import { FIXTURE_CROPS } from "@/fixtures/farm";
import { fixtureHomeSnapshot } from "@/fixtures/home";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "live", isDev: false, apiBase: "/api/v1/web" } }));

afterEach(() => cleanup());

const ROOT = process.cwd();
const ART = "/ui-assets/UI-ASSET-006/v1";
const OLD_ART = /plot-soil|crop-sprouts|crop-pea-v1|crop-radish-v1|crop-tomato\.webp/;
const STAGES = ["growing", "ripe"] as const;
const LABEL: Record<string, string> = { star_tomato: "星星番茄", sun_pea: "太阳豌豆", sea_salt_pea: "海盐豌豆", moon_radish: "月光萝卜", sakura_radish: "樱色萝卜" };

/** 交付单 docs/coordination/ui-assets/deliveries/UI-ASSET-006-v1.md 的 SHA-256：v1 交付后冻结，页面只能引用、不能改字节。 */
const V1_SHA256: Record<string, string> = {
  "plot-tilled-a.webp": "698feb581dc3494a686cd662b23ea6f36a2a91f4a7e645faa24488013a39d801",
  "plot-tilled-b.webp": "690c108fc14c812956ee39b3d5c27399b117680b0c2a1f5b92df38810274515d",
  "plot-tilled-c.webp": "e27ef6ccbe278539a23f0c9cf9b136ee0f5c605f6e74af9dae7b5e3ec167cd8d",
  "crop-growing-star_tomato.webp": "3f0466c703a83fe5dcd759247b5f2562899470732d9b8989c33af2cd977d7dee",
  "crop-ripe-star_tomato.webp": "b0cdc8c5e49425870ad90f135358b886d43976f97d773b0a97ddb988cb2b6f49",
  "crop-growing-sun_pea.webp": "536095ec9ad54384d8bc8e6fb4de7b935fb878b99ae540d6dbe6da2737e28974",
  "crop-ripe-sun_pea.webp": "ada4bf4c8b5c807635b3f5add178328cd1bb4d4e9962573492bef23ab5aabe22",
  "crop-growing-sea_salt_pea.webp": "6a93b727d8576a1bd69a381048df200b7c7abeefeedf2eea679232bfb68be4e1",
  "crop-ripe-sea_salt_pea.webp": "c65fa7b4628ab67834bf82fcdf43cb5f3647056a089a3fd30dbe977d6c0e8407",
  "crop-growing-moon_radish.webp": "f009e9e3d05d4d26da6a112a94f65a10e2469fb135f43d92c912a32f87d03da0",
  "crop-ripe-moon_radish.webp": "d7577ad2166b3effdf1319bec732fa85e25cfe6534edfbb998f9557085faf76e",
  "crop-growing-sakura_radish.webp": "07d591bb61ee8dbf732853ee118ab948758d508b4e43a83160ff8d0e3a8e89e4",
  "crop-ripe-sakura_radish.webp": "1633be96e9dab4efbf72efe7ce219d6f86bb65544cc8b5f15eda7605b04cb31a",
};

function strictServices(services: Record<string, unknown>): ServiceMap {
  return new Proxy(services as unknown as ServiceMap, {
    get(target, prop: string) {
      if (prop in target) return target[prop as keyof ServiceMap];
      throw new Error(`unexpected service ${prop}`);
    },
  });
}

function renderWith(element: React.ReactNode, services: Record<string, unknown>, entry: string, path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ServicesProvider services={strictServices(services)}>
        <MemoryRouter initialEntries={[entry]}>
          <Routes>
            <Route path={path} element={element} />
          </Routes>
        </MemoryRouter>
      </ServicesProvider>
    </QueryClientProvider>,
  );
}

let seq = 0;
function plot(cropKey: string | null, stage: PlotStage, over: Partial<PlotSummary> = {}): PlotSummary {
  seq += 1;
  const planted = stage === "growing" || stage === "ripe";
  return {
    plot_id: `p${seq}`,
    cycle_id: planted ? `c${seq}` : null,
    crop_key: cropKey,
    crop_label: cropKey ? (LABEL[cropKey] ?? "新作物") : null,
    stage,
    ripe_at: stage === "growing" ? new Date(Date.now() + 60 * 60_000).toISOString() : null,
    steal_total: planted ? 2 : null,
    steal_remaining: planted ? 2 : null,
    ...over,
  };
}

function garden(...plots: PlotSummary[]) {
  const snapshot: HomeSnapshot = { ...fixtureHomeSnapshot(), plots };
  renderWith(<MyGarden snapshot={snapshot} />, { farm: { crops: async () => FIXTURE_CROPS, act: vi.fn() }, economy: { collection: async () => [] } }, "/garden", "/garden");
  return within(screen.getByRole("region", { name: /的菜园$/ })).getAllByTestId("garden-plot");
}

function neighbour(plots: PlotSummary[]): NeighborHomeView {
  return {
    home_id: "h-9",
    pet: { pet_id: "pet-9", name: "阿绒", species: "rabbit", avatar_url: null },
    presence: "in_transit",
    guarded: false,
    watch: "nobody",
    plots: plots.map((p) => ({ plot: p, taken_by_me: false })),
    server_time: "2026-09-24T06:00:00Z",
    data_origin: "live",
  };
}

const bedOf = (tile: HTMLElement) => tile.querySelector<HTMLElement>(".ps-garden-bed")!;
const cropOf = (tile: HTMLElement) => tile.querySelector<HTMLImageElement>(".ps-garden-bed__crop");

describe("作物图：五种作物各两档，一律用 UI-ASSET-006 v1 的文件", () => {
  it("五种 × 两档映射到各自的文件，十张互不相同，文件真实存在", () => {
    const seen = new Set<string>();
    for (const crop of KNOWN_CROPS) {
      for (const stage of STAGES) {
        const art = cropArt(crop, stage);
        expect(art.src, `${crop}/${stage}`).toBe(`${ART}/crop-${stage}-${crop}.webp`);
        expect(art.key).toBe(crop);
        expect(existsSync(resolve(ROOT, `public${art.src}`)), art.src).toBe(true);
        seen.add(art.src);
      }
    }
    expect(seen.size).toBe(10);
    expect([...seen].some((src) => OLD_ART.test(src))).toBe(false);
  });

  it("表外作物：不报错，一律用中性的生长中图（只露叶子），不把原始代码带进 key", () => {
    for (const key of [null, "", "pumpkin", "star_tomato ", "STAR_TOMATO", "__proto__", "constructor"]) {
      for (const stage of STAGES) {
        const art = cropArt(key, stage);
        expect(art.key, String(key)).toBe("unknown");
        expect(art.src).toBe(`${ART}/crop-growing-moon_radish.webp`);
        expect(art.root).toBe(false);
      }
    }
  });

  it("v1 十三个文件的字节与交付单 SHA-256 一致（页面只引用，不改图）", () => {
    for (const [name, sha] of Object.entries(V1_SHA256)) {
      const bytes = readFileSync(resolve(ROOT, `public${ART}/${name}`));
      expect(createHash("sha256").update(bytes).digest("hex"), name).toBe(sha);
    }
  });

  it("入土点：萝卜成熟埋到球根最宽处且入土处有一圈（半宽 ≥ 0.2），其余作物入土点贴近图底；几何都在图内", () => {
    for (const crop of KNOWN_CROPS) {
      for (const stage of STAGES) {
        const art = cropArt(crop, stage);
        const radish = crop === "moon_radish" || crop === "sakura_radish";
        expect(art.root, `${crop}/${stage}`).toBe(radish);
        if (radish && stage === "ripe") {
          expect(art.anchorY).toBeGreaterThan(0.6);
          expect(art.anchorY).toBeLessThan(0.75);
          expect(art.ring).toBeGreaterThanOrEqual(0.2);
        } else {
          expect(art.anchorY, `${crop}/${stage}`).toBeGreaterThan(0.9);
          expect(art.ring).toBeLessThan(0.05);
        }
        expect(art.left).toBeLessThan(art.anchorX);
        expect(art.anchorX).toBeLessThan(art.right);
        expect(art.top).toBeLessThan(art.anchorY);
        expect(art.anchorY).toBeLessThanOrEqual(1);
        expect(art.width).toBeGreaterThanOrEqual(55);
        expect(art.width).toBeLessThanOrEqual(80);
      }
    }
  });
});

describe("开垦土块：三块地三张图，没有木框", () => {
  it("场景三块地依次用 plot-tilled-a / b / c，各带自己的种植点", () => {
    const tiles = garden(plot("star_tomato", "ripe"), plot("moon_radish", "growing"), plot(null, "empty"));
    const soils = tiles.map((tile) => tile.style.getPropertyValue("--bed-soil"));
    expect(soils).toEqual(["a", "b", "c"].map((k) => `url("${ART}/plot-tilled-${k}.webp")`));
    expect(new Set(soils).size).toBe(3);
    tiles.forEach((tile, i) => {
      const soil = BED_SOILS[GARDEN_FIELD.slots[i].soil];
      expect(Number(tile.style.getPropertyValue("--plant-x"))).toBe(soil.plant.x);
      expect(Number(tile.style.getPropertyValue("--plant-y"))).toBe(soil.plant.y);
      expect(bedOf(tile).querySelector(".ps-garden-bed__soil")).toBeTruthy();
    });
  });

  it("自家与邻居页面都不再引用木框 plot-soil、通用嫩芽 crop-sprouts 或旧作物图", async () => {
    const all = KNOWN_CROPS.flatMap((crop) => STAGES.map((stage) => plot(crop, stage)));
    garden(all[0], all[1], all[2]);
    const mine = screen.getByRole("region", { name: /的菜园$/ });
    const refs = (root: Element) => [...root.querySelectorAll("img")].map((i) => i.getAttribute("src") ?? "").concat([...root.querySelectorAll("[style]")].map((e) => e.getAttribute("style") ?? ""));
    expect(refs(mine).filter((s) => OLD_ART.test(s))).toEqual([]);
    cleanup();
    renderWith(<NeighborHomePage />, { farm: { neighborHome: async () => neighbour(all.slice(3, 6)) } }, "/homes/h-9", "/homes/:homeId");
    const theirs = await screen.findByRole("region", { name: "阿绒 的菜园" });
    expect(within(theirs).getAllByTestId("steal-plot")).toHaveLength(3);
    expect(refs(theirs).filter((s) => OLD_ART.test(s))).toEqual([]);
    // 源码层面：菜园场景不再 import 木框
    expect(readFileSync(resolve(ROOT, "src/features/farm/GardenScene.tsx"), "utf8")).not.toMatch(/plot-soil/);
  });
});

describe("作物种在地里：入土点、前景土层、只在成熟时发光", () => {
  it("每株作物：图是这一种这一档；入土几何写在地块上；前景土层、接地阴影、点按延伸都在", () => {
    for (const crop of KNOWN_CROPS) {
      for (const stage of STAGES) {
        const [tile] = garden(plot(crop, stage));
        const art = cropArt(crop, stage);
        const bed = bedOf(tile);
        expect(cropOf(tile)?.getAttribute("src"), `${crop}/${stage}`).toBe(art.src);
        expect(cropOf(tile)?.className).toContain(`is-${crop}`);
        expect(bed.className).toContain("has-plant");
        expect(Number(bed.style.getPropertyValue("--crop-ax"))).toBe(art.anchorX);
        expect(Number(bed.style.getPropertyValue("--crop-ay"))).toBe(art.anchorY);
        expect(Number(bed.style.getPropertyValue("--crop-ring"))).toBe(art.ring);
        expect(Number(bed.style.getPropertyValue("--crop-w"))).toBe(art.width);
        expect(bed.querySelector(".ps-garden-bed__front"), `${crop}/${stage}`).toBeTruthy();
        expect(bed.querySelector(".ps-garden-bed__shade")).toBeTruthy();
        expect(bed.querySelector(".ps-garden-bed__reach")).toBeTruthy();
        // 前景土层叠在作物前面（DOM 顺序在后）
        const layers = [...bed.children].map((el) => el.className.split(" ")[0]);
        expect(layers.indexOf("ps-garden-bed__front")).toBeGreaterThan(layers.indexOf("ps-garden-bed__crop"));
        cleanup();
      }
    }
  });

  it("根茎作物（两种萝卜）两档都有前景土层，并标为根茎", () => {
    for (const crop of ["moon_radish", "sakura_radish"]) {
      for (const stage of STAGES) {
        const [tile] = garden(plot(crop, stage));
        expect(bedOf(tile).querySelector(".ps-garden-bed__front"), `${crop}/${stage}`).toBeTruthy();
        expect(cropOf(tile)?.className).toContain("is-root");
        cleanup();
      }
    }
  });

  it("成熟才发光：成熟有光晕并标 is-ripe；生长中、空地、收获后都没有光晕", () => {
    const tiles = garden(plot("sun_pea", "ripe"), plot("sun_pea", "growing"), plot(null, "empty"));
    expect(tiles[0].querySelector(".ps-garden-bed__glow")).toBeTruthy();
    expect(cropOf(tiles[0])?.className).toContain("is-ripe");
    expect(tiles[1].querySelector(".ps-garden-bed__glow")).toBeNull();
    expect(cropOf(tiles[1])?.className).toContain("is-growing");
    expect(cropOf(tiles[1])?.className).not.toContain("is-ripe");
    expect(tiles[2].querySelector(".ps-garden-bed__glow")).toBeNull();
    cleanup();
    const [harvested] = garden(plot("sun_pea", "harvested"));
    expect(harvested.querySelector(".ps-garden-bed__glow")).toBeNull();
  });

  it("空地与收获后照旧只有土：没有作物、前景土层、阴影和点按延伸，整块地仍是按钮", () => {
    const tiles = garden(plot(null, "empty"), plot("moon_radish", "harvested"));
    for (const tile of tiles) {
      const bed = bedOf(tile);
      expect(bed.querySelector(".ps-garden-bed__soil")).toBeTruthy();
      for (const part of ["crop", "front", "shade", "reach", "glow"]) expect(bed.querySelector(`.ps-garden-bed__${part}`), part).toBeNull();
      expect(bed.className).not.toContain("has-plant");
    }
    expect(within(tiles[0]).getByRole("button", { name: "在第 1 块地种点什么" })).toBeTruthy();
    expect(within(tiles[1]).getByRole("button", { name: "在第 2 块地种点什么" })).toBeTruthy();
  });

  it("表外作物在地里显示中性生长中图，木牌用服务端的名字，不露 key", () => {
    const [tile] = garden(plot("pumpkin_x1", "ripe", { crop_label: "南瓜" }));
    expect(cropOf(tile)?.getAttribute("src")).toBe(`${ART}/crop-growing-moon_radish.webp`);
    expect(cropOf(tile)?.className).toContain("is-unknown");
    expect(tile.textContent).toContain("南瓜 · 可收获");
    expect(tile.textContent).not.toContain("pumpkin");
    expect(within(tile).getByRole("button", { name: "收获南瓜" })).toBeTruthy();
  });

  it("邻居页五种成熟作物都能点着摘，可访问名称不变（后两块在场景外的溢出行，用 a 图）", async () => {
    const plots = KNOWN_CROPS.map((crop) => plot(crop, "ripe"));
    renderWith(<NeighborHomePage />, { farm: { neighborHome: async () => neighbour(plots) } }, "/homes/h-9", "/homes/:homeId");
    const tiles = await screen.findAllByTestId("steal-plot");
    expect(tiles).toHaveLength(5);
    expect(tiles.slice(3).every((tile) => tile.className.includes("is-static") && tile.style.getPropertyValue("--bed-soil") === "")).toBe(true);
    tiles.forEach((tile, i) => {
      const crop = KNOWN_CROPS[i];
      expect(within(tile).getByRole("button", { name: `摘一颗${LABEL[crop]}（还能摘 2/2）` })).toBeTruthy();
      expect(cropOf(tile)?.getAttribute("src")).toBe(cropArt(crop, "ripe").src);
    });
  });

  it("种菜面板缩略图跟地里一致：用 cropArt 的成熟图", async () => {
    garden(plot(null, "empty"));
    fireEvent.click(screen.getByRole("button", { name: "在第 1 块地种点什么" }));
    const list = await screen.findByRole("list");
    const items = await within(list).findAllByRole("listitem");
    expect(items).toHaveLength(FIXTURE_CROPS.length);
    items.forEach((item, i) => {
      expect(item.querySelector("img")?.getAttribute("src")).toBe(cropArt(FIXTURE_CROPS[i].crop_key, "ripe").src);
    });
  });
});

describe("样式契约（garden-bed.css）：前景土层与土块同图、遮罩取交集、光晕只挂在成熟上、深色不发灰、减少动效照旧停", () => {
  const css = readFileSync(resolve(ROOT, "src/features/farm/garden-bed.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  const rules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({ selector: m[1].trim(), body: m[2] }));
  const rule = (part: string) => rules.filter((r) => r.selector.includes(part));

  it("土块和前景土层用同一条规则、同一个变量铺图；变量来自地块外层的 --bed-soil", () => {
    const shared = rules.find((r) => r.selector.includes(".ps-garden-bed__soil") && r.selector.includes(".ps-garden-bed__front"));
    expect(shared?.body).toMatch(/background:\s*var\(--soil\)/);
    expect(rule(".ps-garden-bed.is-tilled").some((r) => /--soil:\s*var\(--bed-soil/.test(r.body))).toBe(true);
    // 前景土层自己不另外指定图
    const frontOnly = rules.filter((r) => r.selector.includes(".ps-garden-bed__front") && !r.selector.includes(".ps-garden-bed__soil"));
    expect(frontOnly.every((r) => !/background/.test(r.body))).toBe(true);
  });

  it("前景土层：入土线以下（--py）∩ 入土圈之外（--crop-ring），带 -webkit- 与标准两套", () => {
    const front = rule(".ps-garden-bed__front").map((r) => r.body).join("\n");
    expect(front).toMatch(/mask-image:[\s\S]*linear-gradient\([^;]*var\(--py\)/);
    expect(front).toMatch(/--ring-x:\s*calc\(var\(--crop-w\) \* var\(--crop-ring\)/);
    expect(front).toMatch(/mask-composite:\s*intersect/);
    expect(front).toMatch(/-webkit-mask-composite:\s*source-in/);
  });

  it("作物按入土点对准种植点定位，入土点以下遮掉", () => {
    const crop = rule(".ps-garden-bed.is-tilled .ps-garden-bed__crop").map((r) => r.body).join("\n");
    expect(crop).toMatch(/left:\s*calc\(\(var\(--px\) - var\(--crop-w\) \* var\(--crop-ax\)\)/);
    expect(crop).toMatch(/bottom:\s*calc\(\(100 - var\(--py\) - var\(--crop-w\) \* \(1 - var\(--crop-ay\)\)/);
    expect(crop).toMatch(/mask-image:\s*linear-gradient\(to bottom, #000 calc\(\(var\(--crop-ay\)/);
  });

  it("光晕滤镜只写在 is-ripe 的规则里", () => {
    const withFilter = rules.filter((r) => /(^|;|\s)filter:\s*drop-shadow/.test(r.body));
    expect(withFilter.length).toBeGreaterThan(0);
    expect(withFilter.every((r) => r.selector.includes(".is-ripe"))).toBe(true);
  });

  it("不用主题变量（深色模式下土和菜不跟着变灰），不自带动画", () => {
    expect(css).not.toMatch(/var\(--(c|paper)-/);
    expect(css).not.toMatch(/animation/);
  });

  it("减少动态效果时停动画的规则仍在 farm.css：摇摆、成熟拱起、光晕都在停止名单里", () => {
    const farm = readFileSync(resolve(ROOT, "src/features/farm/farm.css"), "utf8");
    const reduce = farm.slice(farm.indexOf("@media (prefers-reduced-motion: reduce)"));
    for (const selector of [".ps-garden-bed.is-growing .ps-garden-bed__crop", ".ps-garden-bed.is-ripe .ps-garden-bed__crop", ".ps-garden-bed__glow"]) {
      expect(reduce, selector).toContain(selector);
    }
    expect(reduce).toMatch(/animation:\s*none/);
  });
});
