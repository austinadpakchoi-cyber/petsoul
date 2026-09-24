/**
 * 不带定位的一起听 / 一起看徽标（地图接“这趟旅途”第 2 步，方案 A：companion_media 拆出 ActivityBadgeFor）。
 * - 仍由本模块自己决定显示哪一条：当前这一段（快照 current_leg_id，与 vehicleAnchorAt 取的是同一段）上第一条还没结束的车上活动；
 *   它还没有媒体会话就不画。读会话状态（queryKeys.mediaSession，每 15 秒，和播放面板共用），徽标跟着改成播放中 / 已暂停 / 已保存进度。
 * - 点它只打开对应的播放面板：openSheet("media", 会话 id)。
 * - 地图首页（world_map）把它放在面板上那只宠物的标记旁；旧的旅途页经 ActivityBadgeLayer（./ActivityBadge）在交通工具旁用——
 *   那边现在还是自己的一份同样的选法：页面分身第六批正在改 ActivityBadge.tsx（徽标挪到交通工具右下方），等它交活后，
 *   ActivityBadgeLayer 改成 MapAnchor + ActivityBadgeFor，两处就只剩这一份。
 */
import { useQuery } from "@tanstack/react-query";
import { currentLeg } from "@/shared/journey/vehicle";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import type { JourneyOverlayProps } from "@/shared/slots/names";
import { ActivityBadge } from "./ActivityBadge";

export function ActivityBadgeFor({ snapshot, openSheet }: JourneyOverlayProps) {
  const { companionMedia } = useServices();
  const legId = currentLeg(snapshot)?.leg_id;
  // 同一时刻只显示当前这一段的一个主要活动入口，避免挤满图标。
  const entry = snapshot.activity_entries.find((e) => e.leg_id === legId && e.badge_state !== "ended");
  const session = useQuery({
    queryKey: queryKeys.mediaSession(entry?.media_session_id ?? "-"),
    queryFn: () => companionMedia.session(entry!.media_session_id!),
    enabled: Boolean(entry?.media_session_id),
    refetchInterval: 15_000,
  });
  if (!entry || !entry.media_session_id) return null;
  const sessionId = entry.media_session_id;
  const state = session.data?.state;
  const currentEntry = state ? { ...entry, badge_state: state === "playing" ? ("active" as const) : state } : entry;
  return <ActivityBadge entry={currentEntry} onOpen={() => openSheet("media", sessionId)} />;
}
