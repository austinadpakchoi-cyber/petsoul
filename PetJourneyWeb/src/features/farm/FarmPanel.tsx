import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";
import type { CropInfo, HomeSnapshot, PlotSummary } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { formatDuration, useNow } from "@/shared/time/clock";
import { Button, Chip, ErrorState, Icon, Sheet } from "@/shared/ui";
import soil from "@/features/home/assets/living/plot-soil.webp";
import { cropVisual } from "./cropVisual";
import "./farm.css";

const STAGE_TEXT = {
  empty: "空地",
  growing: "生长中",
  ripe: "成熟了",
  harvested: "已收获",
} as const;

function growText(seconds: number): string {
  return seconds < 3600
    ? `${Math.round(seconds / 60)} 分钟`
    : `${(seconds / 3600).toFixed(seconds % 3600 ? 1 : 0)} 小时`;
}

function useFarmAction(homeId: string) {
  const { farm } = useServices();
  const queryClient = useQueryClient();
  // 一次用户动作一个幂等键；失败重试复用同一个键，成功后才换新键。
  const keyRef = useRef(newIdempotencyKey("farm"));
  const fingerprint = useRef("");
  return useMutation({
    mutationFn: (input: {
      plot: PlotSummary;
      action: "plant" | "harvest";
      cropKey?: string;
    }) => {
      const body = {
        home_id: homeId,
        plot_id: input.plot.plot_id,
        cycle_id: input.plot.cycle_id,
        action: input.action,
        crop_key: input.cropKey ?? null,
      };
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

function GardenMoment({
  plot,
  nowMs,
  busy,
  onPlant,
  onHarvest,
}: {
  plot: PlotSummary;
  nowMs: number;
  busy: boolean;
  onPlant: () => void;
  onHarvest: () => void;
}) {
  const left =
    plot.stage === "growing" && plot.ripe_at
      ? Date.parse(plot.ripe_at) - nowMs
      : null;
  const ripe = plot.stage === "ripe";
  const label =
    plot.stage === "harvested" ? "空出来啦" : (plot.crop_label ?? "种点什么");
  const action =
    plot.stage === "ripe"
      ? "收获"
      : plot.stage === "empty" || plot.stage === "harvested"
        ? "种下"
        : null;
  return (
    <section
      className={`ps-garden-moment is-${plot.stage}`}
      data-stage={plot.stage}
      data-testid="garden-moment"
    >
      <div className="ps-garden-moment__art" aria-hidden="true">
        <img src={soil} alt="" />
        {plot.stage === "growing" || plot.stage === "ripe" ? (
          <img
            className={`ps-garden-moment__crop is-${ripe ? plot.crop_key ?? "unknown" : "growing"}`}
            src={cropVisual(plot.crop_key, ripe ? "ripe" : "growing")}
            alt=""
          />
        ) : null}
        {plot.stage === "ripe" ? (
          <span className="ps-garden-moment__spark" />
        ) : null}
      </div>
      <div className="ps-garden-moment__copy">
        <span>庭院菜地</span>
        <h3>{label}</h3>
        <p>
          {left !== null && left > 0
            ? `还要 ${formatDuration(left)}`
            : STAGE_TEXT[plot.stage]}
          {plot.steal_total !== null &&
          plot.stage !== "empty" &&
          plot.stage !== "harvested"
            ? ` · 邻里可摘 ${plot.steal_remaining}/${plot.steal_total}`
            : ""}
        </p>
      </div>
      {action ? (
        <Button
          variant={plot.stage === "ripe" ? "leaf" : "secondary"}
          loading={busy}
          onClick={plot.stage === "ripe" ? onHarvest : onPlant}
        >
          {action}
        </Button>
      ) : null}
    </section>
  );
}

function CropPicker({
  onPick,
  onClose,
  busy,
  error,
}: {
  onPick: (crop: CropInfo) => void;
  onClose: () => void;
  busy: boolean;
  error: unknown;
}) {
  const { farm, economy } = useServices();
  const crops = useQuery({
    queryKey: queryKeys.crops,
    queryFn: () => farm.crops(),
    staleTime: 10 * 60_000,
  });
  const items = useQuery({
    queryKey: queryKeys.collection,
    queryFn: () => economy.collection(),
  });
  const seeds = (key: string) =>
    (items.data ?? []).filter((i) => i.kind === "seed" && i.item_key === key)
      .length;
  return (
    <Sheet
      className="ps-crop-sheet"
      title="种点什么"
      subtitle="成熟后收进仓库，卖掉或交订单变成旅费"
      onClose={onClose}
    >
      {crops.isError ? (
        <ErrorState error={crops.error} onRetry={() => void crops.refetch()} />
      ) : null}
          <ul className="ps-crop-list">
        {(crops.data ?? []).map((crop) => {
          const count = crop.requires_seed ? seeds(crop.crop_key) : null;
          const disabled = count === 0;
          return (
            <li key={crop.crop_key}>
              <span className="ps-crop-list__art" aria-hidden="true">
                <img src={cropVisual(crop.crop_key, "ripe")} alt="" />
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <strong>{crop.label}</strong>
                <div className="ps-muted">
                  {growText(crop.grow_seconds)}成熟 · 收 {crop.yield_units}{" "}
                  个（杂货铺约 {crop.yield_units * crop.unit_value} 旅费）·
                  邻居合计最多摘 {crop.steal_total}
                </div>
                {crop.requires_seed ? (
                  <Chip tone={count ? "leaf" : "neutral"} icon="gift">
                    {count ? `旅行带回的种子 ×${count}` : "需要旅行带回的种子"}
                  </Chip>
                ) : null}
              </div>
              <Button
                size="sm"
                variant="primary"
                disabled={disabled}
                loading={busy}
                onClick={() => onPick(crop)}
              >
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

function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** 宠物外出时主人巡院：短时守护（服务端裁决时长与冷却），不把“外出”默认显示成有人守着。 */
function PatrolControl({ snapshot }: { snapshot: HomeSnapshot }) {
  const { farm } = useServices();
  const queryClient = useQueryClient();
  const patrol = useMutation({
    mutationFn: () => farm.patrol(),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: queryKeys.home }),
  });
  const guard = snapshot.guard;
  if (snapshot.presence === "at_home" || snapshot.presence === "not_activated")
    return null;
  if (guard.basis === "owner_patrol" && guard.until) {
    return (
      <Chip tone="leaf" icon="check">
        你在巡院，守到 {clock(guard.until)}
      </Chip>
    );
  }
  return (
    <div className="ps-row" style={{ flexWrap: "wrap" }}>
      <Button
        size="sm"
        variant="secondary"
        icon="home"
        disabled={Boolean(guard.next_patrol_at)}
        loading={patrol.isPending}
        onClick={() => patrol.mutate()}
      >
        {guard.next_patrol_at
          ? `${clock(guard.next_patrol_at)} 后可以再巡院`
          : "去院子里巡一圈（守 10 分钟）"}
      </Button>
      {patrol.isError ? (
        <span
          role="alert"
          className="ps-muted"
          style={{ color: "var(--c-danger)" }}
        >
          {toApiError(patrol.error).message}
        </span>
      ) : null}
    </div>
  );
}

export function FarmPanel({ snapshot }: { snapshot: HomeSnapshot }) {
  const [params, setParams] = useSearchParams();
  const selected = snapshot.plots.find((p) => p.plot_id === params.get("plot"));
  const closePlot = () => {
    const next = new URLSearchParams(params);
    next.delete("plot");
    setParams(next);
  };
  const queryClient = useQueryClient();
  const nowMs = useNow(1000);
  const action = useFarmAction(snapshot.home_id);
  const [picking, setPicking] = useState<PlotSummary | null>(null);
  const [busyPlot, setBusyPlot] = useState<string | null>(null);
  // 到了成熟时间就重新读取权威快照（成熟由服务端按时间判定）。
  const nextRipe = snapshot.plots
    .filter((p) => p.stage === "growing" && p.ripe_at)
    .map((p) => Date.parse(p.ripe_at!))
    .sort((a, b) => a - b)[0];
  const due = nextRipe !== undefined && nextRipe <= nowMs;
  useEffect(() => {
    if (due) void queryClient.invalidateQueries({ queryKey: queryKeys.home });
  }, [due, queryClient]);

  const run = (
    plot: PlotSummary,
    kind: "plant" | "harvest",
    cropKey?: string,
  ) => {
    if (action.isPending) return;
    setBusyPlot(plot.plot_id);
    action.mutate(
      { plot, action: kind, cropKey },
      { onSettled: () => setBusyPlot(null), onSuccess: () => setPicking(null) },
    );
  };
  const failed = action.error ? toApiError(action.error) : null;

  // 菜地本身是入口；未点地块时不在场景下重复渲染一组功能卡片。
  if (!selected) return null;

  return picking ? (
    <CropPicker
      busy={action.isPending}
      error={action.error}
      onClose={() => setPicking(null)}
      onPick={(crop) => run(picking, "plant", crop.crop_key)}
    />
  ) : (
    <Sheet
      className="ps-garden-sheet"
      title={
        selected.stage === "ripe"
          ? `收下 ${selected.crop_label}`
          : selected.stage === "growing"
            ? `照看 ${selected.crop_label}`
            : "种点什么"
      }
      subtitle="变化会回到庭院；收成先进入仓库，不会直接增加旅费"
      onClose={closePlot}
    >
      <div className="ps-stack ps-garden-sheet__body">
        <GardenMoment
          plot={selected}
          nowMs={nowMs}
          busy={action.isPending || busyPlot === selected.plot_id}
          onPlant={() => setPicking(selected)}
          onHarvest={() => run(selected, "harvest")}
        />
        {action.data?.plot.plot_id === selected.plot_id &&
        action.data.gained_items.length ? (
          <p role="status" className="ps-farm-receipt">
            已收进仓库：{action.data.gained_items.join("、")}
            。旅费未因收获增加。
          </p>
        ) : null}
        <div className="ps-garden-sheet__ledger">
          <span>仓库</span>
          <div className="ps-row" data-testid="plot-pantry">
            {snapshot.pantry.length ? (
              snapshot.pantry.map((item) => (
                <Chip key={item.item_key}>
                  {item.label} ×{item.qty}
                </Chip>
              ))
            ) : (
              <span className="ps-muted">还没有收成</span>
            )}
          </div>
          <p>
            {snapshot.guard.basis === "pet_at_home"
              ? "TA 在家，邻居偷不到。"
              : snapshot.guard.guarding
                ? "你正在巡院。"
                : "TA 出门了，邻居可能来摘一点。"}
          </p>
        </div>
        <PatrolControl snapshot={snapshot} />
        <div className="ps-garden-sheet__links">
          <Link to="/market" className="ps-btn ps-btn--secondary">
            <Icon name="gift" size={16} /> 仓库与集市
          </Link>
          <Link to="/neighbors" className="ps-btn ps-btn--ghost">
            <Icon name="compass" size={16} /> 去邻居家串门
          </Link>
        </div>
        {failed ? <ErrorState error={action.error} /> : null}
      </div>
    </Sheet>
  );
}
