/**
 * 地图适配边界（SchematicMapSurface）。
 *
 * 所有地图叠加物（车辆、音符/电视徽标、地点）只通过 useMapProjection().project(latLng) 取得屏幕坐标，
 * 并用 <MapAnchor> 定位，因此缩放/平移时自动跟随正确车辆。
 *
 * live 模式下，范围落在高德服务区（港澳）时向后端要一张真实底图（服务端代理高德静态地图，密钥不在前端），
 * 投影随底图切换，叠加层代码不变；东京等范围、演示模式或底图不可用时保持示意地图，并在图上标明“非真实底图”。
 * Google 底图尚未接入（项目未开通计费）。
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { env } from "@/shared/config/env";
import type { LatLng } from "@/shared/contracts";
import { queryKeys } from "@/shared/query/queryClient";
import { useServices } from "@/shared/services/registry";
import { Icon } from "@/shared/ui";
import { basemapProjection, boundsBox, isUsableBasemap, schematicProjection } from "./projection";
import "./map.css";

export interface MapProjection {
  project: (point: LatLng) => { x: number; y: number };
  scale: number;
  width: number;
  height: number;
  /** 把某个坐标平移到视野中央（例如“定位车辆”）。 */
  centerOn: (point: LatLng) => void;
  basemap: "schematic" | "amap" | "google";
}

const ProjectionContext = createContext<MapProjection | null>(null);

export function useMapProjection(): MapProjection {
  const ctx = useContext(ProjectionContext);
  if (!ctx) throw new Error("useMapProjection 必须在 MapSurface 内使用");
  return ctx;
}

/** 以 lat/lng 定位的 DOM 叠加物；offset 用于把徽标放在车辆上方/旁边。 */
export function MapAnchor({ at, offsetX = 0, offsetY = 0, z = 1, children }: { at: LatLng; offsetX?: number; offsetY?: number; z?: number; children: ReactNode }) {
  const { project } = useMapProjection();
  const { x, y } = project(at);
  return (
    <div className="ps-map__anchor" style={{ transform: `translate(${x + offsetX}px, ${y + offsetY}px)`, zIndex: z }}>
      {children}
    </div>
  );
}

interface View {
  scale: number;
  tx: number;
  ty: number;
}

/** 底图接口能接受的最小宽高（CSS 像素），与服务端 routers/web/journey.py 的 Query(ge=64) 一致。 */
const MIN_BASEMAP_SIZE = 64;

export function SchematicMapSurface({
  bounds,
  routes,
  places,
  children,
  focus,
  label = "示意地图",
  realBasemap = true,
}: {
  bounds: LatLng[];
  routes: Array<{ id: string; points: LatLng[]; dashed?: boolean; active?: boolean }>;
  places: Array<{ id: string; at: LatLng; name: string }>;
  children?: ReactNode;
  /** 首次渲染时居中的坐标（深链接定位车辆） */
  focus?: LatLng | null;
  label?: string;
  /** live 模式下尝试加载真实底图（默认开启）；传 false 则始终用示意地图。 */
  realBasemap?: boolean;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 360, height: 420 });
  const [measured, setMeasured] = useState(false);
  const [view, setView] = useState<View>({ scale: 1, tx: 0, ty: 0 });
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const pinchStart = useRef<{ dist: number; scale: number } | null>(null);
  const focusedOnce = useRef(false);

  useEffect(() => {
    const el = hostRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) {
        setSize({ width, height });
        setMeasured(true);
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // 真实底图：尺寸按 32 像素取整后再请求，容器细微变化不重复请求；服务端再做一次取整与缓存。
  // 服务端要求宽高都不小于 64（GET /map/basemap 的 Query(ge=64)）。容器一时量出更小的尺寸就先不请求，等量到正常尺寸再要：
  // 2026-09-24 实测 390 宽旅途页在整页截图时视口被临时压成 1px 宽，地图量到 32×340，发出宽 32 的请求被 422 拒绝。
  const { platform } = useServices();
  const box = useMemo(() => boundsBox(bounds), [bounds]);
  const reqWidth = Math.round(size.width / 32) * 32;
  const reqHeight = Math.round(size.height / 32) * 32;
  const basemapQuery = useQuery({
    queryKey: queryKeys.basemap(box ? `${box.south},${box.west},${box.north},${box.east}|${reqWidth}x${reqHeight}` : "none"),
    queryFn: () => platform.basemap({ ...box!, width: reqWidth, height: reqHeight }),
    enabled: realBasemap && env.dataMode === "live" && measured && box !== null && reqWidth >= MIN_BASEMAP_SIZE && reqHeight >= MIN_BASEMAP_SIZE,
    staleTime: 30 * 60_000,
    retry: false,
  });
  // 图片加载失败（例如缓存已过期）时先退回示意图并重新询问；服务端重新取图后 expires_at 会变，再显示新图。
  const [failedImage, setFailedImage] = useState<string | null>(null);
  const imageHref = isUsableBasemap(basemapQuery.data) ? `${basemapQuery.data.image_url}?v=${encodeURIComponent(basemapQuery.data.expires_at ?? "")}` : null;
  const basemap = isUsableBasemap(basemapQuery.data) && imageHref !== failedImage ? basemapQuery.data : null;
  const maxScale = basemap ? 4 : 8;

  // 基础投影：有底图时与底图像素对齐，否则把 bounds 适配到容器（Web Mercator），再叠加用户的缩放/平移。
  const { base, fit } = useMemo(
    () => (basemap ? basemapProjection(basemap, size) : { base: schematicProjection(bounds, size), fit: 1 }),
    [basemap, bounds, size],
  );

  const project = useCallback(
    (p: LatLng) => {
      const b = base(p);
      return { x: b.x * view.scale + view.tx, y: b.y * view.scale + view.ty };
    },
    [base, view],
  );

  const centerOn = useCallback(
    (p: LatLng) => {
      const b = base(p);
      setView((v) => ({ ...v, tx: size.width / 2 - b.x * v.scale, ty: size.height / 2 - b.y * v.scale }));
    },
    [base, size],
  );

  // 底图加载完成（或失效退回示意图）后投影会变：重置视野，再按 focus 重新定位。
  const baseKey = basemap?.image_url ?? "schematic";
  useEffect(() => {
    focusedOnce.current = false;
    setView({ scale: 1, tx: 0, ty: 0 });
  }, [baseKey]);

  useEffect(() => {
    if (focus && !focusedOnce.current && size.width > 0) {
      focusedOnce.current = true;
      const b = base(focus);
      setView({ scale: 1.6, tx: size.width / 2 - b.x * 1.6, ty: size.height / 2 - b.y * 1.6 });
    }
  }, [focus, base, size, baseKey]);

  const zoomBy = useCallback(
    (factor: number, cx = size.width / 2, cy = size.height / 2) => {
      setView((v) => {
        const scale = Math.min(maxScale, Math.max(0.6, v.scale * factor));
        const real = scale / v.scale;
        return { scale, tx: cx - (cx - v.tx) * real, ty: cy - (cy - v.ty) * real };
      });
    },
    [size, maxScale],
  );

  useEffect(() => {
    const el = hostRef.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = el.getBoundingClientRect();
      zoomBy(event.deltaY < 0 ? 1.15 : 1 / 1.15, event.clientX - rect.left, event.clientY - rect.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomBy]);

  const onPointerDown = (event: ReactPointerEvent) => {
    // 只有直接按在底图上才开始拖动；按在徽标/车辆按钮上不触发底图手势。
    if ((event.target as HTMLElement).closest("[data-map-interactive]")) return;
    try {
      (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    } catch {
      /* 某些合成事件/旧浏览器不支持捕获：拖动仍可用 */
    }
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()];
      pinchStart.current = { dist: Math.hypot(a.x - b.x, a.y - b.y), scale: view.scale };
    }
  };
  const onPointerMove = (event: ReactPointerEvent) => {
    const prev = pointers.current.get(event.pointerId);
    if (!prev) return;
    const next = { x: event.clientX, y: event.clientY };
    pointers.current.set(event.pointerId, next);
    if (pointers.current.size === 2 && pinchStart.current) {
      const [a, b] = [...pointers.current.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      const rect = hostRef.current!.getBoundingClientRect();
      const target = pinchStart.current.scale * (dist / pinchStart.current.dist);
      zoomBy(target / view.scale, (a.x + b.x) / 2 - rect.left, (a.y + b.y) / 2 - rect.top);
      return;
    }
    setView((v) => ({ ...v, tx: v.tx + next.x - prev.x, ty: v.ty + next.y - prev.y }));
  };
  const onPointerUp = (event: ReactPointerEvent) => {
    pointers.current.delete(event.pointerId);
    if (pointers.current.size < 2) pinchStart.current = null;
  };

  const projection: MapProjection = { project, scale: view.scale, width: size.width, height: size.height, centerOn, basemap: basemap ? "amap" : "schematic" };
  const gridStep = 48 * view.scale;
  const hasSchematicLine = routes.some((route) => route.dashed);
  const imageRect = basemap
    ? (() => {
        const c = project(basemap.center);
        const w = basemap.width * fit * view.scale;
        const h = basemap.height * fit * view.scale;
        return { x: c.x - w / 2, y: c.y - h / 2, w, h };
      })()
    : null;
  const attribution = basemap
    ? `${basemap.attribution ?? "底图：高德地图"}${hasSchematicLine ? " · 虚线为示意线路" : ""}`
    : `${label} · 非真实底图`;
  const labelHalo = basemap ? "var(--c-surface)" : "var(--c-map-water)";

  return (
    <ProjectionContext.Provider value={projection}>
      <div
        ref={hostRef}
        className="ps-map"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        role="application"
        aria-label={`${basemap ? "旅途地图" : label}：可拖动与缩放`}
        data-basemap={basemap ? "amap" : "schematic"}
      >
        <svg className="ps-map__base" width={size.width} height={size.height} aria-hidden="true">
          <defs>
            <pattern id="ps-grid" width={gridStep} height={gridStep} patternUnits="userSpaceOnUse" x={view.tx % gridStep} y={view.ty % gridStep}>
              <path d={`M ${gridStep} 0 L 0 0 0 ${gridStep}`} fill="none" stroke="var(--c-map-grid)" strokeWidth="1" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="var(--c-map-water)" />
          {imageRect && basemap ? (
            <image
              className="ps-map__basemap"
              href={imageHref ?? basemap.image_url}
              x={imageRect.x}
              y={imageRect.y}
              width={imageRect.w}
              height={imageRect.h}
              preserveAspectRatio="none"
              onError={() => {
                setFailedImage(imageHref);
                void basemapQuery.refetch();
              }}
            />
          ) : (
            <rect width="100%" height="100%" fill="url(#ps-grid)" />
          )}
          {routes.map((route) => {
            const d = route.points.map((p, i) => {
              const { x, y } = project(p);
              return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
            });
            return (
              <g key={route.id}>
                <path d={d.join(" ")} fill="none" stroke="var(--c-surface)" strokeWidth={route.active ? 9 : 6} strokeLinecap="round" strokeLinejoin="round" opacity="0.9" />
                <path
                  d={d.join(" ")}
                  fill="none"
                  stroke="var(--c-route)"
                  strokeWidth={route.active ? 4 : 3}
                  strokeDasharray={route.dashed ? "2 8" : undefined}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity={route.active ? 1 : 0.45}
                />
              </g>
            );
          })}
          {places.map((place) => {
            const { x, y } = project(place.at);
            return (
              <g key={place.id} transform={`translate(${x},${y})`}>
                <circle r="7" fill="var(--c-surface)" stroke="var(--c-deep-ink)" strokeWidth="2" />
                <text y="-12" textAnchor="middle" fontSize="12" fontWeight="700" fill="var(--c-ink)" paintOrder="stroke" stroke={labelHalo} strokeWidth="4">
                  {place.name}
                </text>
              </g>
            );
          })}
        </svg>
        <div className="ps-map__overlay">{children}</div>
        <div className="ps-map__controls" data-map-interactive>
          <button type="button" className="ps-map__ctl" aria-label="放大地图" onClick={() => zoomBy(1.3)}>
            <Icon name="plus" size={18} />
          </button>
          <button type="button" className="ps-map__ctl" aria-label="缩小地图" onClick={() => zoomBy(1 / 1.3)}>
            <Icon name="minus" size={18} />
          </button>
          {focus ? (
            <button type="button" className="ps-map__ctl" aria-label="定位到当前交通工具" onClick={() => centerOn(focus)}>
              <Icon name="locate" size={18} />
            </button>
          ) : null}
        </div>
        <div className={`ps-map__attribution${basemap ? " ps-map__attribution--right" : ""}`}>{attribution}</div>
      </div>
    </ProjectionContext.Provider>
  );
}
