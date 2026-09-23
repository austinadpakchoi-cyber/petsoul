/**
 * 同行影音模块（R0：地图音符/电视入口 + 播放面板 + 迷你播放条 + fixture 会话）。
 * 服务端媒体会话/同步/授权作品清单待用户分配的同行影音模块窗口实现；与图片生成 MediaJob 无关。
 */
import { defineModule, slot } from "@/shared/modules/types";
import { ActivityBadgeLayer } from "./ActivityBadge";
import { MediaDock } from "./MediaDock";
import { MediaSheet } from "./MediaSheet";
import { createFixtureCompanionMediaService, createLiveCompanionMediaService } from "./service";

export default defineModule({
  id: "companion_media",
  services: {
    companionMedia: { fixture: createFixtureCompanionMediaService, live: createLiveCompanionMediaService },
  },
  slots: [
    slot("journey.map.overlay", "companion_media.badge", ActivityBadgeLayer, 20),
    slot("journey.sheet", "companion_media.sheet", MediaSheet, 20),
    slot("journey.dock", "companion_media.dock", MediaDock, 10),
  ],
});
