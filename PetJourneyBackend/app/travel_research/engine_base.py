"""TravelGuideResearchEngine 基础 mixin：路由、brief、query 与能力判断。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..config import Settings
from ..guide_orchestrator import build_guide_orchestration_policy
from ..providers import JourneyCity
from ..schemas import (
    TravelGuideResearch,
    TravelGuideResearchProvider,
    TravelQuestType,
)
from .doubao_client import DoubaoArkClient
from .draft import GuideResearchDraft


class TravelGuideResearchEngineBaseMixin:
    def __init__(self, settings: Settings, doubao_client: DoubaoArkClient | None = None):
        self.settings = settings
        self.doubao_client = doubao_client or DoubaoArkClient(settings)
        self.orchestration_policy = build_guide_orchestration_policy()
    def research(
        self,
        *,
        owner_message: str,
        destination: str,
        quest_type: TravelQuestType,
        current_city: JourneyCity,
        event_name: str | None,
        now: datetime,
        pet_name: str,
    ) -> TravelGuideResearch:
        provider = self._provider_for(destination=destination, quest_type=quest_type)
        region = self._destination_region(destination=destination, provider=provider)
        query = self._query(
            owner_message=owner_message,
            destination=destination,
            quest_type=quest_type,
            current_city=current_city,
            event_name=event_name,
        )
        model_draft: GuideResearchDraft | None = None
        model_error: str | None = None
        if self._should_call_doubao(provider):
            try:
                model_draft = self.doubao_client.guide_research(
                    owner_message=owner_message,
                    destination=destination,
                    query=query,
                    current_city=current_city,
                    event_name=event_name,
                )
            except Exception as exc:
                model_error = self._redact_error(str(exc))

        missing_capabilities = self._missing_capabilities(provider)
        if model_error:
            missing_capabilities.append(f"豆包攻略研究暂时回退到本地规则：{model_error}")
        research_brief = (
            model_draft.research_brief
            if model_draft and model_draft.research_brief
            else self._research_brief(
                destination=destination,
                quest_type=quest_type,
                current_city=current_city,
                event_name=event_name,
            )
        )
        findings = (
            model_draft.findings
            if model_draft and model_draft.findings
            else self._mock_findings(provider, destination, quest_type, event_name, pet_name)
        )
        social_findings = (
            model_draft.social_findings
            if model_draft and model_draft.social_findings
            else self._mock_social_findings(provider, destination, quest_type, event_name)
        )
        if not social_findings:
            social_findings = self._social_findings_from_plain_text(findings)
        fact_provider_priority = self.orchestration_policy.fact_provider_priority(
            destination=destination,
            provider=provider,
        )
        evidence_packets = self._evidence_packets_from_findings(
            destination=destination,
            current_city=current_city,
            social_findings=social_findings,
            fact_provider_priority=fact_provider_priority,
        )
        quality_gate_notes = self._quality_gate_notes(
            provider=provider,
            evidence_packets=evidence_packets,
            model_notes=model_draft.quality_gate_notes if model_draft else [],
        )
        can_inform_replicable_route = self._can_inform_replicable_route(evidence_packets)

        return TravelGuideResearch(
            provider=provider,
            provider_name=self._provider_name(provider, model_draft=model_draft),
            destination_region=region,
            query=query,
            strategy=model_draft.strategy if model_draft and model_draft.strategy else self._strategy(provider, destination, pet_name),
            findings=findings,
            research_brief=research_brief,
            social_findings=social_findings,
            evidence_packets=evidence_packets,
            fact_provider_priority=fact_provider_priority,
            quality_gate_notes=quality_gate_notes,
            orchestration_roles=self.orchestration_policy.role_summaries(),
            pipeline_steps=self.orchestration_policy.pipeline_steps(
                destination=destination,
                provider=provider,
                quest_type=quest_type,
            ),
            quality_gate_rules=self.orchestration_policy.quality_gate_rules(city=destination),
            voice_writer=self.orchestration_policy.voice_provider(self.settings),
            deep_critic=self.orchestration_policy.critic_provider(self.settings),
            deep_critic_required=self.orchestration_policy.deep_critic_required(
                quest_type=quest_type,
                can_inform_replicable_route=can_inform_replicable_route,
            ),
            can_inform_replicable_route=can_inform_replicable_route,
            recommended_sources=model_draft.recommended_sources
            if model_draft and model_draft.recommended_sources
            else self._recommended_sources(provider),
            missing_capabilities=missing_capabilities,
            generated_at=now,
        )
    def _provider_for(self, *, destination: str, quest_type: TravelQuestType) -> TravelGuideResearchProvider:
        configured = self.settings.travel_guide_research_provider
        if configured == "doubao":
            return TravelGuideResearchProvider.doubao_social
        if configured == "openai_web_search":
            return TravelGuideResearchProvider.openai_web_search
        if configured == "hybrid":
            return TravelGuideResearchProvider.hybrid
        if quest_type == TravelQuestType.worldcup:
            return TravelGuideResearchProvider.openai_web_search
        if self._is_china_destination(destination):
            return TravelGuideResearchProvider.doubao_social
        return TravelGuideResearchProvider.openai_web_search
    def _destination_region(self, *, destination: str, provider: TravelGuideResearchProvider) -> str:
        if self._is_china_destination(destination):
            return "china"
        if provider == TravelGuideResearchProvider.hybrid:
            return "hybrid"
        return "global"
    def _research_brief(
        self,
        *,
        destination: str,
        quest_type: TravelQuestType,
        current_city: JourneyCity,
        event_name: str | None,
    ) -> dict[str, Any]:
        if quest_type == TravelQuestType.worldcup:
            return {
                "city": destination,
                "guide_goal": f"先确认 {event_name or '世界杯比赛'} 的城市交通、赛场缓冲点和照片机会。",
                "needed_experience_buckets": ["长途交通", "赛场周边", "安静缓冲", "球迷氛围", "赛后返回或续行"],
                "avoid": ["unverified_ticket_claims", "official_logo_in_photo", "overcrowded_only_points"],
                "current_city": current_city.name,
            }
        if self._is_china_destination(destination):
            return {
                "city": destination,
                "guide_goal": "用国内社媒线索补足真实游记、避坑、店铺体验和拍照位置，再交给 GPT 主脑筛选。",
                "needed_experience_buckets": ["城市代表性", "本地味道", "街区慢逛", "照片点", "安静休息"],
                "avoid": ["chain_fast_food_as_core", "too_many_cafes", "shopping_mall_as_main_route", "social_heat_as_fact"],
                "current_city": current_city.name,
            }
        return {
            "city": destination,
            "guide_goal": "先查公开资料和海外地图事实，再整理成宠物可以先替主人走一遍的路线。",
            "needed_experience_buckets": ["交通抵达", "城市地标", "本地生活", "照片点", "休息缓冲"],
            "avoid": ["unverified_transport_time", "overcrowded_only_points", "ticket_or_price_promise"],
            "current_city": current_city.name,
        }
    def _fact_provider_priority(self, *, destination: str, provider: TravelGuideResearchProvider) -> list[str]:
        # Backward-compatible helper for older tests/imports; policy owns the real matrix.
        return self.orchestration_policy.fact_provider_priority(destination=destination, provider=provider)
    def _legacy_fact_provider_priority(self, *, destination: str, provider: TravelGuideResearchProvider) -> list[str]:
        if self._is_china_destination(destination):
            return ["amap", "doubao_social", "google_optional"]
        if provider == TravelGuideResearchProvider.hybrid:
            return ["google", "openai_web_search", "doubao_social_optional"]
        return ["google", "openai_web_search"]
    def _provider_name(self, provider: TravelGuideResearchProvider, *, model_draft: GuideResearchDraft | None = None) -> str:
        if model_draft and provider == TravelGuideResearchProvider.doubao_social:
            return self.doubao_client.provider_name
        if model_draft and provider == TravelGuideResearchProvider.hybrid:
            return f"hybrid-{self.doubao_client.provider_name}"
        if provider == TravelGuideResearchProvider.doubao_social:
            return "doubao-social-guide-research-placeholder"
        if provider == TravelGuideResearchProvider.openai_web_search:
            return "openai-web-search-guide-research-placeholder"
        if provider == TravelGuideResearchProvider.hybrid:
            return "hybrid-social-and-web-guide-research-placeholder"
        return "mock-guide-research"
    def _query(
        self,
        *,
        owner_message: str,
        destination: str,
        quest_type: TravelQuestType,
        current_city: JourneyCity,
        event_name: str | None,
    ) -> str:
        if quest_type == TravelQuestType.worldcup:
            event = event_name or "World Cup match"
            return f"{event} near {destination} route from {current_city.name} pet-friendly local guide photo spots"
        return f"{destination} local travel guide hidden food cafe park realistic route from {current_city.name}: {owner_message}"
    def _strategy(self, provider: TravelGuideResearchProvider, destination: str, pet_name: str) -> str:
        if provider == TravelGuideResearchProvider.doubao_social:
            return f"用豆包/中国社媒补足 {destination} 的真实游记、避坑、店铺体验和短视频热点，再交给{pet_name}的大脑筛选。"
        if provider == TravelGuideResearchProvider.openai_web_search:
            return f"用 GPT Web Search 查 {destination} 的英文/海外资料、赛程周边、地点介绍和官方交通信息。"
        if provider == TravelGuideResearchProvider.hybrid:
            return f"同时查社媒体验和公开网页，把真实体验与路线可靠性分层汇总。"
        return "先用 mock 攻略占位，等待真实搜索 provider 接入。"
    def _missing_capabilities(self, provider: TravelGuideResearchProvider) -> list[str]:
        missing: list[str] = []
        if provider in {TravelGuideResearchProvider.openai_web_search, TravelGuideResearchProvider.hybrid}:
            if not self.settings.openai_api_key:
                missing.append("国外网页检索暂时使用 mock，等待 Web Search 真实调用接入")
        if provider in {TravelGuideResearchProvider.doubao_social, TravelGuideResearchProvider.hybrid}:
            if not self.settings.doubao_api_key:
                missing.append("国内社媒攻略暂时使用 mock，等待豆包真实调用接入")
        return missing
    def _should_call_doubao(self, provider: TravelGuideResearchProvider) -> bool:
        if provider not in {TravelGuideResearchProvider.doubao_social, TravelGuideResearchProvider.hybrid}:
            return False
        return self.doubao_client.configured
    def _redact_error(self, text: str) -> str:
        if self.settings.doubao_api_key:
            text = text.replace(self.settings.doubao_api_key, "ark-***")
        return text[:240]
    def _is_china_destination(self, destination: str) -> bool:
        china_markers = (
            "厦门",
            "北京",
            "上海",
            "广州",
            "深圳",
            "成都",
            "杭州",
            "重庆",
            "南京",
            "西安",
            "长沙",
            "武汉",
            "青岛",
            "大理",
            "云南",
            "中国",
            "内地",
            "鼓浪屿",
            "长城",
        )
        return any(marker in destination for marker in china_markers)
