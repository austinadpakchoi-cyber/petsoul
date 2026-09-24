/**
 * 平行交通 fixture：飞/铁/船/驾四类 + 暂停/失败/到站变体。
 * 全部 time_basis=demo_fixture：不是已核验时刻表，不对应任何真实班次；承运人名称（喵航 Cat222 等）
 * 是原创动物世界身份示例。起终点坐标仅用于示意地图定位。
 * 时间相对页面加载时刻（world.fixtureEpoch），按真实经过时间推进，不压缩。
 */
import type {
  JourneyLeg,
  JourneyMapSnapshot,
  LatLng,
  MapActivityEntry,
  PetArrivalContext,
  TransportMode,
  TransportNode,
  TravelActivity,
  TravellerRole,
  WorldService,
} from "@/shared/contracts";
import { atMin, atSec } from "./world";

const N = {
  hkg: { node_id: "fx-node-hkg", name: "香港机场（示意）", kind: "airport", timezone: "Asia/Hong_Kong", lat: 22.308, lng: 113.918, verified: false },
  hnd: { node_id: "fx-node-hnd", name: "东京羽田（示意）", kind: "airport", timezone: "Asia/Tokyo", lat: 35.549, lng: 139.779, verified: false },
  gzs: { node_id: "fx-node-gzs", name: "广州南站（示意）", kind: "station", timezone: "Asia/Shanghai", lat: 22.99, lng: 113.269, verified: false },
  wkl: { node_id: "fx-node-wkl", name: "香港西九龙（示意）", kind: "station", timezone: "Asia/Hong_Kong", lat: 22.304, lng: 114.166, verified: false },
  cen: { node_id: "fx-node-central", name: "中环码头（示意）", kind: "port", timezone: "Asia/Hong_Kong", lat: 22.287, lng: 114.157, verified: false },
  mfm: { node_id: "fx-node-macau", name: "澳门码头（示意）", kind: "port", timezone: "Asia/Macau", lat: 22.197, lng: 113.557, verified: false },
  hkc: { node_id: "fx-node-hk-city", name: "香港市区（示意）", kind: "road_point", timezone: "Asia/Hong_Kong", lat: 22.282, lng: 114.158, verified: false },
  szb: { node_id: "fx-node-sz-bay", name: "深圳湾（示意）", kind: "road_point", timezone: "Asia/Shanghai", lat: 22.515, lng: 113.944, verified: false },
} satisfies Record<string, TransportNode>;

const SERVICES: Record<string, WorldService> = {
  cat222: { world_service_id: "fx-ws-cat222", carrier_name: "喵航", service_code: "Cat222", mode: "flight", vehicle_style: "橘色机尾", reference_id: null, mapping_version: 1 },
  paw318: { world_service_id: "fx-ws-paw318", carrier_name: "爪爪铁路", service_code: "Paw318", mode: "train", vehicle_style: "奶白车厢", reference_id: null, mapping_version: 1 },
  otter08: { world_service_id: "fx-ws-otter08", carrier_name: "海獭轮渡", service_code: "Otter08", mode: "ferry", vehicle_style: "蓝白船身", reference_id: null, mapping_version: 1 },
};

function arc(a: LatLng, b: LatLng, bulge: number, steps = 16): LatLng[] {
  const points: LatLng[] = [];
  for (let i = 0; i <= steps; i += 1) {
    const t = i / steps;
    const lift = Math.sin(Math.PI * t) * bulge;
    points.push({ lat: a.lat + (b.lat - a.lat) * t + lift, lng: a.lng + (b.lng - a.lng) * t });
  }
  return points;
}

function ll(node: TransportNode): LatLng {
  return { lat: node.lat as number, lng: node.lng as number };
}

interface LegSeed {
  id: string;
  mode: TransportMode;
  role: TravellerRole;
  service: WorldService | null;
  from: TransportNode;
  to: TransportNode;
  departMin: number;
  arriveMin: number;
  route: LatLng[];
  schematic: boolean;
  arrived?: boolean;
}

function leg(seed: LegSeed): JourneyLeg {
  return {
    leg_id: seed.id,
    journey_id: "fx-journey-001",
    sequence: 1,
    kind: "main",
    mode: seed.mode,
    role: seed.role,
    world_service: seed.service,
    origin: seed.from,
    destination: seed.to,
    times: {
      origin_timezone: seed.from.timezone,
      destination_timezone: seed.to.timezone,
      planned_departure_utc: atMin(seed.departMin),
      planned_arrival_utc: atMin(seed.arriveMin),
      estimated_departure_utc: null,
      estimated_arrival_utc: null,
      actual_departure_utc: null,
      actual_arrival_utc: null,
    },
    time_basis: "demo_fixture",
    freshness: "unavailable",
    position_basis: seed.schematic ? "schematic" : "simulated_route",
    phase: seed.arrived ? "arrived" : "in_transit",
    itinerary_version: 1,
    route: seed.route,
    reference: { reference_id: null, time_basis: "demo_fixture", freshness: "unavailable", source_label: "演示行程，非真实班次", verified_at: null },
    rescheduled_reason: null,
  };
}

function activity(id: string, legId: string, kind: TravelActivity["kind"], state: TravelActivity["state"], startSec: number, endSec: number | null, sessionId: string | null): TravelActivity {
  return { activity_id: id, leg_id: legId, kind, state, starts_at: atSec(startSec), ends_at: endSec === null ? null : atSec(endSec), media_session_id: sessionId, interruptible: true, version: 1 };
}

function entry(a: TravelActivity, label: string, badge: "music" | "tv"): MapActivityEntry {
  return {
    entry_id: `entry-${a.activity_id}`,
    leg_id: a.leg_id,
    activity_id: a.activity_id,
    badge,
    badge_state: a.state,
    media_session_id: a.media_session_id,
    label,
    actions: a.state === "interrupted" ? ["solo", "open_leg_card"] : ["join", "solo", "open_leg_card"],
  };
}

function arrival(legSeed: LegSeed, city: string): PetArrivalContext {
  return {
    journey_id: "fx-journey-001",
    itinerary_version: 1,
    leg_id: legSeed.id,
    city,
    destination_timezone: legSeed.to.timezone,
    feasible_arrival_utc: atMin(legSeed.arriveMin + 20),
    stay_window_start_utc: atMin(legSeed.arriveMin + 30),
    stay_window_end_utc: atMin(legSeed.arriveMin + 150),
  };
}

export interface FixtureScenario {
  id: string;
  label: string;
  build: (nowMs: number) => JourneyMapSnapshot;
}

function snapshot(legSeed: LegSeed, activities: TravelActivity[], entries: MapActivityEntry[], arrivalCity: string | null, nowMs: number): JourneyMapSnapshot {
  const theLeg = leg(legSeed);
  // 活动是否仍在进行由服务器时间决定：结束后徽标消失（fixture 在此模拟服务端的活动窗口）。
  const liveActivities = activities.map((a) => (a.ends_at && Date.parse(a.ends_at) <= nowMs && a.state === "active" ? { ...a, state: "ended" as const } : a));
  const liveEntries = entries.filter((e) => liveActivities.find((a) => a.activity_id === e.activity_id)?.state !== "ended");
  return {
    journey_id: "fx-journey-001",
    pet_id: "fx-pet-001",
    itinerary_version: 1,
    lifecycle: "active",
    destination_title: arrivalCity ? `去${arrivalCity}（演示）` : "演示旅程",
    current_visit_id: null,
    planned_visit_id: "fx-visit-001",
    server_time: new Date(nowMs).toISOString(),
    legs: [theLeg],
    current_leg_id: theLeg.leg_id,
    vehicle: null,
    activities: liveActivities,
    activity_entries: liveEntries,
    arrival_context: arrivalCity ? arrival(legSeed, arrivalCity) : null,
    data_origin: "fixture",
  };
}

const flightSeed: LegSeed = { id: "fx-leg-flight", mode: "flight", role: "passenger", service: SERVICES.cat222, from: N.hkg, to: N.hnd, departMin: -60, arriveMin: 180, route: arc(ll(N.hkg), ll(N.hnd), 3.2), schematic: true };
const trainSeed: LegSeed = {
  id: "fx-leg-train",
  mode: "train",
  role: "passenger",
  service: SERVICES.paw318,
  from: N.gzs,
  to: N.wkl,
  departMin: -25,
  arriveMin: 22,
  route: [ll(N.gzs), { lat: 22.83, lng: 113.5 }, { lat: 22.6, lng: 113.86 }, { lat: 22.45, lng: 114.05 }, ll(N.wkl)],
  schematic: false,
};
const ferrySeed: LegSeed = { id: "fx-leg-ferry", mode: "ferry", role: "passenger", service: SERVICES.otter08, from: N.cen, to: N.mfm, departMin: -30, arriveMin: 30, route: [ll(N.cen), { lat: 22.26, lng: 113.98 }, { lat: 22.22, lng: 113.72 }, ll(N.mfm)], schematic: false };
const driveSeed: LegSeed = { id: "fx-leg-drive", mode: "drive", role: "driver", service: null, from: N.hkc, to: N.szb, departMin: -12, arriveMin: 40, route: [ll(N.hkc), { lat: 22.33, lng: 114.1 }, { lat: 22.42, lng: 114.03 }, { lat: 22.48, lng: 113.98 }, ll(N.szb)], schematic: false };

export const FIXTURE_SCENARIOS: FixtureScenario[] = [
  {
    id: "flight",
    label: "飞机·听歌",
    build: (now) => {
      // 听歌活动约 140 秒后结束 → 音符消失（验证“活动结束后更新图标”），之后是休息（无徽标）。
      const music = activity("fx-act-flight-music", flightSeed.id, "listening", "active", -20 * 60, 140, "fx-ms-flight");
      const rest = activity("fx-act-flight-rest", flightSeed.id, "resting", "active", 60, null, null);
      return snapshot(flightSeed, [music, rest], [entry(music, "TA 在听《窗边的小调》", "music")], null, now);
    },
  },
  {
    id: "train",
    label: "火车·看剧",
    build: (now) => {
      const video = activity("fx-act-train-video", trainSeed.id, "watching", "active", -5 * 60, 85, "fx-ms-train");
      return snapshot(trainSeed, [video], [entry(video, "TA 在看《云上色块》", "tv")], "香港", now);
    },
  },
  {
    id: "ferry",
    label: "轮船·无活动",
    build: (now) => snapshot(ferrySeed, [activity("fx-act-ferry-gaze", ferrySeed.id, "window_gazing", "active", -10 * 60, null, null)], [], "澳门", now),
  },
  {
    id: "drive",
    label: "驾车·只听",
    build: (now) => {
      const music = activity("fx-act-drive-music", driveSeed.id, "listening", "active", -5, null, "fx-ms-drive");
      return snapshot(driveSeed, [music], [entry(music, "TA 边开车边听歌", "music")], null, now);
    },
  },
  {
    id: "paused",
    label: "暂停",
    build: (now) => {
      const music = activity("fx-act-paused-music", flightSeed.id, "listening", "paused", -10 * 60, null, "fx-ms-paused");
      return snapshot(flightSeed, [music], [entry(music, "和 TA 一起暂停了", "music")], null, now);
    },
  },
  {
    id: "failed",
    label: "加载失败",
    build: (now) => {
      const video = activity("fx-act-failed-video", trainSeed.id, "watching", "active", -60, null, "fx-ms-failed");
      return snapshot(trainSeed, [video], [entry(video, "TA 在看纪录片", "tv")], "香港", now);
    },
  },
  {
    id: "arrived",
    label: "到站·已保存",
    build: (now) => {
      const arrivedSeed: LegSeed = { ...ferrySeed, id: "fx-leg-ferry-arrived", departMin: -70, arriveMin: -3, arrived: true };
      const video = activity("fx-act-arrived-video", arrivedSeed.id, "watching", "interrupted", -40 * 60, -3 * 60, "fx-ms-arrived");
      return snapshot(arrivedSeed, [video], [entry(video, "到站了，这集晚上接着看", "tv")], "澳门", now);
    },
  },
];

export const DEFAULT_SCENARIO = "flight";
