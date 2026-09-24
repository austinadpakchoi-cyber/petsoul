/**
 * 地图首页的世界状态（前端视图模型），与 W1 统一世界状态（契约 WorldState）一一对应：
 * 每只宠物给出此刻的活动（种类 + 阶段 + 姿态）、所在或正在走的路、以及位置依据。
 * 数据来自两处：live 读 W1（./worldState 只做形状转换）；fixture 由演示剧本生成（./demoScript，页面明示“演示”）。
 * 坐标一律 WGS-84；画到高德上时再换算（./coords）。
 */
import type { PetMood } from "@/features/pets/PetMoodAvatar";
import { distanceMeters } from "./coords";

export interface MapLatLng {
  lat: number;
  lng: number;
}

/** 活动种类：在家、附近走走、去喝一杯、打工、进城、自驾、远行。 */
export type ActivityKind = "home" | "stroll" | "cafe" | "job" | "city_trip" | "drive_trip" | "trip";
/** 阶段：在家 / 去的路上 / 到了 / 回家的路上 / 不知道。“准备去打工”只能是 going，不能显示成“在打工”。 */
export type ActivityPhase = "home" | "going" | "there" | "returning" | "unknown";
export type TravelMode = "walk" | "taxi" | "drive" | "bus" | "other";
/** 位置依据：家附近的模糊区域 / 到访地点 / 沿路线按时间推算 / 不知道（不画点）。 */
export type MapPositionBasis = "home_area" | "place" | "route" | "unknown";

/**
 * TA 此刻的姿态（结构化事实，驱动地图上的状态表情：睡觉冒 zzz、走路有步态……）。对所有宠物通用，不从文字里猜。
 * live 来自 W1 的 activity.pose（后端只给事实能确定的：作息接不上是 idle 不是 sleeping；在路上读不出交通方式是 unknown）；
 * 演示剧本逐段写明。sleeping / eating / sunbathing / walking 与契约 CharacterPose 同名，以后可换成 TA 自己的姿态图。
 */
export type PetPose = PetMood;

export interface MapLeg {
  mode: TravelMode;
  /** 道路几何；空数组表示没有几何（不画路线，也不假装沿路走）。 */
  route: MapLatLng[];
  departsAt: number;
  arrivesAt: number;
}

export interface MapPlace {
  name: string;
  lat: number;
  lng: number;
}

export interface MapActivity {
  kind: ActivityKind;
  phase: ActivityPhase;
  /** 此刻的姿态（见 PetPose）；地图状态表情只看它。 */
  pose: PetPose;
  /** 这件事的叫法，例如“在家附近走走”“去渔港帮忙收网”。 */
  title: string;
  /** TA 此刻在做的一件小事（来自后端状态文字）；没有就不编。 */
  doing: string | null;
  place: MapPlace | null;
  /** 这一阶段开始 / 预计结束（毫秒）；不知道为 null。 */
  since: number | null;
  until: number | null;
  job: { title: string; pay: number; paid: boolean } | null;
  /** 这一趟（W1 activity.journey_id）：出门期间（走走、喝一杯、打工、进城、远行）一直有值，在家为 null。行程快照按它对齐。 */
  journeyId: string | null;
  /** 到访（W1 activity.visit_id）：到店前（计划中）也可能有值——“在店里”要同时看 phase === "there"。 */
  visitId: string | null;
}

export interface WorldPet {
  petId: string;
  name: string;
  species: string;
  photoUrl: string | null;
  relation: "mine" | "household";
  /** 家的大概位置（片区附近的模糊点，不对应门牌）与模糊半径；只给自家成员。 */
  home: { center: MapLatLng; precisionM: number; label: string } | null;
  activity: MapActivity;
  /** 正在走的这一段（going / returning 才有）。 */
  leg: MapLeg | null;
  position: MapLatLng | null;
  basis: MapPositionBasis;
  /** W1 这只宠物的状态版本（后台每记一件事就变）；行程快照据它和阶段、截止时刻判断要不要重读。演示为 0。 */
  version: number;
}

export interface WorldScene {
  pets: WorldPet[];
  source: "facts" | "demo";
  /** 后端说有已经到期、还没结算到的事实（工资、来信稍后出现），不是出错。 */
  catchingUp: boolean;
}

export function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

/** 按时间算这一段走了多少（0–1）。 */
export function legProgress(leg: MapLeg, nowMs: number): number {
  const span = leg.arrivesAt - leg.departsAt;
  if (span <= 0) return nowMs >= leg.arrivesAt ? 1 : 0;
  return clamp01((nowMs - leg.departsAt) / span);
}

/** 沿路线按距离比例取点；同时给出已经走过的那一截（画“走过的路”）。 */
export function alongRoute(route: MapLatLng[], progress: number): { point: MapLatLng; passed: MapLatLng[] } | null {
  if (route.length === 0) return null;
  if (route.length === 1) return { point: route[0], passed: [route[0]] };
  const seg: number[] = [];
  let total = 0;
  for (let i = 1; i < route.length; i += 1) {
    const d = distanceMeters(route[i - 1], route[i]);
    seg.push(d);
    total += d;
  }
  const target = clamp01(progress) * total;
  let walked = 0;
  for (let i = 0; i < seg.length; i += 1) {
    if (walked + seg[i] >= target) {
      const t = seg[i] === 0 ? 0 : (target - walked) / seg[i];
      const a = route[i];
      const b = route[i + 1];
      const point = { lat: a.lat + (b.lat - a.lat) * t, lng: a.lng + (b.lng - a.lng) * t };
      return { point, passed: [...route.slice(0, i + 1), point] };
    }
    walked += seg[i];
  }
  const last = route[route.length - 1];
  return { point: last, passed: route.slice() };
}

/** 此刻该画在哪：走在路上的按时间沿路线推（客户端只做平滑，不决定到没到）；其余用给定位置。 */
export function positionAt(pet: WorldPet, nowMs: number): MapLatLng | null {
  if (pet.leg && pet.leg.route.length > 0 && (pet.activity.phase === "going" || pet.activity.phase === "returning")) {
    return alongRoute(pet.leg.route, legProgress(pet.leg, nowMs))?.point ?? pet.position;
  }
  return pet.position;
}

export function minutesLeft(until: number | null, nowMs: number): number | null {
  if (until == null) return null;
  return Math.max(0, Math.ceil((until - nowMs) / 60_000));
}
