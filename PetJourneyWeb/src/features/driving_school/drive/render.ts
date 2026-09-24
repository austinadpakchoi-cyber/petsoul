/**
 * 训练场绘制（只负责画，不做任何判定）：场地配置里的装饰、计分线、锥桶、目标区、路线上的信号灯与过街居民、小车与车里的 TA。
 * 颜色全部取自主题变量（读 CSS 变量），日间 / 夜间自动跟随；世界坐标单位是米，y 轴向上。
 */
import { SCHOOL_ART } from "../assets";
import { lightPhase, walkerAt } from "../sim/replay";
import type { Course, Decor, Poly, RouteState, Vec } from "../sim/types";
import type { Pose } from "./engine";

export interface Palette {
  grass: string;
  road: string;
  sidewalk: string;
  paint: string;
  center: string;
  curb: string;
  zone: string;
  zoneStroke: string;
  tree: string;
  paper: string;
  paperShade: string;
  paperInk: string;
  cone: string;
  coneKnocked: string;
  car: string;
  carInk: string;
  glass: string;
  pet: string;
  leaf: string;
  danger: string;
  sun: string;
  sky: string;
  ink: string;
  font: string;
}

const TOKENS: Record<Exclude<keyof Palette, "font">, [string, string]> = {
  grass: ["--c-leaf-soft", "#d9ecdf"],
  road: ["--c-deep-ink", "#203129"],
  sidewalk: ["--c-bg-soft", "#efe7d8"],
  paint: ["--c-on-deep", "#fbf7ef"],
  center: ["--c-sun", "#e9a53a"],
  curb: ["--c-ink-3", "#a1968a"],
  zone: ["--c-sun-soft", "#fbead0"],
  zoneStroke: ["--c-sun", "#e9a53a"],
  tree: ["--c-leaf", "#2f7d5e"],
  paper: ["--paper", "#f4ead5"],
  paperShade: ["--paper-shade", "#e6d6b6"],
  paperInk: ["--paper-ink", "#3b2f22"],
  cone: ["--c-coral", "#df6f55"],
  coneKnocked: ["--c-ink-3", "#a1968a"],
  car: ["--c-sky", "#6aa9dc"],
  carInk: ["--c-deep-ink", "#203129"],
  glass: ["--c-sky-soft", "#d9ebf8"],
  pet: ["--c-sun", "#e9a53a"],
  leaf: ["--c-leaf", "#2f7d5e"],
  danger: ["--c-danger", "#c24b3a"],
  sun: ["--c-sun", "#e9a53a"],
  sky: ["--c-sky", "#6aa9dc"],
  ink: ["--c-ink", "#2b2620"],
};

export function readPalette(el: Element): Palette {
  const style = getComputedStyle(el);
  const out = {} as Palette;
  for (const [key, [token, fallback]] of Object.entries(TOKENS)) {
    const value = style.getPropertyValue(token).trim();
    (out as unknown as Record<string, string>)[key] = value || fallback;
  }
  out.font = style.getPropertyValue("--font-sans").trim() || "sans-serif";
  return out;
}

export interface Camera {
  cx: number;
  cy: number;
  scale: number;
}

export function fitCamera(view: Poly, width: number, height: number, pad = 8): Camera {
  let loX = Infinity;
  let hiX = -Infinity;
  let loY = Infinity;
  let hiY = -Infinity;
  for (const [x, y] of view) {
    loX = Math.min(loX, x);
    hiX = Math.max(hiX, x);
    loY = Math.min(loY, y);
    hiY = Math.max(hiY, y);
  }
  const scale = Math.min((width - pad * 2) / (hiX - loX), (height - pad * 2) / (hiY - loY));
  return { cx: (loX + hiX) / 2, cy: (loY + hiY) / 2, scale };
}

/** 路线跟车：车在画面中偏后的位置，前方多看一点（约 40 米视野，车头前方留出 10 米）。 */
export function followCamera(p: Pose, width: number, height: number): Camera {
  const scale = Math.min(width, height) / 40;
  return { cx: p.x + p.hx * 10, cy: p.y + p.hy * 10, scale };
}

export interface Frame {
  course: Course;
  pose: Pose;
  /** 当前转向档位（车轮角度） */
  steer: number;
  gear: number;
  brake: boolean;
  blink: number;
  tick: number;
  knocked: string[];
  route: RouteState | null;
  /** 正在压着的线（高亮） */
  pressedLine: string | null;
  practice: boolean;
  predicted: Pose[] | null;
  /** 闪烁相位（转向灯）；减少动效时固定常亮 */
  blinkOn: boolean;
  /** 刚发生的扣分 / 红线标记（世界坐标）：画成贴在车或锥桶上方的小牌子，静音也看得见扣在哪里 */
  marks?: FrameMark[];
  /** 左上角状态徽标（D 前进 / 公里/时 / 限速）占住的框（画布像素，从左上角起）：建筑名、场地名落进来就挪到它下面，不被压住 */
  avoid?: { w: number; h: number } | null;
}

export interface FrameMark {
  x: number;
  y: number;
  text: string;
  tone: "bad" | "good";
}

/**
 * 素材（UI-ASSET-009，r7k 交付；网址一律取自 ../assets 的 SCHOOL_ART.field，这里不另写路径）。
 * - 到了就用图片画车身、地面和装饰；没到、加载失败或图片宽为 0 时，那一样退回原来的代码画法，画面照常。
 * - 场地线、车位线、停止线、判定线、目标区、信号灯、预测轨迹、扣分标记永远由代码画：素材只做外观，不参与、也不遮挡判定。
 * - 小车图：俯视、车头朝右（+x），宽高比 3.8:1.7＝模拟车身，按车身矩形旋转画；刹车灯、倒车灯、转向灯、压线描边由代码画在图上；
 *   车里的 TA 画进车顶圆窗（实测圆心在车尾起 37% 处、半径约车宽 21%）；2 倍屏以上用大图。
 * - 地面：草地、柏油 256×256 无缝纹理，平铺成 pattern，每帧按镜头设 setTransform，纹理钉在世界坐标上，镜头移动时不“游”。
 * - 装饰按 decor.type 取（可有几种变体，按出现顺序轮流用，如树 A/B）；可按“type:style”“type:kind”细分，细分的优先。
 *   锥桶图按判定圆的尺寸画（与原来代码画法同一个最小可见尺寸），终点旗插在装着目标区中心的那块区域上，都只管外观。
 * - 龟教练：直接用 SCHOOL_ART.coach.portrait（不在 field 里另加键），画成带纸色圈的圆头像。
 * - 科三建筑（UI-ASSET-010，交付前网址为空）：屋顶纹理平铺、钉在世界坐标上、裁进建筑多边形；有名字的建筑中心放标志，名字挪到标志下面。
 */
export interface DriveSprites {
  car: CanvasImageSource | null;
  grass: CanvasImageSource | null;
  asphalt: CanvasImageSource | null;
  /** 每种装饰的变体（按加载顺序，缺的位置为空） */
  decor: Partial<Record<string, (CanvasImageSource | undefined)[]>>;
  /** 科三建筑的屋顶纹理、标志（按建筑样式；UI-ASSET-010） */
  roof?: Partial<Record<string, CanvasImageSource>>;
  emblem?: Partial<Record<string, CanvasImageSource>>;
  /** 每加载好一张就加 1：画面据此知道要重画 */
  version: number;
}

/** 科三建筑的样式（后端 courses.py 的 style）。 */
export type BuildingStyle = "house" | "barn" | "farm" | "post" | "school" | "canteen";

export interface DriveBuildingUrls {
  /** 屋顶纹理（256×256 无缝）：平铺、钉在世界坐标上、裁进建筑多边形 */
  roof?: Partial<Record<BuildingStyle, string>>;
  /** 建筑标志（透明底）：只画在有名字的建筑中心 */
  emblem?: Partial<Record<BuildingStyle, string>>;
}

export interface DriveSpriteUrls {
  car?: string;
  /** 2 倍屏以上用的小车大图 */
  carLarge?: string;
  grass?: string;
  asphalt?: string;
  decor?: Record<string, string[]>;
  buildings?: DriveBuildingUrls;
}

const FIELD = SCHOOL_ART.field;

/**
 * 科三建筑素材网址（UI-ASSET-010）。素材交付前为空：建筑照旧是代码画的纸色房子，一笔不差；
 * 交付后主窗口把网址填进 ../assets，这里改成从 SCHOOL_ART 取（6 种屋顶、4 个标志）。
 */
export const DRIVE_BUILDING_URLS: DriveBuildingUrls = {};

/** 驾驶画面的素材网址（DriveRunner、ReplayViewer 共用这一处）。 */
export const DRIVE_SPRITE_URLS: DriveSpriteUrls = {
  car: FIELD.car,
  carLarge: FIELD.carLarge,
  grass: FIELD.grass,
  asphalt: FIELD.asphalt,
  decor: { tree: [FIELD.treeA, FIELD.treeB], bush: [FIELD.bush], cone: [FIELD.cone], flag: [FIELD.flag], coach: [SCHOOL_ART.coach.portrait] },
  buildings: DRIVE_BUILDING_URLS,
};

/**
 * 加载素材：立即返回一个空的 DriveSprites，图片加载好一张填一张（version 加 1）；失败的不填，画面继续用代码画法。
 * dpr ≥ 2 且有大图时车用大图（只加载一张）。
 */
export function loadDriveSprites(
  urls: DriveSpriteUrls,
  make: () => HTMLImageElement = () => new Image(),
  dpr = typeof window === "undefined" ? 1 : window.devicePixelRatio || 1,
  /** 每加载好一张调一次（不是每帧重画的画面，比如回放，用它来重画） */
  onLoad?: () => void,
): DriveSprites {
  const sprites: DriveSprites = { car: null, grass: null, asphalt: null, decor: {}, roof: {}, emblem: {}, version: 0 };
  const load = (src: string, put: (img: CanvasImageSource) => void) => {
    const img = make();
    img.decoding = "async";
    img.onload = () => {
      if (img.naturalWidth > 0) {
        put(img);
        sprites.version += 1;
        onLoad?.();
      }
    };
    img.onerror = () => undefined;
    img.src = src;
  };
  const carSrc = dpr >= 2 && urls.carLarge ? urls.carLarge : urls.car;
  if (carSrc) load(carSrc, (img) => (sprites.car = img));
  if (urls.grass) load(urls.grass, (img) => (sprites.grass = img));
  if (urls.asphalt) load(urls.asphalt, (img) => (sprites.asphalt = img));
  for (const [key, list] of Object.entries(urls.decor ?? {})) {
    const slots: (CanvasImageSource | undefined)[] = [];
    sprites.decor[key] = slots;
    list.forEach((src, i) => load(src, (img) => (slots[i] = img)));
  }
  for (const kind of ["roof", "emblem"] as const) {
    const table = sprites[kind]!;
    for (const [style, src] of Object.entries(urls.buildings?.[kind] ?? {})) if (src) load(src, (img) => (table[style] = img));
  }
  return sprites;
}

/** 地面纹理一块代表多少米（纹理 256×256 像素）。 */
export const TILE_METERS = { grass: 6, asphalt: 4 } as const;

/**
 * 素材的明暗处理（在离屏画布上预先压一层颜色，只盖图片不透明的部分；缓存起来，不用 ctx.filter——iOS Safari 画布不支持）：
 * - 浅色：柏油纹理平均亮度 0.150（中灰），黄色中心线、灰色路沿压在上面不到 3:1，所以叠 60% 的路面深墨；
 * - 深色：素材都是白天的，草地叠 70% 深色草地色、柏油叠 75% 深墨、装饰叠 45% 深墨、车叠 20%，不在深色页面里亮成一块白天。
 * 调色板的键 → 叠色取哪个颜色；alpha 为不透明度。改这里要同步用例里的对比度实算。
 */
export const SHADE = {
  light: { grass: null, asphalt: { color: "road", alpha: 0.6 }, decor: null, car: null },
  dark: { grass: { color: "grass", alpha: 0.7 }, asphalt: { color: "road", alpha: 0.75 }, decor: { color: "road", alpha: 0.45 }, car: { color: "road", alpha: 0.2 } },
} as const satisfies Record<"light" | "dark", Record<"grass" | "asphalt" | "decor" | "car", { color: keyof Palette; alpha: number } | null>>;

const shadeCache = new WeakMap<object, Map<string, CanvasImageSource>>();

/** 在离屏画布上给图片压一层颜色（只作用在不透明的像素上）；建不了画布时原样返回。 */
function shaded(img: CanvasImageSource, color: string, alpha: number): CanvasImageSource {
  const key = `${color}|${alpha}`;
  let table = shadeCache.get(img);
  const hit = table?.get(key);
  if (hit) return hit;
  const size = img as { width?: number; height?: number; naturalWidth?: number; naturalHeight?: number };
  const w = size.naturalWidth || size.width || 0;
  const h = size.naturalHeight || size.height || 0;
  if (typeof document === "undefined" || !w || !h) return img;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const c = canvas.getContext("2d");
  if (!c) return img;
  c.drawImage(img, 0, 0, w, h);
  c.globalCompositeOperation = "source-atop";
  c.globalAlpha = alpha;
  c.fillStyle = color;
  c.fillRect(0, 0, w, h);
  if (!table) {
    table = new Map();
    shadeCache.set(img, table);
  }
  table.set(key, canvas);
  return canvas;
}

const patternCache = new WeakMap<object, WeakMap<object, CanvasPattern>>();

function patternOf(ctx: CanvasRenderingContext2D, img: CanvasImageSource): CanvasPattern | null {
  let table = patternCache.get(ctx);
  const hit = table?.get(img);
  if (hit) return hit;
  const p = ctx.createPattern(img, "repeat");
  if (!p) return null;
  if (!table) {
    table = new WeakMap();
    patternCache.set(ctx, table);
  }
  table.set(img, p);
  return p;
}

/** #rrggbb 的相对亮度（WCAG）；认不出的写法返回 null。 */
function luminance(color: string): number | null {
  const m = /^#([0-9a-f]{6})$/i.exec(color.trim());
  if (!m) return null;
  const [r, g, b] = [0, 2, 4].map((i) => {
    const s = parseInt(m[1].slice(i, i + 2), 16) / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** 在实心底色上写字：浅字、深字里挑对比度高的那个（深色主题下警示红、叶绿都变浅，浅字压不住）。 */
export function inkOn(background: string, light: string, dark: string): string {
  const bg = luminance(background);
  const a = luminance(light);
  const b = luminance(dark);
  if (bg === null || a === null || b === null) return light;
  const ratio = (x: number) => (Math.max(bg, x) + 0.05) / (Math.min(bg, x) + 0.05);
  return ratio(a) >= ratio(b) ? light : dark;
}

/** 车顶圆窗（按小车图实测：圆心在车尾起 37.1% 处、车身中线上，半径约车宽 21%）：车里的 TA 画在这里，半径取车宽的 17%，放得进窗里。 */
export const ROOF_WINDOW = { fromRear: 0.371, petRadius: 0.17 } as const;
/** 半径不超过这么多米的树画成灌木。 */
export const BUSH_MAX_R = 1.0;
/** 深色下代码画的房子（纸色是固定色，夜里不变）再叠这么多路面深墨，不在深色页面里亮成一块；名字仍用纸墨，对比度仍 ≥ 4.5。 */
export const BUILDING_DARK_ALPHA = 0.25;

/**
 * 龟教练头像（SCHOOL_ART.coach.portrait，512×512 透明底胸像）：
 * - 圆心＝原来代码画的教练身体中心（装饰坐标），半径＝原来身体椭圆的长半轴 scale×r（r＝max(8px, 0.6 米)，和原来同一个 r）；
 * - 纸色圆底，胸像裁进少 ring/2 的圆里，外面露出 ring 宽的纸色圈，最外一道 35% 纸墨细线（和房子边框一样），在草地上看得清；
 * - 取图中间 crop 的方块（胸像几乎占满，四角由圆裁掉）；
 * - 外沿离每条计分线至少 lineGap 像素：离得不够（320 宽的侧方停车差 3px）就沿离开那条线的方向挪开，大小不变。
 */
export const COACH_AVATAR = { scale: 1.2, ring: 2, crop: 0.78, lineGap: 1 } as const;
/** 纸色名牌的内边距（像素）：场地名牌挪到区域外、建筑名写在屋顶纹理上时，字垫在纸色牌子上。 */
export const PLATE_PAD = { x: 4, y: 2 } as const;
/** 场地名牌离车身至少这么多像素（再加比例尺的 15%：让开压线红框、伸出车尾的尾灯、代码画的车轮）。 */
export const LABEL_CAR_GAP = 4;
/** 屋顶纹理一块代表多少米（UI-ASSET-010：256×256 无缝纹理）。 */
export const ROOF_TILE_METERS = 8;
/** 建筑标志：约 meters 米见方，夹在 min–max 像素（交付单：缩到 24–40px 仍一眼认得出）；名字写在标志下方 gap 像素处。 */
export const EMBLEM = { meters: 3, min: 24, max: 40, gap: 3 } as const;

/** 射线法判断点在不在多边形里（只用来决定终点旗插在哪块区域上，不参与判定）。 */
function insidePoly(x: number, y: number, poly: Poly): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** 画布上的轴对齐矩形（像素） */
interface Box {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** 矩形与凸多边形是否相交（分离轴；只贴着边不算）。 */
function boxHitsPoly(b: Box, poly: Vec[]): boolean {
  const corners: Vec[] = [[b.x0, b.y0], [b.x1, b.y0], [b.x1, b.y1], [b.x0, b.y1]];
  const apart = (nx: number, ny: number) => {
    const p = poly.map(([x, y]) => x * nx + y * ny);
    const q = corners.map(([x, y]) => x * nx + y * ny);
    return Math.max(...p) <= Math.min(...q) || Math.max(...q) <= Math.min(...p);
  };
  if (apart(1, 0) || apart(0, 1)) return false;
  for (let i = 0; i < poly.length; i++) {
    const [ax, ay] = poly[i];
    const [bx, by] = poly[(i + 1) % poly.length];
    if (apart(by - ay, ax - bx)) return false;
  }
  return true;
}

/** 矩形与线段（按半线宽把矩形外扩）是否相交。 */
function boxHitsSegment(b: Box, a: Vec, c: Vec, half: number): boolean {
  const x0 = b.x0 - half;
  const y0 = b.y0 - half;
  const x1 = b.x1 + half;
  const y1 = b.y1 + half;
  if (Math.max(a[0], c[0]) < x0 || Math.min(a[0], c[0]) > x1 || Math.max(a[1], c[1]) < y0 || Math.min(a[1], c[1]) > y1) return false;
  const nx = c[1] - a[1];
  const ny = a[0] - c[0];
  const side = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]].map(([x, y]) => (x - a[0]) * nx + (y - a[1]) * ny);
  return Math.min(...side) <= 0 && Math.max(...side) >= 0;
}

/** 线段上离点 p 最近的点。 */
function nearestOnSegment(p: Vec, a: Vec, b: Vec): Vec {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len2 = dx * dx + dy * dy;
  const t = len2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2)) : 0;
  return [a[0] + dx * t, a[1] + dy * t];
}

/**
 * 分层：all＝一次画完（没有缓存时，与原来完全一样）；static＝只画不随时间变的地面与装饰（给离屏缓存用）；
 * dynamic＝只画会变的：会避让徽标的文字、压着的线、锥桶、信号灯与过街居民、预测轨迹、车、碰锥红圈、扣分牌子。
 */
export type DrawLayers = "all" | "static" | "dynamic";

/**
 * 静态层离屏缓存：接上纹理后 4 倍降速下帧间隔 p95 从 16.8ms 涨到 33.4ms（每帧都在铺纹理、画装饰图），
 * 所以把地面加装饰预渲染到离屏画布里，每帧只贴一次，再画会变的东西。
 * - 场地类（镜头固定）：只画一次，尺寸、比例尺、明暗、素材、练习与否变了才重画；
 * - 科三跟车（镜头只平移不旋转）：离屏画布四周多留 margin 像素，镜头在余量内只挪贴图的位置，走出余量才重画。
 */
export interface StaticLayerCache {
  canvas: HTMLCanvasElement | null;
  key: string;
  /** 缓存画的时候镜头中心（世界坐标） */
  cx: number;
  cy: number;
  margin: number;
  /** 重画了几次（用例与实测用） */
  renders: number;
}

export function createStaticLayerCache(): StaticLayerCache {
  return { canvas: null, key: "", cx: 0, cy: 0, margin: 0, renders: 0 };
}

/** 跟车镜头的余量占画面长边的比例（车最快约 11 米/秒，390 宽下约每 1.6 秒走出余量重画一次）。 */
export const FOLLOW_MARGIN = 0.35;

/**
 * 带缓存地画一帧：没有缓存或建不了离屏画布时退回 draw(all)，画面与原来完全一样。
 * dpr：画布实际像素比（调用方已经按它 setTransform 过主画布）。
 */
export function drawCached(ctx: CanvasRenderingContext2D, width: number, height: number, cam: Camera, frame: Frame, pal: Palette, sprites: DriveSprites | null, cache: StaticLayerCache | null, dpr = 1): void {
  if (!cache || typeof document === "undefined") return draw(ctx, width, height, cam, frame, pal, sprites);
  const margin = frame.course.kind === "route" ? Math.round(Math.max(width, height) * FOLLOW_MARGIN) : 0;
  const W = width + margin * 2;
  const H = height + margin * 2;
  const key = [frame.course.course_id, frame.course.variant, width, height, dpr, cam.scale, frame.practice, pal.grass, pal.road, pal.ink, pal.paint, sprites?.version ?? 0].join("|");
  const dx = (cache.cx - cam.cx) * cam.scale;
  const dy = (cam.cy - cache.cy) * cam.scale;
  const fresh = cache.canvas && cache.key === key && Math.abs(dx) <= cache.margin && Math.abs(dy) <= cache.margin;
  if (!fresh) {
    const canvas = cache.canvas ?? document.createElement("canvas");
    const w = Math.max(1, Math.round(W * dpr));
    const h = Math.max(1, Math.round(H * dpr));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    const c = canvas.getContext("2d");
    if (!c) return draw(ctx, width, height, cam, frame, pal, sprites);
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw(c, W, H, cam, frame, pal, sprites, "static");
    Object.assign(cache, { canvas, key, cx: cam.cx, cy: cam.cy, margin, renders: cache.renders + 1 });
  }
  ctx.clearRect(0, 0, width, height);
  ctx.drawImage(cache.canvas!, (cache.cx - cam.cx) * cam.scale - cache.margin, (cam.cy - cache.cy) * cam.scale - cache.margin, W, H);
  draw(ctx, width, height, cam, frame, pal, sprites, "dynamic");
}

export function draw(ctx: CanvasRenderingContext2D, width: number, height: number, cam: Camera, frame: Frame, pal: Palette, sprites?: DriveSprites | null, layers: DrawLayers = "all"): void {
  const statics = layers !== "dynamic";
  const dynamics = layers !== "static";
  // 深色：ink 在深色主题里是浅色字
  const dark = (luminance(pal.ink) ?? 0) > 0.5;
  const shade = dark ? SHADE.dark : SHADE.light;
  const tone = (img: CanvasImageSource | null | undefined, rule: { readonly color: keyof Palette; readonly alpha: number } | null): CanvasImageSource | null =>
    img ? (rule ? shaded(img, pal[rule.color], rule.alpha) : img) : null;
  /** 某种装饰的第 i 个用哪张图（变体按出现顺序轮流；缺的变体跳过；一张都没有就是 null，走代码画法） */
  const variant = (key: string, i: number): CanvasImageSource | null => {
    const pool = (sprites?.decor[key] ?? []).filter((x): x is CanvasImageSource => !!x);
    return pool.length ? tone(pool[i % pool.length], shade.decor) : null;
  };
  /** 装饰图：细分键（type:style / type:kind）优先，其次 type；没有就返回 null（走代码画法） */
  const decorSprite = (d: Decor): CanvasImageSource | null => {
    const sub = d.style ?? d.kind;
    return (sub ? variant(`${d.type}:${sub}`, 0) : null) ?? variant(d.type, 0);
  };
  const S = cam.scale;
  const X = (x: number) => (x - cam.cx) * S + width / 2;
  const Y = (y: number) => height / 2 - (y - cam.cy) * S;
  /** 地面纹理：平铺，按镜头把纹理原点钉在世界坐标 (0, 0)，每块代表 meters 米；没有纹理就用调色板的颜色 */
  const ground = (img: CanvasImageSource | null, meters: number): CanvasPattern | null => {
    if (!img) return null;
    const p = patternOf(ctx, img);
    if (!p) return null;
    const size = img as { width?: number; naturalWidth?: number };
    const k = (S * meters) / (size.naturalWidth || size.width || 256);
    p.setTransform?.({ a: k, b: 0, c: 0, d: k, e: X(0), f: Y(0) });
    return p;
  };
  const grassFill = statics ? ground(tone(sprites?.grass, shade.grass), TILE_METERS.grass) : null;
  const asphaltFill = statics ? ground(tone(sprites?.asphalt, shade.asphalt), TILE_METERS.asphalt) : null;
  const carImg = tone(sprites?.car, shade.car);
  /** 铺柏油：有纹理就用纹理（已按明暗压过色），没有就是原来的 82% 路面深墨 */
  const fillRoad = () => {
    if (asphaltFill) {
      ctx.fillStyle = asphaltFill;
      ctx.fill();
      return;
    }
    ctx.globalAlpha = 0.82;
    ctx.fillStyle = pal.road;
    ctx.fill();
    ctx.globalAlpha = 1;
  };
  const path = (poly: Poly) => {
    ctx.beginPath();
    poly.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(X(x), Y(y)) : ctx.lineTo(X(x), Y(y))));
    ctx.closePath();
  };
  const segment = (a: Vec, b: Vec) => {
    ctx.beginPath();
    ctx.moveTo(X(a[0]), Y(a[1]));
    ctx.lineTo(X(b[0]), Y(b[1]));
  };
  const label = (text: string, x: number, y: number, size: number, color: string, weight = 600, dodge = false) => {
    const px = Math.max(10, size);
    ctx.font = `${weight} ${px}px ${pal.font}`;
    ctx.fillStyle = color;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    let ty = y;
    const box = frame.avoid;
    if (dodge && box && x - ctx.measureText(text).width / 2 < box.w && ty - px / 2 < box.h) ty = box.h + px / 2 + 2;
    ctx.fillText(text, x, ty);
  };
  /** 纸色名牌：纸底圆角牌子＋纸墨字（深色下纸底和房子一样再压一层，纸墨字仍 ≥ 4.5）；dodge 同 label */
  const plate = (text: string, x: number, y: number, size: number, weight: number, dodge = false) => {
    const px = Math.max(10, size);
    ctx.font = `${weight} ${px}px ${pal.font}`;
    const w = ctx.measureText(text).width + PLATE_PAD.x * 2;
    const h = px + PLATE_PAD.y * 2;
    let ty = y;
    const box = frame.avoid;
    if (dodge && box && x - w / 2 < box.w && ty - h / 2 < box.h) ty = box.h + h / 2 + 2;
    roundRect(x - w / 2, ty - h / 2, w, h, Math.min(h / 2, 6));
    ctx.fillStyle = pal.paper;
    ctx.fill();
    if (dark) {
      ctx.globalAlpha = BUILDING_DARK_ALPHA;
      ctx.fillStyle = pal.road;
      ctx.fill();
      ctx.globalAlpha = 1;
    }
    ctx.fillStyle = pal.paperInk;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, x, ty);
  };
  /** 计分线平时的线宽（压着时另画加粗的红线） */
  const lineWidthOf = (kind: string) => (kind === "curb" || kind === "barrier" ? Math.max(3, S * 0.3) : Math.max(2, S * 0.15));
  /** 车身矩形在画布上的四个角，外扩 pad 像素（和 drawCar 同一套变换） */
  const carHull = (pad: number): Vec[] => {
    const car = frame.course.car;
    const p = frame.pose;
    const a = Math.atan2(-p.hy, p.hx);
    const cos = Math.cos(a);
    const sin = Math.sin(a);
    const x0 = -car.rear * S - pad;
    const x1 = (car.wheelbase + car.front) * S + pad;
    const half = (car.width / 2) * S + pad;
    const corners: Vec[] = [[x0, -half], [x1, -half], [x1, half], [x0, half]];
    return corners.map(([lx, ly]): Vec => [X(p.x) + lx * cos - ly * sin, Y(p.y) + lx * sin + ly * cos]);
  };

  const decor = frame.course.decor;
  const layer = (types: string[]) => decor.filter((d) => types.includes(d.type) && (frame.practice || !d.practice_only));
  /** 判定线（计分线、停止线）在画布上的两端与半线宽：挪开的场地名牌、教练头像都不压它们 */
  const judgeLines = (): [Vec, Vec, number][] => [
    ...frame.course.lines.map((l): [Vec, Vec, number] => [[X(l.a[0]), Y(l.a[1])], [X(l.b[0]), Y(l.b[1])], lineWidthOf(l.kind) / 2]),
    ...layer(["stopline"]).map((d): [Vec, Vec, number] => [[X(d.a![0]), Y(d.a![1])], [X(d.b![0]), Y(d.b![1])], Math.max(3, S * 0.35) / 2]),
  ];
  /** 圆（圆心 x,y，外沿半径 reach）离每条判定线至少 reach：不够就沿离开“差得最多的那条线”的方向挪开 */
  const clearOfLines = (x: number, y: number, reach: number): Vec => {
    let worst = 0;
    let ux = 0;
    let uy = 0;
    for (const [a, b, half] of judgeLines()) {
      const [qx, qy] = nearestOnSegment([x, y], a, b);
      const dist = Math.hypot(x - qx, y - qy);
      const short = reach + half - dist;
      if (dist > 0 && short > worst) {
        worst = short;
        ux = (x - qx) / dist;
        uy = (y - qy) / dist;
      }
    }
    return [x + ux * worst, y + uy * worst];
  };
  /**
   * 场地名牌（起始区、终点区、停在这里、装卸区）：平时写在区域中心，和原来一样；
   * 车开进来盖住字时（车身外扩 LABEL_CAR_GAP＋比例尺 15% 算），挪到区域外不挨着车的一侧——上、下、右、左依次试：
   * 不出画布、不进左上角徽标框、不压车，尽量不压判定线；垫纸色名牌（区域外可能是浅色草地，路面白字看不清）。
   * 名牌在车、压着的线、锥桶之前画，又不和外扩后的车身相交，所以挡不住压线红框和刹车灯。
   */
  const zoneLabel = (text: string, poly: Poly) => {
    const [cx, cy] = centroid(poly);
    const size = S * 0.7;
    const px = Math.max(10, size);
    const tx = X(cx);
    let ty = Y(cy);
    ctx.font = `600 ${px}px ${pal.font}`;
    const tw = ctx.measureText(text).width;
    const box = frame.avoid;
    // 原来的位置（含徽标框避让），和 label() 算法一样
    if (box && tx - tw / 2 < box.w && ty - px / 2 < box.h) ty = box.h + px / 2 + 2;
    const hull = carHull(LABEL_CAR_GAP + S * 0.15);
    if (!boxHitsPoly({ x0: tx - tw / 2, y0: ty - px / 2, x1: tx + tw / 2, y1: ty + px / 2 }, hull)) return label(text, tx, Y(cy), size, pal.paint, 600, true);
    const w = tw + PLATE_PAD.x * 2;
    const h = px + PLATE_PAD.y * 2;
    const gap = 3;
    const xs = poly.map((p) => X(p[0]));
    const ys = poly.map((p) => Y(p[1]));
    const spots: Vec[] = [
      [tx, Math.min(...ys) - gap - h / 2],
      [tx, Math.max(...ys) + gap + h / 2],
      [Math.max(...xs) + gap + w / 2, Y(cy)],
      [Math.min(...xs) - gap - w / 2, Y(cy)],
    ];
    const lines = judgeLines();
    const fits = ([x, y]: Vec, strict: boolean) => {
      const b = { x0: x - w / 2, y0: y - h / 2, x1: x + w / 2, y1: y + h / 2 };
      if (b.x0 < 0 || b.y0 < 0 || b.x1 > width || b.y1 > height) return false;
      if (box && b.x0 < box.w && b.y0 < box.h) return false;
      if (boxHitsPoly(b, hull)) return false;
      return !strict || !lines.some(([a, c, half]) => boxHitsSegment(b, a, c, half));
    };
    const spot = spots.find((s) => fits(s, true)) ?? spots.find((s) => fits(s, false));
    if (!spot) return label(text, tx, Y(cy), size, pal.paint, 600, true);
    plate(text, spot[0], spot[1], size, 600);
  };
  if (statics) {
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = grassFill ?? pal.grass;
    ctx.fillRect(0, 0, width, height);
    for (const d of layer(["sidewalk"])) {
      path(d.poly!);
      ctx.fillStyle = pal.sidewalk;
      ctx.fill();
    }
    for (const d of layer(["asphalt"])) {
      path(d.poly!);
      fillRoad();
    }
    for (const d of layer(["lane"])) drawLane(d);
    for (const d of layer(["crosswalk"])) drawCrosswalk(d.poly!);
  }
  for (const d of layer(["zone"])) {
    if (statics) {
      path(d.poly!);
      ctx.globalAlpha = 0.35;
      ctx.fillStyle = pal.zone;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.setLineDash([6, 5]);
      ctx.lineWidth = 2;
      ctx.strokeStyle = pal.zoneStroke;
      ctx.stroke();
      ctx.setLineDash([]);
    }
    if (dynamics && d.label) zoneLabel(d.label, d.poly!);
  }
  if (statics) {
    for (const d of layer(["paint"])) {
      segment(d.a!, d.b!);
      ctx.setLineDash(d.dash ? [S * 0.8, S * 0.6] : []);
      ctx.lineWidth = Math.max(1.5, S * 0.12);
      ctx.strokeStyle = pal.paint;
      ctx.globalAlpha = 0.7;
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.setLineDash([]);
    }
    for (const d of layer(["stopline"])) {
      segment(d.a!, d.b!);
      ctx.lineWidth = Math.max(3, S * 0.35);
      ctx.strokeStyle = pal.paint;
      ctx.stroke();
    }
    for (const d of layer(["arrow"])) drawArrow(d);
  }

  // 计分线（压到就扣分）：车位线白色、路沿灰色、中心线黄色；正在压的线变红。
  // 分层时：静态层画全部线（都不高亮），动态层只把正在压的那条再画一遍（衬边＋红）。
  for (const line of frame.course.lines) {
    const pressed = layers !== "static" && frame.pressedLine === line.id;
    if (!statics && !pressed) continue;
    segment(line.a, line.b);
    if (pressed) {
      // 正在压的线加粗变红，一眼看得出压的是哪一条；底下垫一道浅色衬边（警示红压在柏油上不到 3:1，衬边在柏油上 ≥ 3:1）
      ctx.lineWidth = Math.max(4, S * 0.32) + 3;
      ctx.strokeStyle = pal.paint;
      ctx.stroke();
    }
    ctx.lineWidth = pressed ? Math.max(4, S * 0.32) : lineWidthOf(line.kind);
    ctx.strokeStyle = pressed ? pal.danger : line.kind === "center" ? pal.center : line.kind === "curb" || line.kind === "barrier" ? pal.curb : pal.paint;
    ctx.stroke();
  }
  for (const d of statics ? layer(["barrier"]) : []) {
    segment(d.a!, d.b!);
    ctx.lineWidth = Math.max(4, S * 0.4);
    ctx.setLineDash([S * 0.5, S * 0.5]);
    ctx.strokeStyle = pal.cone;
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // 练习提示：目标车位与朝向。
  const target = frame.course.target;
  if (statics && frame.practice && target) {
    path(target.poly);
    ctx.globalAlpha = 0.18;
    ctx.fillStyle = pal.leaf;
    ctx.fill();
    ctx.globalAlpha = 1;
    // 浅色衬边（叶绿压在柏油上不到 3:1），再画叶绿虚线
    ctx.lineWidth = 4;
    ctx.strokeStyle = pal.paint;
    ctx.stroke();
    ctx.setLineDash([5, 4]);
    ctx.lineWidth = 2;
    ctx.strokeStyle = pal.leaf;
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // 终点旗：插在装着目标区中心的那块区域（终点区 / 停在这里 / 装卸区）的右上角；只管外观，判定区照旧由代码定义
  const flagImg = statics && target ? variant("flag", 0) : null;
  if (flagImg && target) {
    const [tcx, tcy] = centroid(target.poly);
    for (const d of layer(["zone"])) {
      if (!insidePoly(tcx, tcy, d.poly!)) continue;
      const size = Math.max(20, S * 1.6);
      const xs = d.poly!.map((p) => p[0]);
      const ys = d.poly!.map((p) => p[1]);
      // 旗杆脚在图片左下角：把左下角对到区域右上角
      ctx.drawImage(flagImg, X(Math.max(...xs)) - size * 0.2, Y(Math.max(...ys)) - size * 0.9, size, size);
    }
  }

  (dynamics ? frame.course.cones : []).forEach((cone, i) => {
    const down = frame.knocked.includes(cone.id);
    // 锥桶图按判定圆画（直径＝判定半径 ×1.2 ×2，至少 8px，和原来代码画的锥桶一样大），碰倒的横过来、变淡
    const r = Math.max(4, cone.r * S * 1.2);
    const img = variant("cone", i);
    if (img) {
      ctx.save();
      ctx.translate(X(cone.x) + (down ? S * 0.25 : 0), Y(cone.y));
      if (down) {
        ctx.rotate(Math.PI / 2);
        ctx.globalAlpha = 0.55;
      }
      ctx.drawImage(img, -r, -r, r * 2, r * 2);
      ctx.restore();
      return;
    }
    ctx.beginPath();
    ctx.arc(X(cone.x) + (down ? S * 0.25 : 0), Y(cone.y), r, 0, Math.PI * 2);
    ctx.fillStyle = down ? pal.coneKnocked : pal.cone;
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = pal.paint;
    ctx.stroke();
  });

  for (const d of layer(["building"])) drawBuilding(d);
  // 树：A/B 两种轮流；半径不超过 BUSH_MAX_R 的画成灌木（没有灌木图就用树图）；都没有就是代码画的圆
  (statics ? layer(["tree"]) : []).forEach((d, i) => {
    const r = (d.r ?? 1) * S;
    const img = (d.r ?? 1) <= BUSH_MAX_R ? (variant("bush", i) ?? variant("tree", i)) : variant("tree", i);
    if (img) {
      ctx.drawImage(img, X(d.x!) - r, Y(d.y!) - r, r * 2, r * 2);
      return;
    }
    ctx.beginPath();
    ctx.arc(X(d.x!), Y(d.y!), r, 0, Math.PI * 2);
    ctx.fillStyle = pal.tree;
    ctx.globalAlpha = 0.85;
    ctx.fill();
    ctx.globalAlpha = 1;
  });
  for (const d of layer(["bus_stop"])) {
    if (statics) {
      const img = decorSprite(d);
      if (img) ctx.drawImage(img, X(d.x!) - S * 1.2, Y(d.y!) - S * 0.4, S * 2.4, S * 0.8);
      else {
        ctx.fillStyle = pal.sky;
        ctx.fillRect(X(d.x!) - S * 1.2, Y(d.y!) - S * 0.4, S * 2.4, S * 0.8);
      }
    }
    if (dynamics) label("站", X(d.x!), Y(d.y!), S * 0.6, pal.paint);
  }
  if (statics) {
    for (const d of layer(["sign"])) drawSign(d);
    for (const d of layer(["resident"])) drawResident(d.x!, d.y!, d.kind ?? "penguin");
  }
  for (const d of layer(["coach"])) drawCoach(d);

  const route = frame.course.route;
  if (route && dynamics) {
    const phase = lightPhase(route, frame.tick);
    const [lx, ly] = route.light.pos;
    ctx.fillStyle = pal.carInk;
    ctx.fillRect(X(lx) - S * 0.5, Y(ly) - S * 1.3, S * 1.0, S * 2.6);
    const lamps: ["red" | "yellow" | "green", string, number][] = [["red", pal.danger, 0.8], ["yellow", pal.sun, 0], ["green", pal.leaf, -0.8]];
    for (const [name, color, dy] of lamps) {
      ctx.beginPath();
      ctx.arc(X(lx), Y(ly + dy), S * 0.32, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.globalAlpha = phase === name ? 1 : 0.2;
      ctx.fill();
      ctx.globalAlpha = 1;
    }
    const r = frame.route;
    if (r && r.cw_tick !== null && frame.tick - r.cw_tick < route.crosswalk.walker.ticks) {
      const [wx, wy] = walkerAt(route, r.cw_tick, frame.tick);
      drawResident(wx, wy, route.crosswalk.walker.kind);
    } else if (!r || r.cw_tick === null) {
      const [wx, wy] = route.crosswalk.walker.from;
      drawResident(wx, wy, route.crosswalk.walker.kind);
    }
  }

  if (!dynamics) return;

  if (frame.predicted && frame.predicted.length) {
    ctx.fillStyle = pal.leaf;
    for (const p of frame.predicted) {
      ctx.beginPath();
      ctx.arc(X(p.x), Y(p.y), Math.max(1.5, S * 0.1), 0, Math.PI * 2);
      ctx.fill();
    }
  }

  drawCar(frame);

  // 碰过的锥桶：画在车的上面，套一圈警示红（车停在锥桶上时也看得见碰的是哪一个）
  for (const cone of frame.course.cones) {
    if (!frame.knocked.includes(cone.id)) continue;
    ctx.beginPath();
    ctx.arc(X(cone.x), Y(cone.y), Math.max(9, cone.r * S * 2.6), 0, Math.PI * 2);
    ctx.lineWidth = 2.5;
    ctx.strokeStyle = pal.danger;
    ctx.stroke();
  }
  for (const m of frame.marks ?? []) drawMark(m);

  // ---- 局部绘制函数 ----
  function drawMark(m: FrameMark) {
    ctx.font = `800 13px ${pal.font}`;
    const w = ctx.measureText(m.text).width + 14;
    const h = 24;
    const x = Math.max(4, Math.min(width - w - 4, X(m.x) - w / 2));
    const y = Math.max(4, Math.min(height - h - 4, Y(m.y) - h - 16));
    const bg = m.tone === "bad" ? pal.danger : pal.leaf;
    roundRect(x, y, w, h, h / 2);
    ctx.fillStyle = bg;
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = pal.paint;
    ctx.stroke();
    ctx.fillStyle = inkOn(bg, pal.paint, pal.carInk);
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(m.text, x + w / 2, y + h / 2 + 0.5);
  }

  function drawLane(d: Decor) {
    const left = d.left!;
    const right = d.right!;
    ctx.beginPath();
    left.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(X(x), Y(y)) : ctx.lineTo(X(x), Y(y))));
    for (let i = right.length - 1; i >= 0; i--) ctx.lineTo(X(right[i][0]), Y(right[i][1]));
    ctx.closePath();
    fillRoad();
  }

  function drawCrosswalk(poly: Poly) {
    const xs = poly.map((p) => p[0]);
    const ys = poly.map((p) => p[1]);
    const x0 = Math.min(...xs);
    const x1 = Math.max(...xs);
    const y0 = Math.min(...ys);
    const y1 = Math.max(...ys);
    ctx.fillStyle = pal.paint;
    ctx.globalAlpha = 0.85;
    for (let y = y0 + 0.3; y < y1; y += 1.0) ctx.fillRect(X(x0), Y(y + 0.5), (x1 - x0) * S, 0.5 * S);
    ctx.globalAlpha = 1;
  }

  function drawArrow(d: Decor) {
    const x = X(d.x!);
    const y = Y(d.y!);
    ctx.save();
    ctx.translate(x, y);
    if (d.dir === "right") ctx.rotate(Math.PI / 2);
    ctx.fillStyle = pal.paint;
    ctx.globalAlpha = 0.75;
    ctx.beginPath();
    ctx.moveTo(-S * 0.3, S * 1.2);
    ctx.lineTo(-S * 0.3, -S * 0.2);
    ctx.lineTo(S * 0.6, -S * 0.2);
    ctx.lineTo(S * 0.6, -S * 0.6);
    ctx.lineTo(S * 1.3, 0);
    ctx.lineTo(S * 0.6, S * 0.6);
    ctx.lineTo(S * 0.6, S * 0.2);
    ctx.lineTo(S * 0.3, S * 0.2);
    ctx.lineTo(S * 0.3, S * 1.2);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }

  function drawBuilding(d: Decor) {
    const poly = d.poly!;
    // 房子（屋顶、标志、边框）在静态层；名字在动态层（会避让徽标）。
    // 屋顶纹理、标志按样式取（UI-ASSET-010）；没有网址或加载失败就是原来的纸色房子，一笔不差。
    const roof = sprites?.roof?.[d.style ?? ""] ?? null;
    const emblem = d.label ? (sprites?.emblem?.[d.style ?? ""] ?? null) : null;
    const [cx, cy] = centroid(poly);
    const e = Math.min(EMBLEM.max, Math.max(EMBLEM.min, S * EMBLEM.meters));
    if (statics) {
      path(poly);
      // 屋顶：纹理平铺、原点钉在世界坐标（和地面一样），填进建筑多边形（填色即裁剪）
      const roofFill = roof ? ground(roof, ROOF_TILE_METERS) : null;
      ctx.fillStyle = roofFill ?? (d.style === "canteen" || d.style === "post" || d.style === "school" ? pal.paper : pal.paperShade);
      ctx.fill();
      // 标志放在建筑中心；在压暗之前画，深色下和屋顶一起压 25%
      if (emblem) ctx.drawImage(emblem, X(cx) - e / 2, Y(cy) - e / 2, e, e);
      if (dark) {
        ctx.globalAlpha = BUILDING_DARK_ALPHA;
        ctx.fillStyle = pal.road;
        ctx.fill();
        ctx.globalAlpha = 1;
      }
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = pal.paperInk;
      ctx.globalAlpha = 0.35;
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    if (dynamics && d.label) {
      const size = S * 1.4;
      const px = Math.max(10, size);
      // 有标志：名字写在标志下方（避让徽标只会再往下挪，碰不到标志）；写在屋顶纹理上时垫纸色名牌
      const half = roof ? px / 2 + PLATE_PAD.y : px / 2;
      const y = emblem ? Y(cy) + e / 2 + EMBLEM.gap + half : Y(cy);
      if (roof) plate(d.label, X(cx), y, size, 700, true);
      else label(d.label, X(cx), y, size, pal.paperInk, 700, true);
    }
  }

  function drawSign(d: Decor) {
    const x = X(d.x!);
    const y = Y(d.y!);
    const r = Math.max(9, S * 0.7);
    ctx.beginPath();
    if (d.kind === "stop") {
      for (let i = 0; i < 8; i++) {
        const a = Math.PI / 8 + (i * Math.PI) / 4;
        ctx.lineTo(x + r * Math.cos(a), y + r * Math.sin(a));
      }
      ctx.closePath();
      ctx.fillStyle = pal.danger;
      ctx.fill();
      label(d.label ?? "停", x, y, r * 0.95, pal.paint, 800);
      return;
    }
    if (d.kind === "speed") {
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = pal.paint;
      ctx.fill();
      ctx.lineWidth = Math.max(2, r * 0.22);
      ctx.strokeStyle = pal.danger;
      ctx.stroke();
      label(d.label ?? "", x, y, r * 0.9, pal.paperInk, 800);
      return;
    }
    const text = d.label ?? "";
    ctx.font = `700 ${Math.max(10, S * 0.6)}px ${pal.font}`;
    const w = ctx.measureText(text).width + 10;
    ctx.fillStyle = d.kind === "crossing" ? pal.sky : pal.paper;
    ctx.fillRect(x - w / 2, y - r * 0.8, w, r * 1.6);
    label(text, x, y, S * 0.6, d.kind === "crossing" ? pal.paint : pal.paperInk, 700);
  }

  function drawResident(wx: number, wy: number, kind: string) {
    const x = X(wx);
    const y = Y(wy);
    const r = Math.max(6, S * 0.45);
    const img = decorSprite({ type: "resident", kind });
    if (img) {
      ctx.drawImage(img, x - r * 1.4, y - r * 1.4, r * 2.8, r * 2.8);
      return;
    }
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = kind === "penguin" ? pal.carInk : kind === "bear" ? pal.paperShade : pal.paint;
    ctx.fill();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = pal.ink;
    ctx.stroke();
    if (kind === "rabbit") {
      ctx.fillStyle = pal.paint;
      ctx.fillRect(x - r * 0.55, y - r * 2, r * 0.35, r * 1.3);
      ctx.fillRect(x + r * 0.2, y - r * 2, r * 0.35, r * 1.3);
    }
    ctx.fillStyle = kind === "penguin" ? pal.paint : pal.carInk;
    ctx.beginPath();
    ctx.arc(x - r * 0.35, y - r * 0.1, r * 0.13, 0, Math.PI * 2);
    ctx.arc(x + r * 0.35, y - r * 0.1, r * 0.13, 0, Math.PI * 2);
    ctx.fill();
  }

  function drawCoach(d: Decor) {
    const x = X(d.x!);
    const y = Y(d.y!);
    const r = Math.max(8, S * 0.6);
    // 头像（SCHOOL_ART.coach.portrait，深色下和别的装饰一样压暗）；没到或加载失败：原来的代码画法，一笔不差
    const img = decorSprite(d);
    if (!img) {
      if (statics) {
        ctx.beginPath();
        ctx.ellipse(x, y, r * 1.2, r * 0.9, 0, 0, Math.PI * 2);
        ctx.fillStyle = pal.leaf;
        ctx.fill();
        ctx.beginPath();
        ctx.arc(x + r * 1.3, y - r * 0.2, r * 0.45, 0, Math.PI * 2);
        ctx.fillStyle = pal.tree;
        ctx.fill();
      }
      if (dynamics) label("龟教练", x, y - r * 1.5, Math.max(10, S * 0.5), pal.ink, 700, true);
      return;
    }
    const R = r * COACH_AVATAR.scale;
    const ring = COACH_AVATAR.ring;
    // 外沿＝纸色圈外缘再加 1px 细线
    const outer = R + ring / 2 + 1;
    const [ax, ay] = clearOfLines(x, y, outer + COACH_AVATAR.lineGap);
    if (statics) {
      ctx.save();
      ctx.beginPath();
      ctx.arc(ax, ay, R + ring / 2, 0, Math.PI * 2);
      ctx.fillStyle = pal.paper;
      ctx.fill();
      if (shade.decor) {
        ctx.globalAlpha = shade.decor.alpha;
        ctx.fillStyle = pal[shade.decor.color];
        ctx.fill();
        ctx.globalAlpha = 1;
      }
      ctx.beginPath();
      ctx.arc(ax, ay, R - ring / 2, 0, Math.PI * 2);
      ctx.clip();
      const size = img as { width?: number; height?: number; naturalWidth?: number; naturalHeight?: number };
      const iw = size.naturalWidth || size.width || 1;
      const ih = size.naturalHeight || size.height || 1;
      const side = Math.min(iw, ih) * COACH_AVATAR.crop;
      ctx.drawImage(img, (iw - side) / 2, (ih - side) / 2, side, side, ax - R, ay - R, R * 2, R * 2);
      ctx.restore();
      ctx.beginPath();
      ctx.arc(ax, ay, R + ring / 2 + 0.5, 0, Math.PI * 2);
      ctx.lineWidth = 1;
      ctx.strokeStyle = pal.paperInk;
      ctx.globalAlpha = 0.35;
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    if (dynamics) {
      // 名字写在头像上方；那里落进左上角徽标框时改写到头像下方（徽标避让是往下挪，会压到头像上）
      const px = Math.max(10, S * 0.5);
      ctx.font = `700 ${px}px ${pal.font}`;
      const half = ctx.measureText("龟教练").width / 2;
      const box = frame.avoid;
      const above = ay - outer - 2 - px / 2;
      const under = !!box && ax - half < box.w && above - px / 2 < box.h;
      label("龟教练", ax, under ? ay + outer + 2 + px / 2 : above, px, pal.ink, 700, true);
    }
  }

  function drawCar(f: Frame) {
    const car = f.course.car;
    const p = f.pose;
    const x = X(p.x);
    const y = Y(p.y);
    const angle = Math.atan2(-p.hy, p.hx);
    const len = (car.rear + car.wheelbase + car.front) * S;
    const wid = car.width * S;
    const rear = car.rear * S;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(angle);
    // 车轮（前轮随方向盘转动）
    const wheel = (wx: number, wy: number, rot: number) => {
      ctx.save();
      ctx.translate(wx, wy);
      ctx.rotate(rot);
      ctx.fillStyle = pal.carInk;
      ctx.fillRect(-S * 0.35, -S * 0.13, S * 0.7, S * 0.26);
      ctx.restore();
    };
    const steerAngle = -(f.steer / car.steer_steps) * ((car.steer_max_deg * Math.PI) / 180);
    const wb = car.wheelbase * S;
    // 代码画的车才画车轮（小车图自带车轮；代码车轮半露在车身外，叠在图上会多出四个黑块）
    if (!carImg) {
      wheel(0, -wid / 2, 0);
      wheel(0, wid / 2, 0);
      wheel(wb, -wid / 2, steerAngle);
      wheel(wb, wid / 2, steerAngle);
    }
    // 车身：有小车图就画图（车头朝 +x，占满车身矩形 3.8×1.7），没有就用代码画
    if (carImg) {
      ctx.drawImage(carImg, -rear, -wid / 2, len, wid);
      roundRect(-rear, -wid / 2 + S * 0.08, len, wid - S * 0.16, S * 0.45);
    } else {
      roundRect(-rear, -wid / 2 + S * 0.08, len, wid - S * 0.16, S * 0.45);
      ctx.fillStyle = pal.car;
      ctx.fill();
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = pal.carInk;
      ctx.stroke();
    }
    // 压着线的时候，车身描一圈警示红
    if (f.pressedLine) {
      ctx.lineWidth = Math.max(2.5, S * 0.18);
      ctx.strokeStyle = pal.danger;
      ctx.stroke();
    }
    // 挡风玻璃与车顶（小车图里自带）
    if (!carImg) {
      roundRect(wb - S * 0.9, -wid / 2 + S * 0.3, S * 0.55, wid - S * 0.6, S * 0.15);
      ctx.fillStyle = pal.glass;
      ctx.fill();
    }
    // 车里的 TA：用小车图时画进车顶圆窗（车尾起 37%、车身中线上）；代码画的车坐在左侧驾驶位（局部坐标里车头朝 +x，左侧是 -y）。
    // 圆脑袋加两只朝前的耳朵。
    const hx0 = carImg ? -rear + ROOF_WINDOW.fromRear * len : wb - S * 1.5;
    const hy0 = carImg ? 0 : -S * 0.35;
    const hr = carImg ? ROOF_WINDOW.petRadius * wid : S * 0.34;
    ctx.fillStyle = pal.pet;
    ctx.beginPath();
    ctx.arc(hx0, hy0, hr, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    for (const side of [-1, 1]) {
      ctx.moveTo(hx0 + hr * 0.2, hy0 + side * hr * 0.95);
      ctx.lineTo(hx0 + hr * 1.25, hy0 + side * hr * 0.75);
      ctx.lineTo(hx0 + hr * 0.75, hy0 + side * hr * 0.1);
    }
    ctx.fill();
    // 尾灯：刹车红、倒挡白
    const tail = f.brake ? pal.danger : f.gear === -1 ? pal.paint : null;
    if (tail) {
      ctx.fillStyle = tail;
      ctx.fillRect(-rear - S * 0.05, -wid / 2 + S * 0.15, S * 0.18, S * 0.35);
      ctx.fillRect(-rear - S * 0.05, wid / 2 - S * 0.5, S * 0.18, S * 0.35);
    }
    // 转向灯（-1 左、1 右；车头朝 +x，左侧是 -y 屏幕方向）
    if (f.blink !== 0 && f.blinkOn) {
      ctx.fillStyle = pal.sun;
      const side = f.blink === -1 ? -1 : 1;
      const yy = side * (wid / 2 - S * 0.12);
      ctx.beginPath();
      ctx.arc(len - rear - S * 0.15, yy, S * 0.2, 0, Math.PI * 2);
      ctx.arc(-rear + S * 0.15, yy, S * 0.2, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  function roundRect(x: number, y: number, w: number, h: number, r: number) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }
}

function centroid(poly: Poly): Vec {
  let x = 0;
  let y = 0;
  for (const p of poly) {
    x += p[0];
    y += p[1];
  }
  return [x / poly.length, y / poly.length];
}
