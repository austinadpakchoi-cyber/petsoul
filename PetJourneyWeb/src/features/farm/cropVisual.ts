/*
 * 作物图只有一套：UI-ASSET-006 v1（r7k）五种作物各“生长中 / 成熟”两档，512×512 透明底，字节不改。
 * 图只表达物种与阶段；进度、成熟、收获一律以服务端事实为准。
 * - cropArt()：图 + 把作物“种进地里”的几何。菜园地块、小窝院子的菜园入口（两处都用 GardenScene 的 GardenBed）、
 *   种菜面板缩略图都读它。
 * - cropVisual()：只要图的地方用的旧名字，等同 cropArt(...).src（旧的木框时代作物图已不再引用）。
 * - produceVisual()：摘下来的那一颗用 UI-ASSET-003 的收成小图；表外作物退回 cropArt 的中性图，和地里显示的一致。
 */
const ART = "/ui-assets/UI-ASSET-006/v1";

export const KNOWN_CROPS = ["star_tomato", "sun_pea", "sea_salt_pea", "moon_radish", "sakura_radish"] as const;
export type KnownCrop = (typeof KNOWN_CROPS)[number];
export type CropStage = "growing" | "ripe";

export function isKnownCrop(cropKey: string | null | undefined): cropKey is KnownCrop {
  return typeof cropKey === "string" && (KNOWN_CROPS as readonly string[]).includes(cropKey);
}

/**
 * 一张作物图怎么“种”进地里（数值都从 v1 的透明通道逐行量出，图 512×512）：
 * - width：作物图宽占土块图宽的百分比（地块约 150px 宽时作物约 100–110px，素材按这个尺寸设计）；
 * - anchorX / anchorY：作物与地面的交点在图里的位置（0–1），对准垄沟里的种植点。
 *   番茄、豌豆是茎基，接近图底边中点（番茄生长中底下外露的小根算在土里）；
 *   萝卜成熟是球根最宽处——下半个球根和细根在土里，由前景土层挡住；萝卜生长中是肩部最宽处；
 * - ring：入土处的半宽（占作物图宽）。土面和它相交是一圈，俯视下成一个扁椭圆，前半弧比入土线低——
 *   成熟萝卜在入土线（球根最宽处）以下还能露出前面那一弯，像坐在土窝里，而不是被一刀平切；
 *   茎和生长中萝卜的肩只有很窄一圈，等于平切（萝卜肩下沿是画出来的圆边，要整条埋掉）。
 * - top / left / right：可见内容的包围盒，给成熟光晕和点按范围用。
 * root 标出根茎作物（球根有一截在土里）。
 */
export interface CropArt {
  /** 已知作物的 key；表外作物一律 "unknown"（不把原始代码带进界面）。 */
  key: KnownCrop | "unknown";
  src: string;
  width: number;
  anchorX: number;
  anchorY: number;
  ring: number;
  top: number;
  left: number;
  right: number;
  root: boolean;
}

type Geometry = Omit<CropArt, "key" | "src">;

const GEOMETRY: Record<`${CropStage}:${KnownCrop}`, Geometry> = {
  // 茎基 x≈256、y≈488，往下是外露小根（y 490–505），埋进土里
  "growing:star_tomato": { width: 70, anchorX: 0.501, anchorY: 0.953, ring: 0.017, top: 0.113, left: 0.082, right: 0.916, root: false },
  // 茎基 x 246–272、y≈500；右下两片叶尖垂到图底，一起入土
  "ripe:star_tomato": { width: 74, anchorX: 0.506, anchorY: 0.977, ring: 0.025, top: 0.174, left: 0.082, right: 0.916, root: false },
  // 茎在图中线偏左（x 220–233）
  "growing:sun_pea": { width: 66, anchorX: 0.442, anchorY: 0.977, ring: 0.013, top: 0.084, left: 0.197, right: 0.799, root: false },
  "ripe:sun_pea": { width: 72, anchorX: 0.511, anchorY: 0.977, ring: 0.015, top: 0.109, left: 0.082, right: 0.914, root: false },
  "growing:sea_salt_pea": { width: 66, anchorX: 0.504, anchorY: 0.977, ring: 0.012, top: 0.084, left: 0.119, right: 0.879, root: false },
  "ripe:sea_salt_pea": { width: 72, anchorX: 0.478, anchorY: 0.977, ring: 0.011, top: 0.102, left: 0.084, right: 0.916, root: false },
  // 肩部 y 460–508，最宽在 y≈499（x 169–314）；往下的圆边埋进土里（入土圈取亚像素，等于平切，圆边一点不露）
  "growing:moon_radish": { width: 70, anchorX: 0.472, anchorY: 0.975, ring: 0.004, top: 0.354, left: 0.084, right: 0.916, root: true },
  // 球根 y≈248–452，最宽 y≈344–352（x 126–357，半宽 115）；细根 y 452–510
  "ripe:moon_radish": { width: 64, anchorX: 0.472, anchorY: 0.688, ring: 0.225, top: 0.086, left: 0.186, right: 0.811, root: true },
  "growing:sakura_radish": { width: 70, anchorX: 0.476, anchorY: 0.975, ring: 0.004, top: 0.365, left: 0.084, right: 0.916, root: true },
  // 球根 y≈240–445，最宽 y≈336–346（x 127–344，半宽 108）
  "ripe:sakura_radish": { width: 64, anchorX: 0.46, anchorY: 0.676, ring: 0.212, top: 0.084, left: 0.211, right: 0.787, root: true },
};

/**
 * 表外作物：用月光萝卜“生长中”那丛叶子当中性的生长中图，入土点提到肩部上沿（y≈461），
 * 只露叶子、不露有颜色的肩，不冒充任何一种作物；成熟也用它（光晕照常由代码加）。
 */
const NEUTRAL: CropArt = {
  key: "unknown",
  src: `${ART}/crop-growing-moon_radish.webp`,
  width: 66,
  anchorX: 0.472,
  anchorY: 0.9,
  ring: 0.004,
  top: 0.354,
  left: 0.084,
  right: 0.916,
  root: false,
};

export function cropArt(cropKey: string | null, stage: CropStage): CropArt {
  if (!isKnownCrop(cropKey)) return NEUTRAL;
  return { key: cropKey, src: `${ART}/crop-${stage}-${cropKey}.webp`, ...GEOMETRY[`${stage}:${cropKey}`] };
}

/** Visuals describe crop species only; growth and yield always come from the server. */
export function cropVisual(cropKey: string | null, stage: CropStage): string {
  return cropArt(cropKey, stage).src;
}

/** 收成小图（UI-ASSET-003 v1）：摘下来 / 收进篮子的那一颗。表外作物退回 cropArt 的中性图（和地里显示的一致）。 */
const PRODUCE = new Set(["star_tomato", "sun_pea", "sea_salt_pea", "moon_radish", "sakura_radish"]);
export function produceVisual(cropKey: string | null) {
  return cropKey && PRODUCE.has(cropKey) ? `/ui-assets/UI-ASSET-003/v1/produce-${cropKey}.webp` : cropArt(cropKey, "ripe").src;
}
