import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router";
import type { FeedbackVerdict, FoodRecommendation } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useActiveHome } from "@/shared/session/householdContext";
import { Button, Card, Chip, DataOriginBadge, ErrorState, Page, QueryView, ToggleChip, TopBar } from "@/shared/ui";
import "./food.css";

/** 到店前改去这家：行程版本 +1，旧推荐待复核；到店后不能再换。推荐 ID 本身不产生到访。 */
function ChooseVenue({ rec }: { rec: FoodRecommendation }) {
  const { transport, visits } = useServices();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const keyRef = useRef(newIdempotencyKey("visit-choice"));
  const home = useActiveHome();
  const petId = home.data?.pet.pet_id;
  const map = useQuery({ queryKey: queryKeys.journeyMap(petId ?? "-"), queryFn: () => transport.journeyMap(petId!), enabled: Boolean(petId), retry: false });
  const choose = useMutation({
    mutationFn: () =>
      visits.choose(map.data!.planned_visit_id!, { recommendation_id: rec.recommendation_id, expected_itinerary_version: map.data!.itinerary_version }, keyRef.current),
    onSuccess: (snapshot) => {
      queryClient.setQueryData(queryKeys.journeyMap(snapshot.pet_id), snapshot);
      void queryClient.invalidateQueries({ queryKey: ["food"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.home });
      navigate("/journey");
    },
  });
  const snapshot = map.data;
  if (rec.mode !== "pet_virtual_explore" || !snapshot || snapshot.lifecycle !== "active" || !snapshot.planned_visit_id) return null;
  if (snapshot.current_visit_id) return <Chip>TA 已经到店了，这次不能再换</Chip>;
  if (rec.freshness !== "fresh") return <Chip tone="danger">行程已经变了，这条推荐需要重新查看</Chip>;
  const error = choose.error ? toApiError(choose.error) : null;
  return (
    <Card flat className="ps-stack">
      <Button variant="primary" icon="pin" loading={choose.isPending} onClick={() => choose.mutate()}>
        让 TA 改去这家
      </Button>
      <span className="ps-muted">交通不会为了餐厅缩短；店内是原创场景，不代表真实店内样子。</span>
      {error ? (
        error.code === "VERSION_CONFLICT" || error.code === "ITINERARY_CHANGED" ? (
          <p role="alert" className="ps-muted" style={{ color: "var(--c-danger)", margin: 0 }}>
            {error.message}
          </p>
        ) : (
          <ErrorState error={error} />
        )
      ) : null}
    </Card>
  );
}

const REASONS: Array<{ id: string; label: string }> = [
  { id: "too_salty", label: "偏咸" },
  { id: "too_bland", label: "偏淡" },
  { id: "too_spicy", label: "太辣" },
  { id: "too_oily", label: "太油" },
  { id: "too_sweet", label: "太甜" },
];

/** 主人现实用餐反馈：自报，只修正口味偏好，不回流为品质证据。 */
function OwnerFeedback({ rec }: { rec: FoodRecommendation }) {
  const { food } = useServices();
  const queryClient = useQueryClient();
  const keyRef = useRef(newIdempotencyKey("food-feedback"));
  const [verdict, setVerdict] = useState<FeedbackVerdict | null>(null);
  const [reasons, setReasons] = useState<string[]>([]);
  const submit = useMutation({
    mutationFn: () =>
      food.feedback(
        { recommendation_id: rec.recommendation_id, dish_ids: rec.dishes.map((d) => d.dish.dish_id), verdict: verdict!, reasons, dined_on: new Date().toISOString().slice(0, 10) },
        keyRef.current,
      ),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["food", "preference"] }),
  });
  if (rec.mode !== "owner_real_dining") return null;
  if (submit.isSuccess) return <Card flat role="status">谢谢！已按你的感受微调“我的用餐偏好”（自报反馈不会当作餐厅品质证据）。</Card>;
  return (
    <Card flat className="ps-stack">
      <strong>吃过了？说说感受</strong>
      <div className="ps-segmented" role="group" aria-label="总体感受">
        {(["liked", "neutral", "disliked"] as FeedbackVerdict[]).map((v) => (
          <ToggleChip key={v} pressed={verdict === v} onToggle={() => setVerdict(v)}>
            {v === "liked" ? "喜欢" : v === "neutral" ? "一般" : "不喜欢"}
          </ToggleChip>
        ))}
      </div>
      <div className="ps-segmented" role="group" aria-label="口味问题">
        {REASONS.map((r) => (
          <ToggleChip key={r.id} pressed={reasons.includes(r.id)} onToggle={() => setReasons((prev) => (prev.includes(r.id) ? prev.filter((x) => x !== r.id) : [...prev, r.id]))}>
            {r.label}
          </ToggleChip>
        ))}
      </div>
      <Button variant="secondary" disabled={!verdict} loading={submit.isPending} onClick={() => submit.mutate()}>
        提交
      </Button>
      {submit.isError ? <ErrorState error={submit.error} /> : null}
    </Card>
  );
}

/** 寻味详情：出处、日期、覆盖范围、实际样本量与平台总数分开展示。推荐 ID 不等于到访。 */
export function RecommendationDetailPage() {
  const { recommendationId = "" } = useParams();
  const { food } = useServices();
  const query = useQuery({ queryKey: queryKeys.foodRecommendation(recommendationId), queryFn: () => food.recommendation(recommendationId) });
  return (
    <Page>
      <TopBar title="为什么选这里" back="/journey/food" />
      <QueryView query={query}>
        {(rec) => (
          <div className="ps-stack">
            <Card>
              <h2 className="ps-h2">{rec.branch.name}</h2>
              <div className="ps-muted">分店 ID {rec.branch.branch_id}（带来源命名空间；总店证据不自动转给分店）</div>
              <DataOriginBadge origin={rec.data_origin} label="演示资料，不对应真实商家" />
            </Card>
            <ChooseVenue rec={rec} />
            {rec.dishes.map(({ dish, why, evidence }) => (
              <Card key={dish.dish_id}>
                <strong>{dish.name}</strong>
                <div className="ps-muted">{why}</div>
                {dish.price ? <Chip>{(dish.price.amount_minor / 100).toFixed(0)} {dish.price.currency}（示例价格，日期未知）</Chip> : <Chip>价格未知</Chip>}
                <div className="ps-section-title">依据</div>
                {evidence.length === 0 ? <p className="ps-muted">没有可引用的菜品证据。</p> : null}
                {evidence.map((ev) => (
                  <div key={ev.evidence_id} className="ps-evidence">
                    <Chip>{ev.source_label}</Chip> {ev.aspect}：{ev.observation}
                    <div className="ps-muted">实际取得样本 {ev.sample_count} 条 · 观察时间 {ev.observed_at ?? "未知"}</div>
                  </div>
                ))}
              </Card>
            ))}
            <OwnerFeedback rec={rec} />
            <Card flat>
              <div className="ps-section-title" style={{ marginTop: 0 }}>来源与版本</div>
              <div className="ps-muted">{rec.provenance.coverage_note}</div>
              <div className="ps-muted">
                资料版本 {rec.provenance.fact_version} · 规则 {rec.provenance.rule_version} · 偏好第 {rec.provenance.preference_version} 版 · 数据状态 {rec.provenance.data_status}
              </div>
              <div className="ps-muted">平台评分：{rec.branch.ratings.length ? "见上" : "无（演示资料没有平台评分）"}</div>
            </Card>
          </div>
        )}
      </QueryView>
    </Page>
  );
}
