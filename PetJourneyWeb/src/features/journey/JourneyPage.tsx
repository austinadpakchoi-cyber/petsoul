import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";
import type { HomeSnapshot, JourneyLeg, JourneyMapSnapshot, LatLng, TravelActivityKind } from "@/shared/contracts";
import { toApiError } from "@/shared/api/errors";
import { env } from "@/shared/config/env";
import {
  currentLeg,
  effectiveArrival,
  effectiveDeparture,
  legRoute,
  legTitle,
  MODE_LABEL,
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
  PetAvatar,
  TopBar,
  ToggleChip,
} from "@/shared/ui";
import { resetFixtureEpoch } from "@/fixtures/world";
import { JourneyAtHome } from "./DepartureStation";
import "./journey.css";

const ACTIVITY_TEXT: Record<TravelActivityKind, string> = {
  listening: "在听歌",
  watching: "在看片",
  resting: "在歇一会儿",
  window_gazing: "在看窗外",
  dining: "在吃点东西",
  writing_postcard: "在写明信片",
};

const MOVING: ReadonlyArray<JourneyLeg["phase"]> = ["connecting", "boarding", "in_transit", "arriving"];

function clean(name: string): string {
  return name.replace("（示意）", "");
}

function clock(iso: number, timeZone: string): string {
  try {
    return new Date(iso).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", timeZone });
  } catch {
    return new Date(iso).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  }
}

/** 旅途状态：只从服务端给的行程事实推导，不替 TA 编理由。 */
export function tripState(snapshot: JourneyMapSnapshot, nowMs: number) {
  const leg = currentLeg(snapshot);
  const first = snapshot.legs[0];
  const day = first ? Math.max(1, Math.floor((nowMs - effectiveDeparture(first.times)) / 86_400_000) + 1) : 1;
  const visiting = Boolean(snapshot.current_visit_id);
  const moving = Boolean(leg && MOVING.includes(leg.phase) && remainingMs(leg.times, nowMs) > 0);
  const index = leg ? snapshot.legs.findIndex((item) => item.leg_id === leg.leg_id) : -1;
  const next = leg && (moving || leg.phase === "scheduled" || leg.phase === "waiting") ? leg : snapshot.legs[index + 1];
  const place = visiting ? snapshot.destination_title ?? (leg ? clean(leg.destination.name) : null) : leg ? clean(moving ? leg.destination.name : leg.phase === "arrived" ? leg.destination.name : leg.origin.name) : null;
  const state = visiting ? "在店里" : moving ? "在路上" : leg?.phase === "waiting" || leg?.phase === "scheduled" ? "等出发" : "停留";
  return { leg, day, visiting, moving, next, place, state };
}

function TripStatusChip({ home, snapshot, nowMs }: { home: HomeSnapshot | undefined; snapshot: JourneyMapSnapshot; nowMs: number }) {
  const { day, place, state } = tripState(snapshot, nowMs);
  const pet = home?.pet;
  return (
    <div className="ps-trip-chip" data-testid="trip-chip">
      {pet ? <PetAvatar petId={pet.pet_id} name={pet.name} species={pet.species} photoUrl={pet.photo_url} size={40} /> : null}
      <div>
        <strong>{pet?.name ?? "TA"} · 第 {day} 天</strong>
        <span>{place ? `${place} · ${state}` : state}</span>
        {home?.journey?.headline ? <small>{home.journey.headline}</small> : null}
      </div>
    </div>
  );
}

function TripStatusCard({ home, snapshot, nowMs }: { home: HomeSnapshot | undefined; snapshot: JourneyMapSnapshot; nowMs: number }) {
  const [open, setOpen] = useState(false);
  const { leg, moving, next, visiting, state } = tripState(snapshot, nowMs);
  const activity = snapshot.activities.find((item) => item.state === "active");
  const headline = home?.journey?.headline ?? (snapshot.destination_title ? `这趟去 ${snapshot.destination_title}` : "TA 在旅途中");
  const meta = [
    leg ? (leg.world_service ? legTitle(leg) : MODE_LABEL[leg.mode]) : null,
    next ? `下一站 ${clean(next.destination.name)}` : null,
    moving && leg ? `还要 ${formatDuration(remainingMs(leg.times, nowMs))}` : null,
  ].filter(Boolean);
  return (
    <section className={`ps-trip-card${open ? " is-open" : ""}`} aria-label="TA 此刻的旅途">
      <button type="button" className="ps-trip-card__head" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <span className="ps-trip-card__icon" aria-hidden="true"><Icon name={visiting ? "cup" : moving ? (leg?.mode === "walk" ? "compass" : "journey") : "pin"} size={20} /></span>
        <span className="ps-trip-card__text">
          <span className="ps-trip-card__eyebrow"><i aria-hidden="true" />TA {state}{activity && !headline.includes(ACTIVITY_TEXT[activity.kind].slice(1)) ? ` · ${ACTIVITY_TEXT[activity.kind]}` : ""}</span>
          <strong>{headline}</strong>
          {meta.length ? <small>{meta.join(" · ")}</small> : null}
        </span>
        <Icon name="chevron" size={18} className="ps-trip-card__chevron" />
      </button>
      {open ? (
        <div className="ps-trip-card__body">
          <h3>这一趟的路线</h3>
          <ol className="ps-trip-legs">
            {snapshot.legs.map((item) => {
              const done = item.phase === "arrived" || effectiveArrival(item.times) <= nowMs;
              const current = item.leg_id === leg?.leg_id && !done;
              return (
                <li key={item.leg_id} className={done ? "is-done" : current ? "is-current" : ""}>
                  <span className="ps-trip-legs__time">{clock(effectiveDeparture(item.times), item.times.origin_timezone)}</span>
                  <span className="ps-trip-legs__what">
                    <strong>{clean(item.origin.name)} → {clean(item.destination.name)}</strong>
                    <small>{item.world_service ? legTitle(item) : MODE_LABEL[item.mode]} · {done ? "走过了" : current ? "正在走" : "接下来"}</small>
                  </span>
                </li>
              );
            })}
          </ol>
          <nav className="ps-journey-links" aria-label="这趟旅程的记录">
            <Link to={`/guides?journey=${encodeURIComponent(snapshot.journey_id)}`}><Icon name="bookmark" size={17} /><span>TA 的旅行手账</span></Link>
            <Link to="/communicator?channel=family"><Icon name="mail" size={17} /><span>旅途来信</span></Link>
            <Link to="/collection"><Icon name="gift" size={17} /><span>带回的收藏</span></Link>
            <Link to="/photos?scene=train"><Icon name="camera" size={17} /><span>列车照片与结果</span></Link>
          </nav>
          <p className="ps-trip-card__foot">点地图上的交通工具看行程卡，旁边的音符或电视可以一起听看。</p>
        </div>
      ) : null}
    </section>
  );
}

function JourneyMap({
  snapshot,
  nowMs,
  home,
}: {
  snapshot: JourneyMapSnapshot;
  nowMs: number;
  home: HomeSnapshot | undefined;
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
          name: clean(l.origin.name),
        },
        {
          id: `${l.leg_id}-d`,
          at: { lat: l.destination.lat ?? 0, lng: l.destination.lng ?? 0 },
          name: clean(l.destination.name),
        },
      ]),
    [snapshot.legs],
  );
  const overlayProps: JourneyOverlayProps = { snapshot, nowMs, openSheet };

  return (
    <>
      <div className="ps-trip-stage">
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
          <TripStatusChip home={home} snapshot={snapshot} nowMs={nowMs} />
        </div>
        {snapshot.catching_up ? <p className="ps-journey-catching-up" role="status">TA 的位置继续按时间移动；刚到站的小事还在补记，来信与结算稍后会出现。</p> : null}
        <TripStatusCard home={home} snapshot={snapshot} nowMs={nowMs} />
      </div>
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
  // 宠物在家（从未出发，或上一次旅程已结束）：/journey 显示“TA 在家”；TA 自己出发后同一页换成地图。
  const showHome = atHome || (env.dataMode === "live" && (isNoJourney(map.error) || (map.data !== undefined && map.data.lifecycle !== "active")));
  // 旅程结束的那一刻刷新家园快照（位置、钱包、收藏）。
  const lifecycle = map.data?.lifecycle;
  useEffect(() => {
    if (lifecycle === "completed")
      void queryClient.invalidateQueries({ queryKey: queryKeys.home });
  }, [lifecycle, queryClient]);

  return (
    <Page className={`ps-journey-page${showHome ? "" : " is-traveling"}`}>
      {showHome ? (
        <TopBar title={home.data ? `${home.data.pet.name}的旅途` : "旅途"} subtitle="出不出门由 TA 决定" back="/map" />
      ) : (
        <>
          {/* 旅途中这页同样是不显示底栏的二级页（方案 2.2）：左上角也要能回地图首页，否则是死胡同。
              顶栏里的同名标题只给眼睛看，读屏仍读下面这个 h1，不重复朗读。 */}
          <TopBar title={<span aria-hidden="true">{home.data ? `${home.data.pet.name}的旅途` : "旅途"}</span>} back="/map" />
          <h1 className="visually-hidden">{home.data ? `${home.data.pet.name}的旅途` : "旅途"}</h1>
        </>
      )}
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
      ) : showHome && home.data ? (
        <JourneyAtHome home={home.data} last={map.data ?? null} />
      ) : map.isError ? (
        <ErrorState error={map.error} onRetry={() => void map.refetch()} />
      ) : map.data ? (
        <JourneyMap snapshot={map.data} nowMs={nowMs} home={home.data} />
      ) : (
        <LoadingState lines={2} label="正在寻找 TA 的位置…" />
      )}
    </Page>
  );
}
