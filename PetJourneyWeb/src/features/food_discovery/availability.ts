/**
 * 寻味入口的两条判断。旅途卡片（FoodArrivalCard）在用；地图“这趟旅途”面板（world_map/journeyNotes.ts）接这里的导出，不再自己抄一句。
 *
 * 1) 寻味推荐现在能不能用（foodPicksAvailable / useFoodPicksAvailable）：
 *    - 演示模式用本地演示小样本，总能用；
 *    - live 看 /meta 的 food.recommendations，只有 status 为 available 才算能用。后端没有获准分析的真实菜单/评论资料，
 *      只在开了演示目录（PETJOURNEY_WEB_DEMO_CATALOG）的演示环境给 available；隔离后端和正式环境报 not_configured，
 *      这时 POST /food/recommendations 回 503（页面只能显示“还在搭建中”）——入口就不显示，不引人点进去。
 *    - /meta 还没回来或取不到时不知道，入口先不显示。
 * 2) 入口标题（foodCardTitle）：按数据判断 TA 去的城市是不是家所在的城市，不猜：
 *    - 同一座城市（这趟不出城，或者家就在那座城市）：“让 TA 在附近挑一家”；
 *    - 别的城市：“到{city}后，让 TA 挑一家”；
 *    - 不知道家在哪座城市：“让 TA 在{city}挑一家”（两种情况下都说得通）。
 *    行程版本号只用来判断推荐是否过期，不写给玩家看。
 */
import { useQuery } from "@tanstack/react-query";
import type { Capability, PetArrivalContext } from "@/shared/contracts";
import { env, type DataMode } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";

export const FOOD_PICKS_CAPABILITY = "food.recommendations";

/** 纯判断：true 能用、false 没开；live 下还没拿到能力表（undefined / null）时返回 undefined，表示“还不知道”。 */
export function foodPicksAvailable(dataMode: DataMode, capabilities: readonly Capability[] | null | undefined): boolean | undefined {
  if (dataMode === "fixture") return true;
  if (!capabilities) return undefined;
  return capabilities.some((capability) => capability.key === FOOD_PICKS_CAPABILITY && capability.status === "available");
}

/** 组件里用：只有确定能用才是 true；/meta 没回来、取不到、或能力没开都是 false（入口不显示）。与全站其他能力判断共用 queryKeys.meta 缓存。 */
export function useFoodPicksAvailable(): boolean {
  const { platform } = useServices();
  const live = env.dataMode === "live";
  const meta = useQuery({ queryKey: queryKeys.meta, queryFn: () => platform.meta(), staleTime: 60_000, enabled: live });
  return foodPicksAvailable(env.dataMode, live ? meta.data?.capabilities : null) === true;
}

/** 入口标题。homeCity 取家园快照的 place.city（同一个家里的宠物共用一个家）；没有就传 null。 */
export function foodCardTitle(ctx: Pick<PetArrivalContext, "city">, homeCity: string | null | undefined): string {
  const home = homeCity?.trim();
  if (!home) return `让 TA 在${ctx.city}挑一家`;
  return home === ctx.city.trim() ? "让 TA 在附近挑一家" : `到${ctx.city}后，让 TA 挑一家`;
}
