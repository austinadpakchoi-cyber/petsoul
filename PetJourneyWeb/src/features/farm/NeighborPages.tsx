import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import type { NeighborHomeView, PetPresence, StealResult, VisitorPlot } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { Chip, DataOriginBadge, EmptyState, Icon, Page, PetAvatar, QueryView, TopBar } from "@/shared/ui";
import { BasketCatch, FARM_ART } from "./FarmMotion";
import { GARDEN_FIELD, GardenBed, GardenScene, anchorStyle, slotStyle, type BedSlot } from "./GardenScene";
import { produceVisual } from "./cropVisual";
import { WATCH_TONE, levelFromWatch, visitorWatchText, watchShort } from "./guardCopy";
import "./farm.css";

// 只说宠物在哪；“谁在看着菜园、会不会被发现”统一交给 guardCopy（宠物在家不是绝对防偷）。
const PRESENCE: Record<PetPresence, string> = {
  not_activated: "还没入住",
  at_home: "在家",
  in_transit: "出门旅行了",
  at_destination: "在目的地",
  visiting: "在店里坐着",
  returning: "在回家的路上",
  unknown: "位置未知",
};

export function NeighborsPage() {
  const { farm } = useServices();
  const query = useQuery({ queryKey: queryKeys.neighbors, queryFn: () => farm.neighbors(), refetchInterval: 60_000 });
  return (
    <Page>
      <TopBar title="串门" subtitle="有人看着时去摘，可能会被发现" back="/garden" />
      <QueryView query={query} isEmpty={(l) => l.length === 0} empty={<EmptyState icon="home" title="附近还没有别的家">有别的主人入住后，这里会出现他们的菜园。</EmptyState>}>
        {(list) => (
          <ul className="ps-neighbors">
            {list.map((n) => {
              const level = levelFromWatch(n.watch, n.guarded);
              return (
                <li key={n.home_id}>
                  <Link to={`/homes/${encodeURIComponent(n.home_id)}`} className="ps-neighbor">
                    <PetAvatar petId={n.pet.pet_id} name={n.pet.name} species={n.pet.species} photoUrl={n.pet.avatar_url} size={44} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <strong>{n.pet.name} 的家</strong>
                      <div className="ps-muted">{PRESENCE[n.presence]}</div>
                    </div>
                    {level !== "nobody" ? (
                      <Chip>{watchShort(level, "visitor")}</Chip>
                    ) : n.stealable_plots ? (
                      <Chip tone="leaf">{n.stealable_plots} 块能摘</Chip>
                    ) : (
                      <Chip>暂时没有熟的</Chip>
                    )}
                    <Icon name="chevron" size={16} />
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </QueryView>
    </Page>
  );
}

/** 地里那块小木牌上的字：作物 · 状态。 */
export function bedTag(entry: VisitorPlot): { text: string; tone: "ripe" | "done" | "quiet" } {
  const plot = entry.plot;
  const label = plot.crop_label ?? "空地";
  if (plot.stage === "ripe") {
    if (entry.taken_by_me) return { text: `${label} · 摘过了`, tone: "done" };
    if ((plot.steal_remaining ?? 0) <= 0) return { text: `${label} · 被摘完了`, tone: "done" };
    return { text: `${label} · 可摘 ${plot.steal_remaining}/${plot.steal_total ?? plot.steal_remaining}`, tone: "ripe" };
  }
  if (plot.stage === "growing") return { text: `${label} · 还没熟`, tone: "quiet" };
  return { text: plot.stage === "harvested" ? `${label} · 已收获` : "空地", tone: "quiet" };
}

/**
 * 场景里的一块地。熟了、还能摘时整块地就是按钮（点菜就是摘）；其余只报状态，不发请求。
 * 请求在路上时摘菜爪伸过来、菜被拽着晃；成功与被发现的动效交给场景（飞进篮子 / 门边泡泡），都等服务端回了才放。
 */
function StealBed({ home, entry, index, slot, caught, bedRef, onPicked, onFailed }: {
  home: NeighborHomeView;
  entry: VisitorPlot;
  index: number;
  slot?: BedSlot;
  caught: boolean;
  bedRef: (el: HTMLDivElement | null) => void;
  onPicked: (result: StealResult) => void;
  onFailed: (caught: boolean, message: string) => void;
}) {
  const { farm } = useServices();
  const queryClient = useQueryClient();
  const keyRef = useRef(newIdempotencyKey("steal"));
  const steal = useMutation({
    mutationFn: () => farm.steal({ home_id: home.home_id, plot_id: entry.plot.plot_id, cycle_id: entry.plot.cycle_id ?? "" }, keyRef.current),
    onSuccess: (result) => {
      keyRef.current = newIdempotencyKey("steal");
      onPicked(result);
      void queryClient.invalidateQueries({ queryKey: queryKeys.neighborHome(home.home_id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.neighbors });
      void queryClient.invalidateQueries({ queryKey: queryKeys.home });
    },
    onError: (error) => {
      const problem = toApiError(error);
      onFailed(problem.code === "FARM_GUARDED", problem.message);
      void queryClient.invalidateQueries({ queryKey: queryKeys.neighborHome(home.home_id) });
    },
  });
  const plot = entry.plot;
  const canTry = plot.stage === "ripe" && !entry.taken_by_me && (plot.steal_remaining ?? 0) > 0;
  const tag = bedTag(entry);
  const body = (
    <>
      <GardenBed cropKey={plot.crop_key} stage={plot.stage} />
      <span className={`ps-garden-slot__tag is-${tag.tone}`} aria-hidden="true">{tag.text}</span>
    </>
  );
  return (
    <div
      ref={bedRef}
      className={`ps-garden-slot${slot ? "" : " is-static"}${caught ? " is-caught" : ""}${steal.isPending ? " is-pending" : ""}`}
      style={slot ? slotStyle(slot) : undefined}
      data-testid="steal-plot"
    >
      {canTry ? (
        <button
          type="button"
          className="ps-garden-slot__hit"
          aria-label={`${home.guarded ? "试试看，" : ""}摘一颗${plot.crop_label ?? ""}（还能摘 ${plot.steal_remaining}/${plot.steal_total ?? plot.steal_remaining}）`}
          aria-busy={steal.isPending}
          disabled={steal.isPending}
          onClick={() => steal.mutate()}
        >
          {body}
        </button>
      ) : (
        <div className="ps-garden-slot__hit" role="img" aria-label={`第 ${index + 1} 块地：${tag.text}`}>
          {body}
        </div>
      )}
      {steal.isPending ? <img className="ps-garden-slot__paw" src={FARM_ART.pickPaw} alt="" aria-hidden="true" data-testid="pick-paw" /> : null}
    </div>
  );
}

interface Flight {
  id: number;
  cropKey: string;
  from: { x: number; y: number };
  dx: number;
  dy: number;
}

export function NeighborHomePage() {
  const { homeId = "" } = useParams();
  const { farm } = useServices();
  const layout = GARDEN_FIELD;
  const canvasRef = useRef<HTMLDivElement>(null);
  const basketRef = useRef<HTMLSpanElement>(null);
  const beds = useRef(new Map<string, HTMLDivElement>());
  const [last, setLast] = useState<StealResult | null>(null);
  const [problem, setProblem] = useState<{ caught: boolean; message: string } | null>(null);
  // 被发现时那块地抖一下、门边泡泡闪一下（900ms 后撤掉 class，下次被发现能重播）。
  const [caught, setCaught] = useState<{ plotId: string; n: number } | null>(null);
  const [picks, setPicks] = useState(0);
  const [flights, setFlights] = useState<Flight[]>([]);
  useEffect(() => {
    if (!caught) return;
    const timer = window.setTimeout(() => setCaught(null), 900);
    return () => window.clearTimeout(timer);
  }, [caught]);
  const query = useQuery({ queryKey: queryKeys.neighborHome(homeId), queryFn: () => farm.neighborHome(homeId) });

  const picked = (plotId: string, result: StealResult) => {
    setLast(result);
    setProblem(null);
    setPicks((n) => n + 1);
    // 一颗菜从那块地飞进右下角的篮子（画布坐标，按实际位置算；篮子钉在场景角上也算得对）。
    const canvas = canvasRef.current?.getBoundingClientRect();
    const bed = beds.current.get(plotId)?.getBoundingClientRect();
    const basket = basketRef.current?.getBoundingClientRect();
    if (!canvas || !bed || !basket) return;
    const from = { x: bed.left + bed.width / 2 - canvas.left, y: bed.top + bed.height * 0.2 - canvas.top };
    const to = { x: basket.left + basket.width / 2 - canvas.left, y: basket.top - canvas.top };
    const id = Date.now();
    setFlights((list) => [...list, { id, cropKey: result.gained_item_key, from, dx: to.x - from.x, dy: to.y - from.y }]);
    // 飞完（animationend）就收走；减少动效时不播动画，靠兜底计时收走。
    window.setTimeout(() => landed(id), 3000);
  };
  const landed = (id: number) => setFlights((list) => list.filter((f) => f.id !== id));

  return (
    <Page>
      <TopBar title="邻居家" back="/neighbors" />
      <QueryView query={query}>
        {(home) => {
          const level = levelFromWatch(home.watch, home.guarded);
          const placed = home.plots.slice(0, layout.slots.length);
          const extra = home.plots.slice(layout.slots.length);
          const bed = (entry: VisitorPlot, index: number, slot?: BedSlot) => (
            <StealBed
              key={entry.plot.plot_id}
              home={home}
              entry={entry}
              index={index}
              slot={slot}
              caught={caught?.plotId === entry.plot.plot_id}
              bedRef={(el) => {
                if (el) beds.current.set(entry.plot.plot_id, el);
                else beds.current.delete(entry.plot.plot_id);
              }}
              onPicked={(result) => picked(entry.plot.plot_id, result)}
              onFailed={(isCaught, message) => {
                setProblem({ caught: isCaught, message });
                if (isCaught) setCaught((c) => ({ plotId: entry.plot.plot_id, n: (c?.n ?? 0) + 1 }));
              }}
            />
          );
          return (
            <div className="ps-stack ps-steal-page">
              <GardenScene
                layout={layout}
                label={`${home.pet.name} 的菜园`}
                canvasRef={canvasRef}
                hud={
                  <>
                    <div className="ps-garden-scene__sign">
                      <PetAvatar petId={home.pet.pet_id} name={home.pet.name} species={home.pet.species} photoUrl={home.pet.avatar_url} size={32} />
                      <span>
                        <strong>{home.pet.name} 的家</strong>
                        <small>
                          {PRESENCE[home.presence]} · {watchShort(level, "visitor")}
                        </small>
                      </span>
                      <DataOriginBadge origin={home.data_origin} />
                    </div>
                    <span ref={basketRef} className="ps-garden-scene__basket" role="img" aria-label={picks ? `这次串门摘到 ${picks} 个` : "我的篮子，还空着"}>
                      {picks && last ? <BasketCatch key={picks} cropKey={last.gained_item_key} units={last.gained_units} delayed /> : <img src={FARM_ART.basket} alt="" />}
                    </span>
                  </>
                }
              >
                <p className={`ps-garden-bubble is-door is-${WATCH_TONE[level]}${caught ? " is-caught" : ""}`} style={anchorStyle(layout.door)} data-testid="steal-watch">
                  <Icon name={level === "nobody" ? "sprout" : "alert"} size={14} />
                  <span>{visitorWatchText(level, home.pet.name)}</span>
                </p>
                {placed.map((entry, index) => bed(entry, index, layout.slots[index]))}
                {flights.map((f) => (
                  <span
                    key={f.id}
                    className="ps-garden-flyer"
                    data-testid="garden-flyer"
                    aria-hidden="true"
                    style={{ left: f.from.x, top: f.from.y, "--dx": `${f.dx}px`, "--dy": `${f.dy}px` } as CSSProperties}
                    onAnimationEnd={(e) => {
                      if (e.target === e.currentTarget) landed(f.id);
                    }}
                  >
                    <img src={produceVisual(f.cropKey)} alt="" />
                  </span>
                ))}
              </GardenScene>
              {extra.length ? <div className="ps-garden-overflow">{extra.map((entry, i) => bed(entry, placed.length + i))}</div> : null}
              {last ? (
                <p key={`${last.plot.plot_id}:${picks}`} className="ps-steal-receipt" role="status">
                  {last.message} 卖给杂货铺或交居民订单就能换成旅费。
                </p>
              ) : null}
              {problem ? (
                <p className={`ps-steal-problem${problem.caught ? " is-caught" : ""}`} role="alert">
                  {problem.message}
                </p>
              ) : null}
              <p className="ps-muted">点熟了的菜就能摘。每一批作物，所有来串门的人加起来只能摘走一点点；同一批每人只能摘一次。</p>
            </div>
          );
        }}
      </QueryView>
    </Page>
  );
}
