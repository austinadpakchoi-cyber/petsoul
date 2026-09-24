/**
 * 地图首页模块（批次 1 原型）：/map 全屏，不挂旧版四栏；页面内是新版三栏（地图 · 通讯器 · 回忆）预览。
 * 主布局切换（/ 进 /map、旧底栏换成三栏）要等批次 1 验收并由 I 交接 app 壳后再做，这里不改 app/。
 */
import { defineModule } from "@/shared/modules/types";
import { MapHomePage } from "./MapHomePage";

export default defineModule({
  id: "world_map",
  bareRoutes: [{ path: "map", element: <MapHomePage /> }],
});
