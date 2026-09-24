import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import type { CropInfo, HomeSnapshot, PlotSummary } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useActiveHome, useOptionalCurrentHousehold } from "@/shared/session/householdContext";
import { formatDuration, useNow } from "@/shared/time/clock";
import { Button, Chip, ErrorState, Icon, Page, PetAvatar, QueryView, Sheet, TopBar } from "@/shared/ui";
import { cropArt, produceVisual } from "./cropVisual";
import { BasketCatch, FARM_ART, SeedPour } from "./FarmMotion";
import { GARDEN_FIELD, GardenBed, GardenScene, anchorStyle, slotStyle, type BedSlot } from "./GardenScene";
import { WATCH_TONE, levelFromGuard, ownerWatchText, watchShort } from "./guardCopy";
import "./farm.css";

/*
 * 菜园（二级页 /garden）：从家园的“菜园”入口进来。QQ 农场式——整页是一块场地，点地里的菜就是操作：
 * 熟了点一下就收、空地点一下选种子、正在长的点一下看还要多久。仓库/集市、串门、巡院都从这里去。
 * 规则都由服务端裁决：成熟按服务端时间、收成先进仓库（不直接加旅费）、稀有作物消耗旅行带回的种子。
 */

function growText(seconds: number): string {
  return seconds < 3600 ? `${Math.round(seconds / 60)} 分钟` : `${(seconds / 3600).toFixed(seconds % 3600 ? 1 : 0)} 小时`;
}

function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function useFarmAction(homeId: string) {
  const { farm } = useServices();
  const queryClient = useQueryClient();
  // 一次用户动作一个幂等键；失败重试复用同一个键，成功后才换新键。
  const keyRef = useRef(newIdempotencyKey("farm"));
  const fingerprint = useRef("");
  return useMutation({
    mutationFn: (input: { plot: PlotSummary; action: "plant" | "harvest"; cropKey?: string }) => {
      const body = { home_id: homeId, plot_id: input.plot.plot_id, cycle_id: input.plot.cycle_id, action: input.action, crop_key: input.cropKey ?? null };
      const next = JSON.stringify(body);
      if (fingerprint.current !== next) {
        keyRef.current = newIdempotencyKey("farm");
        fingerprint.current = next;
      }
      return farm.act(body, keyRef.current);
    },
    onSuccess: () => {
      keyRef.current = newIdempotencyKey("farm");
      // 跨模块失效规则（MODULE-MAP）：农场结算后刷新家园快照（钱包/地块/版本）与收藏（种子被消耗）。
      void queryClient.invalidateQueries({ queryKey: queryKeys.home });
      void queryClient.invalidateQueries({ queryKey: queryKeys.collection });
    },
  });
}

function CropPicker({ onPick, onClose, busy, error }: { onPick: (crop: CropInfo) => void; onClose: () => void; busy: boolean; error: unknown }) {
  const { farm, economy } = useServices();
  const crops = useQuery({ queryKey: queryKeys.crops, queryFn: () => farm.crops(), staleTime: 10 * 60_000 });
  // 种子在当前这只宠物的收藏里：按当前宠物读（一家有两只时不带 pet_id 后端回 409，种子数会被当成 0）。
  // 键与“回忆与收藏”页一致：live 按账号与宠物，演示用公共键；种下后按 queryKeys.collection 前缀失效，两种键都覆盖。
  const selection = useOptionalCurrentHousehold();
  const userId = selection?.userId ?? null;
  const petId = selection?.pet?.pet_id ?? null;
  const fixture = env.dataMode === "fixture";
  const items = useQuery({
    queryKey: fixture ? queryKeys.collection : queryKeys.collectionFor(userId ?? "-", petId ?? "-"),
    queryFn: ({ signal }) => economy.collection(petId, signal),
    enabled: fixture || Boolean(userId && petId),
  });
  const seeds = (key: string) => (items.data ?? []).filter((i) => i.kind === "seed" && i.item_key === key).length;
  return (
    <Sheet className="ps-crop-sheet" title="种点什么" subtitle="成熟后收进仓库，卖掉或交订单变成星币" onClose={onClose}>
      {crops.isError ? <ErrorState error={crops.error} onRetry={() => void crops.refetch()} /> : null}
      <ul className="ps-crop-list">
        {(crops.data ?? []).map((crop) => {
          const count = crop.requires_seed ? seeds(crop.crop_key) : null;
          return (
            <li key={crop.crop_key}>
              <span className="ps-crop-list__art" aria-hidden="true">
                <img src={cropArt(crop.crop_key, "ripe").src} alt="" />
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <strong>{crop.label}</strong>
                <div className="ps-muted">
                  {growText(crop.grow_seconds)}成熟 · 收 {crop.yield_units} 个（杂货铺约 {crop.yield_units * crop.unit_value} 星币）· 邻居合计最多摘 {crop.steal_total}
                </div>
                {crop.requires_seed ? <Chip tone={count ? "leaf" : "neutral"} icon="gift">{count ? `旅行带回的种子 ×${count}` : "需要旅行带回的种子"}</Chip> : null}
              </div>
              <Button size="sm" variant="primary" disabled={count === 0} loading={busy} onClick={() => onPick(crop)}>
                种下
              </Button>
            </li>
          );
        })}
      </ul>
      {error ? <ErrorState error={error} /> : null}
    </Sheet>
  );
}

/** 宠物外出时主人巡院：短时守护（服务端裁决时长与冷却），不把“外出”默认显示成有人守着。 */
function PatrolControl({ snapshot }: { snapshot: HomeSnapshot }) {
  const { farm } = useServices();
  const queryClient = useQueryClient();
  const patrol = useMutation({ mutationFn: () => farm.patrol(), onSuccess: () => void queryClient.invalidateQueries({ queryKey: queryKeys.home }) });
  const guard = snapshot.guard;
  if (snapshot.presence === "at_home" || snapshot.presence === "not_activated") return null;
  if (guard.basis === "owner_patrol" && guard.until) {
    return <Chip tone="leaf" icon="check">你在巡院，守到 {clock(guard.until)}</Chip>;
  }
  return (
    <div className="ps-row" style={{ flexWrap: "wrap" }}>
      <Button size="sm" variant="secondary" icon="home" disabled={Boolean(guard.next_patrol_at)} loading={patrol.isPending} onClick={() => patrol.mutate()}>
        {guard.next_patrol_at ? `${clock(guard.next_patrol_at)} 后可以再巡院` : "去院子里巡一圈（守 10 分钟）"}
      </Button>
      {patrol.isError ? <span role="alert" className="ps-muted" style={{ color: "var(--c-danger)" }}>{toApiError(patrol.error).playerMessage}</span> : null}
    </div>
  );
}

/** 自家地里那块小木牌：作物 · 状态。 */
export function myBedTag(plot: PlotSummary): { text: string; tone: "ripe" | "quiet" } {
  if (plot.stage === "ripe") return { text: `${plot.crop_label ?? "作物"} · 可收获`, tone: "ripe" };
  if (plot.stage === "growing") return { text: `${plot.crop_label ?? "作物"} · 正在长`, tone: "quiet" };
  return { text: plot.stage === "harvested" ? "空出来啦 · 种点什么" : "空地 · 种点什么", tone: "quiet" };
}

interface Flight {
  id: number;
  cropKey: string | null;
  from: { x: number; y: number };
  dx: number;
  dy: number;
}

export function MyGarden({ snapshot }: { snapshot: HomeSnapshot }) {
  const layout = GARDEN_FIELD;
  const queryClient = useQueryClient();
  const nowMs = useNow(1000);
  const action = useFarmAction(snapshot.home_id);
  const canvasRef = useRef<HTMLDivElement>(null);
  const basketRef = useRef<HTMLAnchorElement>(null);
  const beds = useRef(new Map<string, HTMLDivElement>());
  const [picking, setPicking] = useState<PlotSummary | null>(null);
  const [peek, setPeek] = useState<string | null>(null);
  const [planted, setPlanted] = useState<string | null>(null);
  const [harvest, setHarvest] = useState<{ cropKey: string | null; n: number } | null>(null);
  const [flights, setFlights] = useState<Flight[]>([]);

  // 到了成熟时间就重新读取权威快照（成熟由服务端按时间判定）。
  const nextRipe = snapshot.plots.filter((p) => p.stage === "growing" && p.ripe_at).map((p) => Date.parse(p.ripe_at!)).sort((a, b) => a - b)[0];
  const due = nextRipe !== undefined && nextRipe <= nowMs;
  useEffect(() => {
    if (due) void queryClient.invalidateQueries({ queryKey: queryKeys.home });
  }, [due, queryClient]);
  useEffect(() => {
    if (!planted) return;
    const timer = window.setTimeout(() => setPlanted(null), 2600);
    return () => window.clearTimeout(timer);
  }, [planted]);

  // 一颗菜从那块地飞进右下角的篮子（画布坐标；篮子钉在场景角上，按实际位置算）。
  const flyToBasket = (plotId: string, cropKey: string | null) => {
    const canvas = canvasRef.current?.getBoundingClientRect();
    const bed = beds.current.get(plotId)?.getBoundingClientRect();
    const basket = basketRef.current?.getBoundingClientRect();
    if (!canvas || !bed || !basket) return;
    const from = { x: bed.left + bed.width / 2 - canvas.left, y: bed.top + bed.height * 0.2 - canvas.top };
    const to = { x: basket.left + basket.width / 2 - canvas.left, y: basket.top - canvas.top };
    const id = Date.now();
    setFlights((list) => [...list, { id, cropKey, from, dx: to.x - from.x, dy: to.y - from.y }]);
    // 飞完（animationend）就收走；减少动效时不播动画，靠兜底计时收走。
    window.setTimeout(() => landed(id), 3000);
  };
  const landed = (id: number) => setFlights((list) => list.filter((f) => f.id !== id));

  const run = (plot: PlotSummary, kind: "plant" | "harvest", cropKey?: string) => {
    if (action.isPending) return;
    setPeek(null);
    action.mutate(
      { plot, action: kind, cropKey },
      {
        onSuccess: () => {
          if (kind === "harvest") {
            setHarvest((h) => ({ cropKey: plot.crop_key, n: (h?.n ?? 0) + 1 }));
            flyToBasket(plot.plot_id, plot.crop_key);
          } else {
            setPicking(null);
            setPlanted(plot.plot_id);
          }
        },
      },
    );
  };

  const done = action.isSuccess ? action.variables.action : null;
  const pantryTotal = snapshot.pantry.reduce((n, item) => n + item.qty, 0);
  const watch = levelFromGuard(snapshot.guard);
  const placed = snapshot.plots.slice(0, layout.slots.length);
  const extra = snapshot.plots.slice(layout.slots.length);

  const bed = (plot: PlotSummary, index: number, slot?: BedSlot) => {
    const tag = myBedTag(plot);
    const busy = action.isPending && action.variables?.plot.plot_id === plot.plot_id;
    const left = plot.stage === "growing" && plot.ripe_at ? Date.parse(plot.ripe_at) - nowMs : null;
    const label =
      plot.stage === "ripe" ? `收获${plot.crop_label ?? ""}` : plot.stage === "growing" ? `看看${plot.crop_label ?? "作物"}还要多久` : `在第 ${index + 1} 块地种点什么`;
    const onClick =
      plot.stage === "ripe"
        ? () => run(plot, "harvest")
        : plot.stage === "growing"
          ? () => setPeek((p) => (p === plot.plot_id ? null : plot.plot_id))
          : () => {
              setPeek(null);
              setPicking(plot);
            };
    return (
      <div
        key={plot.plot_id}
        ref={(el) => {
          if (el) beds.current.set(plot.plot_id, el);
          else beds.current.delete(plot.plot_id);
        }}
        className={`ps-garden-slot${slot ? "" : " is-static"}${busy ? " is-pending" : ""}`}
        style={slot ? slotStyle(slot) : undefined}
        data-testid="garden-plot"
      >
        <button type="button" className="ps-garden-slot__hit" aria-label={label} aria-busy={busy} disabled={busy} onClick={onClick}>
          <GardenBed cropKey={plot.crop_key} stage={plot.stage} planted={planted === plot.plot_id} />
          <span className={`ps-garden-slot__tag is-${tag.tone}`} aria-hidden="true">{tag.text}</span>
        </button>
        {planted === plot.plot_id ? <span className="ps-garden-slot__pour"><SeedPour /></span> : null}
        {busy && plot.stage === "ripe" ? <img className="ps-garden-slot__paw" src={FARM_ART.pickPaw} alt="" aria-hidden="true" data-testid="pick-paw" /> : null}
        {peek === plot.plot_id ? (
          <p className="ps-garden-bubble is-calm is-peek" role="status">
            <Icon name="sprout" size={14} />
            <span>
              {plot.crop_label ?? "作物"}
              {left !== null && left > 0 ? ` 还要 ${formatDuration(left)}` : " 快熟了"}
              {plot.steal_total !== null ? ` · 邻里可摘 ${plot.steal_remaining}/${plot.steal_total}` : ""}
            </span>
          </p>
        ) : null}
      </div>
    );
  };

  return (
    <div className="ps-stack ps-steal-page">
      <GardenScene
        layout={layout}
        label={`${snapshot.pet.name}的菜园`}
        canvasRef={canvasRef}
        hud={
          <>
            <div className="ps-garden-scene__sign">
              <PetAvatar petId={snapshot.pet.pet_id} name={snapshot.pet.name} species={snapshot.pet.species} photoUrl={snapshot.pet.photo_url} size={32} />
              <span>
                <strong>{snapshot.pet.name}的菜园</strong>
                <small>{watchShort(watch, "owner")}</small>
              </span>
            </div>
            <Link ref={basketRef} to="/market" className="ps-garden-scene__basket is-link" aria-label={`仓库里有 ${pantryTotal} 个收成，去仓库与集市`}>
              {harvest ? <BasketCatch key={harvest.n} cropKey={harvest.cropKey} delayed /> : <img src={FARM_ART.basket} alt="" />}
              <b className="ps-garden-scene__count" aria-hidden="true">{pantryTotal}</b>
            </Link>
          </>
        }
      >
        {/* 与邻居页同一套“谁在看着”的说法：宠物在家是概率保护，不承诺绝对防偷 */}
        <p className={`ps-garden-bubble is-door is-${WATCH_TONE[watch]}`} style={anchorStyle(layout.door)} data-testid="garden-watch">
          <Icon name={watch === "nobody" ? "sprout" : "alert"} size={14} />
          <span>{ownerWatchText(watch, snapshot.pet.name, snapshot.guard.until)}</span>
        </p>
        {placed.map((plot, index) => bed(plot, index, layout.slots[index]))}
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
      {extra.length ? <div className="ps-garden-overflow">{extra.map((plot, i) => bed(plot, placed.length + i))}</div> : null}
      {done === "harvest" && action.data?.gained_items.length ? (
        <p key={`h${harvest?.n ?? 0}`} className="ps-steal-receipt" role="status">
          {/* 服务端原话形如「星星番茄 ×6 进了仓库」 */}
          {action.data.gained_items.join("、")}。星币没有变，卖掉或交订单时才会增加。
        </p>
      ) : null}
      {done === "plant" ? (
        <p className="ps-steal-receipt" role="status">
          已种下{action.data?.plot.crop_label ?? "新的作物"}，等它慢慢长大。
        </p>
      ) : null}
      {action.isError && !picking ? (
        <p className="ps-steal-problem" role="alert">
          {toApiError(action.error).playerMessage}
        </p>
      ) : null}
      <nav className="ps-garden-actions" aria-label="菜园去处">
        <Link to="/market" className="ps-btn ps-btn--secondary">
          <Icon name="gift" size={16} /> 仓库与集市
        </Link>
        <Link to="/neighbors" className="ps-btn ps-btn--secondary">
          <Icon name="compass" size={16} /> 去串门
        </Link>
      </nav>
      <PatrolControl snapshot={snapshot} />
      <p className="ps-muted">点熟了的菜就收，点空地选种子。收成先进仓库，卖掉或交居民订单才变成星币。</p>
      {picking ? <CropPicker busy={action.isPending} error={action.error} onClose={() => setPicking(null)} onPick={(crop) => run(picking, "plant", crop.crop_key)} /> : null}
    </div>
  );
}

export function GardenPage() {
  const query = useActiveHome({ refetchInterval: 60_000 });
  const wallet = query.data?.wallet;
  return (
    <Page className="ps-garden-page">
      <TopBar
        title="菜园"
        back="/map"
        right={
          wallet ? (
            <Link to="/market" className="ps-garden-wallet" aria-label={`${wallet.balance} 星币，去仓库与集市`}>
              <Icon name="coin" size={16} />
              <strong>{wallet.balance}</strong>
            </Link>
          ) : null
        }
      />
      <QueryView query={query}>{(snapshot) => <MyGarden snapshot={snapshot} />}</QueryView>
    </Page>
  );
}
