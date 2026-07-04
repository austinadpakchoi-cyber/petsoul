from __future__ import annotations

from dataclasses import dataclass

from .config import Settings
from .schemas import TravelGuideResearchProvider, TravelQuestType


@dataclass(frozen=True, slots=True)
class GuideRolePolicy:
    key: str
    label: str
    responsibility: str
    forbidden: str

    def owner_visible_summary(self) -> str:
        return f"{self.label}：{self.responsibility}；不负责{self.forbidden}"


class GuideOrchestrationPolicy:
    """Single source of truth for how guide tools are allowed to collaborate."""

    provider_name = "guide-orchestration-policy"

    def roles(self) -> list[GuideRolePolicy]:
        return [
            GuideRolePolicy(
                key="map_fact_layer",
                label="高德 / Google Map",
                responsibility="确认真实地点、坐标、距离、路线和地点参考",
                forbidden="宠物情绪、路线价值判断和最终叙事",
            ),
            GuideRolePolicy(
                key="doubao_voice_layer",
                label="Doubao",
                responsibility="整理中文社媒线索，并把已确定路线改写成宠物口吻",
                forbidden="直接决定最终路线或编造 POI 事实",
            ),
            GuideRolePolicy(
                key="gpt_critic_layer",
                label="GPT",
                responsibility="做高阶规划、路线审计、异常修复和复杂多目标取舍",
                forbidden="替地图服务证明地点事实，或承担所有普通短文案",
            ),
            GuideRolePolicy(
                key="rules_gate",
                label="规则引擎",
                responsibility="执行硬性质量门槛，决定攻略能否标记为可照着走",
                forbidden="写大段情绪文案",
            ),
        ]

    def role_summaries(self) -> list[str]:
        return [role.owner_visible_summary() for role in self.roles()]

    def fact_provider_priority(self, *, destination: str, provider: TravelGuideResearchProvider) -> list[str]:
        if self._is_china_destination(destination):
            return ["amap", "doubao_social", "google_optional"]
        if provider == TravelGuideResearchProvider.hybrid:
            return ["google", "openai_web_search", "doubao_social_optional"]
        return ["google", "openai_web_search"]

    def pipeline_steps(
        self,
        *,
        destination: str,
        provider: TravelGuideResearchProvider,
        quest_type: TravelQuestType,
    ) -> list[str]:
        fact_layer = "高德召回国内 POI/路线" if self._is_china_destination(destination) else "Google Maps 召回海外 POI/路线"
        if quest_type == TravelQuestType.worldcup:
            fact_layer = "国内段用高德，海外赛场段用 Google Maps，长途交通单独查询或可信模拟"
        return [
            "WorldSnapshot：读取宠物状态、能量、时间、天气和当前城市",
            "CitySignatureProfile：确定城市代表性体验桶",
            fact_layer,
            "PlaceEvidencePacket：把地图事实和社媒线索标准化",
            "规则评分：过滤连锁核心点、过密餐饮、过长停留和绕路",
            "GPT Critic：只在新城市、世界杯或低质量路线时做深度审计",
            "规则层确认：未通过就降级为普通记录，不显示可照着走",
            "Doubao Voice：只改写宠物口吻，不增删地点或改路线",
        ]

    def quality_gate_rules(self, *, city: str | None = None) -> list[str]:
        rules = [
            "连锁快餐和便利店不能作为 core_anchor",
            "一天最多 1 个咖啡核心点，最多 1 个正餐核心点",
            "一条可参考路线至少需要 2 个城市代表性地点",
            "至少需要 1 个照片/明信片/记忆锚点",
            "核心点最多 6 个，停留时长必须符合地点类型",
            "路线严重绕路或地图事实未核验时，不能标记为可照着走",
        ]
        if city == "厦门":
            rules.append("厦门路线应覆盖山海、老城/本地味道、海边或水边中的至少两类")
        return rules

    def voice_provider(self, settings: Settings) -> str:
        if settings.doubao_api_key:
            return "doubao_pet_voice"
        return "local_pet_voice_template"

    def critic_provider(self, settings: Settings, *, quality_score: float | None = None) -> str:
        if settings.openai_api_key and (quality_score is None or quality_score < 0.82):
            return "gpt_guide_critic_available"
        if settings.openai_api_key:
            return "gpt_guide_critic_optional"
        return "rules_only_critic"

    def deep_critic_required(
        self,
        *,
        quest_type: TravelQuestType | None = None,
        quality_score: float | None = None,
        can_inform_replicable_route: bool = False,
    ) -> bool:
        if quest_type == TravelQuestType.worldcup:
            return True
        if quality_score is not None and quality_score < 0.68:
            return True
        return not can_inform_replicable_route

    def _is_china_destination(self, destination: str) -> bool:
        china_tokens = (
            "中国",
            "厦门",
            "北京",
            "上海",
            "广州",
            "深圳",
            "成都",
            "杭州",
            "重庆",
            "青岛",
            "南京",
            "苏州",
            "鼓浪屿",
        )
        return any(token in destination for token in china_tokens)


def build_guide_orchestration_policy() -> GuideOrchestrationPolicy:
    return GuideOrchestrationPolicy()
