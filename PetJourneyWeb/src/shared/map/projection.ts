import type { BasemapView, LatLng } from "@/shared/contracts";

/** 地图基础投影：把 WGS-84 坐标映射到容器像素（尚未叠加用户的缩放/平移）。 */
export type BaseProjection = (point: LatLng) => { x: number; y: number };

export interface Size {
  width: number;
  height: number;
}

export function mercatorY(lat: number): number {
  const rad = (Math.max(-85, Math.min(85, lat)) * Math.PI) / 180;
  return Math.log(Math.tan(Math.PI / 4 + rad / 2));
}

function centered(size: Size, cx: number, cy: number, k: number): BaseProjection {
  return (p) => ({
    x: size.width / 2 + (p.lng - cx) * (Math.PI / 180) * k,
    y: size.height / 2 - (mercatorY(p.lat) - cy) * k,
  });
}

/** 示意地图：把 bounds 适配进容器（Web Mercator，四周留白）。 */
export function schematicProjection(bounds: LatLng[], size: Size, pad = 56): BaseProjection {
  const ys = bounds.map((p) => mercatorY(p.lat));
  const xs = bounds.map((p) => p.lng);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = Math.max(maxX - minX, 0.02) * (Math.PI / 180);
  const spanY = Math.max(maxY - minY, 0.0004);
  const k = Math.min((size.width - pad * 2) / spanX, (size.height - pad * 2) / spanY);
  return centered(size, (minX + maxX) / 2, (minY + maxY) / 2, k);
}

export type AvailableBasemap = BasemapView & { image_url: string; center: LatLng; zoom: number; width: number; height: number };

export function isUsableBasemap(view: BasemapView | undefined): view is AvailableBasemap {
  return Boolean(view?.available && view.image_url && view.center && view.zoom != null && view.width && view.height);
}

/**
 * 真实底图：底图以“完整显示”方式放进容器（不裁掉图上的供应商标志与审图号），
 * 投影比例与底图像素一致，路线和车辆与街道对齐。返回投影和底图的显示倍率。
 */
export function basemapProjection(basemap: AvailableBasemap, size: Size): { base: BaseProjection; fit: number } {
  const fit = Math.min(size.width / basemap.width, size.height / basemap.height);
  const k = ((256 * 2 ** basemap.zoom) / (2 * Math.PI)) * fit;
  return { base: centered(size, basemap.center.lng, mercatorY(basemap.center.lat), k), fit };
}

/** 请求底图用的范围：四舍五入到约 10 米，避免同一路线因浮点误差重复请求。 */
export function boundsBox(bounds: LatLng[]): { south: number; west: number; north: number; east: number } | null {
  const valid = bounds.filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lng) && !(p.lat === 0 && p.lng === 0));
  if (valid.length === 0) return null;
  const round = (v: number) => Math.round(v * 1e4) / 1e4;
  return {
    south: round(Math.min(...valid.map((p) => p.lat))),
    west: round(Math.min(...valid.map((p) => p.lng))),
    north: round(Math.max(...valid.map((p) => p.lat))),
    east: round(Math.max(...valid.map((p) => p.lng))),
  };
}
