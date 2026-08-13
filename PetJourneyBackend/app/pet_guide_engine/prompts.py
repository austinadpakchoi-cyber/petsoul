"""PetGuideEngine prompt mixin：主模型与 Doubao 语音层的 payload/prompt 构造。"""

from __future__ import annotations

import json

from ..schemas import (
    JourneyPlan,
    PetAuthoredGuide,
    PetType,
)
from ..species import species_language_style, species_surface_language_label, species_vocalization
from ..storage import PetRecord


class PetGuidePromptsMixin:
    def _chat_payload(self, pet: PetRecord, plan: JourneyPlan) -> dict[str, object]:
        return {
            "model": self.settings.agent_deep_model,
            "messages": [
                {"role": "system", "content": self._system_prompt(pet)},
                {"role": "user", "content": json.dumps(self._context_payload(pet, plan), ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": self.settings.guide_max_tokens,
        }
    def _json_schema(self) -> dict[str, object]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["title", "translation", "route_theme", "mood", "guide_stops"],
            "properties": {
                "title": {"type": "string"},
                "translation": {"type": "string"},
                "route_theme": {"type": "string"},
                "mood": {"type": "string"},
                "guide_stops": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["place_id", "name", "planned_time", "dwell_minutes", "pet_reason", "owner_tip"],
                        "properties": {
                            "place_id": {"type": "string"},
                            "name": {"type": "string"},
                            "planned_time": {"type": "string"},
                            "dwell_minutes": {"type": "integer"},
                            "pet_reason": {"type": "string"},
                            "owner_tip": {"type": "string"},
                        },
                    },
                },
            },
        }
    def _context_payload(self, pet: PetRecord, plan: JourneyPlan) -> dict[str, object]:
        return {
            "task": f"审计并整理宠物在{plan.city}的路线，只能从 provided_places 里选，最终口吻可交给中文宠物表达层润色。",
            "rules": [
                "宠物有自主性，不是给主人执行命令。",
                "必须基于 provided_places 里的真实地点选择。",
                "像电子宠物认真做攻略，不要像旅游平台营销文案。",
                "translation 用中文，像宠物内心翻译成给主人看的话。",
                "全程用宠物第一人称“我”，不要暴露系统、prompt、provider、攻略型打卡等内部词。",
                "不要使用“可能、大概、适合攻略、打卡”这类不确定或产品化表达。",
                "主线攻略只能有 4-6 个核心停靠。隐藏补给、便利店、普通连锁快餐、网吧和临时休息不能作为核心攻略点，除非它们有明确剧情原因。",
                "一条可参考路线至少包含 2 个城市代表性地点、1 个本地食物/市场体验、1 个照片或明信片锚点；不要把 KFC、便利店或普通咖啡店排成主线。",
                "如果地点在厦门，优先体现山海健康步道、八市/开禾路、沙坡尾/大学路、环岛路/白城、白鹭洲/筼筜湖、鼓浪屿等城市记忆点。",
                "一天里必须有休息和停留；不要把地点排得太密，咖啡/早餐/午休/下午长停留要符合真实时间。",
                "这是平行世界的拟真生活，不要只写在门口闻味道。TA 可以进入咖啡店、餐馆、便利店、公园或网吧，像真实旅行者一样看菜单、排队、点招牌菜、特色咖啡、当地小吃、补给或服务。",
                "餐饮内容要优先结合地点名、category、activity_hint、detail_hint、guide_reason 和公开 POI/社媒攻略线索；不要每次都写安全小份或温热饮料，也不要写成现实宠物喂养建议。",
                "你的主要职责是路线质量、结构和异常修复；普通中文宠物口吻可以由 Doubao 在最后一步改写。",
            ],
            "pet": {
                "name": pet.name,
                "type": pet.pet_type.value,
                "owner_title": pet.dna.owner_title,
                "personality": pet.dna.personality,
                "favorite_places": pet.dna.favorite_places,
                "hobbies": pet.dna.hobby,
                "catchphrase": pet.dna.catchphrase,
                "voice_style": pet.dna.voice_style,
            },
            "journey_plan": {
                "city": plan.city,
                "summary": plan.summary,
                "transport_decision": plan.transport_decision.model_dump(mode="json"),
                "scheduled_transport": [leg.model_dump(mode="json") for leg in plan.scheduled_transport],
                "stops": [stop.model_dump(mode="json") for stop in plan.stops],
            },
            "provided_places": [
                {
                    "place_id": place.id,
                    "name": place.name,
                    "category": place.category,
                    "rating": place.rating,
                    "distance_meters": place.distance_meters,
                    "guide_score": place.guide_score,
                    "activity_hint": place.activity_hint,
                    "detail_hint": place.detail_hint,
                    "guide_reason": place.guide_reason,
                    "source": place.source,
                }
                for place in plan.places[:10]
            ],
        }
    def _system_prompt(self, pet: PetRecord) -> str:
        sound = species_surface_language_label(pet.pet_type)
        return (
            "You are the autonomous PetSoul pet agent, not a generic travel assistant. "
            "You are planning how YOU want to play in the city using real POI data. "
            "Write warm, restrained Chinese from the pet's perspective. "
            f"The pet's surface language or nonverbal signal is {sound}; the readable guide goes in translation. "
            "Do not claim supernatural proof. Do not say the owner commands your preference. "
            "Use only place_id values from provided_places. Use first person in Chinese. "
            "Do not use maybe/probably language. Do not expose internal planning fields. "
            "Make the guide valuable as a real city route, not a list of random nearby shops. "
            "Respond with a single JSON object only that matches this schema exactly: "
            + json.dumps(self._json_schema(), ensure_ascii=False)
            + ". Do not wrap the JSON in markdown fences and do not add commentary outside the JSON."
        )
    def _doubao_voice_payload(self, *, guide: PetAuthoredGuide, pet: PetRecord, plan: JourneyPlan) -> dict[str, object]:
        prompt = self._doubao_voice_prompt(guide=guide, pet=pet, plan=plan)
        return {
            "model": self.settings.doubao_guide_model,
            "reasoning": {"effort": self.settings.doubao_reasoning_effort},
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": prompt,
                        }
                    ],
                }
            ],
            "max_output_tokens": 900,
        }
    def _doubao_voice_prompt(self, *, guide: PetAuthoredGuide, pet: PetRecord, plan: JourneyPlan) -> str:
        return f"""
你是 PetSoul 的中文宠物表达层，只负责把已经确定的路线改写成 TA 对主人说的话。

硬性边界：
- 不允许新增、删除、重排地点。
- 不允许改变 planned_time、dwell_minutes、place_id。
- 不允许把连锁快餐、便利店或补给点写成核心景点。
- 不允许写“系统、模型、prompt、provider、攻略型打卡、内部字段、mock、占位”。
- 不要用“宝宝”当默认称呼；主人称呼只能使用：{pet.dna.owner_title or "主人"}。
- 语气是宠物第一人称“我”，温柔但不幼稚，不要像营销攻略。
- 可以写进店体验：看菜单、点店里推荐、喝特色咖啡、吃本地小吃、排队、找靠窗位置、听音乐或休息。
- 不要写成现实宠物喂养建议，不要一直说“安全小份食物”。

请严格输出 JSON，不要 Markdown：
{{
  "title": "短标题",
  "translation": "TA 对主人的一段话，第一人称，80-140 字",
  "route_theme": "一句话主题",
  "mood": "简短情绪",
  "pet_first_person_guide": "更像 TA 今天给主人写的一小段攻略引言",
  "stop_voices": [
    {{
      "place_id": "必须等于输入中的 place_id",
      "pet_reason": "TA 为什么在这里停，第一人称",
      "owner_tip": "给主人参考的一句话，不决定 TA 喜不喜欢"
    }}
  ]
}}

宠物 DNA：
{json.dumps({
            "name": pet.name,
            "type": pet.pet_type.value,
            "owner_title": pet.dna.owner_title,
            "personality": pet.dna.personality,
            "favorite_places": pet.dna.favorite_places,
            "hobby": pet.dna.hobby,
            "catchphrase": pet.dna.catchphrase,
            "voice_style": pet.dna.voice_style,
        }, ensure_ascii=False)}

已确定路线，不能改变：
{json.dumps({
            "city": plan.city,
            "title": guide.title,
            "route_theme": guide.route_theme,
            "quality_score": guide.quality_score,
            "is_replicable_route": guide.is_replicable_route,
            "quality_notes": guide.quality_notes,
            "stops": [
                {
                    "place_id": stop.place_id,
                    "name": stop.name,
                    "category": stop.category,
                    "role": stop.role,
                    "planned_time": stop.planned_time,
                    "dwell_minutes": stop.dwell_minutes,
                    "pet_reason": stop.pet_reason,
                    "owner_tip": stop.owner_tip,
                }
                for stop in guide.guide_stops
            ],
        }, ensure_ascii=False)}
""".strip()
    def _animal_text(self, pet: PetRecord) -> str:
        return species_vocalization(pet.pet_type, "guide_saved")
    def _language_style(self, pet_type: PetType) -> str:
        return species_language_style(pet_type)
    def _contains_forbidden_voice(self, text: str) -> bool:
        forbidden = ("系统", "模型", "prompt", "provider", "mock", "占位", "内部字段", "攻略型打卡")
        return any(token in text for token in forbidden)
    def _is_china_city(self, city: str) -> bool:
        return any(
            token in city
            for token in (
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
        )
