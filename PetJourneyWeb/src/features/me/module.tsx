/**
 * “我的”模块：/me 全屏，从地图右上角头像进入，左上角回地图，不挂任何底栏（新版信息架构，方案第 9 节）。
 * 入口指向现有页面：/households/manage、/pets/new（只对家庭管理员）、/me/dna（TA 的档案）、/onboarding/reception?mode=supplement、
 * /me/look（TA 的形象）、/me/reports（我的举报）、/settings。
 * /me/dna、/me/look 与 /me/reports 同样是全屏页，左上角回 /me。
 */
import { defineModule } from "@/shared/modules/types";
import { DnaPage } from "./DnaPage";
import { LookPage } from "./LookPage";
import { MePage } from "./MePage";
import { MyReportsPage } from "./MyReportsPage";

export default defineModule({
  id: "me",
  bareRoutes: [
    { path: "me", element: <MePage /> },
    { path: "me/dna", element: <DnaPage /> },
    { path: "me/look", element: <LookPage /> },
    { path: "me/reports", element: <MyReportsPage /> },
  ],
});
