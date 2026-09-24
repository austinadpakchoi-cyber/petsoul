/**
 * 驾照详情页里的“有了驾照以后”：把拿证之后的事连起来（docs/contracts/DRIVING-SCHOOL-v1.md §6）。
 * - 事实：没有驾照不能自己开车（服务端拒绝），坐车、坐船、坐飞机不受影响；有驾照也要租车
 *   （web_journey/local.py 的“自己开车去兜风”：租一辆小车）。
 * - 借车券：只有这只宠物的收藏里真有一张时才写（后端只返回还没用掉的）；用途写那张券的服务端 note 原文，点过去是收藏。
 * - 不许诺 TA 什么时候去：后端的自主生活不会自己挑“自己开车去兜风”（web_agent/life.py 只挑散步、喝一杯、进城），所以只说“有资格”。
 * 收藏的查询键与收藏页、回忆页同一个（fixture 用 queryKeys.collection，live 按账号与当前宠物分），缓存共用，切宠物就换键。
 */
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import type { CollectionItem } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useCurrentHousehold } from "@/shared/session/householdContext";

function useCarVoucher(): CollectionItem | null {
  const services = useServices();
  const { userId, pet } = useCurrentHousehold();
  const fixture = env.dataMode === "fixture";
  const petId = pet?.pet_id ?? null;
  const query = useQuery({
    queryKey: fixture ? queryKeys.collection : queryKeys.collectionFor(userId ?? "-", petId ?? "-"),
    // 服务在查询函数里才取：收藏读不到（不论哪种失败）只落到这条查询的错误态——少一行借车券，驾照页照常。
    queryFn: ({ signal }) => services.economy.collection(petId, signal),
    enabled: fixture || Boolean(petId && userId),
  });
  return query.data?.find((item) => item.kind === "car_voucher") ?? null;
}

export function LicenseUse({ petName }: { petName: string }) {
  const voucher = useCarVoucher();
  const note = voucher?.note?.trim();
  return (
    <section className="ps-license-use" aria-labelledby="ps-license-use-title" data-testid="license-use">
      <h2 id="ps-license-use-title">有了驾照以后</h2>
      <p>{petName}有资格自己开车去兜风了，要租一辆小车；坐车、坐船、坐飞机本来就不需要驾照。</p>
      {voucher ? (
        <div className="ps-license-use__voucher" data-testid="license-voucher">
          <p>
            还有一张{voucher.title}
            {note ? `：${note}` : "。"}
          </p>
          <Link className="ps-license-use__go" to="/collection">
            去收藏里看
          </Link>
        </div>
      ) : null}
    </section>
  );
}
