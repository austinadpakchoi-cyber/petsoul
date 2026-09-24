import type { PetSpecies } from "@/shared/contracts";

/**
 * 访客星球的头图（2026-09-24 起替代原来的示意地图）。
 *
 * 为什么不是地图：公开接口（/public/world、/public/residents）里居民**没有任何坐标**，
 * 只显示后台事实、不拿假位置顶替，所以不在地图上画居民；空着的底图只会重演“半屏空地图”。
 * 原来按驿站名配的一张坐标表（STATION_ANCHORS）也一并删掉——那是前端自己写的坐标。
 * 等后端给出公开的驿站 / 居民位置（字段见交接），再换回地图首页同一组件的访客模式。
 *
 * 这张图纯装饰（aria-hidden）：一颗小星球、两座驿站小屋、几棵树；站在星球上的是**这些居民的物种插画**
 * （一位居民一只，最多 6 只，不写名字、不按位置排），只表示“这里住着猫、狗、兔子……”，不代表任何一位的样子。
 * 颜色全部来自主题令牌（planet.css），深色下自然变成夜里的星球；没有动画。
 */
const CX = 195;
const CY = 640;
const R = 500;

/** 星球表面在 x 处的高度（viewBox 坐标，只是画画用的几何，不是地理坐标）。 */
function rimY(x: number): number {
  return CY - Math.sqrt(R * R - (x - CX) * (x - CX));
}

const SLOTS: Array<{ x: number; size: number; flip: boolean }> = [
  { x: 64, size: 46, flip: false },
  { x: 326, size: 46, flip: true },
  { x: 116, size: 40, flip: true },
  { x: 274, size: 40, flip: false },
  { x: 30, size: 36, flip: false },
  { x: 360, size: 36, flip: true },
];

const STARS: Array<[number, number, number]> = [
  [34, 38, 1.4], [78, 18, 1.1], [132, 48, 1.6], [176, 22, 1.1], [228, 40, 1.3], [262, 14, 1.1], [300, 56, 1.2], [356, 30, 1.5], [206, 70, 1], [96, 76, 1.1],
];

function House({ x, scale = 1 }: { x: number; scale?: number }) {
  const y = rimY(x) + 2;
  return (
    <g transform={`translate(${x} ${y}) scale(${scale})`}>
      <rect className="ps-world-scene__wall" x={-15} y={-24} width={30} height={24} rx={2} />
      <path className="ps-world-scene__roof" d="M-19 -22 L0 -38 L19 -22 Z" />
      <rect className="ps-world-scene__window" x={-9} y={-17} width={7} height={7} rx={1.5} />
      <rect className="ps-world-scene__window" x={3} y={-17} width={7} height={11} rx={1.5} />
    </g>
  );
}

function Tree({ x, scale = 1 }: { x: number; scale?: number }) {
  const y = rimY(x) + 2;
  return (
    <g transform={`translate(${x} ${y}) scale(${scale})`}>
      <rect className="ps-world-scene__trunk" x={-1.5} y={-12} width={3} height={12} rx={1} />
      <circle className="ps-world-scene__leaves" cx={0} cy={-18} r={9} />
    </g>
  );
}

export function PlanetScene({ species }: { species: PetSpecies[] }) {
  const figures = species.slice(0, SLOTS.length).map((kind, index) => ({ kind, ...SLOTS[index] }));
  return (
    // 视口 390×250 与 390 宽手机上的头图等比（不裁两边）；更矮的屏只从天空那头裁，星球表面始终在。
    <svg className="ps-world-scene" viewBox="0 -30 390 250" preserveAspectRatio="xMidYMax slice" aria-hidden="true" focusable="false" data-testid="planet-scene">
      {STARS.map(([x, y, r]) => <circle key={`${x}-${y}`} className="ps-world-scene__star" cx={x} cy={y} r={r} />)}
      <circle className="ps-world-scene__sun" cx={322} cy={86} r={15} />
      <g className="ps-world-scene__cloud">
        <ellipse cx={82} cy={104} rx={26} ry={9} />
        <ellipse cx={100} cy={97} rx={16} ry={10} />
        <ellipse cx={246} cy={82} rx={20} ry={7} />
      </g>
      <circle className="ps-world-scene__halo" cx={CX} cy={CY} r={R + 10} />
      <circle className="ps-world-scene__land" cx={CX} cy={CY} r={R} />
      <Tree x={92} scale={0.9} />
      <Tree x={146} />
      <House x={176} />
      <House x={218} scale={0.86} />
      <Tree x={246} scale={0.85} />
      <Tree x={300} scale={0.95} />
      {figures.map((figure, index) => {
        const y = rimY(figure.x) + 4;
        return (
          <g key={index} transform={`translate(${figure.x} ${y}) scale(${figure.flip ? -1 : 1} 1)`} data-species={figure.kind}>
            <ellipse className="ps-world-scene__shadow" cx={0} cy={-1} rx={figure.size * 0.3} ry={3} />
            {/* 插画四边各留约 10% 透明边：往下挪一成，脚才踩在星球表面上 */}
            <image href={`/ui-assets/UI-ASSET-002/v1/species-${figure.kind}.webp`} x={-figure.size / 2} y={-figure.size * 0.9} width={figure.size} height={figure.size} />
          </g>
        );
      })}
    </svg>
  );
}
