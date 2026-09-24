/**
 * 地图运行时配置：JS Key 与安全代理地址只在运行时向后端要（`GET /map/config`，契约 `MapConfig`，W0），不进 bundle、不进仓库。
 * 安全密钥永远不下发，由站点根的 `/_AMapService` 代理补上。
 *
 * 前端视角的状态 = 后端给的 `MapConfig`，或者前端自己取不到（接口不在、网络断、格式不对）——后者不属于契约，原因只在这里。
 * 取不到就 available=false，地图组件退回示意底图——不用假数据顶替。
 * 接口进 ServiceMap（platform.mapConfig）之前，这里是本模块唯一的直连请求。
 */
import type { MapConfig } from "@/shared/contracts";
import { env } from "@/shared/config/env";

export interface MapConfigUnavailable {
  provider: "amap";
  available: false;
  js_key: null;
  service_host: null;
  style: null;
  style_dark: null;
  overseas_tiles: false;
  /** 后端的 not_configured，或前端取不到时的原因（http_404、unreachable、malformed、incomplete）。 */
  unavailable_reason: string;
}

export type MapConfigState = MapConfig | MapConfigUnavailable;

export const MAP_UNAVAILABLE: MapConfigUnavailable = {
  provider: "amap",
  available: false,
  js_key: null,
  service_host: null,
  style: null,
  style_dark: null,
  overseas_tiles: false,
  unavailable_reason: "not_configured",
};

function unavailable(reason: string): MapConfigUnavailable {
  return { ...MAP_UNAVAILABLE, unavailable_reason: reason };
}

function isMapConfig(value: unknown): value is MapConfig {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return v.provider === "amap" && typeof v.available === "boolean";
}

export async function fetchMapConfig(signal?: AbortSignal): Promise<MapConfigState> {
  try {
    const res = await fetch(`${env.apiBase}/map/config`, { credentials: "same-origin", headers: { Accept: "application/json" }, signal });
    if (!res.ok) return unavailable(`http_${res.status}`);
    const body: unknown = await res.json();
    if (!isMapConfig(body)) return unavailable("malformed");
    if (!body.available) return unavailable(body.unavailable_reason ?? "not_configured");
    if (!body.js_key || !body.service_host) return unavailable("incomplete");
    return body;
  } catch (error) {
    if ((error as { name?: string }).name === "AbortError") throw error;
    return unavailable("unreachable");
  }
}
