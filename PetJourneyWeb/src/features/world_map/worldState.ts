/**
 * W1 统一世界状态（`GET /world/state`，契约 `WorldState`）→ 地图视图模型。
 * 只做形状转换，不补、不猜：position 为 null 就不画点；leg 缺出发 / 到达时间或几何不足两点，就不沿线插值（用服务端给的 position）；
 * pose 原样透传（作息接不上时后端给 idle，不是 sleeping）。坐标仍是 WGS-84，画到高德上时由 AmapView 换算。
 */
import type { WorldPetState, WorldState } from "@/shared/contracts";
import type { TravelMode, MapLeg, WorldPet, WorldScene } from "./model";

function travelMode(mode: string): TravelMode {
  if (mode === "walk" || mode === "taxi" || mode === "drive") return mode;
  if (mode === "transit" || mode === "bus") return "bus";
  return "other";
}

function time(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

function legOf(pet: WorldPetState): MapLeg | null {
  if (!pet.leg || pet.leg.route.length < 2) return null;
  const departsAt = time(pet.leg.departs_at);
  const arrivesAt = time(pet.leg.arrives_at);
  if (departsAt == null || arrivesAt == null) return null;
  return { mode: travelMode(pet.leg.mode), route: pet.leg.route, departsAt, arrivesAt };
}

/**
 * 头像：W1 的 `avatar_url` 是证件照上方裁好的 256 小图，没有就是 null（后端不拿别的图冒充）。
 * 那时前端退回这只宠物在家庭资料里的照片——和全站其他头像同一张（PetAvatar / PetPortrait 用的 photo_url）；
 * 再没有才是爪印。`fallbackPhoto` 只来自当前账号的家庭资料，别人的宠物没有这一项。
 */
export function worldPetFromState(pet: WorldPetState, fallbackPhoto: string | null = null): WorldPet {
  const a = pet.activity;
  return {
    petId: pet.pet_id,
    name: pet.name,
    species: pet.species,
    photoUrl: pet.avatar_url ?? fallbackPhoto,
    relation: pet.relation,
    home: pet.home ? { center: pet.home.center, precisionM: pet.home.precision_m, label: pet.home.label } : null,
    activity: {
      kind: a.kind,
      phase: a.phase,
      pose: a.pose,
      title: a.title,
      doing: a.doing,
      place: a.place ? { name: a.place.name, lat: a.place.lat, lng: a.place.lng } : null,
      since: time(a.since),
      until: time(a.until),
      job: a.job,
      journeyId: a.journey_id ?? null,
      visitId: a.visit_id ?? null,
    },
    leg: legOf(pet),
    position: pet.position ? { lat: pet.position.lat, lng: pet.position.lng } : null,
    basis: pet.position?.basis ?? "unknown",
    version: pet.version ?? 0,
  };
}

export function sceneFromWorldState(state: WorldState, householdPhotos: ReadonlyMap<string, string | null> = new Map()): WorldScene {
  return { pets: state.pets.map((pet) => worldPetFromState(pet, householdPhotos.get(pet.pet_id) ?? null)), source: "facts", catchingUp: false };
}

/** 地图先看哪一只：当前选中的家庭宠物 → 自己的第一只 → 第一只。 */
export function focusPetId(scene: WorldScene, currentPetId: string | null | undefined): string | null {
  if (currentPetId && scene.pets.some((p) => p.petId === currentPetId)) return currentPetId;
  return scene.pets.find((p) => p.relation === "mine")?.petId ?? scene.pets[0]?.petId ?? null;
}
