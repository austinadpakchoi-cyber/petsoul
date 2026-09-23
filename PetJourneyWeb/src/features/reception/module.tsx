/**
 * 接待模块（R0：接待员/对话插槽、可编辑《入住叮嘱》便笺、交给 TA / 只留这里 / 不保存、跳过/保存失败/冲突，
 * 两组 fixture：自己的宠物、领养伙伴）。真实保存、模型理解、删除传播待用户分配的接待模块窗口实现。
 * 路由：/onboarding/reception（?branch=own_pet|adopted，?mode=supplement 为通讯器/家里的补充入口）、/onboarding/notes。
 */
import { defineModule } from "@/shared/modules/types";
import { CareNotesPage } from "./CareNotesPage";
import { ReceptionPage } from "./ReceptionPage";
import { createFixtureReceptionService, createLiveReceptionService } from "./service";

export default defineModule({
  id: "reception",
  bareRoutes: [
    { path: "onboarding/reception", element: <ReceptionPage /> },
    { path: "onboarding/notes", element: <CareNotesPage /> },
  ],
  services: { reception: { fixture: createFixtureReceptionService, live: createLiveReceptionService } },
});
