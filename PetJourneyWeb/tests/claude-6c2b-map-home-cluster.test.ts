/**
 * claude-6c2b · 地图第 0b 步第 4 条：同一个家只画一个小窝标记，在家的几只围着它错开（world_map/homeCluster 的纯函数）。
 * 盒子都按标记的实际尺寸（小窝按钮 HOME_MARKER_SIZE 见方、按交付单锚点平移；宠物 52×62）相对家那个点算，单位 px。
 */
import { describe, expect, it } from "vitest";
import { homeKey, homeLayout, homeSlot, isAtHome, PET_MARKER_BOX } from "@/features/world_map/homeCluster";
import { HOME_MARKER_SIZE, homeMarkerShift } from "@/features/world_map/markers";
import type { WorldPet } from "@/features/world_map/model";

interface Box {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

const overlaps = (a: Box, b: Box) => Math.min(a.right, b.right) - Math.max(a.left, b.left) > 0 && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 0;
const petBoxAt = ({ x, y }: { x: number; y: number }): Box => ({ left: x - PET_MARKER_BOX.width / 2, right: x + PET_MARKER_BOX.width / 2, top: y - PET_MARKER_BOX.height, bottom: y });
function houseBox(): Box {
  const { x, y } = homeMarkerShift();
  return { left: x - HOME_MARKER_SIZE / 2, right: x + HOME_MARKER_SIZE / 2, top: y - HOME_MARKER_SIZE, bottom: y };
}

const HOME = { lat: 24.441642, lng: 118.112039 };
const OTHER_HOME = { lat: 31.2304, lng: 121.4737 };

function pet(petId: string, where: "home" | "out" | "other-home" = "home"): WorldPet {
  const home = where === "other-home" ? OTHER_HOME : HOME;
  const out = where === "out";
  return {
    petId,
    name: petId,
    species: "cat",
    photoUrl: null,
    relation: "household",
    home: { center: home, precisionM: 900, label: "家" },
    activity: { kind: out ? "cafe" : "home", phase: out ? "there" : "home", pose: "idle", title: "", doing: null, place: null, since: null, until: null, job: null, journeyId: null, visitId: null },
    leg: null,
    position: out ? { lat: 24.4452, lng: 118.1063 } : home,
    basis: out ? "place" : "home_area",
    version: 0,
  };
}

describe("homeCluster：在家的几只围着小窝错开", () => {
  it("第 1–14 只的位置：谁也不盖住谁，也不盖住小窝（两排都算上）", () => {
    const boxes = Array.from({ length: 14 }, (_, i) => petBoxAt(homeSlot(i)));
    boxes.forEach((box, i) => {
      expect(overlaps(box, houseBox()), `第 ${i + 1} 只盖住了小窝`).toBe(false);
      boxes.slice(i + 1).forEach((other, j) => expect(overlaps(box, other), `第 ${i + 1} 只和第 ${i + j + 2} 只叠在一起`).toBe(false));
    });
  });

  it("先右后左、由近到远，一排 6 只满了才往上一排；第一只离小窝不远（贴着站，不飞出去）", () => {
    expect([0, 1, 2, 3, 4, 5].map((i) => homeSlot(i))).toEqual([
      { x: 56, y: 0 },
      { x: -56, y: 0 },
      { x: 116, y: 0 },
      { x: -116, y: 0 },
      { x: 176, y: 0 },
      { x: -176, y: 0 },
    ]);
    expect(homeSlot(6)).toEqual({ x: 56, y: -70 });
    expect(homeSlot(7)).toEqual({ x: -56, y: -70 });
  });

  it("同一个家只由第一只画小窝；在家的按场景顺序占位，出门的不挪；别的家各画各的", () => {
    const pets = [pet("a"), pet("b", "out"), pet("c"), pet("d", "other-home")];
    const layout = homeLayout(pets);
    expect([...layout.residents.keys()]).toEqual(["a", "d"]);
    expect(layout.residents.get("a")?.map((p) => p.petId)).toEqual(["a", "b", "c"]);
    expect(layout.residents.get("d")?.map((p) => p.petId)).toEqual(["d"]);
    expect(Object.fromEntries(layout.offsets)).toEqual({ a: homeSlot(0), c: homeSlot(1), d: homeSlot(0) });
  });

  it("在家的判断：phase 是 home 且位置就在家那个点上（比较到小数点后 6 位）；没有位置、没有家、或还在路上都不算", () => {
    expect(isAtHome(pet("a"))).toBe(true);
    expect(isAtHome(pet("b", "out"))).toBe(false);
    expect(isAtHome({ ...pet("c"), position: null })).toBe(false);
    expect(isAtHome({ ...pet("d"), home: null })).toBe(false);
    expect(isAtHome({ ...pet("e"), position: { lat: HOME.lat + 0.0000001, lng: HOME.lng } })).toBe(true);
    expect(isAtHome({ ...pet("f"), activity: { ...pet("f").activity, phase: "going" } })).toBe(false);
    expect(homeKey(HOME)).toBe("24.441642,118.112039");
  });
});
