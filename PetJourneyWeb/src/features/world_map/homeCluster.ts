/**
 * 同一个家只画一个小窝标记；在家的几只宠物围着它错开（第 0b 步，含巡检报的“TA 在家时小窝被头像压住一半”）。
 * - 家按 home.center 归并（W1 按家庭给家，同一家的宠物是同一个点；比较到小数点后 6 位）；这个家在场景里的第一只负责画小窝标记。
 * - 在家（phase = home，且位置就在家那个点上）的宠物按场景顺序排到小窝两侧：先右后左、由近到远，一排 6 只，满了再往上一排。
 *   平移是屏幕像素（不随缩放变），按标记的实际尺寸算：谁也不盖住谁，也不盖住小窝。
 * - 出门在外的宠物不挪。
 */
import { HOME_MARKER_SIZE, homeMarkerShift } from "./markers";
import type { MapLatLng, WorldPet } from "./model";

/** 宠物标记的外框（px），与 world-map.css 的 .ps-wmap-pet 一致。 */
export const PET_MARKER_BOX = { width: 52, height: 62 } as const;
/** 标记之间留的空（px）。 */
const GAP = 8;
/** 一排放几只（右 3、左 3）。 */
const PER_ROW = 6;

export interface MarkerOffset {
  x: number;
  y: number;
}

export function homeKey(point: MapLatLng): string {
  return `${point.lat.toFixed(6)},${point.lng.toFixed(6)}`;
}

export function isAtHome(pet: WorldPet): boolean {
  return pet.activity.phase === "home" && pet.home !== null && pet.position !== null && homeKey(pet.position) === homeKey(pet.home.center);
}

/** 第 index 只（从 0 数）在家的宠物相对家那个点的平移（px）：宠物标记的底边中点挪到这里。 */
export function homeSlot(index: number): MarkerOffset {
  const shift = homeMarkerShift();
  // 第一列离家那个点：小窝半宽（含交付单锚点的横向平移）+ 空 + 宠物半宽。
  const firstColumn = HOME_MARKER_SIZE / 2 + Math.abs(shift.x) + GAP + PET_MARKER_BOX.width / 2;
  const row = Math.floor(index / PER_ROW);
  const inRow = index % PER_ROW;
  const side = inRow % 2 === 0 ? 1 : -1;
  const rank = Math.floor(inRow / 2);
  const x = side * (firstColumn + rank * (PET_MARKER_BOX.width + GAP));
  const y = -row * (PET_MARKER_BOX.height + GAP);
  // + 0：第一排的 -0 归成 0（写进 transform 也干净）。
  return { x: Math.round(x) + 0, y: Math.round(y) + 0 };
}

export interface HomeLayout {
  /** 负责画小窝标记的那只 → 这个家的全部宠物（场景顺序）。 */
  residents: Map<string, WorldPet[]>;
  /** 在家的宠物 → 相对家那个点的平移。 */
  offsets: Map<string, MarkerOffset>;
}

export function homeLayout(pets: readonly WorldPet[]): HomeLayout {
  const groups = new Map<string, WorldPet[]>();
  for (const pet of pets) {
    if (!pet.home) continue;
    const key = homeKey(pet.home.center);
    groups.set(key, [...(groups.get(key) ?? []), pet]);
  }
  const residents = new Map<string, WorldPet[]>();
  const offsets = new Map<string, MarkerOffset>();
  for (const members of groups.values()) {
    residents.set(members[0].petId, members);
    members.filter(isAtHome).forEach((pet, index) => offsets.set(pet.petId, homeSlot(index)));
  }
  return { residents, offsets };
}
