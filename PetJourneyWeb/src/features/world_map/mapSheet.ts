/**
 * 地图上的底部面板写在地址里：?sheet=trip（这趟旅途）、?sheet=leg:<段 id>（行程卡）、?sheet=media:<会话 id>（一起听 / 一起看）。
 * - 打开用 push，并在历史记录里做个记号：浏览器返回键就能关掉；面板里的“收起”也退回上一条（和返回键一样）。
 * - 直接打开带 ?sheet= 的链接、或刷新后：面板照样在；这时没有站内的上一条，“收起”改成 replace 去掉参数，不把人退出站外。
 * - 和 ?focus= 可以同时出现：地图处理 focus 时只删 focus，sheet 保留（见 MapHomePage）。
 */
import { useLocation, useNavigate, useSearchParams } from "react-router";

export const SHEET_PARAM = "sheet";
/** 从地图里打开面板时写进历史记录的记号。 */
export const SHEET_FROM_MAP = { sheetFrom: "map" } as const;

export type MapSheet = { kind: "trip" } | { kind: "leg" | "media"; id: string };

export function parseSheet(value: string | null): MapSheet | null {
  if (!value) return null;
  if (value === "trip") return { kind: "trip" };
  const at = value.indexOf(":");
  if (at < 0) return null;
  const kind = value.slice(0, at);
  const id = value.slice(at + 1);
  return (kind === "leg" || kind === "media") && id ? { kind, id } : null;
}

/** 面板提醒等链接用的地址（只带 sheet，在当前页打开）。 */
export function sheetHref(value: string): string {
  return `?${new URLSearchParams({ [SHEET_PARAM]: value }).toString()}`;
}

export function openedOnMap(state: unknown): boolean {
  return typeof state === "object" && state !== null && (state as { sheetFrom?: unknown }).sheetFrom === "map";
}

export function useMapSheet() {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const sheet = parseSheet(params.get(SHEET_PARAM));
  const open = (value: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set(SHEET_PARAM, value);
        return next;
      },
      { state: SHEET_FROM_MAP },
    );
  const close = () => {
    if (openedOnMap(location.state)) {
      navigate(-1);
      return;
    }
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete(SHEET_PARAM);
        return next;
      },
      { replace: true },
    );
  };
  return { sheet, open, close };
}
