/**
 * claude-6c2b · 菜园与串门的动效只在服务端确认之后出现，文案按服务端的“谁在看着”说话；物种图标用 UI-ASSET-002。
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import { FarmWatchValues, PetSpeciesValues } from "@/shared/contracts";
import type { FarmActionResult, HomeSnapshot, NeighborHomeView, PlotSummary, StealResult } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { ServicesProvider } from "@/shared/services/registry";
import type { ServiceMap } from "@/shared/services/types";
import { NeighborHomePage, bedTag } from "@/features/farm/NeighborPages";
import { WATCH_TONE, levelFromGuard, levelFromWatch, ownerWatchText, visitorWatchText, watchShort, type WatchLevel } from "@/features/farm/guardCopy";
import { MyGarden } from "@/features/farm/GardenPage";
import { HomeScene } from "@/features/home/HomeScene";
import { FARM_ART } from "@/features/farm/FarmMotion";
import { SpeciesIllustration } from "@/features/pets/SpeciesIllustration";
import { fixtureHomeSnapshot } from "@/fixtures/home";

vi.mock("@/shared/config/env", () => ({ env: { dataMode: "live", isDev: false, apiBase: "/api/v1/web" } }));

afterEach(() => cleanup());

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

const plot = (over: Partial<PlotSummary>): PlotSummary => ({
  plot_id: "p1", cycle_id: "c1", crop_key: "star_tomato", crop_label: "星星番茄", stage: "ripe", ripe_at: null, steal_total: 2, steal_remaining: 2, ...over,
});

function neighbour(over: Partial<NeighborHomeView> = {}): NeighborHomeView {
  return {
    home_id: "h-2",
    pet: { pet_id: "pet-2", name: "阿绒", species: "rabbit", avatar_url: null },
    presence: "in_transit",
    guarded: false,
    watch: "nobody",
    plots: [
      { plot: plot({}), taken_by_me: false },
      { plot: plot({ plot_id: "p2", cycle_id: "c2", crop_key: "moon_radish", crop_label: "月光萝卜", stage: "growing" }), taken_by_me: false },
      { plot: plot({ plot_id: "p3", cycle_id: null, crop_key: null, crop_label: null, stage: "empty", steal_total: null, steal_remaining: null }), taken_by_me: false },
    ],
    server_time: "2026-09-23T12:00:00Z",
    data_origin: "live",
    ...over,
  };
}

// 宠物在家只是“有概率被发现”（服务端封顶，不是绝对防偷）；这些说法在任何状态下都不能出现。
const ABSOLUTE = /偷不到|摘不到|不会被偷|不会丢|万无一失|绝对安全|一定不会/;
const GUARDS: Array<Pick<HomeSnapshot["guard"], "basis" | "guarding_pets">> = [
  { basis: "pet_at_home", guarding_pets: ["pet-1"] },
  { basis: "pet_at_home", guarding_pets: [] },
  { basis: "pet_at_home" },
  { basis: "owner_patrol" },
  { basis: "none" },
];

describe("菜园“谁在看着”：自家与邻居同一套说法，不承诺绝对防偷", () => {
  it("邻居页：每种 watch、以及缺 watch 时，都有不露原始码、不写概率、不承诺偷不到的一句话", () => {
    for (const guarded of [true, false]) {
      for (const watch of [...FarmWatchValues, undefined, null]) {
        const level = levelFromWatch(watch, guarded);
        const text = visitorWatchText(level, "阿绒");
        expect(text, `${watch}/${guarded}`).not.toMatch(ABSOLUTE);
        expect(text).not.toMatch(/\d+ ?%/);
        if (watch) expect(text).not.toContain(watch);
      }
    }
  });

  it("缺 watch 但有人守着：只说“可能会被发现”，不说一定、不猜是宠物还是巡院", () => {
    expect(levelFromWatch(undefined, true)).toBe("unknown");
    expect(levelFromWatch(null, false)).toBe("nobody");
    const text = visitorWatchText("unknown", "阿绒");
    expect(text).toContain("可能会被发现");
    expect(text).not.toMatch(/一定|巡院|醒着|打盹/);
  });

  it("自家菜园：按 guard.basis 与 guarding_pets 分级；宠物在家只说“可能 / 很容易”，缺字段时也写明不是绝对防偷", () => {
    expect(GUARDS.map(levelFromGuard)).toEqual(["awake", "resting", "unknown", "patrol", "nobody"]);
    for (const guard of GUARDS) {
      const text = ownerWatchText(levelFromGuard(guard), "栗子", null);
      expect(text, JSON.stringify(guard)).not.toMatch(ABSOLUTE);
    }
    expect(ownerWatchText("resting", "栗子")).toContain("有可能被发现");
    expect(ownerWatchText("awake", "栗子")).toMatch(/很容易被发现.*不是绝对防偷/);
    expect(ownerWatchText("unknown", "栗子")).toMatch(/可能被发现.*不是绝对防偷/);
  });

  it("同一情形两页口径一致：语气等级一样，关键词一样（没人看着 / 可能 / 很容易 / 会被发现）", () => {
    const pairs: Array<[WatchLevel, RegExp]> = [
      ["nobody", /没人看着/],
      ["resting", /可能/],
      ["awake", /很容易被发现/],
      ["patrol", /巡院.*会被发现/],
      ["unknown", /可能.*被发现/],
    ];
    for (const [level, words] of pairs) {
      expect(visitorWatchText(level, "阿绒"), `visitor ${level}`).toMatch(words);
      expect(ownerWatchText(level, "阿绒"), `owner ${level}`).toMatch(words);
    }
    expect(watchShort("patrol", "owner")).toBe("你在巡院");
    expect(watchShort("patrol", "visitor")).toBe("主人在巡院");
    expect(WATCH_TONE).toEqual({ nobody: "calm", resting: "careful", awake: "alert", patrol: "alert", unknown: "careful" });
  });

  it("自家菜园页面：宠物在家打盹时门边泡泡说“有可能被发现”，整页没有“偷不到”", () => {
    const base = fixtureHomeSnapshot();
    const snapshot: HomeSnapshot = { ...base, presence: "at_home", guard: { guarding: true, basis: "pet_at_home", until: null, next_patrol_at: null, guarding_pets: [] } };
    const view = renderWith(<MyGarden snapshot={snapshot} />, { farm: {}, economy: {} }, "/garden", "/garden");
    expect(screen.getByTestId("garden-watch").textContent).toBe(`${base.pet.name} 在家打盹，邻居来摘有可能被发现，也可能摘走一点。`);
    expect(screen.getByRole("region", { name: /的菜园$/ }).textContent).toContain("TA 在打盹");
    expect(view.container.textContent).not.toMatch(ABSOLUTE);
  });

  it("邻居页面：旧数据缺 watch 但 guarded 时，泡泡只说“可能会被发现”", async () => {
    renderWith(<NeighborHomePage />, { farm: { neighborHome: async () => neighbour({ guarded: true, presence: "at_home", watch: undefined }) } }, "/homes/h-2", "/homes/:homeId");
    const bubble = await screen.findByTestId("steal-watch");
    expect(bubble.textContent).toBe("有人看着 阿绒 的菜园——去摘可能会被发现。");
    expect(screen.getByRole("region", { name: "阿绒 的菜园" }).textContent).toContain("在家 · 有人看着");
    expect(screen.getByRole("region", { name: "阿绒 的菜园" }).textContent).not.toMatch(ABSOLUTE);
  });
});

describe("串门：邻居家的菜园场景（QQ 农场式，点地里的菜就是摘）", () => {
  it("三块地按真实阶段摆在场景里：熟了的有作物和光且整块可点，长着的是幼苗，空地只有土，都不可点", async () => {
    renderWith(<NeighborHomePage />, { farm: { neighborHome: async () => neighbour() } }, "/homes/h-2", "/homes/:homeId");
    const scene = await screen.findByRole("region", { name: "阿绒 的菜园" });
    const tiles = within(scene).getAllByTestId("steal-plot");
    expect(tiles.map((tile) => tile.querySelector("[data-stage]")?.getAttribute("data-stage"))).toEqual(["ripe", "growing", "empty"]);
    // 每块地都定位在底图上（不是网格/列表）
    expect(tiles.every((tile) => tile.style.left.endsWith("%") && tile.style.bottom.endsWith("%"))).toBe(true);
    expect(tiles[0].querySelector(".ps-garden-bed__crop")).toBeTruthy();
    expect(tiles[0].querySelector(".ps-garden-bed__glow")).toBeTruthy();
    expect(tiles[1].querySelector(".ps-garden-bed__crop.is-growing")).toBeTruthy();
    expect(tiles[2].querySelector(".ps-garden-bed__crop")).toBeNull();
    expect(within(tiles[0]).getByRole("button", { name: "摘一颗星星番茄（还能摘 2/2）" })).toBeTruthy();
    expect(within(tiles[1]).queryByRole("button")).toBeNull();
    expect(within(tiles[2]).queryByRole("button")).toBeNull();
    expect(within(tiles[1]).getByRole("img", { name: "第 2 块地：月光萝卜 · 还没熟" })).toBeTruthy();
    expect(screen.getByTestId("steal-watch").textContent).toContain("没人看着");
    // 还没摘：篮子是空的，没有落篮、没有飞起来的那一颗
    expect(screen.getByRole("img", { name: "我的篮子，还空着" })).toBeTruthy();
    expect(screen.queryByTestId("basket-catch")).toBeNull();
    expect(screen.queryByTestId("garden-flyer")).toBeNull();
  });

  it("摘到之后才有一颗飞进篮子、篮子计数，回执用服务端原话；这批摘过就不能再点", async () => {
    let taken = false;
    const result: StealResult = { home_id: "h-2", plot: plot({ steal_remaining: 1 }), gained_item_key: "star_tomato", gained_units: 1, message: "悄悄摘走了一颗星星番茄，放进了自己家的仓库。" };
    let settle: (value: StealResult) => void = () => {};
    const steal = vi.fn(() => new Promise<StealResult>((resolve) => { settle = resolve; }));
    const neighborHome = vi.fn(async () => {
      const home = neighbour();
      if (taken) home.plots[0] = { plot: plot({ steal_remaining: 1 }), taken_by_me: true };
      return home;
    });
    renderWith(<NeighborHomePage />, { farm: { neighborHome, steal } }, "/homes/h-2", "/homes/:homeId");
    fireEvent.click(await screen.findByRole("button", { name: /摘一颗星星番茄/ }));
    await waitFor(() => expect(steal).toHaveBeenCalledTimes(1));
    // 请求还在路上：摘菜爪伸过来、菜被拽着晃，但不提前放飞行和落篮
    expect(screen.getAllByTestId("steal-plot")[0].className).toContain("is-pending");
    expect(screen.getByTestId("pick-paw").getAttribute("src")).toBe(FARM_ART.pickPaw);
    expect(screen.queryByTestId("basket-catch")).toBeNull();
    expect(screen.queryByTestId("garden-flyer")).toBeNull();
    taken = true;
    settle(result);
    expect((await screen.findByRole("status")).textContent).toContain(result.message);
    // 飞进篮子的是 UI-ASSET-003 的收成小图；回了结果爪子就收走
    expect(screen.getByTestId("garden-flyer").querySelector("img")?.getAttribute("src")).toBe("/ui-assets/UI-ASSET-003/v1/produce-star_tomato.webp");
    expect(screen.queryByTestId("pick-paw")).toBeNull();
    expect(screen.getByTestId("basket-catch").querySelector(".ps-basket-catch__basket")?.getAttribute("src")).toBe(FARM_ART.basket);
    expect(screen.getByRole("img", { name: "这次串门摘到 1 个" })).toBeTruthy();
    expect(await screen.findByRole("img", { name: "第 1 块地：星星番茄 · 摘过了" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /摘一颗/ })).toBeNull();
  });

  it("被发现（FARM_GUARDED）时那块地抖一下、门边泡泡闪一下，保留服务端的话；别的失败不抖，也都没有篮子", async () => {
    const guarded = neighbour({ guarded: true, presence: "at_home", watch: "pet_awake" });
    const caught = vi.fn(async () => { throw new ApiError({ kind: "http", status: 409, code: "FARM_GUARDED", message: "阿绒 正在家，一眼就发现了你，只好空手而归。", details: { reason: "guarded" } }); });
    renderWith(<NeighborHomePage />, { farm: { neighborHome: async () => guarded, steal: caught } }, "/homes/h-2", "/homes/:homeId");
    fireEvent.click(await screen.findByRole("button", { name: /试试看，摘一颗星星番茄/ }));
    expect((await screen.findByRole("alert")).textContent).toBe("阿绒 正在家，一眼就发现了你，只好空手而归。");
    expect(screen.getAllByTestId("steal-plot")[0].className).toContain("is-caught");
    expect(screen.getByTestId("steal-watch").className).toContain("is-caught");
    expect(screen.queryByTestId("basket-catch")).toBeNull();
    expect(screen.queryByTestId("garden-flyer")).toBeNull();
    cleanup();

    const empty = vi.fn(async () => { throw new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "这批能摘的都被摘完了。", details: { reason: "nothing_left" } }); });
    renderWith(<NeighborHomePage />, { farm: { neighborHome: async () => neighbour(), steal: empty } }, "/homes/h-2", "/homes/:homeId");
    fireEvent.click(await screen.findByRole("button", { name: /摘一颗星星番茄/ }));
    expect((await screen.findByRole("alert")).textContent).toBe("这批能摘的都被摘完了。");
    expect(screen.getAllByTestId("steal-plot")[0].className).not.toContain("is-caught");
    expect(screen.queryByTestId("basket-catch")).toBeNull();
  });

  it("木牌文字：可摘 / 摘过了 / 被摘完了 / 还没熟 / 已收获 / 空地", () => {
    expect(bedTag({ plot: plot({}), taken_by_me: false })).toEqual({ text: "星星番茄 · 可摘 2/2", tone: "ripe" });
    expect(bedTag({ plot: plot({}), taken_by_me: true }).text).toBe("星星番茄 · 摘过了");
    expect(bedTag({ plot: plot({ steal_remaining: 0 }), taken_by_me: false }).text).toBe("星星番茄 · 被摘完了");
    expect(bedTag({ plot: plot({ stage: "growing" }), taken_by_me: false }).text).toBe("星星番茄 · 还没熟");
    expect(bedTag({ plot: plot({ stage: "harvested" }), taken_by_me: false }).text).toBe("星星番茄 · 已收获");
    expect(bedTag({ plot: plot({ stage: "empty", crop_label: null }), taken_by_me: false }).text).toBe("空地");
  });
});

describe("菜园二级页 /garden：点地里的菜就是操作", () => {
  function snapshotWith(...plots: PlotSummary[]): HomeSnapshot {
    return { ...fixtureHomeSnapshot(), plots };
  }

  it("三块地摆在场景里，按阶段给出不同的点法；木牌写作物 · 状态", async () => {
    const plots = [
      plot({ plot_id: "a", stage: "ripe" }),
      plot({ plot_id: "b", cycle_id: "cb", crop_key: "moon_radish", crop_label: "月光萝卜", stage: "growing", ripe_at: new Date(Date.now() + 80 * 60_000).toISOString(), steal_total: 3, steal_remaining: 3 }),
      plot({ plot_id: "c", cycle_id: null, crop_key: null, crop_label: null, stage: "empty", steal_total: null, steal_remaining: null }),
    ];
    const act = vi.fn();
    renderWith(<MyGarden snapshot={snapshotWith(...plots)} />, { farm: { act }, economy: {} }, "/garden", "/garden");
    const scene = screen.getByRole("region", { name: /的菜园$/ });
    const beds = within(scene).getAllByTestId("garden-plot");
    expect(beds.every((bed) => bed.style.left.endsWith("%") && bed.style.bottom.endsWith("%"))).toBe(true);
    expect(within(beds[0]).getByRole("button", { name: "收获星星番茄" })).toBeTruthy();
    expect(within(beds[1]).getByRole("button", { name: "看看月光萝卜还要多久" })).toBeTruthy();
    expect(within(beds[2]).getByRole("button", { name: "在第 3 块地种点什么" })).toBeTruthy();
    expect(beds.map((bed) => bed.querySelector(".ps-garden-slot__tag")?.textContent)).toEqual(["星星番茄 · 可收获", "月光萝卜 · 正在长", "空地 · 种点什么"]);
    // 点正在长的：只冒“还要多久”的泡泡，不发请求
    fireEvent.click(within(beds[1]).getByRole("button"));
    expect(within(beds[1]).getByRole("status").textContent).toMatch(/月光萝卜 还要 .+ · 邻里可摘 3\/3/);
    expect(act).not.toHaveBeenCalled();
    // 仓库篮子与去处都在菜园里
    expect(screen.getByRole("link", { name: /^仓库里有 \d+ 个收成，去仓库与集市$/ }).getAttribute("href")).toBe("/market");
    expect(screen.getByRole("link", { name: /去串门/ }).getAttribute("href")).toBe("/neighbors");
  });

  it("收获成功：一颗飞进仓库篮子 + 服务端原话；失败时只有提示、没有飞行和落篮", async () => {
    const ripe = plot({ plot_id: "fx-plot-1", stage: "ripe" });
    const ok: FarmActionResult = { plot: { ...ripe, stage: "harvested" }, wallet: { currency: "travel_coin", balance: 120, updated_at: "2026-09-23T12:00:00Z" }, gained_items: ["星星番茄 ×6 进了仓库"] };
    const act = vi.fn(async () => ok);
    renderWith(<MyGarden snapshot={snapshotWith(ripe)} />, { farm: { act }, economy: {} }, "/garden", "/garden");
    fireEvent.click(screen.getByRole("button", { name: "收获星星番茄" }));
    expect((await screen.findByRole("status")).textContent).toBe("星星番茄 ×6 进了仓库。旅费未因收获增加。");
    expect(screen.getByTestId("garden-flyer")).toBeTruthy();
    expect(screen.getByTestId("basket-catch")).toBeTruthy();
    expect(act).toHaveBeenCalledWith(expect.objectContaining({ action: "harvest", plot_id: "fx-plot-1" }), expect.any(String));
    cleanup();

    const fail = vi.fn(async () => { throw new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "还没成熟。" }); });
    renderWith(<MyGarden snapshot={snapshotWith(ripe)} />, { farm: { act: fail }, economy: {} }, "/garden", "/garden");
    fireEvent.click(screen.getByRole("button", { name: "收获星星番茄" }));
    expect((await screen.findByRole("alert")).textContent).toBe("还没成熟。");
    expect(screen.queryByTestId("garden-flyer")).toBeNull();
    expect(screen.queryByTestId("basket-catch")).toBeNull();
  });

  it("点空地选种子种下：种子袋在那块地上倾倒、那块地冒芽，回执一句话", async () => {
    const empty = plot({ plot_id: "fx-plot-3", cycle_id: null, crop_key: null, crop_label: null, stage: "empty", steal_total: null, steal_remaining: null });
    const growing = plot({ plot_id: "fx-plot-3", cycle_id: "c9", crop_key: "sun_pea", crop_label: "太阳豌豆", stage: "growing", ripe_at: "2026-09-23T14:00:00Z" });
    const act = vi.fn(async () => ({ plot: growing, wallet: { currency: "travel_coin", balance: 118, updated_at: "2026-09-23T12:00:00Z" }, gained_items: [] }) as FarmActionResult);
    const crops = vi.fn(async () => [{ crop_key: "sun_pea", label: "太阳豌豆", grow_seconds: 7200, yield_units: 4, unit_value: 2, steal_total: 1, requires_seed: false }]);
    renderWith(<MyGarden snapshot={snapshotWith(empty)} />, { farm: { act, crops }, economy: { collection: async () => [] } }, "/garden", "/garden");
    fireEvent.click(screen.getByRole("button", { name: "在第 1 块地种点什么" }));
    const list = await screen.findByRole("list");
    fireEvent.click(await within(list).findByRole("button", { name: "种下" }));
    expect((await screen.findByRole("status")).textContent).toBe("已种下太阳豌豆，等它慢慢长大。");
    const bed = screen.getByTestId("garden-plot");
    expect(within(bed).getByTestId("seed-pour").querySelector("img")?.getAttribute("src")).toBe(FARM_ART.seedBag);
    expect(bed.querySelector(".ps-garden-bed")?.className).toContain("is-just-planted");
    expect(screen.queryByRole("list")).toBeNull();
  });
});

describe("家园首页只放菜园入口（菜园是二级页）", () => {
  it("院子里没有可操作的地块，只有一个带状态的菜园入口", () => {
    const base = fixtureHomeSnapshot();
    const plots = [
      plot({ plot_id: "p1", cycle_id: "c1", crop_key: "sun_pea", crop_label: "太阳豌豆", stage: "growing" }),
      plot({ plot_id: "p3", cycle_id: "c3", crop_key: "moon_radish", crop_label: "月光萝卜", stage: "ripe" }),
    ];
    render(<MemoryRouter><HomeScene snapshot={{ ...base, presence: "at_home", plots }} /></MemoryRouter>);
    // 小窝里的东西平时不写字：入口的状态在无障碍名称里，点开才冒出“去菜园”（claude-6c2b 小窝二级页）。
    const gate = screen.getByRole("button", { name: "菜园，1 块熟了" });
    expect(gate.className).toContain("is-ready");
    // 露出的是最值得看的那块（熟了的）
    expect(gate.querySelector("[class*='is-ripe']")).toBeTruthy();
    fireEvent.click(gate);
    expect(screen.getByRole("link", { name: "去菜园" }).getAttribute("href")).toBe("/garden");
    expect(screen.queryByRole("button", { name: /菜地/ })).toBeNull();
    expect(screen.queryByRole("link", { name: /打开仓库/ })).toBeNull();
  });
});

describe("物种小图（UI-ASSET-002）", () => {
  it("七个类别都用 r7k 交付的透明 WebP，且是装饰图（名字由旁边的文字给出）", () => {
    for (const species of PetSpeciesValues) {
      const { container } = render(<SpeciesIllustration species={species} />);
      const img = container.querySelector("img.ps-species-art");
      expect(img?.getAttribute("src")).toBe(`/ui-assets/UI-ASSET-002/v1/species-${species}.webp`);
      expect(img?.getAttribute("alt")).toBe("");
      cleanup();
    }
  });
});
