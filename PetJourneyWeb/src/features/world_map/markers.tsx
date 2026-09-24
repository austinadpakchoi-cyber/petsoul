/**
 * 地图上的标记（通过 portal 渲染进高德 Marker 的 DOM）：
 * - 宠物：白色贴纸圈 + 带状态表情的头像（PetMoodAvatar，按 activity.pose：睡觉冒 zzz、走路有步态和爪印……）；
 *   名字不常驻，点中后才在主状态面板里出现；头像永远是 TA 自己的样子（不用名字首字）；
 * - 家：小窝插画（UI-ASSET-004），只画“这一带”，不对应门牌；
 * - 目的地：小旗，名字点到才显示。
 * 阶段变化时由上层换 key，让出门 / 到达 / 回家的小动画重新播放一次。任何宠物（家里的、朋友的、公开的）都用同一套。
 */
import type { CSSProperties } from "react";
import { Icon } from "@/shared/ui";
import { PetMoodAvatar } from "@/features/pets/PetMoodAvatar";
import type { WorldPet } from "./model";

/**
 * 小窝标记素材：UI-ASSET-004 v1（r7k，192×192 RGBA WebP，字节冻结；交付单 docs/coordination/ui-assets/deliveries/UI-ASSET-004-v1.md）。
 * 交付单实测真透明包围盒 (20,24,173,169)：小房子底部中点在画布 x=96、y=169；画布底下还有 23px 透明安全边，不能拿画布底边当锚点。
 */
export const HOME_MARKER_ART = { src: "/ui-assets/UI-ASSET-004/v1/map-home-marker.webp", canvas: 192, baseX: 96, baseY: 169 } as const;
/** 画布在屏幕上的边长（px）：小房子本体约 35×33px；按钮就是可点区域，44px ≥ 40px。 */
export const HOME_MARKER_SIZE = 44;

/**
 * 高德 Marker 以内容盒的底边中点对准坐标（anchor: bottom-center）。把整张画布平移这么多，
 * 小房子的底部中点就正好落在坐标上（安全边由代码补偿，素材不裁）。
 */
export function homeMarkerShift(size: number = HOME_MARKER_SIZE): { x: number; y: number } {
  const { canvas, baseX, baseY } = HOME_MARKER_ART;
  const round = (value: number) => Math.round(value * 100) / 100 + 0;
  return { x: round(size * (0.5 - baseX / canvas)), y: round(size * (1 - baseY / canvas)) };
}

export function PetMarkerView({ pet, selected, onSelect, label }: { pet: WorldPet; selected: boolean; onSelect: () => void; label: string }) {
  const { kind, phase, pose } = pet.activity;
  return (
    <button
      type="button"
      className={`ps-wmap-pet is-${phase}${selected ? " is-selected" : ""}`}
      data-kind={kind}
      data-pose={pose}
      aria-label={label}
      aria-pressed={selected}
      onClick={(event) => {
        event.stopPropagation();
        onSelect();
      }}
    >
      <span className="ps-wmap-pet__ring">
        <PetMoodAvatar name={pet.name} photoUrl={pet.photoUrl} mood={pose} size={44} />
      </span>
      <span className="ps-wmap-pet__shadow" aria-hidden="true" />
    </button>
  );
}

export function HomeMarkerView({ petName, occupied, onOpen }: { petName: string; occupied: boolean; onOpen: () => void }) {
  const shift = homeMarkerShift();
  const style = { "--home-size": `${HOME_MARKER_SIZE}px`, "--home-dx": `${shift.x}px`, "--home-dy": `${shift.y}px` } as CSSProperties;
  return (
    <button
      type="button"
      className={`ps-wmap-home${occupied ? " is-occupied" : ""}`}
      style={style}
      aria-label={occupied ? `${petName}的小窝，TA 在家，进去看看` : `${petName}的小窝，TA 出门了，进去看看`}
      onClick={(event) => {
        event.stopPropagation();
        onOpen();
      }}
    >
      <img className="ps-wmap-home__art" src={HOME_MARKER_ART.src} alt="" width={HOME_MARKER_SIZE} height={HOME_MARKER_SIZE} decoding="async" draggable={false} />
    </button>
  );
}

export function PlaceMarkerView({ name, open, onToggle }: { name: string; open: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      className={`ps-wmap-place${open ? " is-open" : ""}`}
      aria-label={name}
      aria-expanded={open}
      onClick={(event) => {
        event.stopPropagation();
        onToggle();
      }}
    >
      <Icon name="pin" size={16} />
      {open ? <span className="ps-wmap-place__name">{name}</span> : null}
    </button>
  );
}
