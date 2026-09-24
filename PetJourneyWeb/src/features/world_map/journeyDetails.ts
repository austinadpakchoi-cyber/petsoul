/**
 * 面板上这只宠物此刻这一趟的行程快照（地图接上“这趟旅途”第 1 步；只做 live）。
 * 分工：位置、阶段、姿态、标题、起止只认 W1；快照只补这一趟的细节（各段、当前段、车上活动与媒体会话、到达上下文、到访、行程版本）。
 * - 什么时候读：只为面板上显示的那只；只读自己家的宠物；W1 的 activity.journey_id 不为空才读——在家不读（免得 404 no_journey）。
 * - 键：queryKeys.journeyMap(petId)，不带 scenario：与寻味列表 / 详情、改选分店后的 setQueryData、照片页共用一份。
 * - 对齐：W1 的 journey_id 等于快照的 journey_id，并且快照 lifecycle === "active"，才用快照。对不上 = 快照还没跟上：
 *   任何从快照来的行、按钮、面板、卡片都不出现，并重读一次（同一种对不上只重读一次）。
 * - 刷新：不另开 10 秒轮询。W1 这只的 (journey_id, phase, version, until) 一变就让它失效；staleTime 10 秒；
 *   只有对齐成功时才有 45 秒的保底刷新（车上活动开始 / 结束）。
 * - W1 的 leg 是主段、不是当前段（I 已确认）：分段细节（下一站、行程卡、车上活动）一律取对齐后快照的 current_leg_id；地图位置照旧由 W1 决定。
 */
import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { JourneyLeg, JourneyMapSnapshot, MapActivityEntry } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useOptionalCurrentHousehold } from "@/shared/session/householdContext";
import type { WorldPet } from "./model";

export const JOURNEY_STALE_MS = 10_000;
export const JOURNEY_FALLBACK_MS = 45_000;

export type JourneyDetails = { status: "none" } | { status: "pending" } | { status: "lagging" } | { status: "aligned"; snapshot: JourneyMapSnapshot };

export function isAligned(snapshot: JourneyMapSnapshot | undefined, journeyId: string | null): snapshot is JourneyMapSnapshot {
  return Boolean(snapshot && journeyId && snapshot.journey_id === journeyId && snapshot.lifecycle === "active");
}

/** 保底刷新：只在对齐成功时开；还在读、读不到、对不上都不开。 */
export function journeyRefetchInterval(snapshot: JourneyMapSnapshot | undefined, journeyId: string | null): number | false {
  return isAligned(snapshot, journeyId) ? JOURNEY_FALLBACK_MS : false;
}

/** W1 这只的四样：(journey_id, phase, version, until)，一变就让快照失效。 */
export function worldJourneyKey(pet: WorldPet): string {
  return [pet.activity.journeyId ?? "-", pet.activity.phase, pet.version, pet.activity.until ?? "-"].join("|");
}

/** 当前这一段：快照的 current_leg_id（W1 的 leg 是主段，不能用来判断在哪一段）。 */
export function currentJourneyLeg(snapshot: JourneyMapSnapshot): JourneyLeg | null {
  return snapshot.legs.find((leg) => leg.leg_id === snapshot.current_leg_id) ?? null;
}

/** 当前这一段上还没结束、带媒体会话的车上活动（一起听 / 一起看）。 */
export function currentMediaEntry(snapshot: JourneyMapSnapshot): (MapActivityEntry & { media_session_id: string }) | null {
  const entry = snapshot.activity_entries.find((e) => e.leg_id === snapshot.current_leg_id && e.badge_state !== "ended" && Boolean(e.media_session_id));
  return entry ? (entry as MapActivityEntry & { media_session_id: string }) : null;
}

const NONE: JourneyDetails = { status: "none" };
const PENDING: JourneyDetails = { status: "pending" };
const LAGGING: JourneyDetails = { status: "lagging" };

export function useJourneyDetails(pet: WorldPet | null): JourneyDetails {
  const services = useServices();
  const household = useOptionalCurrentHousehold();
  const queryClient = useQueryClient();
  const petId = pet?.petId ?? null;
  const journeyId = pet?.activity.journeyId ?? null;
  const own = Boolean(petId && household?.pets.some(({ pet: p }) => p.pet_id === petId));
  const enabled = env.dataMode === "live" && own && Boolean(journeyId);
  const query = useQuery({
    queryKey: queryKeys.journeyMap(petId ?? "-"),
    // 服务在查询函数里才取：读不到只落到这条查询的错误态，地图照常。
    queryFn: () => services.transport.journeyMap(petId as string),
    enabled,
    staleTime: JOURNEY_STALE_MS,
    refetchInterval: (q) => journeyRefetchInterval(q.state.data, journeyId),
  });

  // W1 这只的 (journey_id, phase, version, until) 变了：让快照失效（前后两次都在读快照时才算；刚出门由 enabled 自己去读）。
  const w1Key = pet ? worldJourneyKey(pet) : null;
  const seen = useRef<{ petId: string | null; key: string | null; enabled: boolean }>({ petId: null, key: null, enabled: false });
  useEffect(() => {
    const prev = seen.current;
    seen.current = { petId, key: w1Key, enabled };
    if (!enabled || !prev.enabled || !petId || prev.petId !== petId || prev.key === w1Key) return;
    void queryClient.invalidateQueries({ queryKey: queryKeys.journeyMap(petId), exact: true });
  }, [enabled, petId, w1Key, queryClient]);

  // 对不上（journey_id 不同、不是进行中、或读不到）：重读一次；同一种对不上只重读一次，之后等 W1 变化再读。
  const data = query.data;
  const lagging = enabled && !query.isFetching && (query.isError || (data !== undefined && !isAligned(data, journeyId)));
  const signature = `${petId}|${journeyId}|${data?.journey_id ?? (query.isError ? "error" : "-")}|${data?.lifecycle ?? "-"}`;
  const retried = useRef<string | null>(null);
  useEffect(() => {
    if (!lagging || retried.current === signature) return;
    retried.current = signature;
    void query.refetch();
  }, [lagging, signature]);

  if (!enabled) return NONE;
  if (isAligned(data, journeyId)) return { status: "aligned", snapshot: data };
  if (query.isPending) return PENDING;
  return LAGGING;
}
