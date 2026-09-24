import type { CSSProperties, ReactNode, Ref } from "react";
import type { PlotStage } from "@/shared/contracts";
import { cropArt, type CropArt } from "./cropVisual";
import "./garden-bed.css";

/** 开垦土块：UI-ASSET-006 v1（r7k）三张，720×440 透明底、四边留 6% 透明边，没有木框。字节不改。 */
export type BedSoilKey = "a" | "b" | "c";

export interface BedSoil {
  src: string;
  /** 垄沟里的种植点（%，相对土块图 720×440）：作物与地面的交点对准这里。按图里的暗沟逐列量出。 */
  plant: { x: number; y: number };
}

export const BED_SOILS: Record<BedSoilKey, BedSoil> = {
  // 偏圆，四道横垄：种在第二道沟（x 360、y≈180），前面还留两道垄的土
  a: { src: "/ui-assets/UI-ASSET-006/v1/plot-tilled-a.webp", plant: { x: 50, y: 40.9 } },
  // 偏长偏扁，五道横垄：种在正中那道沟（x 360、y≈217）
  b: { src: "/ui-assets/UI-ASSET-006/v1/plot-tilled-b.webp", plant: { x: 50, y: 49.3 } },
  // 不规则，斜垄：种在穿过中部的那道斜沟上（x 400、y≈201）
  c: { src: "/ui-assets/UI-ASSET-006/v1/plot-tilled-c.webp", plant: { x: 55.6, y: 45.7 } },
};

/** 一块地在底图上的位置（都相对底图）：x = 土块图中心横向 %，base = 土块图底边纵向 %，w = 土块图宽度 %；soil = 用哪张土块。 */
export interface BedSlot {
  x: number;
  base: number;
  w: number;
  soil: BedSoilKey;
}

export interface GardenLayout {
  id: string;
  src: string;
  /** 底图宽 / 高。画布按这个比例铺满宽度，坑位百分比一直对得上底图。 */
  aspect: number;
  slots: BedSlot[];
  /** 门边状态泡泡的锚点（%，泡泡贴在锚点右侧、上下居中）。 */
  door: { x: number; y: number };
}

/**
 * UI-ASSET-003 v1 菜园场地（r7k，1080×1660，交付单 docs/coordination/ui-assets/deliveries/UI-ASSET-003-v1.md）。
 * 门约在 (260, 360)；平地 x 8–92%、y 40–86%；底部 86–100% 是可裁的安静草地。
 * 三块地两块在上、一块在下，三张土块轮流用（a 左上、b 右上、c 下）。土块图 720×440 比旧木框扁，
 * 按新比例重排：土块可见部分约占图宽 87%，上排宽 44%（390 宽时土约 150px）、下排近一点放大到 47%；
 * 按钮（整张土块图）面积不小于旧木框时。上排土面中心约在底图 54%、下排约 77%，中间留出木牌和草地
 * （下排的高个作物仍会长到上排木牌那一行，木牌压在作物上面照常可读）。
 */
export const GARDEN_FIELD: GardenLayout = {
  id: "field-v1",
  src: "/ui-assets/UI-ASSET-003/v1/garden-field.webp",
  aspect: 1080 / 1660,
  slots: [
    { x: 28, base: 63, w: 44, soil: "a" },
    { x: 72, base: 63, w: 44, soil: "b" },
    { x: 50, base: 86, w: 47, soil: "c" },
  ],
  door: { x: 33, y: 21 },
};

/** 地块外层的位置；土块图与种植点作为 CSS 变量传给里面的 GardenBed（garden-bed.css 读）。 */
export function slotStyle(slot: BedSlot): CSSProperties {
  const soil = BED_SOILS[slot.soil];
  return {
    left: `${slot.x - slot.w / 2}%`,
    bottom: `${100 - slot.base}%`,
    width: `${slot.w}%`,
    "--bed-soil": `url("${soil.src}")`,
    "--plant-x": String(soil.plant.x),
    "--plant-y": String(soil.plant.y),
  } as CSSProperties;
}

export function anchorStyle(point: { x: number; y: number }): CSSProperties {
  return { left: `${point.x}%`, top: `${point.y}%` };
}

/**
 * 整块场景：画布（底图 + 地 + 泡泡 + 飞行物）按底图比例铺满宽度、顶部对齐；矮屏只裁掉底部安静草地。
 * `hud` 放门牌、篮子这类钉在场景角上的东西（不随裁切丢失）。
 */
export function GardenScene({ layout, label, canvasRef, hud, children }: { layout: GardenLayout; label: string; canvasRef?: Ref<HTMLDivElement>; hud?: ReactNode; children: ReactNode }) {
  return (
    <section className="ps-garden-scene" aria-label={label}>
      <div className="ps-garden-scene__stage" data-layout={layout.id} style={{ "--scene-aspect": String(layout.aspect) } as CSSProperties}>
        <div ref={canvasRef} className="ps-garden-scene__canvas">
          <img className="ps-garden-scene__bg" src={layout.src} alt="" />
          {children}
        </div>
        {hud}
      </div>
    </section>
  );
}

/** 作物几何 → CSS 变量（garden-bed.css 按它们把作物的入土点对准种植点）。 */
function artVars(art: CropArt): CSSProperties {
  return {
    "--crop-w": String(art.width),
    "--crop-ax": String(art.anchorX),
    "--crop-ay": String(art.anchorY),
    "--crop-ring": String(art.ring),
    "--crop-top": String(art.top),
    "--crop-l": String(art.left),
    "--crop-r": String(art.right),
  } as CSSProperties;
}

/**
 * 场景里的一块地：开垦土块 + 种在地里的作物（只表达物种与阶段；数量、时间、能不能摘都来自服务端）。
 * 由下往上：土块 → 接地阴影 → 成熟光晕 → 作物 → 前景土层（同一张土块图只露种植线以下，盖住入土的那一截）
 * → 点按延伸（让露在土块上方的作物也能点）。空地与收获后只有土块。
 */
export function GardenBed({ cropKey, stage, planted = false }: { cropKey: string | null; stage: PlotStage; planted?: boolean }) {
  const ripe = stage === "ripe";
  const art = stage === "growing" || ripe ? cropArt(cropKey, ripe ? "ripe" : "growing") : null;
  return (
    <span
      className={`ps-garden-bed is-tilled is-${stage}${art ? " has-plant" : ""}${planted ? " is-just-planted" : ""}`}
      data-stage={stage}
      aria-hidden="true"
      style={art ? artVars(art) : undefined}
    >
      <span className="ps-garden-bed__soil" />
      {art ? (
        <>
          <span className="ps-garden-bed__shade" />
          {ripe ? <span className="ps-garden-bed__glow" /> : null}
          <img className={`ps-garden-bed__crop is-${art.key} is-${ripe ? "ripe" : "growing"}${art.root ? " is-root" : ""}`} src={art.src} alt="" />
          <span className="ps-garden-bed__front" />
          <span className="ps-garden-bed__reach" />
        </>
      ) : null}
    </span>
  );
}
