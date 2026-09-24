/**
 * 带状态表情的宠物头像（任何宠物、任何页面都能复用：地图标记、主状态面板、通讯器头部、别人家的宠物……）。
 * 表情只由结构化的 `mood` 决定（来自世界状态的 activity.pose），不从文字里猜：
 *   sleeping 头顶飘 z Z z、身体轻轻起伏；walking 一颠一颠的步态 + 脚下交替的小爪印；riding 身后速度线；
 *   eating 小口啄食；sunbathing 身后慢慢转的阳光；cafe 杯子冒热气；working 冒小星星；exploring 左右张望；idle 呼吸。
 * 头像本身永远是 TA 自己的样子（PetPortrait）。遵守 prefers-reduced-motion：只留静态的样子。
 */
import type { CSSProperties } from "react";
import { Icon } from "@/shared/ui";
import { PetPortrait } from "./PetPortrait";
import "./pet-mood.css";

export type PetMood = "idle" | "sleeping" | "eating" | "sunbathing" | "walking" | "riding" | "cafe" | "working" | "exploring" | "unknown";

/** 无障碍名称里的一句（界面上不直接显示）。 */
export const MOOD_LABEL: Record<PetMood, string> = {
  idle: "在歇着",
  sleeping: "在睡觉",
  eating: "在吃东西",
  sunbathing: "在晒太阳",
  walking: "在走路",
  riding: "在路上",
  cafe: "在店里坐着",
  working: "在干活",
  exploring: "在四处看看",
  unknown: "此刻的状态还没同步",
};

const PATHS = {
  moon: "M19 14.5A7 7 0 0 1 9.5 5a7 7 0 1 0 9.5 9.5z",
  bowl: "M4 11h16a8 8 0 0 1-16 0zM8 11c.3-1.8 1.9-3.5 4-3.5s3.7 1.7 4 3.5M9.5 19.5h5",
  sun: "M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 2.5v2M12 19.5v2M4.8 4.8l1.4 1.4M17.8 17.8l1.4 1.4M2.5 12h2M19.5 12h2M4.8 19.2l1.4-1.4M17.8 6.2l1.4-1.4",
  paw: "M8.5 13.5c-1.9 0-3.5 1.9-3.5 3.6 0 1.4 1.2 1.9 2.4 1.9 1.1 0 1.9-.5 3.1-.5s2 .5 3.1.5c1.2 0 2.4-.5 2.4-1.9 0-1.7-1.6-3.6-3.5-3.6zM5.5 11.5a1.6 2 0 1 0 0-.01zM9.3 8.6a1.7 2.1 0 1 0 0-.01zM14.7 8.6a1.7 2.1 0 1 0 0-.01zM18.5 11.5a1.6 2 0 1 0 0-.01z",
  bag: "M4 8h16v11H4zM9 8V6a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M4 13h16",
} as const;

function Glyph({ d, size }: { d: string; size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

export function MoodGlyph({ mood, size = 13 }: { mood: PetMood; size?: number }) {
  switch (mood) {
    case "sleeping":
      return <Glyph d={PATHS.moon} size={size} />;
    case "eating":
      return <Glyph d={PATHS.bowl} size={size} />;
    case "sunbathing":
      return <Glyph d={PATHS.sun} size={size} />;
    case "walking":
      return <Glyph d={PATHS.paw} size={size} />;
    case "riding":
      return <Icon name="car" size={size} />;
    case "cafe":
      return <Icon name="cup" size={size} />;
    case "working":
      return <Glyph d={PATHS.bag} size={size} />;
    case "exploring":
      return <Icon name="compass" size={size} />;
    case "idle":
      return <Icon name="home" size={size} />;
    default:
      return <Icon name="info" size={size} />;
  }
}

function MoodFx({ mood }: { mood: PetMood }) {
  switch (mood) {
    case "sleeping":
      return (
        <span className="ps-mood__zzz" aria-hidden="true">
          <i>z</i>
          <i>z</i>
          <i>Z</i>
        </span>
      );
    case "walking":
      return (
        <span className="ps-mood__steps" aria-hidden="true">
          <i />
          <i />
        </span>
      );
    case "riding":
      return (
        <span className="ps-mood__wind" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
      );
    case "cafe":
      return (
        <span className="ps-mood__steam" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
      );
    case "working":
    case "exploring":
      return (
        <span className="ps-mood__spark" aria-hidden="true">
          <i>✦</i>
          <i>✦</i>
          <i>✧</i>
        </span>
      );
    case "eating":
      return (
        <span className="ps-mood__crumbs" aria-hidden="true">
          <i />
          <i />
        </span>
      );
    default:
      return null;
  }
}

export function PetMoodAvatar({
  name,
  photoUrl,
  mood,
  size = 44,
  badge = true,
  compact = false,
}: {
  name: string;
  photoUrl?: string | null;
  mood: PetMood;
  size?: number;
  /** 右下角的小徽标（地图标记、面板用；列表里可以关掉）。 */
  badge?: boolean;
  /** 紧凑版：表情收在头像附近、不飘出所在卡片（主状态面板、列表里用）。 */
  compact?: boolean;
}) {
  return (
    <span className={`ps-mood is-${mood}${compact ? " is-compact" : ""}`} style={{ "--mood-size": `${size}px` } as CSSProperties} role="img" aria-label={`${name}，${MOOD_LABEL[mood]}`} data-mood={mood}>
      {mood === "sunbathing" ? <span className="ps-mood__rays" aria-hidden="true" /> : null}
      <span className="ps-mood__body" aria-hidden="true">
        <PetPortrait name={name} photoUrl={photoUrl} size={size} />
      </span>
      <MoodFx mood={mood} />
      {badge ? (
        <span className="ps-mood__badge" aria-hidden="true">
          <MoodGlyph mood={mood} size={Math.max(11, Math.round(size * 0.28))} />
        </span>
      ) : null}
    </span>
  );
}
