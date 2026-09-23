/**
 * 寻味模块（R0：双模式页面、清淡/浓郁 fixture 推荐卡、详情/出处、旅途卡片入口）。
 * 筛选/排序算法、真实资料、现实反馈学习均未实现，待用户分配的寻味模块窗口完成。
 */
import { defineModule, slot } from "@/shared/modules/types";
import { FoodArrivalCard } from "./FoodArrivalCard";
import { FoodDiscoveryPage } from "./FoodDiscoveryPage";
import { RecommendationDetailPage } from "./RecommendationDetailPage";
import { createFixtureFoodService, createLiveFoodService } from "./service";

export default defineModule({
  id: "food_discovery",
  routes: [
    { path: "journey/food", element: <FoodDiscoveryPage /> },
    { path: "journey/food/:recommendationId", element: <RecommendationDetailPage /> },
  ],
  services: { food: { fixture: createFixtureFoodService, live: createLiveFoodService } },
  slots: [slot("journey.cards", "food_discovery.arrival", FoodArrivalCard, 10)],
});
