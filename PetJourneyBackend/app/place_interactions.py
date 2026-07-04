from __future__ import annotations

from datetime import datetime
import hashlib
from math import cos, radians, sqrt
import re
import uuid

from .photo_mission_brain import PhotoMissionBrain, PhotoMissionContext, PhotoMissionDraft
from .photo_pipeline import PhotoPipeline
from .photo_prompt_builder import PetPhotoPromptBuilder
from .schemas import (
    PhotoMission,
    PhotoPerspective,
    PlaceInteraction,
    PlaceSignal,
    WorldActivity,
)
from .storage import PetRecord


class PlaceInteractionEngine:
    provider_name = "place-interaction-engine"
    _source_phrase_pattern = re.compile(
        r"[\s·。；;，,]*(?:地点来源|数据来源|来源|source|provider)\s*[:：]\s*[\w.+/\- ]+",
        re.IGNORECASE,
    )
    _provider_token_pattern = re.compile(
        r"\b(?:amap|google|mock|hybrid|openai|web|map|provider|service|engine|client|route|planner|mission)"
        r"(?:[-_][A-Za-z0-9]+)+\b",
        re.IGNORECASE,
    )

    def __init__(self, photo_mission_brain: PhotoMissionBrain | None = None, photo_pipeline: PhotoPipeline | None = None):
        self.photo_mission_brain = photo_mission_brain
        self.photo_prompt_builder = PetPhotoPromptBuilder()
        self.photo_pipeline = photo_pipeline or PhotoPipeline()

    def build_photo_mission(
        self,
        *,
        pet: PetRecord,
        activity: WorldActivity | None,
        places: list[PlaceSignal],
        weather: str,
        now: datetime,
        worldcup_event: bool = False,
    ) -> PhotoMission:
        place = self._select_place(activity=activity, places=places)
        if not place:
            place = self._fallback_place(activity)
        time_of_day = self._time_of_day(now)
        if self.photo_mission_brain is not None:
            draft = self.photo_mission_brain.draft(
                PhotoMissionContext(
                    pet=pet,
                    place=place,
                    activity=activity,
                    weather=weather,
                    now=now,
                    time_of_day=time_of_day,
                    worldcup_event=worldcup_event,
                )
            )
            if draft is not None:
                mission = self._mission_from_draft(
                    pet=pet,
                    place=place,
                    weather=weather,
                    time_of_day=time_of_day,
                    now=now,
                    draft=draft,
                )
                return self._enrich_mission(mission=mission, pet=pet)

        mission = self._rule_based_photo_mission(
            pet=pet,
            place=place,
            activity=activity,
            weather=weather,
            now=now,
            time_of_day=time_of_day,
            worldcup_event=worldcup_event,
        )
        return self._enrich_mission(mission=mission, pet=pet)

    def _enrich_mission(self, *, mission: PhotoMission, pet: PetRecord) -> PhotoMission:
        try:
            return self.photo_pipeline.enrich_mission(mission=mission, pet=pet)
        except Exception:
            return mission

    def _rule_based_photo_mission(
        self,
        *,
        pet: PetRecord,
        place: PlaceSignal,
        activity: WorldActivity | None,
        weather: str,
        now: datetime,
        time_of_day: str,
        worldcup_event: bool,
    ) -> PhotoMission:
        interaction = self._interaction_for_place(
            pet=pet,
            place=place,
            activity=activity,
            worldcup_event=worldcup_event,
        )
        perspective = self._perspective_for(place, worldcup_event)
        landmark_hints = self._landmark_hints(place, worldcup_event)
        local_detail_hints = self._local_detail_hints(place)
        crowd_hints = self._crowd_hints(place, worldcup_event)
        image_prompt = self._image_prompt(
            pet=pet,
            place=place,
            interaction=interaction,
            perspective=perspective,
            landmark_hints=landmark_hints,
            local_detail_hints=local_detail_hints,
            crowd_hints=crowd_hints,
            weather=weather,
            time_of_day=time_of_day,
        )
        return PhotoMission(
            id=self._stable_photo_id(pet=pet, place=place, now=now),
            pet_id=pet.pet_id,
            generated_at=now,
            provider=self.provider_name,
            city=place.city,
            place=place,
            interaction=interaction,
            camera_perspective=perspective,
            scene_anchor=self._scene_anchor(place, landmark_hints),
            landmark_hints=landmark_hints,
            local_detail_hints=local_detail_hints,
            crowd_hints=crowd_hints,
            weather=weather,
            time_of_day=time_of_day,
            image_prompt=image_prompt,
            postcard_text=self._postcard_text(pet, place, interaction, perspective),
            safety_notes=[
                "Preserve the user's pet identity from the reference photo when available.",
                "Do not use official sports logos, readable brand marks, or recognizable real players.",
                "This is an emotional companion simulation, not proof of a real spiritual event.",
                "Rule-based fallback used because the photo mission brain was unavailable.",
                self._prompt_quality_note(image_prompt, pet=pet, place=place),
            ],
        )

    def _mission_from_draft(
        self,
        *,
        pet: PetRecord,
        place: PlaceSignal,
        weather: str,
        time_of_day: str,
        now: datetime,
        draft: PhotoMissionDraft,
    ) -> PhotoMission:
        interaction = PlaceInteraction(
            id=self._stable_interaction_id(pet=pet, place=place, now=now),
            pet_id=pet.pet_id,
            place=place,
            interaction_type=self._clean_user_text(draft.interaction_type, fallback="parallel_world_stop"),
            title=self._clean_user_text(draft.title, fallback=f"在 {place.name} 停了一会儿"),
            detail=self._clean_user_text(
                draft.detail,
                fallback=f"{pet.name} 在 {place.name} 附近按自己的节奏停留了一会儿。",
            ),
            pet_action=self._clean_user_text(
                draft.pet_action,
                fallback=f"在 {place.name} 附近停下来认真看了看",
            ),
            emotional_tone=self._clean_user_text(draft.emotional_tone, fallback="温柔、克制、像寄回一小段生活"),
            dwell_minutes=draft.dwell_minutes,
            can_generate_photo=True,
            source=draft.provider,
        )
        image_prompt = self._ensure_image_prompt_contract(
            draft.image_prompt,
            pet=pet,
            place=place,
            interaction=interaction,
            perspective=PhotoPerspective.first_person_selfie,
            landmark_hints=draft.landmark_hints,
            local_detail_hints=draft.local_detail_hints,
            crowd_hints=draft.crowd_hints,
            weather=weather,
            time_of_day=time_of_day,
        )
        return PhotoMission(
            id=self._stable_photo_id(pet=pet, place=place, now=now),
            pet_id=pet.pet_id,
            generated_at=now,
            provider=draft.provider,
            city=place.city,
            place=place,
            interaction=interaction,
            camera_perspective=PhotoPerspective.first_person_selfie,
            scene_anchor=self._clean_user_text(draft.scene_anchor or self._scene_anchor(place, draft.landmark_hints)),
            landmark_hints=self._clean_user_list(draft.landmark_hints or [place.detail_hint]),
            local_detail_hints=self._clean_user_list(draft.local_detail_hints or [place.activity_hint]),
            crowd_hints=self._clean_user_list(draft.crowd_hints),
            weather=weather,
            time_of_day=time_of_day,
            image_prompt=image_prompt,
            postcard_text=self._clean_user_text(
                draft.postcard_text,
                fallback=f"我在 {place.name} 附近停了一会儿，把这一刻拍给你看。",
            ),
            safety_notes=self._safety_notes(draft.safety_notes, pet=pet, place=place, prompt=image_prompt),
        )

    def _ensure_image_prompt_contract(
        self,
        prompt: str,
        *,
        pet: PetRecord,
        place: PlaceSignal,
        interaction: PlaceInteraction,
        perspective: PhotoPerspective,
        landmark_hints: list[str],
        local_detail_hints: list[str],
        crowd_hints: list[str],
        weather: str,
        time_of_day: str,
    ) -> str:
        return self.photo_prompt_builder.build_prompt(
            pet=pet,
            place=place,
            interaction=interaction,
            perspective=perspective,
            weather=weather,
            time_of_day=time_of_day,
            landmark_hints=landmark_hints,
            local_detail_hints=local_detail_hints,
            crowd_hints=crowd_hints,
            base_prompt=prompt,
            has_pet_reference=bool(pet.photo_path),
            has_place_reference=bool(place.photo_url),
        )

    def _safety_notes(self, notes: list[str], *, pet: PetRecord, place: PlaceSignal, prompt: str) -> list[str]:
        required = [
            "Preserve the user's pet identity from the reference photo when available.",
            "Do not use official sports logos, readable brand marks, recognizable real athletes, or public figures.",
            "This is an emotional companion simulation, not proof of a real spiritual event.",
            "Model-generated photo mission; rule layer only validates safety and fallback constraints.",
            self._prompt_quality_note(prompt, pet=pet, place=place),
        ]
        seen: set[str] = set()
        merged: list[str] = []
        for note in [*notes, *required]:
            clean = note.strip()
            if not clean or clean.lower() in seen:
                continue
            seen.add(clean.lower())
            merged.append(clean)
        return merged

    def _prompt_quality_note(self, prompt: str, *, pet: PetRecord, place: PlaceSignal) -> str:
        roles = self.photo_prompt_builder.expected_reference_roles(
            has_pet_reference=bool(pet.photo_path),
            has_place_reference=bool(place.photo_url),
        )
        return self.photo_prompt_builder.safety_note_for_prompt(prompt, expected_roles=roles, place=place)

    def _select_place(self, activity: WorldActivity | None, places: list[PlaceSignal]) -> PlaceSignal | None:
        if not places:
            return None
        if activity and activity.place_name:
            by_name = next((place for place in places if place.name == activity.place_name), None)
            if by_name:
                return by_name
        if activity:
            return min(
                places,
                key=lambda place: self._rough_distance_meters(activity.lat, activity.lng, place.lat, place.lng),
            )
        return max(
            places,
            key=lambda place: (
                place.guide_score or 0,
                1 if place.photo_url else 0,
                place.rating or 0,
            ),
        )

    def _fallback_place(self, activity: WorldActivity | None) -> PlaceSignal:
        city = activity.city if activity else "平行世界"
        name = activity.place_name or city if activity else city
        lat = activity.lat if activity else 0.0
        lng = activity.lng if activity else 0.0
        return PlaceSignal(
            id=f"fallback-{uuid.uuid4().hex[:8]}",
            name=name,
            category=activity.kind if activity else "place",
            city=city,
            lat=lat,
            lng=lng,
            activity_hint=activity.detail if activity else "安静地停留了一会儿",
            detail_hint="由世界模拟当前位置生成的临时地点。",
            source=self.provider_name,
        )

    def _interaction_for_place(
        self,
        *,
        pet: PetRecord,
        place: PlaceSignal,
        activity: WorldActivity | None,
        worldcup_event: bool,
    ) -> PlaceInteraction:
        interaction_type = self._interaction_type(place, worldcup_event)
        pet_action = self._pet_action(pet, place, interaction_type, worldcup_event)
        title = activity.title if activity and activity.kind == "stop" else self._interaction_title(place, interaction_type)
        detail = (
            f"{pet.name} 正在 {place.name} 附近{pet_action}。"
            "这不是用户下达的命令，而是 TA 当前旅程里自然发生的一段生活。"
        )
        return PlaceInteraction(
            id=f"interaction-{uuid.uuid4().hex[:12]}",
            pet_id=pet.pet_id,
            place=place,
            interaction_type=interaction_type,
            title=title,
            detail=detail,
            pet_action=pet_action,
            emotional_tone=self._emotional_tone(place, worldcup_event),
            dwell_minutes=activity.dwell_minutes or 25 if activity else 25,
            can_generate_photo=True,
            source=self.provider_name,
        )

    def _stable_photo_id(self, *, pet: PetRecord, place: PlaceSignal, now: datetime) -> str:
        return self._stable_id("photo", pet.pet_id, place.id, place.name, now.strftime("%Y%m%d%H"))

    def _stable_interaction_id(self, *, pet: PetRecord, place: PlaceSignal, now: datetime) -> str:
        return self._stable_id("interaction", pet.pet_id, place.id, place.name, now.strftime("%Y%m%d%H"))

    def _stable_id(self, prefix: str, *parts: str) -> str:
        digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:14]
        return f"{prefix}-{digest}"

    def _clean_user_list(self, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = self._clean_user_text(value)
            if not text or text.lower() in seen:
                continue
            cleaned.append(text)
            seen.add(text.lower())
        return cleaned

    def _clean_user_text(self, text: str, fallback: str = "") -> str:
        clean = str(text or "").strip()
        clean = self._source_phrase_pattern.sub("", clean)
        clean = re.sub(r"这个地点来自[^。；;]*[。；;]?", "", clean)
        clean = re.sub(r"来自(?:高德|Google|google|AMap|amap)[^。；;]*[。；;]?", "", clean)
        clean = self._provider_token_pattern.sub("", clean)
        clean = re.sub(r"\s{2,}", " ", clean)
        clean = re.sub(r"\s+([。；;，,])", r"\1", clean)
        clean = clean.strip(" ·,，;；。")
        return clean or fallback

    def _interaction_type(self, place: PlaceSignal, worldcup_event: bool) -> str:
        text = f"{place.name} {place.category}".lower()
        if worldcup_event or "stadium" in text or "赛场" in text:
            return "watching_match_at_stadium"
        if "鼓浪屿" in text or "海" in text:
            return "seaside_memory_walk"
        if "长城" in text or "great wall" in text:
            return "landmark_visit"
        if place.category in {"cafe", "food"}:
            return "local_food_or_cafe_stop"
        if place.category in {"netcafe", "entertainment"}:
            return "indoor_screen_light_stop"
        if place.category in {"park", "sight"}:
            return "quiet_landmark_stop"
        if place.category in {"shop"}:
            return "local_life_observation"
        return "parallel_world_stop"

    def _pet_action(self, pet: PetRecord, place: PlaceSignal, interaction_type: str, worldcup_event: bool) -> str:
        if interaction_type == "watching_match_at_stadium":
            return "坐在赛场外较安静的一侧，捧着小饮料听远处的欢呼声，偶尔看一眼黑红金颜色的人群"
        if interaction_type == "seaside_memory_walk":
            return "沿着海风慢慢走，找了一块能看见海的位置坐下，把手机放低一点看风"
        if interaction_type == "landmark_visit":
            return "站在能看见地标轮廓的位置，回头看镜头，像是在认真确认自己真的到了这里"
        if interaction_type == "local_food_or_cafe_stop":
            order = self._signature_order(place)
            if place.category == "cafe":
                return f"进到店里找了一个能看见街景的位置，看了看菜单和店里的推荐，点了{order}，一边喝一边看人来人往"
            return f"走进店里在不挡路的位置坐下，看了看菜单和旁边桌上的食物，点了{order}，像当地旅行者一样慢慢吃完"
        if interaction_type == "indoor_screen_light_stop":
            return "坐到屏幕光旁边戴上耳机，认真看别人打一局游戏，偶尔用爪子碰一下键盘边缘"
        if interaction_type == "local_life_observation":
            return "走进店里绕了一小圈，挑了一个小小的补给品，又在收银台旁边安静等了一会儿"
        return f"按自己的节奏在 {place.name} 附近停留"

    def _interaction_title(self, place: PlaceSignal, interaction_type: str) -> str:
        titles = {
            "watching_match_at_stadium": f"在 {place.name} 外听见比赛声",
            "seaside_memory_walk": f"在 {place.name} 旁边走到海风里",
            "landmark_visit": f"在 {place.name} 留下一张自拍",
            "local_food_or_cafe_stop": f"在 {place.name} 里面慢慢坐了一会儿",
            "indoor_screen_light_stop": f"在 {place.name} 的屏幕光里待了一会儿",
            "local_life_observation": f"在 {place.name} 看城市生活",
        }
        return titles.get(interaction_type, f"在 {place.name} 停了一会儿")

    def _emotional_tone(self, place: PlaceSignal, worldcup_event: bool) -> str:
        if worldcup_event or place.category == "stadium":
            return "兴奋但不吵闹"
        if place.category in {"cafe", "food", "shop"}:
            return "好奇、温暖、有一点嘴馋"
        if place.category in {"park", "sight"}:
            return "安静、开阔、认真"
        if place.category == "netcafe":
            return "陪伴感、屏幕光、轻轻的冒险"
        return "温柔、克制、像寄回一小段生活"

    def _perspective_for(self, place: PlaceSignal, worldcup_event: bool) -> PhotoPerspective:
        return PhotoPerspective.first_person_selfie

    def _landmark_hints(self, place: PlaceSignal, worldcup_event: bool) -> list[str]:
        text = f"{place.city} {place.name} {place.category}".lower()
        if worldcup_event or "stadium" in text or "赛场" in text:
            return ["stadium exterior lights", "security barriers", "match-day crowd", "distant pitch glow"]
        if "鼓浪屿" in text:
            return ["鼓浪屿海岸线", "红瓦老别墅", "海面和轮渡方向", "日光岩远景或岛上石阶"]
        if "厦门" in text:
            return ["海风", "红瓦屋顶", "骑楼街巷", "远处海面"]
        if "长城" in text or "great wall" in text:
            return ["长城城墙垛口", "山脊线", "灰色石阶", "远处蜿蜒城墙"]
        if "京都" in text or "kyoto" in text:
            return ["木造街屋", "石板路", "低矮屋檐", "安静街角"]
        if "洛杉矶" in text or "los angeles" in text:
            return ["wide street light", "palm tree silhouettes", "stadium district atmosphere"]
        if "伦敦" in text or "london" in text:
            return ["brick facades", "soft cloudy light", "street corner"]
        return [place.detail_hint]

    def _local_detail_hints(self, place: PlaceSignal) -> list[str]:
        category = place.category
        if category == "netcafe":
            return ["screen glow", "keyboard", "headphones", "drink cup", "dark indoor ambience"]
        if category == "cafe":
            return ["signature coffee or seasonal drink", "menu board", "window table", "barista counter", "soft reflections"]
        if category == "food":
            return ["signature local dish", "menu on the table", "steam from food", "nearby diners", "warm restaurant light"]
        if category == "shop":
            return ["small bags", "shelf lights", "doorway", "local neighborhood texture"]
        if category in {"park", "sight"}:
            return ["stone path", "open air", "quiet visitors", "natural light"]
        if category == "stadium":
            return ["scarves", "supporters", "stadium entrance", "event lighting"]
        return [place.activity_hint]

    def _signature_order(self, place: PlaceSignal) -> str:
        text = " ".join(
            str(value or "")
            for value in (
                place.name,
                place.category,
                place.activity_hint,
                place.detail_hint,
                place.guide_reason,
                place.raw.get("type"),
                place.raw.get("tag"),
                place.raw.get("keytag"),
                place.raw.get("rectag"),
            )
        ).lower()
        if place.category == "cafe":
            if any(token in text for token in ("茶", "tea", "奶茶", "早茶", "茶餐厅", "点心")):
                return "一杯店里的招牌茶饮，旁边还放着一小碟点心"
            if any(token in text for token in ("甜品", "dessert", "蛋糕", "cake", "烘焙", "bakery", "面包")):
                return "一杯店里的特色咖啡，旁边配着一小块甜点"
            if any(token in text for token in ("手冲", "specialty", "精品")):
                return "一杯店里推荐的手冲咖啡"
            if any(token in text for token in ("拿铁", "latte")):
                return "一杯招牌拿铁"
            return "一杯店里的招牌咖啡或当季特调"

        if any(token in text for token in ("沙茶", "satay")):
            return "一份本地沙茶面"
        if any(token in text for token in ("汉堡", "burger", "肯德基", "kfc")):
            return "一份热乎的招牌汉堡套餐"
        if any(token in text for token in ("海鲜", "seafood")):
            return "一份有海风味道的招牌海鲜饭"
        if any(token in text for token in ("面", "noodle", "ramen", "拉面")):
            return "一碗店里热气腾腾的招牌面"
        if any(token in text for token in ("粥", "congee")):
            return "一碗店里常被点的热粥"
        if any(token in text for token in ("寿司", "sushi")):
            return "一份店里的招牌寿司"
        if any(token in text for token in ("小笼", "包子", "dumpling", "点心")):
            return "一份刚端上来的招牌点心"
        if any(token in text for token in ("小食", "snack", "street food", "市场", "market")):
            return "一份当地人会顺手买的招牌小吃"
        return "一份店里最有代表性的招牌餐食"

    def _crowd_hints(self, place: PlaceSignal, worldcup_event: bool) -> list[str]:
        if worldcup_event or place.category == "stadium":
            return [
                "generic Germany supporters in black-red-gold colors",
                "scarves and jerseys without official logos",
                "no recognizable real players",
                "faces not prominent",
            ]
        return []

    def _scene_anchor(self, place: PlaceSignal, landmark_hints: list[str]) -> str:
        return f"{place.city} · {place.name} · {landmark_hints[0] if landmark_hints else place.category}"

    def _postcard_text(
        self,
        pet: PetRecord,
        place: PlaceSignal,
        interaction: PlaceInteraction,
        perspective: PhotoPerspective,
    ) -> str:
        if perspective == PhotoPerspective.passerby_third_person:
            return (
                f"今天我在 {place.name} 停了一会儿。有人从旁边帮我按了一下手机，"
                f"所以你能看到我和这里在同一张照片里。{interaction.pet_action}。"
            )
        if perspective == PhotoPerspective.first_person_selfie:
            return (
                f"我把手机举得低低的，在 {place.name} 把这一刻留下来了。"
                f"这里的味道和声音都是真的：{interaction.pet_action}。"
            )
        return (
            f"手机自己记录了 {place.name} 的这一刻。"
            f"{pet.name} 没有被安排，只是在这里按自己的节奏停了一会儿。"
        )

    def _image_prompt(
        self,
        *,
        pet: PetRecord,
        place: PlaceSignal,
        interaction: PlaceInteraction,
        perspective: PhotoPerspective,
        landmark_hints: list[str],
        local_detail_hints: list[str],
        crowd_hints: list[str],
        weather: str,
        time_of_day: str,
    ) -> str:
        return self.photo_prompt_builder.build_prompt(
            pet=pet,
            place=place,
            interaction=interaction,
            perspective=perspective,
            weather=weather,
            time_of_day=time_of_day,
            landmark_hints=landmark_hints,
            local_detail_hints=local_detail_hints,
            crowd_hints=crowd_hints,
            has_pet_reference=bool(pet.photo_path),
            has_place_reference=bool(place.photo_url),
        )

    def _time_of_day(self, now: datetime) -> str:
        hour = now.astimezone().hour
        if hour < 6:
            return "late night"
        if hour < 11:
            return "morning"
        if hour < 14:
            return "noon"
        if hour < 18:
            return "afternoon"
        if hour < 21:
            return "evening"
        return "night"

    def _rough_distance_meters(self, origin_lat: float, origin_lng: float, lat: float, lng: float) -> int:
        dy = (lat - origin_lat) * 111_320
        dx = (lng - origin_lng) * 111_320 * cos(radians((lat + origin_lat) / 2))
        return int(sqrt(dx * dx + dy * dy))
