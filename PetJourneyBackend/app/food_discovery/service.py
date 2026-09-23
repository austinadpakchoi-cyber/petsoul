"""FoodDiscovery 服务边界（R0 只定义接口；实现由用户分配的寻味模块窗口完成）。

实现要求（见 FOOD-DISCOVERY-ENGINE.md §5/§7）：
- 获准证据提取 → 确定性筛选/排序 → 有事实约束的宠物表达，三层分开；
- 先过硬条件（确认关闭、超硬预算、行程不可行、已知饮食冲突），未知单列 needs_verification；
- 对合格候选按计算结果**真正重排**后再截取；同分用 branch_id/dish_id 稳定排序；
- 不复用 ``street_rank.PetStreetRankEngine`` 的 rank_score 作为品质分（它含照片/距离/天气，
  且对 places[:10] 上游顺序算分后未重排）；
- 缓存键至少区分 资料版本 / 规则版本 / 偏好版本 / 模式；不混用不同用户；
- 推荐不产生到访：确认下一站后由 Journey 服务创建 visit_id；
- 表中数据迁移编号区间 0900–0999。
"""

from __future__ import annotations

from typing import Protocol

from ..schemas.web.food import (
    FoodFeedback,
    FoodPreference,
    FoodRecommendation,
    FoodRecommendationList,
    FoodRecommendationRequest,
    PreferenceSubject,
)


class FoodDiscoveryService(Protocol):
    def get_preference(self, user_id: str, pet_id: str, subject: PreferenceSubject) -> FoodPreference: ...

    def put_preference(
        self, user_id: str, pet_id: str, preference: FoodPreference, idempotency_key: str
    ) -> FoodPreference: ...

    def recommend(self, user_id: str, request: FoodRecommendationRequest) -> FoodRecommendationList: ...

    def get_recommendation(self, user_id: str, recommendation_id: str) -> FoodRecommendation: ...

    def submit_feedback(self, user_id: str, feedback: FoodFeedback, idempotency_key: str) -> FoodFeedback: ...
