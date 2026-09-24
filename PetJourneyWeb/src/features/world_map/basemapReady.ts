/**
 * 底图（图块）真的画出来了没有——撤“地图加载中…”用（./MapLoadingHint）。
 * - 高德 JS API 2.0 的 complete 事件（地图的、底图图层的）在图块到之前就发：实测把图块请求扣住 6 秒，
 *   两种 complete 仍在建图后约 40ms 到（它们说的是“地图资源、图层来源准备好了”，不是“图块画上了”）。拿它撤提示，提示一闪就没，空白网格照旧。
 * - 所以看浏览器的 Resource Timing：建图之后，高德域名下第一块底图图块（路径里带 tile，例如 jsapi.amap.com/web_map/get_tile）
 *   成功回来，再等两帧让它画上，就算底图出来了。样式数据（custyle…/vdata）、图标、脚本都不算。
 *   每建一张地图（重试重建、从别的页面回来）高德都会重新请求图块（实测），所以每次都等得到。
 * - 浏览器不能按资源观察（没有 PerformanceObserver，或不支持 resource）时，退回高德的 complete——至少不会一直挂着提示。
 */

/** 是不是一块成功回来的高德底图图块。status：浏览器给的 HTTP 状态（给不出时为 0 或没有，当作成功）。 */
export function isBasemapTile(name: string, status?: number): boolean {
  let url: URL;
  try {
    url = new URL(name);
  } catch {
    return false;
  }
  if (!/(^|\.)(amap|autonavi)\.com$/i.test(url.hostname)) return false;
  if (!/tile/i.test(url.pathname)) return false;
  return !status || (status >= 200 && status < 300);
}

/** 这个浏览器能不能按资源观察图块。 */
export function canWatchTiles(): boolean {
  return typeof PerformanceObserver === "function" && (PerformanceObserver.supportedEntryTypes ?? []).includes("resource");
}

function nextFrame(callback: () => void): void {
  if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => callback());
  else window.setTimeout(callback, 16);
}

/**
 * 建图之前调用：之后第一块底图图块成功回来、再过两帧时调用 onReady（只调一次）。返回取消函数（地图卸载时调）。
 * 要先于建图开始观察：图块在建图后几百毫秒就开始回来。
 */
export function watchBasemapTiles(onReady: () => void): () => void {
  let settled = false;
  let cancelled = false;
  const observer = new PerformanceObserver((list) => {
    if (settled) return;
    for (const entry of list.getEntries()) {
      if (!isBasemapTile(entry.name, (entry as PerformanceResourceTiming & { responseStatus?: number }).responseStatus)) continue;
      settled = true;
      observer.disconnect();
      nextFrame(() =>
        nextFrame(() => {
          if (!cancelled) onReady();
        }),
      );
      return;
    }
  });
  observer.observe({ type: "resource" });
  return () => {
    cancelled = true;
    observer.disconnect();
  };
}
