/**
 * 面板上这只此刻在的地方是不是“店”（主窗口 2026-09-24）：“进店看看”只在地点确实是门店类时出现，按数据判断，不按名字猜。
 * - 读这次到访（GET /visits/:id，键 queryKeys.visit(id)，和到访页共用一份），交给到访模块自己的 visitSetting（venue/visitKind）判断：
 *   场景模板 cafe / restaurant 是店（"shop"）；park（附近走走的小路、公园）、generic（打工的地方、城里的景点）不是。
 *   和到访页、旅途页的“到店 / 到了”用同一个判断，不另抄一份。
 * - 不用 W1 的 activity.kind：后端把“去附近喝一杯”（local:cafe）也报成 stroll（world.py 的 _LOCAL_KINDS 只收了 stroll），
 *   按 kind 判断会把咖啡馆当成散步；kind 里也没有“小路 / 公园 / 店”的区分。
 * - 只在 live、自己家的宠物、W1 phase = there 且有 visit_id 时读；还在读、读不到都当“不是店”——没有依据就不说“进店”。
 */
import { useQuery } from "@tanstack/react-query";
import type { Visit } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useOptionalCurrentHousehold } from "@/shared/session/householdContext";
import { visitSetting } from "@/features/venue/visitKind";
import type { WorldPet } from "./model";

export function isStoreVisit(visit: Pick<Visit, "template"> | null | undefined): boolean {
  return Boolean(visit && visitSetting(visit) === "shop");
}

/** 在店里就给这次到访的 id（“进店看看”去 /visits/:id）；不在店里、还不知道是不是店，都给 null。 */
export function useStoreVisitId(pet: WorldPet | null): string | null {
  const services = useServices();
  const household = useOptionalCurrentHousehold();
  const visitId = pet && pet.activity.phase === "there" ? pet.activity.visitId : null;
  const own = Boolean(pet && household?.pets.some(({ pet: p }) => p.pet_id === pet.petId));
  const enabled = env.dataMode === "live" && own && Boolean(visitId);
  const query = useQuery({
    queryKey: queryKeys.visit(visitId ?? "-"),
    // 服务在查询函数里才取：读不到只落到这条查询的错误态，面板照常（按“不是店”）。
    queryFn: () => services.visits.visit(visitId as string),
    enabled,
    staleTime: 30_000,
  });
  return enabled && isStoreVisit(query.data) ? visitId : null;
}
