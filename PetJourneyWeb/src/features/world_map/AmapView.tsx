/**
 * 高德可交互地图（JS API 2.0）。只负责“画”：家的这一带、走的路（走过的实线 + 没走的虚线）、目的地、宠物。
 * 位置由上层给的世界状态和时钟决定（./model.positionAt），这里不判断到没到、在不在。
 * 标记内容用 React portal 渲染进高德 Marker 的 DOM，交互和动画都在 React 里。
 * 同一个家只画一个小窝标记（和“家在这一带”的圈）；在家的几只围着它错开，出门的不挪（./homeCluster）。
 * 镜头：上层给了上次的镜头（进小窝再回来）就从那里接着看；镜头每次停下、以及地图卸载前，把当前镜头报给上层存起来。
 */
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { loadAmap, type AMapCircle, type AMapMap, type AMapMarker, type AMapNamespace, type AMapPath, type AmapLngLat } from "./amapLoader";
import { ensureCopyright } from "./attribution";
import { canWatchTiles, watchBasemapTiles } from "./basemapReady";
import { toAmapLngLat } from "./coords";
import type { MapConfigState } from "./mapConfig";
import { homeLayout, type MarkerOffset } from "./homeCluster";
import type { SavedCamera } from "./mapSession";
import { alongRoute, legProgress, positionAt, type MapLatLng, type WorldPet } from "./model";

export type MapStatus = "loading" | "ready" | "failed";

interface PetOverlays {
  petEl: HTMLDivElement;
  homeEl: HTMLDivElement;
  placeEl: HTMLDivElement;
  pet: AMapMarker;
  home: AMapMarker;
  place: AMapMarker;
  area: AMapCircle;
  passed: AMapPath;
  remaining: AMapPath;
}

export interface AmapViewProps {
  config: MapConfigState;
  pets: WorldPet[];
  nowMs: number;
  /** 镜头跟着这只宠物；用户拖动地图后由上层关掉。 */
  followPetId: string | null;
  /** 每次递增都把镜头推回跟随的宠物（“定位 TA”）。 */
  recenterToken: number;
  /** 底部面板盖住的高度（px）：镜头把宠物放在“露出来的地图”正中，而不是整屏正中。 */
  bottomInset: number;
  /** 顶部压住地图的高度（px，演示条的下沿；没有演示条时为 0）：宠物放在它与底部面板之间那块地图的正中。 */
  topInset?: number;
  /** 上次离开地图时的镜头（只在挂载时读一次）：有它就从这里接着看，不再从全国视图推到 TA 身上。 */
  initialCamera?: SavedCamera | null;
  onUserMove(): void;
  onStatus(status: MapStatus, reason?: string): void;
  /** 底图第一次画出来：第一块底图图块回来并画上（./basemapReady）。地图对象建好（status = ready）、高德的 complete 都不等于底图出来了。 */
  onBasemapReady?(): void;
  /** 镜头停下（拖动、缩放、跟随平移结束）以及地图卸载前报告当前镜头。 */
  onCameraChange?(camera: SavedCamera): void;
  renderPet(pet: WorldPet): ReactNode;
  /** 每个家只调一次：owner 是这个家在场景里的第一只，residents 是住这个家的全部宠物。 */
  renderHome(owner: WorldPet, residents: WorldPet[]): ReactNode;
  renderPlace(pet: WorldPet): ReactNode;
}

const FOLLOW_ZOOM = 16;
const ROUTE_COLOR = "#e0773a";

function makeEl(className: string): HTMLDivElement {
  const el = document.createElement("div");
  el.className = className;
  return el;
}

function createOverlays(AMap: AMapNamespace, map: AMapMap): PetOverlays {
  const petEl = makeEl("ps-wmap-anchor ps-wmap-anchor--pet");
  const homeEl = makeEl("ps-wmap-anchor ps-wmap-anchor--home");
  const placeEl = makeEl("ps-wmap-anchor ps-wmap-anchor--place");
  const origin: AmapLngLat = [0, 0];
  // 高德 Polyline 不接受空路径（会报 “error Polyline path”）：先给两点占位并隐藏，之后只在有路线时 setPath。
  const placeholder: AmapLngLat[] = [origin, origin];
  const marker = (content: HTMLElement, zIndex: number) => new AMap.Marker({ position: origin, content, anchor: "bottom-center", zIndex, bubble: false, visible: false });
  const overlays: PetOverlays = {
    petEl,
    homeEl,
    placeEl,
    pet: marker(petEl, 130),
    home: marker(homeEl, 110),
    place: marker(placeEl, 120),
    area: new AMap.Circle({ center: origin, radius: 1, strokeColor: "#d99a62", strokeOpacity: 0.35, strokeWeight: 1, fillColor: "#f6c89a", fillOpacity: 0.16, bubble: true, visible: false, zIndex: 20 }),
    passed: new AMap.Polyline({ path: placeholder, strokeColor: ROUTE_COLOR, strokeOpacity: 0.95, strokeWeight: 6, lineJoin: "round", lineCap: "round", isOutline: true, outlineColor: "#ffffff", borderWeight: 2, zIndex: 60, bubble: true, visible: false }),
    remaining: new AMap.Polyline({ path: placeholder, strokeColor: ROUTE_COLOR, strokeOpacity: 0.5, strokeWeight: 4, strokeStyle: "dashed", strokeDasharray: [8, 8], lineJoin: "round", lineCap: "round", zIndex: 55, bubble: true, visible: false }),
  };
  for (const overlay of [overlays.area, overlays.remaining, overlays.passed, overlays.home, overlays.place, overlays.pet]) map.add(overlay);
  return overlays;
}

function place(marker: AMapMarker | AMapCircle, point: MapLatLng | null) {
  if (!point) {
    marker.hide();
    return;
  }
  if ("setPosition" in marker) marker.setPosition(toAmapLngLat(point));
  else marker.setCenter(toAmapLngLat(point));
  marker.show();
}

/** 拉近到街区级别后，“家在这一带”的模糊圈会盖满屏幕：只在缩远时画圈，近处只留小房子。 */
const AREA_MAX_ZOOM = 14.5;

/**
 * drawsHome：这只负责画它家的小窝标记和圈（同一个家只画一次）；offset：在家时围着小窝错开的像素平移（出门的为 null）。
 */
function updateOverlays(o: PetOverlays, pet: WorldPet, nowMs: number, zoom: number, drawsHome: boolean, offset: MarkerOffset | null): MapLatLng | null {
  const position = positionAt(pet, nowMs);
  place(o.pet, position);
  o.petEl.style.transform = offset ? `translate(${offset.x}px, ${offset.y}px)` : "";

  const home = drawsHome ? pet.home : null;
  place(o.home, home?.center ?? null);
  place(o.area, home && zoom <= AREA_MAX_ZOOM ? home.center : null);
  if (home) o.area.setRadius(home.precisionM);

  const showPlace = pet.activity.place && (pet.activity.phase === "going" || pet.activity.phase === "there");
  place(o.place, showPlace ? pet.activity.place : null);

  const leg = pet.leg;
  const moving = pet.activity.phase === "going" || pet.activity.phase === "returning";
  const split = leg && moving ? alongRoute(leg.route, legProgress(leg, nowMs)) : null;
  if (leg && split) {
    o.passed.setPath(split.passed.map(toAmapLngLat));
    o.remaining.setPath([split.point, ...leg.route.slice(split.passed.length - 1)].map(toAmapLngLat));
    o.passed.show();
    o.remaining.show();
  } else {
    o.passed.hide();
    o.remaining.hide();
  }
  return position;
}

export function AmapView(props: AmapViewProps) {
  const { config, pets, nowMs, followPetId, recenterToken, bottomInset, topInset = 0, initialCamera = null, onUserMove, onStatus, onBasemapReady, onCameraChange, renderPet, renderHome, renderPlace } = props;
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<{ AMap: AMapNamespace; map: AMapMap; report(): void } | null>(null);
  const overlaysRef = useRef(new Map<string, PetOverlays>());
  const restoreRef = useRef(initialCamera);
  // 接着上次的镜头看时已经“对好过”：不再做第一次的整段推近，跟随时只平移到 TA 现在的位置。
  const cameraRef = useRef<{ framed: boolean; lastPan: number; token: number }>({ framed: Boolean(initialCamera), lastPan: 0, token: recenterToken });
  const callbacks = useRef({ onUserMove, onStatus, onBasemapReady, onCameraChange });
  callbacks.current = { onUserMove, onStatus, onBasemapReady, onCameraChange };
  const [ready, setReady] = useState(false);
  const [, setOverlayVersion] = useState(0);

  useEffect(() => {
    let disposed = false;
    let stopTiles: (() => void) | null = null;
    callbacks.current.onStatus("loading");
    loadAmap(config)
      .then((AMap) => {
        if (disposed || !containerRef.current) return;
        const dark = typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches;
        const restore = restoreRef.current;
        // 底图画出来没有：看第一块底图图块回来（./basemapReady；高德的 complete 在图块到之前就发，不能用）。要在建图之前开始看。
        const watchTiles = canWatchTiles();
        if (watchTiles) stopTiles = watchBasemapTiles(() => callbacks.current.onBasemapReady?.());
        // 还不知道 TA 在哪时先看全国，不落到任何具体城市（高德默认会按访问者 IP 选城市，容易被误读成 TA 的位置）；知道后再推过去。
        // 从小窝等二级页回来：直接用离开时的中心与缩放。
        const map = new AMap.Map(containerRef.current, {
          zoom: restore?.zoom ?? 4,
          center: restore?.center ?? [104.2, 35.9],
          viewMode: "2D",
          resizeEnable: true,
          mapStyle: (dark ? config.style_dark : null) ?? config.style ?? undefined,
          showIndoorMap: false,
          jogEnable: true,
        });
        const report = () => {
          const center = map.getCenter();
          callbacks.current.onCameraChange?.({ center: [center.lng, center.lat], zoom: map.getZoom() });
        };
        // 高德在窄于 350px 的地图上不写版权文字：按它的写法补上（./attribution）。地图资源到齐（complete）时再补一次（幂等）。
        const container = containerRef.current;
        ensureCopyright(container);
        map.on("complete", () => {
          ensureCopyright(container);
          // 浏览器看不了图块时才退回用 complete 撤“地图加载中…”。
          if (!watchTiles) callbacks.current.onBasemapReady?.();
        });
        map.on("dragstart", () => callbacks.current.onUserMove());
        map.on("touchstart", () => callbacks.current.onUserMove());
        map.on("moveend", report);
        map.on("zoomend", report);
        mapRef.current = { AMap, map, report };
        setReady(true);
        callbacks.current.onStatus("ready");
      })
      .catch((error: Error) => {
        if (!disposed) callbacks.current.onStatus("failed", error.message);
      });
    const overlays = overlaysRef.current;
    return () => {
      disposed = true;
      stopTiles?.();
      overlays.clear();
      const current = mapRef.current;
      if (current) {
        // 卸载前记下最后的镜头（进小窝再回来接着看）。
        current.report();
        current.map.destroy();
      }
      mapRef.current = null;
    };
  }, [config]);

  // 宠物进出场：按 id 建立 / 移除覆盖物（位置在下面每一帧更新）。
  const petIds = pets.map((p) => p.petId).join("|");
  useEffect(() => {
    const current = mapRef.current;
    if (!ready || !current) return;
    const overlays = overlaysRef.current;
    let changed = false;
    for (const pet of pets) {
      if (!overlays.has(pet.petId)) {
        overlays.set(pet.petId, createOverlays(current.AMap, current.map));
        changed = true;
      }
    }
    for (const [id, o] of overlays) {
      if (!pets.some((p) => p.petId === id)) {
        for (const overlay of [o.area, o.remaining, o.passed, o.home, o.place, o.pet]) current.map.remove(overlay);
        overlays.delete(id);
        changed = true;
      }
    }
    if (changed) setOverlayVersion((v) => v + 1);
    // 依赖只用 petIds：它概括了宠物成员的变化；位置变化不需要重建覆盖物。
  }, [ready, petIds]);

  // 同一个家只画一个小窝；在家的围着它错开（每一帧按当前场景重算，宠物进出家门随时生效）。
  const layout = homeLayout(pets);

  // 每个时刻：更新位置与路线，按需移动镜头。
  useEffect(() => {
    const current = mapRef.current;
    if (!ready || !current) return;
    let followPoint: MapLatLng | null = null;
    const zoom = current.map.getZoom();
    for (const pet of pets) {
      const o = overlaysRef.current.get(pet.petId);
      if (!o) continue;
      const point = updateOverlays(o, pet, nowMs, zoom, layout.residents.has(pet.petId), layout.offsets.get(pet.petId) ?? null);
      if (pet.petId === followPetId) followPoint = point ?? pet.home?.center ?? null;
    }
    const camera = cameraRef.current;
    if (!followPoint) return;
    const [lng, lat] = toAmapLngLat(followPoint);
    // 地图中心放在宠物下方 (bottomInset - topInset)/2 像素处，宠物就落在露出来那块地图（演示条下沿到底部面板上沿）的正中。
    // 比例尺按目标缩放级别算：每放大一级，每像素米数减半。
    const centerBelow = (zoomAt: number): AmapLngLat => {
      const metersPerPx = current.map.getResolution() * 2 ** (current.map.getZoom() - zoomAt);
      const shift = (((bottomInset - topInset) / 2) * metersPerPx) / 111_320;
      return [lng, lat - (Number.isFinite(shift) ? shift : 0)];
    };
    if (!camera.framed || camera.token !== recenterToken) {
      current.map.setZoomAndCenter(FOLLOW_ZOOM, centerBelow(FOLLOW_ZOOM), !camera.framed, 400);
      camera.framed = true;
      camera.token = recenterToken;
      camera.lastPan = performance.now();
      return;
    }
    if (performance.now() - camera.lastPan > 1500) {
      current.map.panTo(centerBelow(current.map.getZoom()), 900);
      camera.lastPan = performance.now();
    }
  });

  return (
    <div className="ps-wmap-canvas" ref={containerRef}>
      {ready
        ? pets.map((pet) => {
            const o = overlaysRef.current.get(pet.petId);
            if (!o) return null;
            const residents = layout.residents.get(pet.petId);
            return (
              <Fragment key={pet.petId}>
                {createPortal(renderPet(pet), o.petEl)}
                {createPortal(residents ? renderHome(pet, residents) : null, o.homeEl)}
                {createPortal(renderPlace(pet), o.placeEl)}
              </Fragment>
            );
          })
        : null}
    </div>
  );
}
