import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import type { NeighborHomeView, PetPresence, StealResult, VisitorPlot } from "@/shared/contracts";
import { newIdempotencyKey } from "@/shared/api/idempotency";
import { toApiError } from "@/shared/api/errors";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { Button, Card, Chip, DataOriginBadge, EmptyState, Icon, Page, PetAvatar, QueryView, TopBar } from "@/shared/ui";
import "./farm.css";

const PRESENCE: Record<PetPresence, string> = {
  not_activated: "还没入住",
  at_home: "在家守着菜园",
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
      <TopBar title="串门" subtitle="宠物出门时，菜园没有守护" back="/home" />
      <QueryView query={query} isEmpty={(l) => l.length === 0} empty={<EmptyState icon="home" title="附近还没有别的家">有别的主人入住后，这里会出现他们的菜园。</EmptyState>}>
        {(list) => (
          <ul className="ps-neighbors">
            {list.map((n) => (
              <li key={n.home_id}>
                <Link to={`/homes/${encodeURIComponent(n.home_id)}`} className="ps-neighbor">
                  <PetAvatar petId={n.pet.pet_id} name={n.pet.name} species={n.pet.species} photoUrl={n.pet.avatar_url} size={44} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <strong>{n.pet.name} 的家</strong>
                    <div className="ps-muted">{PRESENCE[n.presence]}</div>
                  </div>
                  {n.guarded ? <Chip>有守护</Chip> : n.stealable_plots ? <Chip tone="leaf">{n.stealable_plots} 块能摘</Chip> : <Chip>暂时没有熟的</Chip>}
                  <Icon name="chevron" size={16} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </QueryView>
    </Page>
  );
}

function StealButton({ home, entry, onDone }: { home: NeighborHomeView; entry: VisitorPlot; onDone: (result: StealResult) => void }) {
  const { farm } = useServices();
  const queryClient = useQueryClient();
  const keyRef = useRef(newIdempotencyKey("steal"));
  const steal = useMutation({
    mutationFn: () => farm.steal({ home_id: home.home_id, plot_id: entry.plot.plot_id, cycle_id: entry.plot.cycle_id ?? "" }, keyRef.current),
    onSuccess: (result) => {
      keyRef.current = newIdempotencyKey("steal");
      onDone(result);
      void queryClient.invalidateQueries({ queryKey: queryKeys.neighborHome(home.home_id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.neighbors });
      void queryClient.invalidateQueries({ queryKey: queryKeys.home });
    },
    onError: () => void queryClient.invalidateQueries({ queryKey: queryKeys.neighborHome(home.home_id) }),
  });
  const plot = entry.plot;
  const canTry = plot.stage === "ripe" && !entry.taken_by_me && (plot.steal_remaining ?? 0) > 0;
  return (
    <div className="ps-stack" style={{ gap: 4, alignItems: "center" }}>
      <Button size="sm" variant={home.guarded ? "secondary" : "leaf"} disabled={!canTry} loading={steal.isPending} onClick={() => steal.mutate()}>
        {entry.taken_by_me ? "摘过了" : home.guarded ? "试试看" : "摘一颗"}
      </Button>
      {steal.isError ? (
        <span role="alert" className="ps-muted" style={{ color: toApiError(steal.error).code === "FARM_GUARDED" ? "var(--c-coral)" : "var(--c-danger)", fontSize: 11 }}>
          {toApiError(steal.error).message}
        </span>
      ) : null}
    </div>
  );
}

export function NeighborHomePage() {
  const { homeId = "" } = useParams();
  const { farm } = useServices();
  const [last, setLast] = useState<StealResult | null>(null);
  const query = useQuery({ queryKey: queryKeys.neighborHome(homeId), queryFn: () => farm.neighborHome(homeId) });
  return (
    <Page>
      <TopBar title="邻居家" back="/neighbors" />
      <QueryView query={query}>
        {(home) => (
          <div className="ps-stack">
            <Card className="ps-row">
              <PetAvatar petId={home.pet.pet_id} name={home.pet.name} species={home.pet.species} photoUrl={home.pet.avatar_url} size={52} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <h2 className="ps-h2">{home.pet.name} 的家</h2>
                <div className="ps-muted">{PRESENCE[home.presence]}</div>
              </div>
              <DataOriginBadge origin={home.data_origin} />
            </Card>
            {home.guarded ? (
              <Card flat className="ps-row">
                <Icon name="alert" />
                <span>{home.presence === "at_home" ? `${home.pet.name} 正在家守着菜园` : `${home.pet.name} 的主人正在巡院`}——这时候去摘会被发现。</span>
              </Card>
            ) : null}
            {last ? (
              <Card flat className="ps-row" role="status">
                <Icon name="gift" />
                <span>{last.message} 卖给杂货铺或交居民订单就能换成旅费。</span>
              </Card>
            ) : null}
            <div className="ps-plots">
              {home.plots.map((entry) => (
                <div key={entry.plot.plot_id} className={`ps-plot ps-plot--${entry.plot.stage}`}>
                  <div className="ps-plot__art" aria-hidden="true">
                    <Icon name="sprout" size={28} />
                  </div>
                  <div style={{ fontWeight: 700, fontSize: "var(--fs-sm)" }}>{entry.plot.crop_label ?? "空地"}</div>
                  {entry.plot.stage === "ripe" ? (
                    <span className="ps-muted" style={{ fontSize: 11 }}>
                      还能摘 {entry.plot.steal_remaining}/{entry.plot.steal_total}
                    </span>
                  ) : (
                    <Chip>{entry.plot.stage === "growing" ? "还没熟" : entry.plot.stage === "harvested" ? "已收获" : "空地"}</Chip>
                  )}
                  {entry.plot.stage === "ripe" ? <StealButton home={home} entry={entry} onDone={setLast} /> : null}
                </div>
              ))}
            </div>
            <p className="ps-muted">每一批作物，所有来串门的人加起来只能摘走一点点；同一批每人只能摘一次。</p>
          </div>
        )}
      </QueryView>
    </Page>
  );
}
