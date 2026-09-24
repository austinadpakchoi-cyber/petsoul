import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import type { LatLng, PublicResident } from "@/shared/contracts";
import { MapAnchor, SchematicMapSurface } from "@/shared/map";
import { Icon, Sheet } from "@/shared/ui";
import { PawMark, petPortraitUrl } from "./PetPortrait";

const SPECIES_NAMES: Record<string, string> = { cat: "猫", dog: "狗", rabbit: "兔子", hamster: "仓鼠", bird: "鸟", parrot: "鹦鹉", other: "动物" };

/**
 * 居民驿站在世界里的概念位置：与后端迁移 m0240_residents 写入 web_residences 的坐标一致（片区里的概念地点，不对应门牌）。
 * 公开接口目前不下发任何坐标（见本窗口 CHANGE_REQUEST）；接口补上居民实时位置后，以接口为准并删除这张表。
 */
const STATION_ANCHORS: Record<string, LatLng> = {
  "星球居民驿站·中环": { lat: 22.2819, lng: 114.1581 },
  "星球居民驿站·西贡海边": { lat: 22.3818, lng: 114.2719 },
};

export interface PlanetPin {
  resident: PublicResident;
  /** 驿站概念点；位置依据只是“住在哪个驿站”，不是实时定位。 */
  at: LatLng;
  /** 围着驿站排开的屏幕像素偏移：同一驿站的居民在任何缩放下都不互相压住。 */
  offset: { x: number; y: number };
}

export interface PlanetStation {
  name: string;
  at: LatLng;
  pins: PlanetPin[];
}

function clusterOffsets(count: number): Array<{ x: number; y: number }> {
  if (count === 1) return [{ x: 0, y: 0 }];
  const radius = Math.min(104, 56 + count * 6);
  return Array.from({ length: count }, (_, index) => {
    const angle = (2 * Math.PI * index) / count - Math.PI / 2;
    return { x: Math.round(radius * Math.cos(angle)), y: Math.round(radius * 0.82 * Math.sin(angle)) };
  });
}

export function planetStations(residents: PublicResident[]): { stations: PlanetStation[]; unplaced: PublicResident[] } {
  const groups = new Map<string, PublicResident[]>();
  const unplaced: PublicResident[] = [];
  for (const resident of residents) {
    if (!STATION_ANCHORS[resident.residence]) unplaced.push(resident);
    else groups.set(resident.residence, [...(groups.get(resident.residence) ?? []), resident]);
  }
  const stations = [...groups.entries()].map(([name, members]) => {
    const at = STATION_ANCHORS[name];
    const offsets = clusterOffsets(members.length);
    return { name, at, pins: members.map((resident, index) => ({ resident, at, offset: offsets[index] })) };
  });
  return { stations, unplaced };
}

/** 气泡只说服务端给的真实状态：此刻在做什么，或 TA 最近一条公开动态。 */
export function bubbleText(resident: PublicResident, round: number): string {
  const post = resident.recent_posts[0]?.text?.trim();
  if (post && round % 2 === 1) return `“${post.length > 38 ? `${post.slice(0, 38)}…` : post}”`;
  const where = resident.place_name ?? (resident.presence === "at_home" ? null : resident.city);
  return where ? `${resident.doing} · ${where}` : resident.doing;
}

function usePrefersReducedMotion(): boolean {
  const [reduce, setReduce] = useState(() => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduce(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return reduce;
}

/** 居民头像：还没有公开照片字段——演示模式用授权小灰猫，live 用爪印占位；不写名字首字。 */
function ResidentMark() {
  const src = petPortraitUrl(null);
  return src ? <img src={src} alt="" aria-hidden="true" /> : <PawMark size={18} />;
}

/** 点中后的轻量相遇卡：此刻、性格、小愿望、最近一条公开小事。不是领养页；想多了解再进 TA 的公开手账。 */
export function EncounterCard({ resident, onClose }: { resident: PublicResident; onClose: () => void }) {
  const post = resident.recent_posts[0] ?? null;
  const where = resident.place_name ?? (resident.presence === "at_home" ? resident.residence : resident.city);
  return (
    <Sheet title={<span className="ps-encounter__title">和 {resident.name} 打了个照面</span>} subtitle={`星球居民 · ${SPECIES_NAMES[resident.species] ?? "动物"}`} onClose={onClose} className="ps-encounter">
      <div className="ps-encounter__body" data-testid="encounter-card">
        <div className="ps-encounter__who">
          <span className="ps-encounter__portrait" aria-label={`${resident.name}暂无公开照片`}><ResidentMark /><small>暂无公开照片</small></span>
          <div>
            <span className="ps-encounter__now"><i aria-hidden="true" className={resident.presence === "at_home" ? "is-home" : "is-out"} />此刻</span>
            <strong>{resident.doing}</strong>
            <small>{where}</small>
          </div>
        </div>
        <p className="ps-encounter__line">{resident.personality}</p>
        {resident.dream ? <p className="ps-encounter__dream"><span>TA 的小愿望</span>{resident.dream}</p> : null}
        {post ? <blockquote className="ps-encounter__post">{post.text}</blockquote> : null}
        <Link className="ps-encounter__more" to={`/world/residents/${encodeURIComponent(resident.pet_id)}`}>
          看看 TA 的公开手账 <Icon name="chevron" size={15} />
        </Link>
      </div>
    </Sheet>
  );
}

export function PlanetMap({ residents, onEncounter, paused, realBasemap }: { residents: PublicResident[]; onEncounter: (resident: PublicResident) => void; paused: boolean; realBasemap: boolean }) {
  const { stations } = useMemo(() => planetStations(residents), [residents]);
  const pins = useMemo(() => stations.flatMap((station) => station.pins), [stations]);
  const reduceMotion = usePrefersReducedMotion();
  const [turn, setTurn] = useState(0);
  useEffect(() => {
    if (paused || pins.length === 0) return undefined;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") setTurn((value) => value + 1);
    }, reduceMotion ? 9000 : 5200);
    return () => window.clearInterval(timer);
  }, [paused, pins.length, reduceMotion]);
  const bounds = useMemo<LatLng[]>(() => {
    const points = stations.length ? stations.map((station) => station.at) : Object.values(STATION_ANCHORS);
    // 只有一处驿站时也留出周边，免得地图缩到一个点上。
    const pad = 0.035;
    const lats = points.map((p) => p.lat);
    const lngs = points.map((p) => p.lng);
    return [{ lat: Math.min(...lats) - pad, lng: Math.min(...lngs) - pad }, { lat: Math.max(...lats) + pad, lng: Math.max(...lngs) + pad }];
  }, [stations]);
  const speaking = pins.length ? pins[turn % pins.length] : null;
  return (
    <SchematicMapSurface bounds={bounds} routes={[]} places={[]} realBasemap={realBasemap} label="星球示意图">
      {stations.map((station) => (
        <MapAnchor key={station.name} at={station.at} z={1}>
          <span className="ps-planet-station" aria-hidden="true"><i />{station.name.replace("星球居民驿站·", "")} 驿站</span>
        </MapAnchor>
      ))}
      {pins.map((pin) => (
        <MapAnchor key={pin.resident.pet_id} at={pin.at} offsetX={pin.offset.x} offsetY={pin.offset.y} z={pin === speaking ? 4 : 2}>
          <button
            type="button"
            className={`ps-planet-pin${pin.resident.presence === "at_home" ? " is-home" : " is-out"}${pin === speaking ? " is-speaking" : ""}`}
            data-map-interactive
            data-testid="planet-pin"
            aria-label={`${pin.resident.name}，${pin.resident.doing}，驿站一带，打开相遇卡`}
            onClick={() => onEncounter(pin.resident)}
          >
            <span className="ps-planet-pin__avatar"><ResidentMark /></span>
            <span className="ps-planet-pin__name">{pin.resident.name}</span>
          </button>
        </MapAnchor>
      ))}
      {speaking && !paused ? (
        <MapAnchor at={speaking.at} offsetX={speaking.offset.x} offsetY={speaking.offset.y} z={5}>
          <button
            key={`${speaking.resident.pet_id}-${turn}`}
            type="button"
            className="ps-planet-bubble"
            data-map-interactive
            data-testid="planet-bubble"
            onClick={() => onEncounter(speaking.resident)}
          >
            <span className="ps-planet-bubble__who">{speaking.resident.name}</span>
            <span className="ps-planet-bubble__text">{bubbleText(speaking.resident, Math.floor(turn / pins.length))}</span>
          </button>
        </MapAnchor>
      ) : null}
    </SchematicMapSurface>
  );
}
