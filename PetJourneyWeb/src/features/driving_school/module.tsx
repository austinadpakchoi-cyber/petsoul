/**
 * 爪爪驾校模块（主人陪考，宠物拿证）：四科（科一规则小课堂、科二场地、科三小城路线、科四情境判断）、
 * 每科首次＋一次补考、两次不过冷却 7×24 小时、服务端复算、拿证与领证仪式，以及比赛现场的倒车入库体验版。
 * 规格：docs/contracts/DRIVING-SCHOOL-v1.md。正式成绩只由服务端的规则与复算决定。
 * 页面与演示数据按需加载（进入驾校才下载），主包里只有三个入口卡片。
 */
import { defineModule, slot } from "@/shared/modules/types";
import { LoadingState } from "@/shared/ui";
import { createFixtureDrivingService, createLiveDrivingService, fixtureStageFromUrl } from "./service";
import { CircleSchoolEntry, HomeSchoolCard, JourneySchoolHint } from "./slots";
import "./school.css";

/** 直接打开驾校页面时（页面代码还在下载），先显示加载占位。 */
function Loading() {
  return <LoadingState label="正在进入爪爪驾校…" />;
}

export default defineModule({
  id: "driving_school",
  routes: [
    { path: "school", HydrateFallback: Loading, lazy: async () => ({ Component: (await import("./pages/SchoolHomePage")).SchoolHomePage }) },
    { path: "school/subject/:subject", HydrateFallback: Loading, lazy: async () => ({ Component: (await import("./pages/SubjectPage")).SubjectPage }) },
    { path: "school/result/:sessionId", HydrateFallback: Loading, lazy: async () => ({ Component: (await import("./pages/ResultPage")).ResultPage }) },
  ],
  // 正式考试、领证仪式与体验版全屏进行，收起底部主导航。
  bareRoutes: [
    { path: "school/session/:sessionId", HydrateFallback: Loading, lazy: async () => ({ Component: (await import("./pages/SessionPage")).SessionPage }) },
    { path: "school/ceremony", HydrateFallback: Loading, lazy: async () => ({ Component: (await import("./pages/CeremonyPage")).CeremonyPage }) },
    { path: "school/try", HydrateFallback: Loading, lazy: async () => ({ Component: (await import("./pages/TryPage")).TryPage }) },
  ],
  slots: [
    slot("circle.places", "driving_school.entry", CircleSchoolEntry, 10),
    slot("home.panels", "driving_school.progress", HomeSchoolCard, 40),
    slot("journey.cards", "driving_school.hint", JourneySchoolHint, 40),
  ],
  services: {
    driving: { fixture: () => createFixtureDrivingService({ stage: fixtureStageFromUrl() }), live: createLiveDrivingService },
  },
});
