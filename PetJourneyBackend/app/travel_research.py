from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from json import JSONDecodeError
import json
import re
from typing import Any
from urllib import error, request

from .config import Settings
from .guide_orchestrator import GuideOrchestrationPolicy, build_guide_orchestration_policy
from .providers import JourneyCity
from .schemas import (
    PlaceEvidencePacket,
    PlaceEvidenceScores,
    SocialTravelFinding,
    TravelGuideResearch,
    TravelGuideResearchProvider,
    TravelQuestType,
)


CHAIN_STORE_TOKENS = ("肯德基", "kfc", "麦当劳", "mcdonald", "汉堡王", "burger king", "必胜客", "pizza hut")
SUPPLY_STOP_TOKENS = ("便利店", "7-eleven", "7-11", "全家", "familymart", "罗森", "lawson", "超市")
XIAMEN_SIGNATURE_TOKENS = ("狐尾山", "山海步道", "八市", "开禾路", "沙坡尾", "大学路", "环岛路", "白城", "黄厝", "白鹭洲", "筼筜湖", "鼓浪屿", "南普陀", "植物园", "演武大桥")
LOCAL_FOOD_TOKENS = ("八市", "开禾路", "沙茶", "面线糊", "土笋冻", "姜母鸭", "花生汤", "烧肉粽", "海蛎煎", "小吃", "老街", "市场")
PHOTO_ANCHOR_TOKENS = ("海边", "日落", "灯光", "明信片", "拍照", "机位", "塔", "桥", "沙坡尾", "鼓浪屿", "白城", "环岛路", "演武")


@dataclass(frozen=True, slots=True)
class GuideResearchDraft:
    strategy: str
    findings: list[str]
    recommended_sources: list[str]
    raw_text: str
    research_brief: dict[str, Any] = field(default_factory=dict)
    social_findings: list[SocialTravelFinding] = field(default_factory=list)
    quality_gate_notes: list[str] = field(default_factory=list)


class DoubaoArkClient:
    provider_name = "doubao-ark-responses"

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.doubao_api_key)

    def guide_research(
        self,
        *,
        owner_message: str,
        destination: str,
        query: str,
        current_city: JourneyCity,
        event_name: str | None,
    ) -> GuideResearchDraft:
        if not self.settings.doubao_api_key:
            raise RuntimeError("Doubao Ark API key is not configured")

        payload = self.build_guide_research_payload(
            owner_message=owner_message,
            destination=destination,
            query=query,
            current_city=current_city,
            event_name=event_name,
        )
        response = self._post_json("/responses", payload)
        raw_text = self._extract_text(response)
        data = self._parse_json_candidate(raw_text)
        return GuideResearchDraft(
            strategy=self._clean_text(data.get("strategy")),
            findings=self._clean_list(data.get("findings"), limit=5),
            recommended_sources=self._clean_list(data.get("recommended_sources"), limit=6),
            raw_text=raw_text,
            research_brief=self._clean_research_brief(data.get("research_brief")),
            social_findings=self._clean_social_findings(data.get("social_findings")),
            quality_gate_notes=self._clean_list(data.get("quality_gate_notes"), limit=5),
        )

    def build_guide_research_payload(
        self,
        *,
        owner_message: str,
        destination: str,
        query: str,
        current_city: JourneyCity,
        event_name: str | None,
        image_urls: list[str] | None = None,
    ) -> dict[str, object]:
        content: list[dict[str, str]] = []
        for image_url in image_urls or []:
            content.append({"type": "input_image", "image_url": image_url})
        content.append(
            {
                "type": "input_text",
                "text": self._guide_prompt(
                    owner_message=owner_message,
                    destination=destination,
                    query=query,
                    current_city=current_city,
                    event_name=event_name,
                ),
            }
        )
        return {
            "model": self.settings.doubao_guide_model,
            "reasoning": {"effort": self.settings.doubao_reasoning_effort},
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": 700,
        }

    def build_vision_probe_payload(self, *, image_url: str, text: str) -> dict[str, object]:
        return {
            "model": self.settings.doubao_guide_model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_image", "image_url": image_url},
                        {"type": "input_text", "text": text},
                    ],
                }
            ],
        }

    def _guide_prompt(
        self,
        *,
        owner_message: str,
        destination: str,
        query: str,
        current_city: JourneyCity,
        event_name: str | None,
    ) -> str:
        event_line = f"\n- 特殊事件：{event_name}" if event_name else ""
        return f"""
你是 PetSoul 的国内旅行攻略研究员，只负责中文社媒与真实游客经验的情报采集，不写最终攻略，不替宠物决定路线。

产品设定：
- 宠物生活在平行世界，会先替主人走一遍，把值得来的地方、路线、照片线索和小故事寄回来。
- 攻略要像真实旅行经验，不像模板景点清单。
- 宠物可以进咖啡馆、饭馆、便利店、公园、网吧、花店等真实地点，像人一样在里面停留和体验。
- 用户可以参考攻略，但不能命令宠物喜欢或必须去某处。

任务：
- 当前城市：{current_city.name}
- 目的地：{destination}
- 主人的话：{owner_message}{event_line}
- 检索意图：{query}

请输出严格 JSON，不要 Markdown，不要代码块，内容要短。你输出的是“社媒情报”，不是最终攻略：
{{
  "research_brief": {{
    "city": "{destination}",
    "guide_goal": "一句话说明这次要替主人先看什么",
    "needed_experience_buckets": ["3 到 5 个体验桶，例如老城/本地味道/海边/照片点/安静休息"],
    "avoid": ["chain_fast_food_as_core", "too_many_cafes", "shopping_mall_as_main_route"]
  }},
  "strategy": "一句话说明怎么查、怎么先替主人走一遍",
  "findings": [
    "正好 3 条真实攻略线索：交通/路线、吃喝/店铺、照片点或避坑"
  ],
  "social_findings": [
    {{
      "claim": "一条可被 GPT 主脑参考的社媒经验判断",
      "evidence_type": "route_tip/photo_anchor/local_food/avoid_note/time_window",
      "mentioned_places": ["地点名"],
      "sentiment": "positive/mixed/negative",
      "usefulness": 0.0,
      "risk": "人多、排队、商业化或其他风险；没有就空字符串",
      "suggested_time": "morning/noon/afternoon/evening/unknown",
      "tags": ["老城", "海边", "本地小吃"],
      "evidence_level": "low/medium/high",
      "source_type": "social_travel_notes",
      "recency": "recent_or_unknown",
      "confidence": 0.0,
      "should_verify_with_map": true
    }}
  ],
  "quality_gate_notes": [
    "给规则引擎的提醒：哪些点不能直接作为核心路线，哪些信息必须用高德/Google核验"
  ],
  "recommended_sources": [
    "正好 4 个建议后续使用的信息来源名称"
  ]
}}

文字要求：
- 中文。
- 不要写“mock”“placeholder”“provider”“prompt”“内部字段”。
- 不要编造确定的票价、航班号、店铺营业状态。
- 可以说“适合先查/优先确认/后续补充”。
- 不能把社媒热度当作地点存在或营业事实；涉及坐标、距离、营业、路线必须标记 should_verify_with_map=true。
""".strip()

    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = f"{self.settings.doubao_base_url.rstrip('/')}{path}"
        req = request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.settings.doubao_api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=self.settings.doubao_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Doubao Ark request failed: {exc.code} {detail}") from exc

    def _extract_text(self, response: dict[str, object]) -> str:
        output_text = response.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        output = response.get("output")
        if isinstance(output, list):
            chunks: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for content_item in content:
                    if not isinstance(content_item, dict):
                        continue
                    text = content_item.get("text")
                    if isinstance(text, str) and text.strip():
                        chunks.append(text.strip())
            if chunks:
                return "\n".join(chunks)

        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        return content.strip()

        raise RuntimeError("Doubao Ark response did not contain text")

    def _parse_json_candidate(self, raw_text: str) -> dict[str, object]:
        text = raw_text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        try:
            data = json.loads(text)
        except JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            data = json.loads(text[start : end + 1])
        if not isinstance(data, dict):
            raise RuntimeError("Doubao Ark research JSON must be an object")
        return data

    def _clean_text(self, value: object) -> str:
        if not isinstance(value, str):
            return ""
        return " ".join(value.strip().split())

    def _clean_list(self, value: object, *, limit: int) -> list[str]:
        if not isinstance(value, list):
            return []
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = self._clean_text(item)
            if not text or text in seen:
                continue
            seen.add(text)
            cleaned.append(text)
            if len(cleaned) >= limit:
                break
        return cleaned

    def _clean_research_brief(self, value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        brief: dict[str, Any] = {}
        for key in ("city", "guide_goal"):
            text = self._clean_text(value.get(key))
            if text:
                brief[key] = text
        for key in ("needed_experience_buckets", "avoid"):
            items = self._clean_list(value.get(key), limit=8)
            if items:
                brief[key] = items
        return brief

    def _clean_social_findings(self, value: object) -> list[SocialTravelFinding]:
        if not isinstance(value, list):
            return []
        findings: list[SocialTravelFinding] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, dict):
                continue
            claim = self._clean_text(item.get("claim"))
            if not claim or claim in seen:
                continue
            seen.add(claim)
            findings.append(
                SocialTravelFinding(
                    claim=claim,
                    evidence_type=self._clean_text(item.get("evidence_type")) or "route_tip",
                    mentioned_places=self._clean_list(item.get("mentioned_places"), limit=6),
                    sentiment=self._clean_text(item.get("sentiment")) or "mixed",
                    usefulness=self._bounded_float(item.get("usefulness"), default=0.62),
                    risk=self._clean_text(item.get("risk")) or None,
                    suggested_time=self._clean_text(item.get("suggested_time")) or None,
                    tags=self._clean_list(item.get("tags"), limit=8),
                    evidence_level=self._clean_text(item.get("evidence_level")) or "medium",
                    source_type=self._clean_text(item.get("source_type")) or "social_travel_notes",
                    recency=self._clean_text(item.get("recency")) or "recent_or_unknown",
                    confidence=self._bounded_float(item.get("confidence"), default=0.58),
                    should_verify_with_map=self._truthy(item.get("should_verify_with_map"), default=True),
                )
            )
            if len(findings) >= 8:
                break
        return findings

    def _bounded_float(self, value: object, *, default: float) -> float:
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            number = default
        return max(0.0, min(1.0, number))

    def _truthy(self, value: object, *, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False
        return default


class TravelGuideResearchEngine:
    provider_name = "travel-guide-research-router"

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
            else self._mock_findings(provider, destination, quest_type, event_name)
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
            strategy=model_draft.strategy if model_draft and model_draft.strategy else self._strategy(provider, destination),
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

    def _strategy(self, provider: TravelGuideResearchProvider, destination: str) -> str:
        if provider == TravelGuideResearchProvider.doubao_social:
            return f"用豆包/中国社媒补足 {destination} 的真实游记、避坑、店铺体验和短视频热点，再交给小福的大脑筛选。"
        if provider == TravelGuideResearchProvider.openai_web_search:
            return f"用 GPT Web Search 查 {destination} 的英文/海外资料、赛程周边、地点介绍和官方交通信息。"
        if provider == TravelGuideResearchProvider.hybrid:
            return f"同时查社媒体验和公开网页，把真实体验与路线可靠性分层汇总。"
        return "先用 mock 攻略占位，等待真实搜索 provider 接入。"

    def _mock_findings(
        self,
        provider: TravelGuideResearchProvider,
        destination: str,
        quest_type: TravelQuestType,
        event_name: str | None,
    ) -> list[str]:
        if quest_type == TravelQuestType.worldcup:
            return [
                f"{event_name or '世界杯比赛'} 前后应避免直接扎进人群，先找赛场附近安静停留点。",
                "照片任务要包含赛场外观、人群颜色、城市夜色和宠物状态，但避免官方 logo。",
                "长途交通需要独立查询航班/火车班次；地图 API 只负责落地后的本地路线。",
            ]
        if provider == TravelGuideResearchProvider.doubao_social:
            return [
                f"{destination} 攻略需要优先看近期本地社媒经验，而不是只看景点榜单。",
                "保留小吃店、咖啡店、公园、便利店等生活化停留点，让小福像真的在当地生活。",
                "攻略要区分给主人看的旅行建议和小福自己的自主选择。",
            ]
        return [
            f"{destination} 攻略先查公开网页、地图评价和交通信息，再生成适合小福停留的路线。",
            "国外目的地优先用 Google Places/Routes 补真实 POI、照片参考和本地移动时间。",
            "长途段只记录真实存在的交通方案和时间，不在产品内卖票。",
        ]

    def _mock_social_findings(
        self,
        provider: TravelGuideResearchProvider,
        destination: str,
        quest_type: TravelQuestType,
        event_name: str | None,
    ) -> list[SocialTravelFinding]:
        if quest_type == TravelQuestType.worldcup:
            match_text = event_name or "世界杯比赛"
            return [
                SocialTravelFinding(
                    claim=f"{match_text} 前后适合先找赛场外的安静缓冲点，再靠近人群和灯光。",
                    evidence_type="time_window",
                    mentioned_places=["赛场外广场", "球迷区"],
                    sentiment="mixed",
                    usefulness=0.78,
                    risk="人流密集，需要避开拥挤入口",
                    suggested_time="evening",
                    tags=["赛场", "缓冲", "照片点"],
                    confidence=0.62,
                ),
                SocialTravelFinding(
                    claim="赛场照片要记录城市、球迷颜色和宠物状态，但不能依赖官方 logo 或票务承诺。",
                    evidence_type="photo_anchor",
                    mentioned_places=["赛场外观"],
                    sentiment="positive",
                    usefulness=0.72,
                    risk="需要避免官方标识和公众人物",
                    suggested_time="evening",
                    tags=["照片", "球迷氛围"],
                    confidence=0.58,
                ),
            ]
        if provider == TravelGuideResearchProvider.doubao_social or self._is_china_destination(destination):
            if "厦门" in destination or "鼓浪屿" in destination:
                return [
                    SocialTravelFinding(
                        claim="厦门慢生活路线需要覆盖老城、本地味道、海边和傍晚水边，不能只停普通连锁店。",
                        evidence_type="route_tip",
                        mentioned_places=["八市", "沙坡尾", "环岛路", "白鹭洲"],
                        sentiment="positive",
                        usefulness=0.88,
                        risk="热门区域节假日人多",
                        suggested_time="full_day",
                        tags=["老城", "海边", "本地小吃", "傍晚"],
                        evidence_level="medium",
                        confidence=0.76,
                    ),
                    SocialTravelFinding(
                        claim="八市和开禾路更适合作为本地味道线索，早上去更像真实游客会写的攻略。",
                        evidence_type="local_food",
                        mentioned_places=["八市", "开禾路"],
                        sentiment="positive",
                        usefulness=0.84,
                        risk="人多、路窄，需要留出慢走时间",
                        suggested_time="morning",
                        tags=["本地小吃", "烟火气"],
                        evidence_level="medium",
                        confidence=0.74,
                    ),
                    SocialTravelFinding(
                        claim="沙坡尾、大学路和海边适合照片、明信片和慢逛，但要避开只为打卡的网红店。",
                        evidence_type="photo_anchor",
                        mentioned_places=["沙坡尾", "大学路", "白城", "环岛路"],
                        sentiment="positive",
                        usefulness=0.82,
                        risk="部分店铺商业化、排队久",
                        suggested_time="afternoon",
                        tags=["照片点", "街区", "海边"],
                        evidence_level="medium",
                        confidence=0.72,
                    ),
                ]
            return [
                SocialTravelFinding(
                    claim=f"{destination} 攻略要先找城市代表性地点，再安排一个真实生活化休息点。",
                    evidence_type="route_tip",
                    mentioned_places=[destination],
                    sentiment="mixed",
                    usefulness=0.68,
                    risk="需要地图核验真实距离和营业状态",
                    suggested_time="unknown",
                    tags=["城市代表性", "慢旅行"],
                    confidence=0.55,
                )
            ]
        return [
            SocialTravelFinding(
                claim=f"{destination} 需要优先用 Google/公开网页确认真实地点、交通和照片线索。",
                evidence_type="route_tip",
                mentioned_places=[destination],
                sentiment="mixed",
                usefulness=0.66,
                risk="海外地点需要确认营业、路线和当地交通",
                suggested_time="unknown",
                tags=["海外", "地图核验"],
                confidence=0.52,
            )
        ]

    def _social_findings_from_plain_text(self, findings: list[str]) -> list[SocialTravelFinding]:
        return [
            SocialTravelFinding(
                claim=finding,
                evidence_type="route_tip",
                mentioned_places=self._mentioned_places(finding),
                usefulness=0.55,
                confidence=0.5,
            )
            for finding in findings[:5]
            if finding.strip()
        ]

    def _evidence_packets_from_findings(
        self,
        *,
        destination: str,
        current_city: JourneyCity,
        social_findings: list[SocialTravelFinding],
        fact_provider_priority: list[str],
    ) -> list[PlaceEvidencePacket]:
        packets: list[PlaceEvidencePacket] = []
        seen: set[str] = set()
        for finding in social_findings:
            place_names = finding.mentioned_places or self._mentioned_places(finding.claim) or [destination]
            for place_name in place_names:
                name = " ".join(place_name.split())
                if not name:
                    continue
                key = self._canonical_place_id(destination if name != current_city.name else current_city.name, name)
                if key in seen:
                    continue
                seen.add(key)
                scores = self._evidence_scores(name=name, destination=destination, finding=finding)
                user_visible = not self._is_chain_or_supply(name) and finding.evidence_type != "avoid_note"
                packets.append(
                    PlaceEvidencePacket(
                        canonical_place_id=key,
                        name=name,
                        city=destination if name != current_city.name else current_city.name,
                        source_priority=fact_provider_priority,
                        provider_evidence={
                            "doubao_social": {
                                "claim": finding.claim,
                                "evidence_type": finding.evidence_type,
                                "sentiment": finding.sentiment,
                                "usefulness": finding.usefulness,
                                "risk": finding.risk,
                                "suggested_time": finding.suggested_time,
                                "tags": finding.tags,
                                "evidence_level": finding.evidence_level,
                                "confidence": finding.confidence,
                            },
                            "map_fact": {
                                "exists": None,
                                "coordinates": None,
                                "route_time": None,
                                "business_hours": None,
                                "required_provider_priority": fact_provider_priority,
                            },
                        },
                        derived_scores=scores,
                        eligible_roles=self._eligible_roles(name=name, finding=finding, scores=scores),
                        user_visible=user_visible,
                        needs_verification=True,
                        verification_status="social_only_needs_map_verification",
                        evidence_notes=self._evidence_notes(finding, fact_provider_priority=fact_provider_priority),
                    )
                )
                if len(packets) >= 12:
                    return packets
        return packets

    def _quality_gate_notes(
        self,
        *,
        provider: TravelGuideResearchProvider,
        evidence_packets: list[PlaceEvidencePacket],
        model_notes: list[str],
    ) -> list[str]:
        notes = [note for note in model_notes if note]
        if any(packet.needs_verification for packet in evidence_packets):
            notes.append("社媒线索只作为软证据，坐标、路线、营业和距离必须由高德或 Google 回填。")
        if any(packet.derived_scores.chain_store_penalty > 0.5 for packet in evidence_packets):
            notes.append("连锁快餐、便利店或补给点不能作为核心攻略点，只能作为隐藏补给或短暂停留。")
        if provider == TravelGuideResearchProvider.doubao_social:
            notes.append("国内目的地优先用高德确认地点事实，再让 GPT 主脑做路线和文案。")
        if provider == TravelGuideResearchProvider.openai_web_search:
            notes.append("海外目的地优先用 Google 确认地点事实，公开网页只补背景和官方信息。")
        return self._dedupe(notes)[:6]

    def _can_inform_replicable_route(self, evidence_packets: list[PlaceEvidencePacket]) -> bool:
        if not evidence_packets:
            return False
        return any(not packet.needs_verification for packet in evidence_packets) and not any(
            packet.derived_scores.chain_store_penalty > 0.7 and packet.user_visible for packet in evidence_packets
        )

    def _recommended_sources(self, provider: TravelGuideResearchProvider) -> list[str]:
        if provider == TravelGuideResearchProvider.doubao_social:
            return ["Doubao Search", "抖音公开内容", "小红书公开攻略", "高德 POI/榜单"]
        if provider == TravelGuideResearchProvider.openai_web_search:
            return ["OpenAI Web Search", "Google Places", "Google Routes", "official venue pages"]
        if provider == TravelGuideResearchProvider.hybrid:
            return ["OpenAI Web Search", "Doubao Search", "Google/高德地图", "social travel notes"]
        return ["mock local guide catalog"]

    def _evidence_scores(
        self,
        *,
        name: str,
        destination: str,
        finding: SocialTravelFinding,
    ) -> PlaceEvidenceScores:
        text = self._joined_text(name, destination, finding.claim, " ".join(finding.tags))
        chain_penalty = 0.92 if self._is_chain_or_supply(text) else 0.0
        crowd_penalty = 0.35 if self._contains_any(finding.risk or "", ("人多", "拥挤", "排队", "路窄")) else 0.08
        overhyped_penalty = 0.28 if self._contains_any(text, ("网红", "营销", "商业化", "打卡")) else 0.0
        city_signature = 0.85 if self._contains_any(text, XIAMEN_SIGNATURE_TOKENS) else 0.35
        if "厦门" not in destination and "鼓浪屿" not in destination:
            city_signature = 0.55 if finding.evidence_type in {"route_tip", "photo_anchor"} else 0.35
        local_food = 0.86 if self._contains_any(text, LOCAL_FOOD_TOKENS) or finding.evidence_type == "local_food" else 0.2
        photo = 0.82 if self._contains_any(text, PHOTO_ANCHOR_TOKENS) or finding.evidence_type == "photo_anchor" else 0.35
        pet_fit = max(0.2, min(0.88, 0.72 - crowd_penalty * 0.35 - chain_penalty * 0.25))
        confidence = max(0.1, min(0.95, finding.confidence * 0.75 + finding.usefulness * 0.25))
        return PlaceEvidenceScores(
            city_signature=round(city_signature, 2),
            local_food_value=round(local_food, 2),
            photo_potential=round(photo, 2),
            pet_fit=round(pet_fit, 2),
            crowd_penalty=round(crowd_penalty, 2),
            chain_store_penalty=round(chain_penalty, 2),
            overhyped_penalty=round(overhyped_penalty, 2),
            confidence=round(confidence, 2),
        )

    def _eligible_roles(
        self,
        *,
        name: str,
        finding: SocialTravelFinding,
        scores: PlaceEvidenceScores,
    ) -> list[str]:
        if self._is_chain_or_supply(name):
            return ["supply_stop"]
        if finding.evidence_type == "avoid_note":
            return ["avoid_note"]
        roles: list[str] = []
        if scores.city_signature >= 0.7:
            roles.append("core_anchor")
        if scores.local_food_value >= 0.7:
            roles.append("food_anchor")
        if scores.photo_potential >= 0.7:
            roles.append("photo_anchor")
        if finding.evidence_type in {"route_tip", "time_window"}:
            roles.append("memory_anchor")
        return self._dedupe(roles) or ["candidate_anchor"]

    def _evidence_notes(self, finding: SocialTravelFinding, *, fact_provider_priority: list[str]) -> list[str]:
        notes = ["这条线索来自社媒/游记语境，不能单独证明地点事实。"]
        if finding.risk:
            notes.append(f"风险：{finding.risk}")
        if finding.should_verify_with_map:
            notes.append(f"需要按 {' / '.join(fact_provider_priority[:2])} 核验坐标、路线、距离和营业。")
        return notes

    def _mentioned_places(self, text: str) -> list[str]:
        places: list[str] = []
        for token in XIAMEN_SIGNATURE_TOKENS:
            if token in text:
                places.append(token)
        if not places:
            # Keep only likely Chinese place-name chunks; this is a fallback, not factual extraction.
            for match in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9·（）()]{2,18}", text):
                if any(stop in match for stop in ("攻略", "需要", "适合", "真实", "路线", "用户", "宠物")):
                    continue
                places.append(match)
                if len(places) >= 3:
                    break
        return self._dedupe(places)[:6]

    def _canonical_place_id(self, city: str, name: str) -> str:
        raw = f"{city}-{name}".lower()
        slug = re.sub(r"[^0-9a-z\u4e00-\u9fa5]+", "-", raw).strip("-")
        return slug or "place-evidence"

    def _is_chain_or_supply(self, text: str) -> bool:
        lowered = text.lower()
        return any(token.lower() in lowered for token in CHAIN_STORE_TOKENS + SUPPLY_STOP_TOKENS)

    def _contains_any(self, text: str, tokens: tuple[str, ...]) -> bool:
        lowered = text.lower()
        return any(token.lower() in lowered for token in tokens)

    def _joined_text(self, *parts: str) -> str:
        return " ".join(part for part in parts if part)

    def _dedupe(self, items: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            text = " ".join(item.split())
            if not text or text in seen:
                continue
            seen.add(text)
            deduped.append(text)
        return deduped

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


def build_travel_guide_research_engine(settings: Settings) -> TravelGuideResearchEngine:
    return TravelGuideResearchEngine(settings)
