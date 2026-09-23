import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import type { DestinationOption, HomeSnapshot, JourneyMapSnapshot, JourneySuggestion } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useOptionalCurrentHousehold } from "@/shared/session/householdContext";
import { Button, Card, Chip, ErrorState, Icon, LoadingState, QueryView, type IconName } from "@/shared/ui";

const MODE_ICON: Record<string, IconName> = { walk: "compass", taxi: "car", car: "car", ferry: "ship", flight: "plane", train: "train" };
const MODE_TEXT: Record<string, string> = { walk: "步行", taxi: "打车", car: "自驾", ferry: "轮渡", flight: "飞机", train: "火车" };

function minutesText(total: number): string {
  if (total < 60) return `约 ${total} 分钟`;
  const h = Math.floor(total / 60);
  const m = total % 60;
  return m ? `约 ${h} 小时 ${m} 分` : `约 ${h} 小时`;
}

function tripTime(iso: string): string {
  return new Date(iso).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function DestinationCard({ option, balance, petId, suggestion, onSuggested, onDeparted }: {
  option: DestinationOption;
  balance: number;
  petId: string;
  suggestion: JourneySuggestion | null;
  onSuggested: () => void;
  onDeparted: (snapshot: JourneyMapSnapshot) => void;
}) {
  const { transport } = useServices();
  const keyRef = useRef(newIdempotencyKey("depart"));
  const [planOpen, setPlanOpen] = useState(false);
  const available = option.available !== false;
  const plan = useQuery({
    queryKey: queryKeys.journeyPlan(petId, option.destination_key),
    queryFn: ({ signal }) => transport.plan(option.destination_key, petId, signal),
    enabled: planOpen && available,
    retry: false,
  });
  const suggest = useMutation({
    mutationFn: () => transport.suggest(option.destination_key, petId),
    onSuccess: onSuggested,
  });
  const depart = useMutation({
    mutationFn: () => transport.depart(option.destination_key, keyRef.current, petId),
    onSuccess: (snapshot) => {
      keyRef.current = newIdempotencyKey("depart");
      onDeparted(snapshot);
    },
  });
  const error = depart.error ? toApiError(depart.error) : null;
  return (
    <Card className="ps-stack ps-destination ps-destination--editorial">
      <div className="ps-row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div style={{ minWidth: 0 }}>
          <h3 className="ps-h2" style={{ margin: 0 }}>
            {option.title}
          </h3>
          <div className="ps-muted">{option.city}</div>
        </div>
        <Chip tone="sun" icon="coin">{option.fee} 旅费</Chip>
      </div>
      <p style={{ margin: 0 }}>{option.summary}</p>
      <div className="ps-row" style={{ flexWrap: "wrap" }}>
        {option.modes.map((m) => (
          <Chip key={m} icon={MODE_ICON[m] ?? "journey"}>
            {MODE_TEXT[m] ?? m}
          </Chip>
        ))}
        <Chip>往返{minutesText(option.total_minutes)}</Chip>
      </div>
      {option.wish_match ? (
        <Chip tone="leaf" icon="bookmark">
          {option.wish_match}
        </Chip>
      ) : null}
      {option.reference_note ? <p className="ps-destination__basis">{option.reference_note}</p> : option.time_basis === "demo_fixture" ? <p className="ps-destination__basis">故事路线示意，不对应核验过的班次或实时车程。</p> : <p className="ps-destination__basis">出发前会再核对交通和可用时间；计划不等于已经出发。</p>}
      {!available ? <p role="status" className="ps-destination__unavailable">目前不能出发：{option.unavailable_reason || "交通资料暂不可用"}</p> : null}
      {suggestion ? <p className="ps-destination__suggestion" role="status">{suggestion.status === "pending" ? "你的建议已送达，TA 正在考虑；何时出发由 TA 决定。" : suggestion.status === "accepted" ? "TA 接受了这条建议。" : suggestion.status === "passed" ? "TA 这次没有采纳，可以再聊聊。" : "你后来换了一个建议。"}</p> : null}
      <div className="ps-destination__actions">
        <Button variant="leaf" block disabled={!available || suggestion?.status === "pending"} loading={suggest.isPending} onClick={() => suggest.mutate()}>
          {suggestion?.status === "pending" ? "等待 TA 决定" : "建议 TA 去这里"}
        </Button>
        <button type="button" className="ps-destination__plan-toggle" aria-expanded={planOpen} onClick={() => setPlanOpen((open) => !open)} disabled={!available}>
          {planOpen ? "收起路线" : "先看路线与时间"} <Icon name="chevron" size={14} />
        </button>
      </div>
      {suggest.isError ? <ErrorState error={suggest.error} /> : null}
      {planOpen && available ? <div className="ps-destination__plan">
        {plan.isPending ? <LoadingState lines={2} label="正在核对这段路…" /> : plan.isError ? <ErrorState error={plan.error} onRetry={() => void plan.refetch()} /> : plan.data ? <>
          <strong>出发前的计划 · 尚未发生</strong>
          <p>{tripTime(plan.data.leave_home_at)} 出门 · {tripTime(plan.data.returns_home_at)} 回家</p>
          <ol>{plan.data.legs.map((leg) => <li key={`${leg.direction}-${leg.sequence}`}><span>{MODE_TEXT[leg.mode] ?? leg.mode}</span><div>{leg.origin.name} → {leg.destination.name}<small>{tripTime(leg.departs_at)} · {leg.source_label || "参考时间"}</small></div></li>)}</ol>
          {plan.data.notes.map((note) => <p key={note} className="ps-destination__plan-note">{note}</p>)}
        </> : null}
      </div> : null}
      {available ? <details className="ps-destination__now">
        <summary>我想现在陪 TA 出发</summary>
        <p>这是你主动发起的出行，与上面的建议不同；点击后服务端才会生成行程并扣除 TA 的星球旅费。</p>
        <Button variant="secondary" block icon="journey" disabled={!option.affordable} loading={depart.isPending} onClick={() => depart.mutate()}>
          {option.affordable ? `确认现在出发 · ${option.fee} 旅费` : `旅费还差 ${option.fee - balance}`}
        </Button>
      </details> : null}
      {error ? (
        error.code === "INSUFFICIENT_FUNDS" || error.code === "ALREADY_TRAVELING" ? (
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

/** 出发站：宠物在家时 /journey 的内容。出发后同一张地图接管（不是独立交通页）。 */
export function DepartureStation({ home, last }: { home: HomeSnapshot; last: JourneyMapSnapshot | null }) {
  const { transport } = useServices();
  const userId = useOptionalCurrentHousehold()?.userId;
  const queryClient = useQueryClient();
  const [departed, setDeparted] = useState(false);
  const otherGardenKeepers = (home.guard.guarding_pets ?? []).filter((id) => id !== home.pet.pet_id);
  const query = useQuery({ queryKey: queryKeys.destinationsFor(userId ?? "-", home.pet.pet_id), queryFn: ({ signal }) => transport.destinations(home.pet.pet_id, signal) });
  const suggestions = useQuery({ queryKey: queryKeys.journeySuggestions(userId ?? "-", home.pet.pet_id), queryFn: ({ signal }) => transport.suggestions(home.pet.pet_id, signal), retry: false });
  const onDeparted = (snapshot: JourneyMapSnapshot) => {
    setDeparted(true);
    queryClient.setQueryData(queryKeys.journeyMap(home.pet.pet_id), snapshot);
    void queryClient.invalidateQueries({ queryKey: queryKeys.home });
    void queryClient.invalidateQueries({ queryKey: ["transport", "destinations"] });
    void queryClient.invalidateQueries({ queryKey: ["communicator"] });
  };
  return (
    <div className="ps-stack">
      <Card flat className="ps-row">
        <Icon name="home" />
        <div style={{ flex: 1 }}>
          <strong>{home.pet.name} 在家</strong>
          <div className="ps-muted">
            旅费 {home.wallet.balance}。{otherGardenKeepers.length > 0
              ? `还有 ${otherGardenKeepers.length} 位伙伴在家照看菜园；TA 出门也不会让家空下来。`
              : "TA 出门后，若没有其他伙伴或主人巡院，邻居可能来摘一点。"}
          </div>
        </div>
      </Card>
      {last && last.lifecycle === "completed" ? (
        <Card flat className="ps-row">
          <Icon name="check" />
          <span>
            上一次去了 {last.destination_title ?? "外面"}，已经平安回家。带回的东西在
            <Link to="/collection"> 回忆与收藏</Link>。
          </span>
        </Card>
      ) : null}
      {departed ? <p className="ps-muted">出发啦，正在打开地图…</p> : null}
      <Link className="ps-departure-archive" to="/guides"><Icon name="bookmark" size={17} /> 翻看 TA 之前的攻略手账 <Icon name="chevron" size={15} /></Link>
      <div className="ps-departure-intro"><span>旅途提议 · 由 TA 决定</span><h2>想把哪一段路，轻轻告诉 TA？</h2><p>你可以给建议，TA 会考虑；也可以明确选择现在陪 TA 出发。两种操作不会混在一起。</p></div>
      {suggestions.isError ? <ErrorState error={suggestions.error} onRetry={() => void suggestions.refetch()} /> : null}
      <QueryView query={query} isEmpty={(l) => l.length === 0}>
        {(list) => (
          <div className="ps-stack">
            {list.map((option) => (
              <DestinationCard key={option.destination_key} option={option} balance={home.wallet.balance} petId={home.pet.pet_id} suggestion={suggestions.data?.find((item) => item.destination_key === option.destination_key) ?? null} onSuggested={() => { void queryClient.invalidateQueries({ queryKey: queryKeys.journeySuggestions(userId ?? "-", home.pet.pet_id) }); void queryClient.invalidateQueries({ queryKey: ["communicator"] }); }} onDeparted={onDeparted} />
            ))}
          </div>
        )}
      </QueryView>
    </div>
  );
}
