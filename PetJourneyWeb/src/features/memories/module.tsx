/**
 * 回忆模块（新版信息架构的第三栏）：/memories 全屏，不挂旧版四栏，页面底部是新版三栏预览（地图 · 通讯器 · 回忆）。
 * 入口指向：/timeline（生活片段，本模块的二级页）、/life、/life?tab=jobs、/collection、/photos、/guides。主布局切换后随三栏一起并回 app 壳。
 * /timeline 是全屏二级页（方案 2.2）：不挂底栏，自带 WorldGate（写法同 /memories）。
 */
import { defineModule } from "@/shared/modules/types";
import { MemoriesPage } from "./MemoriesPage";
import { TimelinePage } from "./TimelinePage";

export default defineModule({
  id: "memories",
  bareRoutes: [
    { path: "memories", element: <MemoriesPage /> },
    { path: "timeline", element: <TimelinePage /> },
  ],
});
