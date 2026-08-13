"""Doubao Ark 客户端：社媒情报检索与响应清洗。"""

from __future__ import annotations

from json import JSONDecodeError
import json
from typing import Any
from urllib import error, request

from ..config import Settings
from ..providers import JourneyCity
from ..schemas import SocialTravelFinding
from .draft import GuideResearchDraft


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
