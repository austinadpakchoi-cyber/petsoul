/**
 * 面板上这只宠物自己的家园快照里的两条提醒（C84A-MAP-MAIL-SCOPE-01、第 0b 步）：
 * - 信箱：未读是每只宠物自己的（后端按 pet_id 计数）；
 * - 世界正在更新：后端 catching_up 也只看这只宠物的行程（settlement.catching_up(pet_id)），不是全家通用。
 * 两条都带 petId，面板换宠物就跟着换。
 * - live：`world.home(petId)`，键 `queryKeys.homeFor(用户, 宠物)`——与 useActiveHome 同键同读法，共用缓存；60 秒刷新；
 * - 只为自己家的宠物读（当前账号家庭名单里的）；
 * - 读不到或还在读时一条都不出，**绝不拿别的宠物的顶替**；
 * - 演示（fixture）没有这两条（沿用原来的做法）。
 */
import { useQuery } from "@tanstack/react-query";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useOptionalCurrentHousehold } from "@/shared/session/householdContext";
import type { PanelNote } from "./panelNotes";

export const CATCHING_UP_TEXT = "世界正在更新，工钱和来信稍后出现。";

/** 面板上这只自己的家园快照（live、自己家的宠物才读）。和 useActiveHome 同键同读法，共用缓存。 */
function usePanelHome(petId: string | null) {
  const services = useServices();
  const household = useOptionalCurrentHousehold();
  const userId = household?.userId ?? null;
  const own = Boolean(petId && household?.pets.some(({ pet }) => pet.pet_id === petId));
  const enabled = env.dataMode === "live" && Boolean(userId) && own;
  const home = useQuery({
    queryKey: queryKeys.homeFor(userId ?? "-", petId ?? "-"),
    // 服务在查询函数里才取：读不到只落到这条查询的错误态，面板照常。
    queryFn: ({ signal }) => services.world.home(petId, signal),
    enabled,
    refetchInterval: 60_000,
  });
  return { enabled, home };
}

/** 面板上这只的家在哪座城市（家园快照 place.city）：寻味那一行按它说“在附近 / 到{city}后”。读不到、演示里都是 null。 */
export function useHomeCity(petId: string | null): string | null {
  const { enabled, home } = usePanelHome(petId);
  return enabled && home.isSuccess ? home.data.place?.city?.trim() || null : null;
}

export function useHomeNotes(petId: string | null): PanelNote[] {
  const { enabled, home } = usePanelHome(petId);
  if (!enabled || !petId || !home.isSuccess) return [];
  const notes: PanelNote[] = [];
  const unread = home.data.unread?.messages ?? 0;
  if (unread > 0) notes.push({ id: "mail", kind: "mail", text: `TA 发来 ${unread} 条消息`, to: "/communicator", petId });
  if (home.data.catching_up) notes.push({ id: "catching-up", kind: "system", text: CATCHING_UP_TEXT, petId });
  return notes;
}
