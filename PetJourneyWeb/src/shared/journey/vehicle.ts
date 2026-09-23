/**
 * 交通段进度与车辆位置（与后端 app/transport_world/timeline.py 同语义）。
 * 只用于呈现：进度由服务器时间与已确认时间线决定；打开网页、媒体播放、金币都不影响交通时长。
 */
import type { JourneyLeg, JourneyMapSnapshot, LatLng, LegTimes, TransportMode } from "@/shared/contracts";

export function effectiveDeparture(times: LegTimes): number {
  return Date.parse(times.actual_departure_utc ?? times.estimated_departure_utc ?? times.planned_departure_utc);
}

export function effectiveArrival(times: LegTimes): number {
  return Date.parse(times.actual_arrival_utc ?? times.estimated_arrival_utc ?? times.planned_arrival_utc);
}

export function legProgress(times: LegTimes, nowMs: number): number {
  const start = effectiveDeparture(times);
  const end = effectiveArrival(times);
  const total = end - start;
  if (total <= 0) return nowMs >= end ? 1 : 0;
  return Math.min(1, Math.max(0, (nowMs - start) / total));
}

export function remainingMs(times: LegTimes, nowMs: number): number {
  return Math.max(0, effectiveArrival(times) - nowMs);
}

function haversine(a: LatLng, b: LatLng): number {
  const r = 6_371_000;
  const p1 = (a.lat * Math.PI) / 180;
  const p2 = (b.lat * Math.PI) / 180;
  const dp = p2 - p1;
  const dl = ((b.lng - a.lng) * Math.PI) / 180;
  const h = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(h));
}

export function positionAlong(route: LatLng[], progress: number): { point: LatLng; heading: number } {
  if (route.length === 0) throw new Error("route is empty");
  if (route.length === 1) return { point: route[0], heading: 0 };
  const lengths = route.slice(0, -1).map((p, i) => haversine(p, route[i + 1]));
  const total = lengths.reduce((s, v) => s + v, 0) || 1;
  const target = Math.min(Math.max(progress, 0), 1) * total;
  let walked = 0;
  for (let i = 0; i < lengths.length; i += 1) {
    const a = route[i];
    const b = route[i + 1];
    const seg = lengths[i];
    if (walked + seg >= target || i === lengths.length - 1) {
      const ratio = seg === 0 ? 0 : Math.min(Math.max((target - walked) / seg, 0), 1);
      const heading = ((Math.atan2(b.lng - a.lng, b.lat - a.lat) * 180) / Math.PI + 360) % 360;
      return { point: { lat: a.lat + (b.lat - a.lat) * ratio, lng: a.lng + (b.lng - a.lng) * ratio }, heading };
    }
    walked += seg;
  }
  return { point: route[route.length - 1], heading: 0 };
}

export function currentLeg(snapshot: JourneyMapSnapshot): JourneyLeg | undefined {
  return snapshot.legs.find((leg) => leg.leg_id === snapshot.current_leg_id) ?? snapshot.legs[0];
}

export function legRoute(leg: JourneyLeg): LatLng[] {
  if (leg.route.length >= 2) return leg.route;
  const nodes = [leg.origin, leg.destination].filter((n) => n.lat !== null && n.lng !== null);
  return nodes.map((n) => ({ lat: n.lat as number, lng: n.lng as number }));
}

/** 车辆当前呈现位置：优先按服务器时间 + 路线插值（平滑），无路线时退回快照中的位置。 */
export function vehicleAnchorAt(snapshot: JourneyMapSnapshot, nowMs: number): { legId: string; point: LatLng; heading: number; progress: number } | null {
  const leg = currentLeg(snapshot);
  if (!leg) return null;
  const route = legRoute(leg);
  const progress = legProgress(leg.times, nowMs);
  if (route.length >= 1) {
    const { point, heading } = positionAlong(route, progress);
    return { legId: leg.leg_id, point, heading, progress };
  }
  if (snapshot.vehicle) {
    return { legId: leg.leg_id, point: { lat: snapshot.vehicle.lat, lng: snapshot.vehicle.lng }, heading: snapshot.vehicle.heading_deg, progress };
  }
  return null;
}

export const MODE_LABEL: Record<TransportMode, string> = {
  flight: "飞机",
  train: "火车",
  ferry: "轮船",
  drive: "自驾",
  taxi: "出租车",
  transit: "公共交通",
  walk: "步行",
};

/** 行程标题：有动物世界班次身份就显示承运人+班次号；出租车/步行/自驾不伪造班次，只写交通方式。 */
export function legTitle(leg: JourneyLeg): string {
  if (leg.world_service) return `${leg.world_service.carrier_name} ${leg.world_service.service_code}`;
  if (leg.mode === "walk") return "步行前往";
  if (leg.mode === "taxi") return "打车前往";
  if (leg.mode === "drive") return "自驾出行";
  return MODE_LABEL[leg.mode];
}
