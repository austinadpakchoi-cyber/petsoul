/**
 * 底图还没画出来时的一句提示（主窗口 2026-09-24：地图打开后要等 5–10 秒才出底图，之前只有一张空白网格、没有任何提示）。
 * - “地图加载中…”：安静的一小块，放在顶部两侧按钮之间（有演示条时在演示条下面），不挡面板；它的下沿算进镜头的顶部让位
 *   （MapHomePage 量它的高度），TA 的标记落在它下面，不被它压住——窄屏（320×568）上面板很高、标记靠上时也一样。
 *   底图真的画出来（第一块底图图块回来，见 ./basemapReady——高德的 complete 在图块到之前就发，不能用）上层就不再渲染它。
 * - 转圈只在没开“减少动态效果”时出现（world-map.css）。
 * - 超过 15 秒还没出来：换成“地图还没加载出来”，给一个“重试”（上层重建地图；attempt 变了就重新计时）。
 */
import { useEffect, useState, type Ref } from "react";

export const MAP_SLOW_MS = 15_000;

export function MapLoadingHint({ onRetry, top, attempt = 0, ref }: { onRetry: () => void; top?: number; attempt?: number; ref?: Ref<HTMLDivElement> }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    setSlow(false);
    const timer = window.setTimeout(() => setSlow(true), MAP_SLOW_MS);
    return () => window.clearTimeout(timer);
  }, [attempt]);
  return (
    <div className={`ps-wmap-loading${slow ? " is-slow" : ""}`} role="status" style={top ? { top } : undefined} ref={ref}>
      {slow ? (
        <>
          <span>地图还没加载出来</span>
          <button type="button" className="ps-btn ps-btn--leaf ps-btn--sm" onClick={onRetry}>
            重试
          </button>
        </>
      ) : (
        <>
          <span className="ps-wmap-loading__spin" aria-hidden="true" />
          <span>地图加载中…</span>
        </>
      )}
    </div>
  );
}
