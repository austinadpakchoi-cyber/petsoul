import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import type { FoodMode, FoodRecommendationRequestInput, PetArrivalContext } from "@/shared/contracts";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useActiveHome } from "@/shared/session/householdContext";
import { formatLocalTime } from "@/shared/time/clock";
import { Card, DataOriginBadge, EmptyState, ErrorState, Icon, LoadingState, Page, ToggleChip, TopBar } from "@/shared/ui";
import { PreferenceEditor } from "./PreferenceEditor";
import { RecommendationCard } from "./RecommendationCard";
import "./food.css";

function nextSaturday(): string {
  const d = new Date();
  d.setDate(d.getDate() + ((6 - d.getDay() + 7) % 7 || 7));
  return d.toISOString().slice(0, 10);
}

/** 行程版本号只用来判断推荐是否过期（见下面 stale），不写给玩家看。 */
function ArrivalSummary({ ctx }: { ctx: PetArrivalContext }) {
  return (
    <Card flat className="ps-food-ctx">
      <Icon name="pin" />
      <div>
        <strong>按 TA 的行程</strong>
        <div className="ps-muted">
          {ctx.city} · 可行到达 {formatLocalTime(ctx.feasible_arrival_utc, ctx.destination_timezone)} · 可停留 {formatLocalTime(ctx.stay_window_start_utc, ctx.destination_timezone)}–
          {formatLocalTime(ctx.stay_window_end_utc, ctx.destination_timezone)}
        </div>
      </div>
    </Card>
  );
}

const CITIES: Array<{ city: string; timezone: string }> = [
  { city: "香港", timezone: "Asia/Hong_Kong" },
  { city: "澳门", timezone: "Asia/Macau" },
  { city: "东京", timezone: "Asia/Tokyo" },
];

export function FoodDiscoveryPage() {
  const { food, transport } = useServices();
  const [params, setParams] = useSearchParams();
  const mode: FoodMode = params.get("mode") === "owner" ? "owner_real_dining" : "pet_virtual_explore";
  const variants = food.fixtureVariants();
  const variant = params.get("taste") ?? variants[0]?.id;
  const fixture = env.dataMode === "fixture";
  const [simulateDelay, setSimulateDelay] = useState(false);
  const [ownerDate, setOwnerDate] = useState(nextSaturday);
  const [ownerTime, setOwnerTime] = useState("12:30");
  const [ownerCity, setOwnerCity] = useState(CITIES[0]);

  const home = useActiveHome();
  const petId = home.data?.pet.pet_id;
  // 寻味消费交通的到达上下文：live 用 TA 当前真实旅程；fixture 用“火车”演示场景（目的地香港）。
  const scenario = fixture ? "train" : undefined;
  const journey = useQuery({
    queryKey: queryKeys.journeyMap(petId ?? "-", scenario),
    queryFn: () => transport.journeyMap(petId!, { fixtureScenario: scenario }),
    enabled: Boolean(petId) && mode === "pet_virtual_explore",
    retry: false,
  });
  const activeJourney = journey.data && journey.data.lifecycle === "active" ? journey.data : null;
  const arrival = activeJourney?.arrival_context ?? null;
  const noJourney = mode === "pet_virtual_explore" && !journey.isPending && !arrival;

  const request = useMemo<FoodRecommendationRequestInput | null>(() => {
    if (!petId) return null;
    if (mode === "pet_virtual_explore") {
      if (!arrival) return null;
      return { mode, pet_id: petId, pet_context: arrival, max_results: 3 };
    }
    return { mode, pet_id: petId, owner_context: { plan_date: ownerDate, meal_time_local: ownerTime, timezone: ownerCity.timezone, city: ownerCity.city, area: null }, max_results: 3 };
  }, [petId, mode, arrival, ownerDate, ownerTime, ownerCity]);

  const recs = useQuery({
    queryKey: queryKeys.foodRecommendations(JSON.stringify([request, variant])),
    queryFn: () => food.recommend(request!, variant),
    enabled: Boolean(request),
  });

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    next.set(key, value);
    setParams(next, { replace: true });
  };

  return (
    <Page>
      <TopBar title="让 TA 挑一家" subtitle="寻味：它有自己的口味，也记得你的喜好" back="/map" />
      <div className="ps-row" role="group" aria-label="模式">
        <ToggleChip pressed={mode === "pet_virtual_explore"} onToggle={() => setParam("mode", "pet")}>
          TA 的旅途探索
        </ToggleChip>
        <ToggleChip pressed={mode === "owner_real_dining"} onToggle={() => setParam("mode", "owner")}>
          我的现实用餐
        </ToggleChip>
      </div>
      {variants.length ? (
        <div className="ps-row" role="group" aria-label="演示偏好" style={{ marginTop: 8 }}>
          <span className="ps-muted">演示偏好：</span>
          {variants.map((v) => (
            <ToggleChip key={v.id} pressed={variant === v.id} onToggle={() => setParam("taste", v.id)}>
              {v.label}
            </ToggleChip>
          ))}
        </div>
      ) : null}

      <div className="ps-stack" style={{ marginTop: 12 }}>
        {petId ? <PreferenceEditor petId={petId} subject={mode === "pet_virtual_explore" ? "pet" : "owner"} variant={variant} /> : null}
        {mode === "pet_virtual_explore" ? (
          arrival ? (
            <>
              <ArrivalSummary ctx={arrival} />
              {fixture ? (
                <label className="ps-check ps-muted">
                  <input type="checkbox" checked={simulateDelay} onChange={(e) => setSimulateDelay(e.target.checked)} /> 演示：行程延误（版本变化后旧推荐待复核，交通不会为餐厅缩短）
                </label>
              ) : (
                <p className="ps-muted" style={{ margin: 0 }}>
                  到店前可以让 TA 改去推荐的分店；已经到店就不能再换。
                </p>
              )}
            </>
          ) : noJourney ? (
            <EmptyState icon="journey" title="TA 现在不在旅途中">
              {activeJourney ? "TA 已经到店或在回家的路上了。" : "出发后，这里会按 TA 的到达时间挑一家。"}
            </EmptyState>
          ) : journey.isError ? (
            <ErrorState error={journey.error} />
          ) : (
            <LoadingState lines={1} />
          )
        ) : (
          <Card flat className="ps-stack">
            <strong>用你自己的日期和位置</strong>
            <div className="ps-row">
              <input className="ps-input" style={{ width: "auto" }} type="date" value={ownerDate} onChange={(e) => setOwnerDate(e.target.value)} aria-label="用餐日期" />
              <input className="ps-input" style={{ width: "auto" }} type="time" value={ownerTime} onChange={(e) => setOwnerTime(e.target.value)} aria-label="用餐时间" />
              <select className="ps-input" style={{ width: "auto" }} aria-label="城市" value={ownerCity.city} onChange={(e) => setOwnerCity(CITIES.find((c) => c.city === e.target.value) ?? CITIES[0])}>
                {CITIES.map((c) => (
                  <option key={c.city} value={c.city}>
                    {c.city}
                  </option>
                ))}
              </select>
            </div>
            <div className="ps-muted">
              <Icon name="lock" size={12} /> 你的饮食限制只用于给你推荐，不会出现在朋友圈或别人的评论里。
            </div>
          </Card>
        )}

        {recs.isPending && request ? <LoadingState lines={2} /> : null}
        {recs.isError ? <ErrorState error={recs.error} onRetry={() => void recs.refetch()} /> : null}
        {recs.data ? (
          <>
            <div className="ps-row" style={{ justifyContent: "space-between" }}>
              <span className="ps-muted">偏好：{recs.data.preference.label}</span>
              <DataOriginBadge origin={recs.data.data_origin} label="演示资料，不是真实口碑" />
            </div>
            {recs.data.items.length === 0 ? <EmptyState title="暂时没有合适的候选">没有合格资料时不编造推荐。</EmptyState> : null}
            {recs.data.items.map((rec) => (
              <RecommendationCard
                key={rec.recommendation_id}
                rec={rec}
                // 与后端 food_discovery.recommendation_freshness 同语义：行程版本变化 → 待复核。
                stale={rec.mode === "pet_virtual_explore" && arrival !== null && rec.itinerary_version !== arrival.itinerary_version + (simulateDelay ? 1 : 0)}
              />
            ))}
            {recs.data.shortfall_note ? <p className="ps-muted">{recs.data.shortfall_note}</p> : null}
          </>
        ) : null}
      </div>
    </Page>
  );
}
