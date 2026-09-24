import type { HomeSnapshot, JourneyMapSnapshot, Visit } from "@/shared/contracts";

/**
 * 插槽名与各插槽传给贡献组件的 props（共享契约，由框架维护）。
 * 新增插槽 = 修改本文件 + 在宿主页面放置 <Slot>，属于共享入口变更，需在日志提出。
 */
export interface JourneyOverlayProps {
  snapshot: JourneyMapSnapshot;
  /** 服务器校准后的当前时间（毫秒）；只用于呈现插值，不结算。 */
  nowMs: number;
  /** 打开地图面板：kind 为 leg / media，写入 URL（?sheet=kind:id），支持深链接与返回键关闭。 */
  openSheet: (kind: "leg" | "media", id: string) => void;
}

export interface JourneySheetProps {
  snapshot: JourneyMapSnapshot;
  nowMs: number;
  /** 例如 "leg:leg-1"、"media:ms-1" 中冒号后的 id */
  targetId: string;
  kind: "leg" | "media";
  close: () => void;
}

export interface SlotPropsMap {
  /** 家园页面板区：农场、旅途状态等 */
  "home.panels": { snapshot: HomeSnapshot };
  /** 家园顶部欢迎区：入住叮嘱兑现（HomeWelcome） */
  "home.welcome": { snapshot: HomeSnapshot };
  /** 旅途地图叠加层：车辆标记、活动徽标（跟随地图投影） */
  "journey.map.overlay": JourneyOverlayProps;
  /** 旅途地图底部面板：班次卡、播放器 */
  "journey.sheet": JourneySheetProps;
  /** 旅途页常驻层（例如收起后的迷你播放条），面板开关不影响它 */
  "journey.dock": JourneyOverlayProps;
  /** 旅途页地图下方卡片区（到达后寻味入口等） */
  "journey.cards": JourneyOverlayProps;
  /** 店内页的附加区块（寻味“为什么选这里”等） */
  "venue.panels": { visit: Visit };
  /** 星球圈顶部“星球上的地方”（爪爪驾校等）：放在动态流之前的入口卡片 */
  "circle.places": Record<string, never>;
}

export type SlotName = keyof SlotPropsMap;
