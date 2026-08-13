"""TravelGuideResearchEngine 证据 mixin：社媒线索转证据包、评分与质量门。"""

from __future__ import annotations

import re

from ..providers import JourneyCity
from ..schemas import (
    PlaceEvidencePacket,
    PlaceEvidenceScores,
    SocialTravelFinding,
    TravelGuideResearchProvider,
    TravelQuestType,
)

CHAIN_STORE_TOKENS = ("肯德基", "kfc", "麦当劳", "mcdonald", "汉堡王", "burger king", "必胜客", "pizza hut")
SUPPLY_STOP_TOKENS = ("便利店", "7-eleven", "7-11", "全家", "familymart", "罗森", "lawson", "超市")
XIAMEN_SIGNATURE_TOKENS = ("狐尾山", "山海步道", "八市", "开禾路", "沙坡尾", "大学路", "环岛路", "白城", "黄厝", "白鹭洲", "筼筜湖", "鼓浪屿", "南普陀", "植物园", "演武大桥")
LOCAL_FOOD_TOKENS = ("八市", "开禾路", "沙茶", "面线糊", "土笋冻", "姜母鸭", "花生汤", "烧肉粽", "海蛎煎", "小吃", "老街", "市场")
PHOTO_ANCHOR_TOKENS = ("海边", "日落", "灯光", "明信片", "拍照", "机位", "塔", "桥", "沙坡尾", "鼓浪屿", "白城", "环岛路", "演武")


class TravelGuideResearchEvidenceMixin:
    def _mock_findings(
        self,
        provider: TravelGuideResearchProvider,
        destination: str,
        quest_type: TravelQuestType,
        event_name: str | None,
        pet_name: str,
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
                f"保留小吃店、咖啡店、公园、便利店等生活化停留点，让{pet_name}像真的在当地生活。",
                "攻略要区分给主人看的旅行建议和宠物自己的自主选择。",
            ]
        return [
            f"{destination} 攻略先查公开网页、地图评价和交通信息，再生成适合{pet_name}停留的路线。",
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
