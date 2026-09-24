/**
 * 高德 Logo 与版权按使用条款要一直完整可见（主窗口 2026-09-24：所有面板状态、320 与 390、浅色与深色）。
 * - 版权文字：高德 JS API 2.0 只在地图宽于 350px 时才往 .amap-copyright 里写字（它源码里的判断：
 *   `350 < 宽度 && (版权.innerHTML = "© 年份 AutoNavi ", 再建审图号的 span.amap-mcode)`），窄屏只留 Logo。
 *   ensureCopyright 在窄屏时按高德自己的写法补上同一句，并把审图号的位置挂好（高德之后按底图往里写审图号）；已经有字的不动。
 * - 位置：Logo 和版权抬到“盖住地图的最高那一层”之上——底部一叠（面板 + 三栏），或打开着的底部面板
 *   （这趟旅途、一起听、行程卡：shared/ui 的 Sheet 经 portal 挂在 body、贴着底边弹出）。useAttributionInset 量好写进 --wmap-attrib。
 *   样式（字号、衬底、颜色、位置）在 world-map.css 开头。
 */
import { useEffect, type RefObject } from "react";

/** 高德在宽屏上写的就是这一句（年份取当前年份，和高德一样）。 */
export function copyrightText(year: number): string {
  return `© ${year} AutoNavi `;
}

/** 窄屏上高德没写版权时补上；已经有字（宽屏）的不动。 */
export function ensureCopyright(container: HTMLElement, year = new Date().getFullYear()): void {
  const el = container.querySelector<HTMLElement & { mapNumber?: HTMLElement }>(".amap-copyright");
  if (!el || (el.textContent ?? "").trim()) return;
  el.textContent = copyrightText(year);
  const mapNumber = document.createElement("span");
  mapNumber.className = "amap-mcode";
  el.appendChild(mapNumber);
  // 高德按这个属性找审图号的位置（宽屏时它自己建的也挂在这个属性上）；找不到时它不写，不影响版权本身。
  el.mapNumber = mapNumber;
}

/** 打开着的底部面板：Sheet 经 portal 直接挂在 body 下。 */
const OPEN_SHEETS = "body > .ps-sheet";

/**
 * 写 --wmap-attrib（px）= max(底部一叠的高度, 打开着的底部面板盖住的高度)。
 * 面板贴着底边（position: fixed; bottom: 0），盖住的高度就是它的 offsetHeight——弹出动画的 transform 不影响它。
 * 面板开、关（body 的子节点变化）和面板内容变高变矮（ResizeObserver）都会重算；底部一叠的高度由上层量好传进来。
 */
export function useAttributionInset(rootRef: RefObject<HTMLElement | null>, bottomInset: number): void {
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    let sheets: HTMLElement[] = [];
    const apply = () => {
      const covered = Math.max(bottomInset, ...sheets.map((sheet) => sheet.offsetHeight));
      root.style.setProperty("--wmap-attrib", `${Math.round(covered)}px`);
    };
    const resize = typeof ResizeObserver === "function" ? new ResizeObserver(apply) : null;
    const collect = () => {
      resize?.disconnect();
      sheets = [...document.querySelectorAll<HTMLElement>(OPEN_SHEETS)];
      for (const sheet of sheets) resize?.observe(sheet);
      apply();
    };
    collect();
    const mutations = new MutationObserver(collect);
    mutations.observe(document.body, { childList: true });
    return () => {
      mutations.disconnect();
      resize?.disconnect();
    };
  }, [rootRef, bottomInset]);
}
