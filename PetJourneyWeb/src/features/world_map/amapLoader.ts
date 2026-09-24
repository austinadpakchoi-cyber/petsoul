/**
 * 按需加载高德 JS API 2.0（不引入 npm 依赖）。
 * 先写 window._AMapSecurityConfig.serviceHost（同源代理，安全密钥只在服务端），再插入脚本；同一页只加载一次。
 */
import type { MapConfigState } from "./mapConfig";

/* 高德 JS API 没有随包类型；这里只声明本模块用到的最小形状。坐标一律是 GCJ-02 的 [lng, lat]。 */
export type AmapLngLat = [number, number];

export interface AMapMap {
  add(overlay: unknown): void;
  remove(overlay: unknown): void;
  destroy(): void;
  on(event: string, handler: (...args: unknown[]) => void): void;
  setZoomAndCenter(zoom: number, center: AmapLngLat, immediately?: boolean, duration?: number): void;
  panTo(center: AmapLngLat, duration?: number): void;
  getZoom(): number;
  /** 当前镜头中心（GCJ-02）。 */
  getCenter(): { lng: number; lat: number };
  /** 当前中心处每像素多少米。 */
  getResolution(): number;
  setFitView(overlays?: unknown[] | null, immediately?: boolean, avoid?: [number, number, number, number], maxZoom?: number): void;
  setMapStyle(style: string): void;
}

interface AMapShowable {
  show(): void;
  hide(): void;
}

export interface AMapMarker extends AMapShowable {
  setPosition(position: AmapLngLat): void;
  setzIndex(z: number): void;
}

export interface AMapPath extends AMapShowable {
  setPath(path: AmapLngLat[]): void;
}

export interface AMapCircle extends AMapShowable {
  setCenter(center: AmapLngLat): void;
  setRadius(radius: number): void;
}

export interface AMapNamespace {
  Map: new (container: HTMLElement, options: Record<string, unknown>) => AMapMap;
  Marker: new (options: Record<string, unknown>) => AMapMarker;
  Polyline: new (options: Record<string, unknown>) => AMapPath;
  Circle: new (options: Record<string, unknown>) => AMapCircle;
  Pixel: new (x: number, y: number) => unknown;
}

declare global {
  interface Window {
    AMap?: AMapNamespace;
    _AMapSecurityConfig?: { serviceHost?: string; securityJsCode?: string };
  }
}

const SCRIPT_ID = "ps-amap-jsapi";
const LOAD_TIMEOUT_MS = 15_000;
let loading: Promise<AMapNamespace> | null = null;

export function loadAmap(config: MapConfigState): Promise<AMapNamespace> {
  if (!config.available || !config.js_key || !config.service_host) return Promise.reject(new Error("map_unavailable"));
  if (window.AMap) return Promise.resolve(window.AMap);
  if (loading) return loading;
  const serviceHost = new URL(config.service_host, window.location.origin).toString().replace(/\/$/, "");
  window._AMapSecurityConfig = { serviceHost };
  loading = new Promise<AMapNamespace>((resolve, reject) => {
    const script = document.createElement("script");
    script.id = SCRIPT_ID;
    script.async = true;
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(config.js_key!)}&plugin=AMap.MoveAnimation`;
    const timer = window.setTimeout(() => fail(new Error("map_load_timeout")), LOAD_TIMEOUT_MS);
    function fail(error: Error) {
      window.clearTimeout(timer);
      script.remove();
      loading = null;
      reject(error);
    }
    script.onload = () => {
      window.clearTimeout(timer);
      if (window.AMap) resolve(window.AMap);
      else fail(new Error("map_load_empty"));
    };
    script.onerror = () => fail(new Error("map_load_failed"));
    document.head.appendChild(script);
  });
  return loading;
}
