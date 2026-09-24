/**
 * 旅行心愿的数据来源（TRV-06）：页面、攻略列表、地图那一行都从这里拿，不各自去找。
 * - 当前活动心愿：GET /travel/wish（合同 §23.4，已可接 live）。fixture 与 live 都走 visits 服务的 travelWish（journey 模块提供，
 *   fixture 实现按需加载演示数据）。服务在查询函数里才取：服务不论以哪种方式失败（没接入、报错、根本不在），
 *   都只落到这条查询的错误态——地图面板与列表照常，只是没有心愿那一行（照 world_map/schoolNote 的做法）。
 * - 计划（第③期，2026-09-24 23:2x 接上）：live 走 visits 服务的 travelPlan（GET /travel/plans/{plan_id}，I 已实现，能力表 travel.plan 可用），
 *   与心愿同一口径——只在拿到当前宠物以后才读、显式带 pet_id；演示仍是 fixture 的演示计划（动态 import，单独一个 chunk，主包里没有演示数据），
 *   每份演示计划各带自己的心愿（PlanBundle）。计划页 = 这份计划（手账在它当前那一版的 journals 里）+ GET /travel/wish 的心愿
 *   （业务状态 status、TA 的理由 owner_reason；只有 wish_id 对得上才放在一起，对不上就只按计划本身说，见 ./model 的 viewOfPlanOnly）。
 *   别人家的、不存在的、还没发布过计划的心愿都是 404 + plan_not_found（见 isPlanNotFound）；后端没有这条路（路由级 404）不算这一种。
 */
import { useQuery } from "@tanstack/react-query";
import type { TravelPlan, TravelWish } from "@/shared/contracts";
import { isApiError, toApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { useServices } from "@/shared/services/registry";
import { useOptionalCurrentHousehold } from "@/shared/session/householdContext";
import type { PlanBundle } from "./model";

/** 读的几种状态。出错时 retry 只在值得再试时给（后端说明不可重试的，如 404，不给重试键）。 */
export type Read<T> = { state: "unavailable" } | { state: "loading" } | { state: "error"; error: unknown; retry?: () => void } | { state: "ready"; data: T };

/**
 * 当前宠物的活动心愿；没有活动心愿时 data 为 null（I 已定：GET /travel/wish 此时返回 200 + null）。
 * 一律显式传当前宠物的 id：pet_id 省略（null）时后端按 require_pet 去推，只有能照顾的宠物恰好一只才默认它，否则 409 pet_required（§29.5）——
 * 所以 live 只在拿到当前宠物以后才读、从不传 null；演示实现不看 petId（演示世界的家庭上下文没有当前宠物，不发请求）。
 */
export function useCurrentWish(): Read<TravelWish | null> {
  const services = useServices();
  const household = useOptionalCurrentHousehold();
  const fixture = env.dataMode === "fixture";
  const userId = household?.userId ?? null;
  const petId = household?.pet?.pet_id ?? null;
  const enabled = fixture || Boolean(userId && petId);
  const query = useQuery({
    queryKey: fixture ? ["travel", "wish", "demo"] : ["travel", "wish", userId ?? "-", petId ?? "-"],
    queryFn: ({ signal }) => services.visits.travelWish(petId, signal),
    enabled,
  });
  if (!enabled) return { state: "unavailable" };
  if (query.isPending) return { state: "loading" };
  if (query.isError) return { state: "error", error: query.error };
  return { state: "ready", data: query.data ?? null };
}

function reasonOf(error: unknown): string | null {
  const reason = toApiError(error).details?.reason;
  return typeof reason === "string" ? reason : null;
}

/**
 * GET /travel/plans/{plan_id} 答“这份计划还没写好，或者已经不在了”：404 + details.reason = plan_not_found（形状同 no_journey）。
 * 后端没有这条路的路由级 404 不带 details，不算这一种（照常走统一错误态）。
 */
export function isPlanNotFound(error: unknown): boolean {
  return toApiError(error).status === 404 && reasonOf(error) === "plan_not_found";
}

/**
 * live 的某一份计划（GET /travel/plans/{plan_id}）。与 useCurrentWish 同一口径：只在拿到当前宠物以后才读、显式带 pet_id（不拿 null 让后端去推）；
 * 键带账号、宠物与计划号（切宠物就是另一条）。演示模式不走这里（state 恒为 unavailable），演示计划见 useDemoPlans。
 */
export function useLivePlan(planId: string | undefined): Read<TravelPlan> {
  const services = useServices();
  const household = useOptionalCurrentHousehold();
  const live = env.dataMode === "live";
  const userId = household?.userId ?? null;
  const petId = household?.pet?.pet_id ?? null;
  const enabled = live && Boolean(userId && petId && planId);
  const query = useQuery({
    queryKey: ["travel", "plan", userId ?? "-", petId ?? "-", planId ?? "-"],
    queryFn: ({ signal }) => services.visits.travelPlan(planId!, petId, signal),
    enabled,
  });
  if (!enabled) return { state: "unavailable" };
  if (query.isPending) return { state: "loading" };
  if (query.isError) {
    // 后端说明不可重试的（如 404）不给重试键；网络断了、服务忙这类可以再试。
    const retry = isApiError(query.error) && !query.error.retryable ? undefined : () => void query.refetch();
    return { state: "error", error: query.error, retry };
  }
  return { state: "ready", data: query.data };
}

/** 旅行路由没法确定是哪只宠物：409 + details.reason = pet_required（require_pet 的惯例，§29.5）。页面说“需要先选一只宠物”，不白屏、不一直转。 */
export function isPetRequired(error: unknown): boolean {
  return toApiError(error).status === 409 && reasonOf(error) === "pet_required";
}

/** 演示计划（只在 fixture；每份各带自己的心愿）；live 的计划见 useLivePlan。 */
export function useDemoPlans(): Read<readonly PlanBundle[]> {
  const fixture = env.dataMode === "fixture";
  const query = useQuery({
    queryKey: ["travel", "plans", "demo"],
    queryFn: async () => (await import("./fixture")).DEMO_PLANS,
    enabled: fixture,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  if (!fixture) return { state: "unavailable" };
  if (query.isPending) return { state: "loading" };
  if (query.isError) return { state: "error", error: query.error };
  return { state: "ready", data: query.data };
}
