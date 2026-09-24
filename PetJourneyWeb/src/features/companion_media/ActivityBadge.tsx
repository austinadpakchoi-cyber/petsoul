import type { MapActivityEntry } from "@/shared/contracts";
import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { MapAnchor } from "@/shared/map";
import { vehicleAnchorAt } from "@/shared/journey/vehicle";
import type { JourneyOverlayProps } from "@/shared/slots/names";
import { Icon } from "@/shared/ui";
import "./companion.css";

const STATE_LABEL = {
  active: "进行中",
  paused: "已暂停",
  interrupted: "已保存进度",
  ended: "已结束",
} as const;

/**
 * ActivityBadge：锚定在对应交通工具旁的音符/小电视。只由实际 TravelActivity 决定显示；
 * 无活动时不渲染。点击只打开对应播放面板，不触发底图拖动或车辆班次卡。
 */
export function ActivityBadge({
  entry,
  onOpen,
}: {
  entry: MapActivityEntry;
  onOpen: () => void;
}) {
  const icon = entry.badge === "music" ? "music" : "tv";
  const kindLabel = entry.badge === "music" ? "一起听" : "一起看";
  return (
    <button
      type="button"
      className={`ps-badge ps-badge--${entry.badge} ps-badge--${entry.badge_state}`}
      data-map-interactive
      data-testid={`activity-badge-${entry.badge}`}
      data-leg-id={entry.leg_id}
      aria-label={`${kindLabel}：${entry.label}（${STATE_LABEL[entry.badge_state]}）`}
      onClick={(event) => {
        event.stopPropagation();
        onOpen();
      }}
    >
      <Icon
        name={
          entry.badge_state === "paused"
            ? "pause"
            : entry.badge_state === "interrupted"
              ? "bookmark"
              : icon
        }
        size={20}
        strokeWidth={2}
      />
      {entry.badge_state === "active" && entry.badge === "music" ? (
        <span className="ps-badge__notes" aria-hidden="true">
          <i>♪</i>
          <i>♫</i>
        </span>
      ) : null}
    </button>
  );
}

/**
 * 徽标放在交通工具的右下方（原来在右上方 30, -38）。地名写在地点上方（MapSurface 的文字 y=-12，旅途页的 journey.css 再往上挪 18px），
 * TA 走到目的地、或刚从家出发时，车正压在地点上，右上方的徽标就盖住地名（2026-09-24 巡检截图 W20：音符盖住“家附近的星球小路”）。
 * 放右下方：不碰车身（车是 52px 的圆，半径 26），也碰不到车所在地点的地名；徽标上的小音符往上飘到车身中线附近就淡出，飘不进地名。
 * 几何用例：tests/claude-6c2b-journey-fixes.test.tsx（车在目的地上、车在起点）。
 */
const BADGE_OFFSET = { x: 50, y: 30 } as const;

export function ActivityBadgeLayer({
  snapshot,
  nowMs,
  openSheet,
}: JourneyOverlayProps) {
  const { companionMedia } = useServices();
  const anchor = vehicleAnchorAt(snapshot, nowMs);
  // 同一时刻只显示当前交通工具的一个主要活动入口，避免挤满图标。
  const entry = snapshot.activity_entries.find(
    (e) => e.leg_id === anchor?.legId && e.badge_state !== "ended",
  );
  const session = useQuery({
    queryKey: queryKeys.mediaSession(entry?.media_session_id ?? "-"),
    queryFn: () => companionMedia.session(entry!.media_session_id!),
    enabled: Boolean(entry?.media_session_id),
    refetchInterval: 15_000,
  });
  if (!anchor || !entry || !entry.media_session_id) return null;
  const sessionId = entry.media_session_id;
  const state = session.data?.state;
  const currentEntry = state
    ? {
        ...entry,
        badge_state: state === "playing" ? ("active" as const) : state,
      }
    : entry;
  return (
    <MapAnchor at={anchor.point} offsetX={BADGE_OFFSET.x} offsetY={BADGE_OFFSET.y} z={3}>
      <ActivityBadge
        entry={currentEntry}
        onOpen={() => openSheet("media", sessionId)}
      />
    </MapAnchor>
  );
}
