/**
 * 串门与偷菜 fixture：两户演示邻居（明确 fixture，不是真实玩家）。
 * 规则与服务端一致：宠物在家守护时偷不到；每批作物全体访客共享可偷上限；同一批每人只能摘一次；幂等键重放同一结果。
 */
import type { CropInfo, NeighborHomeSummary, NeighborHomeView, StealRequest, StealResult } from "@/shared/contracts";
import { ApiError } from "@/shared/api/errors";
import { atMin } from "./world";

export const FIXTURE_CROPS: CropInfo[] = [
  { crop_key: "sun_pea", label: "太阳豌豆", grow_seconds: 180, yield_units: 4, unit_value: 2, steal_total: 1, requires_seed: false },
  { crop_key: "star_tomato", label: "星星番茄", grow_seconds: 1800, yield_units: 6, unit_value: 3, steal_total: 2, requires_seed: false },
  { crop_key: "moon_radish", label: "月光萝卜", grow_seconds: 3600, yield_units: 8, unit_value: 3, steal_total: 3, requires_seed: false },
  { crop_key: "sea_salt_pea", label: "海盐豌豆", grow_seconds: 900, yield_units: 6, unit_value: 4, steal_total: 2, requires_seed: true },
  { crop_key: "sakura_radish", label: "樱色萝卜", grow_seconds: 1200, yield_units: 8, unit_value: 5, steal_total: 3, requires_seed: true },
];

const neighbors: NeighborHomeView[] = [
  {
    home_id: "fx-home-lizi",
    pet: { pet_id: "fx-pet-lizi", name: "栗子（演示邻居）", species: "dog", avatar_url: null },
    presence: "in_transit",
    guarded: false,
    plots: [
      { plot: { plot_id: "fx-n1-p1", cycle_id: "fx-n1-c1", crop_key: "star_tomato", crop_label: "星星番茄", stage: "ripe", ripe_at: atMin(-10), steal_total: 2, steal_remaining: 2 }, taken_by_me: false },
      { plot: { plot_id: "fx-n1-p2", cycle_id: "fx-n1-c2", crop_key: "sun_pea", crop_label: "太阳豌豆", stage: "growing", ripe_at: atMin(40), steal_total: 1, steal_remaining: 1 }, taken_by_me: false },
    ],
    server_time: new Date().toISOString(),
    data_origin: "fixture",
  },
  {
    home_id: "fx-home-arong",
    pet: { pet_id: "fx-pet-arong", name: "阿绒（演示邻居）", species: "rabbit", avatar_url: null },
    presence: "at_home",
    guarded: true,
    plots: [
      { plot: { plot_id: "fx-n2-p1", cycle_id: "fx-n2-c1", crop_key: "moon_radish", crop_label: "月光萝卜", stage: "ripe", ripe_at: atMin(-5), steal_total: 3, steal_remaining: 3 }, taken_by_me: false },
    ],
    server_time: new Date().toISOString(),
    data_origin: "fixture",
  },
];

const settled = new Map<string, StealResult>();

export function fixtureNeighbors(): NeighborHomeSummary[] {
  return neighbors.map((n) => ({
    home_id: n.home_id,
    pet: n.pet,
    presence: n.presence,
    guarded: n.guarded,
    stealable_plots: n.guarded ? 0 : n.plots.filter((p) => p.plot.stage === "ripe" && (p.plot.steal_remaining ?? 0) > 0 && !p.taken_by_me).length,
    data_origin: "fixture",
  }));
}

export function fixtureNeighborHome(homeId: string): NeighborHomeView {
  const home = neighbors.find((n) => n.home_id === homeId);
  if (!home) throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有找到这个家。" });
  return { ...home, server_time: new Date().toISOString() };
}

export function fixtureSteal(body: StealRequest, key: string): StealResult {
  const replay = settled.get(key);
  if (replay) return replay;
  const home = neighbors.find((n) => n.home_id === body.home_id);
  const entry = home?.plots.find((p) => p.plot.plot_id === body.plot_id);
  if (!home || !entry) throw new ApiError({ kind: "http", status: 404, code: "NOT_FOUND", message: "没有这块地。" });
  if (home.guarded) throw new ApiError({ kind: "http", status: 409, code: "FARM_GUARDED", message: `${home.pet.name} 在家守着菜园，被发现啦，只好空手而归。`, details: { reason: "guarded" } });
  if (entry.taken_by_me) throw new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "这批你已经摘过一次了。", details: { reason: "already_taken" } });
  if ((entry.plot.steal_remaining ?? 0) <= 0) throw new ApiError({ kind: "http", status: 409, code: "CONFLICT", message: "这批能摘的都被摘完了。", details: { reason: "nothing_left" } });
  entry.plot = { ...entry.plot, steal_remaining: (entry.plot.steal_remaining ?? 1) - 1 };
  entry.taken_by_me = true;
  const result: StealResult = {
    home_id: home.home_id,
    plot: entry.plot,
    gained_item_key: entry.plot.crop_key ?? "sun_pea",
    gained_units: 1,
    message: `悄悄摘走了一颗${entry.plot.crop_label}，放进了自己家的仓库。`,
  };
  settled.set(key, result);
  return result;
}
