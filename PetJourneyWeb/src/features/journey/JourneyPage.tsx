import { useCallback, useEffect, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";
import type { JourneyMapSnapshot, LatLng } from "@/shared/contracts";
import { toApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import {
  currentLeg,
  legRoute,
  legTitle,
  remainingMs,
  vehicleAnchorAt,
} from "@/shared/journey/vehicle";
import { SchematicMapSurface } from "@/shared/map";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { useActiveHome } from "@/shared/session/householdContext";
import { Slot } from "@/shared/slots/Slot";
import type { JourneyOverlayProps } from "@/shared/slots/names";
import { formatDuration, useNow } from "@/shared/time/clock";
import {
  Button,
  DataOriginBadge,
  ErrorState,
  Icon,
  LoadingState,
  Page,
  TopBar,
  ToggleChip,
} from "@/shared/ui";
import { resetFixtureEpoch } from "@/fixtures/world";
import { DepartureStation } from "./DepartureStation";
import "./journey.css";

function JourneyMap({
  snapshot,
  nowMs,
}: {
  snapshot: JourneyMapSnapshot;
  nowMs: number;
}) {
  const [params, setParams] = useSearchParams();
  const sheet = params.get("sheet");
  const [sheetKind, sheetId] = sheet
    ? (sheet.split(":", 2) as ["leg" | "media", string])
    : [null, null];

  const openSheet = useCallback(
    (kind: "leg" | "media", id: string) => {
      const next = new URLSearchParams(params);
      next.set("sheet", `${kind}:${id}`);
      setParams(next);
    },
    [params, setParams],
  );
  const closeSheet = useCallback(() => {
    const next = new URLSearchParams(params);
    next.delete("sheet");
    setParams(next);
  }, [params, setParams]);

  const leg = currentLeg(snapshot);
  const anchor = vehicleAnchorAt(snapshot, nowMs);
  const bounds = useMemo<LatLng[]>(
    () => snapshot.legs.flatMap((l) => legRoute(l)),
    [snapshot.legs],
  );
  const routes = useMemo(
    () =>
      snapshot.legs.map((l) => ({
        id: l.leg_id,
        points: legRoute(l),
        dashed: l.position_basis === "schematic",
        active: l.leg_id === leg?.leg_id,
      })),
    [snapshot.legs, leg?.leg_id],
  );
  const places = useMemo(
    () =>
      snapshot.legs.flatMap((l) => [
        {
          id: `${l.leg_id}-o`,
          at: { lat: l.origin.lat ?? 0, lng: l.origin.lng ?? 0 },
          name: l.origin.name.replace("（示意）", ""),
        },
        {
          id: `${l.leg_id}-d`,
          at: { lat: l.destination.lat ?? 0, lng: l.destination.lng ?? 0 },
          name: l.destination.name.replace("（示意）", ""),
        },
      ]),
    [snapshot.legs],
  );
  const overlayProps: JourneyOverlayProps = { snapshot, nowMs, openSheet };

  return (
    <>
      {leg ? (
        <button
          type="button"
          className="ps-journey-summary"
          onClick={() => openSheet("leg", leg.leg_id)}
        >
          <span>
            <strong>{legTitle(leg)}</strong>
            <span>
              {leg.origin.name.replace("（示意）", "")} → {leg.destination.name.replace("（示意）", "")}
            </span>
          </span>
          <span className="ps-journey-summary__remaining">
            {leg.phase === "arrived" || (anchor?.progress ?? 0) >= 1
              ? "已到站"
              : `剩余 ${formatDuration(remainingMs(leg.times, nowMs))}`}
            <Icon name="chevron" size={16} />
          </span>
        </button>
      ) : null}
      {snapshot.catching_up ? <p className="ps-journey-catching-up" role="status">TA 的位置继续按时间移动；刚到站的小事还在补记，来信与结算稍后会出现。</p> : null}
      <div className="ps-journey-map" data-testid="journey-map">
        <SchematicMapSurface
          bounds={bounds}
          routes={routes}
          places={places}
          focus={anchor?.point ?? null}
          label={leg?.position_basis === "schematic" ? "线路示意" : "示意地图"}
        >
          <Slot name="journey.map.overlay" props={overlayProps} />
        </SchematicMapSurface>
      </div>
      <p className="ps-journey-map__hint">
        点交通工具看行程，点旁边的音符或电视一起听看。
      </p>
      <nav className="ps-journey-links" aria-label="这趟旅程的记录">
        <Link to="/photos?scene=train"><Icon name="camera" size={17} /><span>列车照片与结果</span></Link>
        <Link to={`/guides?journey=${encodeURIComponent(snapshot.journey_id)}`}><Icon name="bookmark" size={17} /><span>TA 的攻略手账</span></Link>
        <Link to="/communicator?channel=family"><Icon name="mail" size={17} /><span>旅途来信</span></Link>
        <Link to="/collection"><Icon name="gift" size={17} /><span>带回的收藏</span></Link>
      </nav>
      <div className="ps-row" style={{ marginTop: 8 }}>
        <DataOriginBadge
          origin={snapshot.data_origin}
          label="演示行程：不对应真实班次或车辆位置"
        />
      </div>
      <div className="ps-stack" style={{ marginTop: 12 }}>
        <Slot name="journey.cards" props={overlayProps} />
      </div>
      <Slot name="journey.dock" props={overlayProps} />
      {sheetKind && sheetId ? (
        <Slot
          name="journey.sheet"
          props={{
            snapshot,
            nowMs,
            kind: sheetKind,
            targetId: sheetId,
            close: closeSheet,
          }}
        />
      ) : null}
    </>
  );
}

function isNoJourney(error: unknown): boolean {
  const e = toApiError(error);
  return (
    e.status === 404 &&
    (e.details as { reason?: string } | undefined)?.reason === "no_journey"
  );
}

export function JourneyPage() {
  const { transport } = useServices();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const scenario = params.get("scenario") ?? undefined;
  const nowMs = useNow(1000);
  const home = useActiveHome();
  const petId = home.data?.pet.pet_id;
  const atHome = env.dataMode === "live" && home.data?.presence === "at_home";
  const map = useQuery({
    queryKey: queryKeys.journeyMap(petId ?? "-", scenario),
    queryFn: () => transport.journeyMap(petId!, { fixtureScenario: scenario }),
    // A pet who has never left has no map (404 no_journey). Do not issue an
    // expected failed request merely to discover the already-known home state.
    enabled: Boolean(petId) && (env.dataMode === "fixture" || !atHome),
    refetchInterval: (q) =>
      q.state.data?.lifecycle === "active" ? 10_000 : false,
    retry: (count, error) => !isNoJourney(error) && count < 2,
  });
  const scenarios = transport.fixtureScenarios();
  // 宠物在家（从未出发，或上一次旅程已结束）：/journey 显示出发站；出发后同一页换成地图。
  const showStation = atHome || (env.dataMode === "live" && (isNoJourney(map.error) || (map.data !== undefined && map.data.lifecycle !== "active")));
  // 旅程结束的那一刻刷新家园快照（位置、钱包、收藏）。
  const lifecycle = map.data?.lifecycle;
  useEffect(() => {
    if (lifecycle === "completed")
      void queryClient.invalidateQueries({ queryKey: queryKeys.home });
  }, [lifecycle, queryClient]);

  return (
    <Page className="ps-journey-page">
      <TopBar
        title={home.data ? `${home.data.pet.name}的旅途` : "旅途"}
        subtitle={showStation ? "在家，随时可以出发" : undefined}
      />
      {env.dataMode === "fixture" && scenarios.length ? (
        <details className="ps-scenario-disclosure">
          <summary>切换测试场景</summary>
          <div className="ps-scenarios" role="group" aria-label="演示场景">
            {scenarios.map((s) => (
              <ToggleChip
                key={s.id}
                pressed={(scenario ?? "flight") === s.id}
                onToggle={() => {
                  const next = new URLSearchParams();
                  next.set("scenario", s.id);
                  setParams(next);
                }}
              >
                {s.label}
              </ToggleChip>
            ))}
            <Button
              size="sm"
              variant="ghost"
              icon="refresh"
              onClick={() => {
                resetFixtureEpoch();
                void queryClient.invalidateQueries({ queryKey: ["transport"] });
                void queryClient.invalidateQueries({
                  queryKey: ["companion-media"],
                });
              }}
            >
              重置演示时间
            </Button>
          </div>
        </details>
      ) : null}
      {home.isError ? (
        <ErrorState error={home.error} onRetry={() => void home.refetch()} />
      ) : showStation && home.data ? (
        <DepartureStation home={home.data} last={map.data ?? null} />
      ) : map.isError ? (
        <ErrorState error={map.error} onRetry={() => void map.refetch()} />
      ) : map.data ? (
        <JourneyMap snapshot={map.data} nowMs={nowMs} />
      ) : (
        <LoadingState lines={2} label="正在寻找 TA 的位置…" />
      )}
    </Page>
  );
}
