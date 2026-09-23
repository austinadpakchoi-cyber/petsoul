/**
 * Fixture 世界（显式演示数据）。
 * 来源：R0 框架窗口 claude-20260922-014933-307b 于 2026-09-22 手写；不对应任何真实账号、宠物、商家、班次或作品授权。
 * 只能在 VITE_PETSOUL_DATA_MODE=fixture 下被 fixture 服务使用；live 模式绝不回退到这里。
 * 样板宠物名只出现在 fixture 中；UI 始终从数据读取“当前宠物”。
 */
import type { PetPrivateSummary } from "@/shared/contracts";

export const FIXTURE_SOURCE = "R0 框架手写演示数据（2026-09-22）";

/** fixture 时间基准：页面加载时刻。交通按真实经过时间推进（1 秒 = 1 秒），只是起点相对加载时刻。 */
let epoch = Date.now();

export function fixtureEpoch(): number {
  return epoch;
}

export function resetFixtureEpoch(): void {
  epoch = Date.now();
}

export function atMin(offsetMinutes: number): string {
  return new Date(epoch + offsetMinutes * 60_000).toISOString();
}

export function atSec(offsetSeconds: number): string {
  return new Date(epoch + offsetSeconds * 1000).toISOString();
}

export const fixturePet: PetPrivateSummary = {
  pet_id: "fx-pet-001",
  home_id: "fx-home-001",
  name: "团子",
  species: "cat",
  photo_url: null,
  origin: "own_pet",
  owner_title: null,
  presence: "in_transit",
};

export function delay<T>(value: T, ms = 220): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(structuredClone(value)), ms));
}
