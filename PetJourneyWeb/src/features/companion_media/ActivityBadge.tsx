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
    <MapAnchor at={anchor.point} offsetX={30} offsetY={-38} z={3}>
      <ActivityBadge
        entry={currentEntry}
        onOpen={() => openSheet("media", sessionId)}
      />
    </MapAnchor>
  );
}
