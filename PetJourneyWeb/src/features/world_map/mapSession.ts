/**
 * 地图首页“回来接着看”（方案 v2.1 第 13 节第一批验收：进小窝再返回地图要一气呵成，状态不丢）。
 * 进小窝等二级页时地图组件会卸载；回来重新挂载时从这里读回：选中的宠物、是否跟着 TA、镜头中心与缩放、演示时钟。
 * - 存 sessionStorage：只在这个标签页、这次浏览里有效；按账号分开存，换了账号不会带着上一个人的镜头打开。
 * - 选中 / 跟随、镜头各自记下存的时候的“当前宠物”（focusId），只在当前宠物没换时恢复；换了就从头对准新的那只。
 * - 读写都包 try/catch：私密模式、存储被禁用、内容损坏时一律按默认（跟着 TA、演示从头开始），地图本身不受影响。
 * - 镜头坐标是高德的 GCJ-02 [lng, lat]，只回灌给高德镜头，不当作任何宠物的位置。
 */

export interface SavedCamera {
  center: [number, number];
  zoom: number;
}

/** 演示时钟：真实时刻 wallAt（Date.now）时，演示时钟读数是 demoAt；dayStart 是演示“一天”的起点（演示时钟坐标）。 */
export interface SavedDemoClock {
  dayStart: number;
  demoAt: number;
  wallAt: number;
  speed: number;
  paused: boolean;
}

export interface SavedView {
  focusId: string | null;
  selectedId: string | null;
  following: boolean;
}

export interface MapSession {
  view: SavedView | null;
  camera: (SavedCamera & { focusId: string | null }) | null;
  demo: SavedDemoClock | null;
}

const PREFIX = "petsoul:world-map:v1:";

export function mapSessionScope(userId: string | null): string {
  return userId ? `user:${userId}` : "demo";
}

const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const idOrNull = (value: unknown): value is string | null => value === null || typeof value === "string";
const record = (value: unknown): Record<string, unknown> | null => (value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null);

function viewOf(value: unknown): SavedView | null {
  const v = record(value);
  if (!v || !idOrNull(v.focusId) || !idOrNull(v.selectedId) || typeof v.following !== "boolean") return null;
  return { focusId: v.focusId, selectedId: v.selectedId, following: v.following };
}

function cameraOf(value: unknown): MapSession["camera"] {
  const v = record(value);
  if (!v || !idOrNull(v.focusId) || !Array.isArray(v.center) || v.center.length !== 2) return null;
  const [lng, lat] = v.center as unknown[];
  if (!finite(lng) || !finite(lat) || !finite(v.zoom)) return null;
  if (Math.abs(lng) > 180 || Math.abs(lat) > 90 || v.zoom < 2 || v.zoom > 20) return null;
  return { focusId: v.focusId, center: [lng, lat], zoom: v.zoom };
}

function demoOf(value: unknown): SavedDemoClock | null {
  const v = record(value);
  if (!v || !finite(v.dayStart) || !finite(v.demoAt) || !finite(v.wallAt) || !finite(v.speed) || v.speed <= 0 || typeof v.paused !== "boolean") return null;
  return { dayStart: v.dayStart, demoAt: v.demoAt, wallAt: v.wallAt, speed: v.speed, paused: v.paused };
}

/** 逐项校验；哪一项不对，就只有那一项回到默认。 */
function sanitize(value: unknown): MapSession {
  const v = record(value) ?? {};
  return { view: viewOf(v.view), camera: cameraOf(v.camera), demo: demoOf(v.demo) };
}

export function readMapSession(scope: string): MapSession {
  try {
    const raw = window.sessionStorage.getItem(PREFIX + scope);
    return raw ? sanitize(JSON.parse(raw)) : { view: null, camera: null, demo: null };
  } catch {
    return { view: null, camera: null, demo: null };
  }
}

export function writeMapSession(scope: string, patch: Partial<MapSession>): void {
  try {
    window.sessionStorage.setItem(PREFIX + scope, JSON.stringify({ ...readMapSession(scope), ...patch }));
  } catch {
    /* 存不下（私密模式、配额满）：只是下次回来从默认开始。 */
  }
}

/** 这一次挂载要接上的选中、跟随与镜头：只认同一只当前宠物下存的；没有就是默认（不选别的、跟着 TA、镜头从头对准）。 */
export function restoredView(saved: MapSession, focusId: string | null): { selectedId: string | null; following: boolean; camera: SavedCamera | null } {
  const view = saved.view && saved.view.focusId === focusId ? saved.view : null;
  const camera = saved.camera && saved.camera.focusId === focusId ? { center: saved.camera.center, zoom: saved.camera.zoom } : null;
  return { selectedId: view?.selectedId ?? null, following: view?.following ?? true, camera };
}

/** 演示时钟接着走：离开的这段真实时间按倍速补上；暂停着就停在原处。 */
export function resumeDemoClock(saved: SavedDemoClock, wallNow: number): number {
  return saved.paused ? saved.demoAt : saved.demoAt + Math.max(0, wallNow - saved.wallAt) * saved.speed;
}
