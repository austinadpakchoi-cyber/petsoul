/**
 * 演示剧本：fixture 模式下让地图首页能完整看到“TA 在生活”——在家 → 附近走走 → 回家 → 喝一杯 → 回家 → 去打工 → 收工回家，循环。
 * 只在 fixture 模式由页面按需 import；live 模式永远不会用到这里（live 只认后端事实）。
 * 宠物身份沿用 fixture 世界的样板宠物，保证进小窝看到的是同一只；页面上始终挂“演示剧本”标记。
 * 剧本时间可以加速（演示时钟），路线和时长按高德真实步行估时。
 */
import { fixturePet } from "@/fixtures/world";
import { DEMO_HOME, DEMO_ROUTE_BEACH, DEMO_ROUTE_CAFE, DEMO_ROUTE_HARBOR } from "./demoGeometry";
import type { ActivityKind, ActivityPhase, MapLatLng, PetPose, WorldPet, WorldScene } from "./model";

type Route = { durationS: number; route: Array<[number, number]> };

interface Segment {
  kind: ActivityKind;
  phase: ActivityPhase;
  /** 这一段的姿态：演示剧本逐段写明（相当于后台给的 activity.pose），不从 doing 文字里猜。 */
  pose: PetPose;
  minutes: number;
  title: string;
  doing: string | null;
  place: { name: string; route: Route } | null;
  job?: { title: string; pay: number; paid: boolean };
}

const toLatLng = ([lat, lng]: [number, number]): MapLatLng => ({ lat, lng });
const HOME = toLatLng(DEMO_HOME);
const BEACH = { name: "海边步道", route: DEMO_ROUTE_BEACH };
const CAFE = { name: "街角的咖啡馆", route: DEMO_ROUTE_CAFE };
const HARBOR = { name: "渔港", route: DEMO_ROUTE_HARBOR };
const JOB = { title: "渔港帮工", pay: 25 };
const walkMinutes = (route: Route) => route.durationS / 60;

/** 一天的剧本（真实时长，单位分钟）。走路的时长就是高德步行估时。 */
export const DEMO_DAY: readonly Segment[] = [
  { kind: "home", phase: "home", pose: "sleeping", minutes: 20, title: "在小窝", doing: "在窝里打盹", place: null },
  { kind: "stroll", phase: "going", pose: "walking", minutes: walkMinutes(BEACH.route), title: "在家附近走走", doing: "慢慢往海边走", place: BEACH },
  { kind: "stroll", phase: "there", pose: "exploring", minutes: 25, title: "在家附近走走", doing: "在海边看浪", place: BEACH },
  { kind: "stroll", phase: "returning", pose: "walking", minutes: walkMinutes(BEACH.route), title: "在家附近走走", doing: null, place: BEACH },
  { kind: "home", phase: "home", pose: "eating", minutes: 15, title: "在小窝", doing: "在吃饭", place: null },
  { kind: "cafe", phase: "going", pose: "walking", minutes: walkMinutes(CAFE.route), title: "去附近喝一杯", doing: null, place: CAFE },
  { kind: "cafe", phase: "there", pose: "cafe", minutes: 25, title: "去附近喝一杯", doing: "在窗边坐着，看路上的人", place: CAFE },
  { kind: "cafe", phase: "returning", pose: "walking", minutes: walkMinutes(CAFE.route), title: "去附近喝一杯", doing: null, place: CAFE },
  { kind: "home", phase: "home", pose: "sunbathing", minutes: 12, title: "在小窝", doing: "在院子里晒太阳", place: null },
  { kind: "job", phase: "going", pose: "walking", minutes: walkMinutes(HARBOR.route), title: "去渔港帮忙收网", doing: null, place: HARBOR, job: { ...JOB, paid: false } },
  { kind: "job", phase: "there", pose: "working", minutes: 90, title: "去渔港帮忙收网", doing: "帮渔船收网、理渔具", place: HARBOR, job: { ...JOB, paid: false } },
  { kind: "job", phase: "returning", pose: "walking", minutes: walkMinutes(HARBOR.route), title: "去渔港帮忙收网", doing: null, place: HARBOR, job: { ...JOB, paid: true } },
  { kind: "home", phase: "home", pose: "sleeping", minutes: 30, title: "在小窝", doing: "在窝里打盹", place: null },
];

const DAY_MS = DEMO_DAY.reduce((sum, s) => sum + s.minutes * 60_000, 0);

/** 剧本里第 index 段的起点（相对一天开头，毫秒）。 */
export function segmentStart(index: number): number {
  return DEMO_DAY.slice(0, index).reduce((sum, s) => sum + s.minutes * 60_000, 0);
}

export function demoDayLength(): number {
  return DAY_MS;
}

/** 演示时刻落在第几段（循环）。 */
export function segmentAt(offsetMs: number): { index: number; start: number; end: number } {
  const within = ((offsetMs % DAY_MS) + DAY_MS) % DAY_MS;
  let start = 0;
  for (let i = 0; i < DEMO_DAY.length; i += 1) {
    const end = start + DEMO_DAY[i].minutes * 60_000;
    if (within < end) return { index: i, start: offsetMs - within + start, end: offsetMs - within + end };
    start = end;
  }
  return { index: 0, start: offsetMs - within, end: offsetMs - within + DEMO_DAY[0].minutes * 60_000 };
}

/** 演示时钟 nowMs 下的世界。dayStartMs 是剧本“一天”的起点（演示时钟坐标）。 */
export function demoScene(nowMs: number, dayStartMs: number): WorldScene {
  const { index, start, end } = segmentAt(nowMs - dayStartMs);
  const seg = DEMO_DAY[index];
  const since = dayStartMs + start;
  const until = dayStartMs + end;
  const placeRoute = seg.place ? seg.place.route.route.map(toLatLng) : [];
  const destination = placeRoute.length ? placeRoute[placeRoute.length - 1] : null;
  const legRoute = seg.phase === "going" ? placeRoute : seg.phase === "returning" ? placeRoute.slice().reverse() : [];
  const pet: WorldPet = {
    petId: fixturePet.pet_id,
    name: fixturePet.name,
    species: fixturePet.species,
    photoUrl: fixturePet.photo_url,
    relation: "mine",
    home: { center: HOME, precisionM: 600, label: "环岛路附近的海边" },
    activity: {
      kind: seg.kind,
      phase: seg.phase,
      pose: seg.pose,
      title: seg.title,
      doing: seg.doing,
      place: seg.place && destination ? { name: seg.place.name, ...destination } : null,
      since,
      until,
      job: seg.job ?? null,
      // 演示剧本这一步不接行程快照（只做 live）：不编 journey / 到访编号。
      journeyId: null,
      visitId: null,
    },
    leg: legRoute.length ? { mode: "walk", route: legRoute, departsAt: since, arrivesAt: until } : null,
    position: seg.phase === "there" ? destination : seg.phase === "home" ? HOME : null,
    basis: seg.phase === "home" ? "home_area" : seg.phase === "there" ? "place" : "route",
    version: 0,
  };
  return { pets: [pet], source: "demo", catchingUp: false };
}
