/**
 * 按到访 id 读这次到访是什么样的地方（门店 / 户外 / 其他，规则见 ./visitKind）。和到访页共用 queryKeys.visit 的缓存。
 * 没有到访、还在读、读不到都返回 null（不知道）——调用方按“不是店”说，不写“店”字。
 * 旅途页（journey/JourneyPage.tsx、JourneyStatusPanel.tsx）在用；地图的 world_map/visitPlace.ts 目前是同一条规则的另一份，
 * 主窗口 2026-09-24 定：以后由地图分身改成引用这里。
 */
import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { visitSetting, type VisitSetting } from "./visitKind";

export function useVisitSetting(visitId: string | null | undefined): VisitSetting | null {
  const services = useServices();
  const query = useQuery({
    queryKey: queryKeys.visit(visitId ?? "-"),
    // 服务在查询函数里才取：没有到访时不碰 visits 服务；读不到只落到这条查询的错误态，页面照常（按“不知道”）。
    queryFn: () => services.visits.visit(visitId as string),
    enabled: Boolean(visitId),
    staleTime: 30_000,
  });
  return visitId && query.data ? visitSetting(query.data) : null;
}
