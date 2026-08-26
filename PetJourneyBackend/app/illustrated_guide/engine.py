"""图文攻略引擎编排核心：构建流程、页面组装与内容选取（架构审计 P1-2 包化）。"""

from __future__ import annotations

from datetime import datetime

from ..config import Settings
from ..image_provider import ImageProvider
from ..illustrated_guide_styles import (
    STYLE_PACK_VERSION,
    IllustratedGuideStyle,
    select_illustrated_guide_style,
)
from ..schemas import (
    IllustratedGuide,
    IllustratedGuidePage,
    IllustratedGuideStatus,
    IllustratedGuideStop,
    JourneyPlan,
    PetAuthoredGuide,
)
from ..storage import PetRecord
from .media import IllustratedGuideMediaMixin
from .prompts import IllustratedGuidePromptMixin


class IllustratedGuideEngine(IllustratedGuidePromptMixin, IllustratedGuideMediaMixin):
    def _image_model_label(self) -> str:
        """返回当前生图 provider 实际使用的模型名（而非配置里的默认 image_model）。"""
        snapshot = self.image_provider.config_snapshot()
        value = snapshot.get("image_model")
        return str(value) if value else self.settings.image_model

    provider_name = "illustrated-guide-engine"
    def __init__(self, *, settings: Settings, image_provider: ImageProvider):
        self.settings = settings
        self.image_provider = image_provider
    def build(
        self,
        *,
        pet: PetRecord,
        plan: JourneyPlan,
        guide: PetAuthoredGuide | None = None,
        now: datetime,
        generate_image: bool = False,
        style_id: str | None = None,
        force_new_style: bool = False,
    ) -> IllustratedGuide:
        stops = self._stops(guide=guide, plan=plan)
        title = self._title(pet_name=pet.name, city=plan.city, guide=guide)
        theme = self._theme(guide=guide, plan=plan)
        pet_thought = self._pet_thought(guide=guide, plan=plan)
        base_guide_id = self._guide_id(pet_id=pet.pet_id, city=plan.city, day=now.date().isoformat())
        if not style_id and not force_new_style:
            style_id = self._read_active_style_id(pet_id=pet.pet_id, base_guide_id=base_guide_id)
        guide_id = base_guide_id
        source_itinerary_id = f"{pet.pet_id}:{plan.city}:{now.date().isoformat()}"
        style = select_illustrated_guide_style(
            seed=source_itinerary_id,
            city=plan.city,
            theme=theme,
            stops=stops,
            preferred_style_id=style_id,
            force_new_style=force_new_style,
        )
        guide_id = f"{guide_id}_{style.id}"
        pages = self._pages(
            pet_name=pet.name,
            city=plan.city,
            title=title,
            theme=theme,
            pet_thought=pet_thought,
            stops=stops,
            style=style,
        )
        pages = self._attach_cached_images(pet_id=pet.pet_id, guide_id=guide_id, pages=pages)
        prompt = pages[0].image_prompt if pages else self._prompt(
            pet_name=pet.name,
            city=plan.city,
            title=title,
            theme=theme,
            pet_thought=pet_thought,
            stops=stops,
            style=style,
        )
        first_ready_page = next((page for page in pages if page.image_url), None)
        all_pages_ready = bool(pages) and all(page.image_url for page in pages)
        result = IllustratedGuide(
            id=guide_id,
            pet_id=pet.pet_id,
            city=plan.city,
            date=now.date(),
            status=IllustratedGuideStatus.ready
            if all_pages_ready
            else IllustratedGuideStatus.generating
            if first_ready_page
            else IllustratedGuideStatus.prompt_ready,
            title=title,
            theme=theme,
            pet_name=pet.name,
            pet_thought=pet_thought,
            stops=stops,
            style_id=style.id,
            style_name=style.name_zh,
            style_pack_version=STYLE_PACK_VERSION,
            style_locked=not force_new_style,
            pages=pages,
            source_itinerary_id=source_itinerary_id,
            image_prompt=prompt,
            image_url=first_ready_page.image_url if first_ready_page else None,
            thumbnail_url=first_ready_page.thumbnail_url if first_ready_page else None,
            provider=self.provider_name,
            model=self._image_model_label(),
            created_at=now,
        )
        if not generate_image or all_pages_ready:
            return result
        generated_pages: list[IllustratedGuidePage] = []
        provider = self.provider_name
        model = self._image_model_label()
        root_image_url = result.image_url
        root_thumbnail_url = result.thumbnail_url
        root_prompt = prompt
        try:
            for page in pages:
                if page.image_url:
                    generated_pages.append(page)
                    continue
                image = self.image_provider.generate_image(page.image_prompt, size="1024x1536")
                media_path = self._save_image(
                    pet_id=pet.pet_id,
                    guide_id=guide_id,
                    page_index=page.index,
                    image_bytes=image.image_bytes,
                    mime_type=image.mime_type,
                )
                image_url = self._media_url(media_path)
                next_page = page.model_copy(
                    update={
                        "status": IllustratedGuideStatus.ready,
                        "image_url": image_url,
                        "thumbnail_url": image_url,
                        "image_prompt": image.revised_prompt or page.image_prompt,
                    }
                )
                generated_pages.append(next_page)
                provider = image.provider
                model = image.model
                if root_image_url is None:
                    root_image_url = image_url
                    root_thumbnail_url = image_url
                    root_prompt = image.revised_prompt or page.image_prompt

            all_generated = bool(generated_pages) and all(page.image_url for page in generated_pages)
            if root_image_url:
                self._write_active_style_id(pet_id=pet.pet_id, base_guide_id=base_guide_id, style_id=style.id)
            return result.model_copy(
                update={
                    "status": IllustratedGuideStatus.ready if all_generated else IllustratedGuideStatus.generating,
                    "image_url": root_image_url,
                    "thumbnail_url": root_thumbnail_url,
                    "pages": generated_pages,
                    "provider": provider,
                    "model": model,
                    "image_prompt": root_prompt,
                }
            )
        except Exception as exc:
            generated_page_ids = {page.index for page in generated_pages}
            partial_pages = generated_pages + [page for page in pages if page.index not in generated_page_ids]
            if root_image_url:
                self._write_active_style_id(pet_id=pet.pet_id, base_guide_id=base_guide_id, style_id=style.id)
                return result.model_copy(
                    update={
                        "status": IllustratedGuideStatus.generating,
                        "error_message": self._redact_error(str(exc)),
                        "image_url": root_image_url,
                        "thumbnail_url": root_thumbnail_url,
                        "pages": partial_pages,
                        "provider": provider,
                        "model": model,
                        "image_prompt": root_prompt,
                    }
                )
            if not style_id and not force_new_style:
                fallback = self.build(
                    pet=pet,
                    plan=plan,
                    guide=guide,
                    now=now,
                    generate_image=True,
                    force_new_style=True,
                )
                if fallback.image_url or fallback.status != IllustratedGuideStatus.failed:
                    return fallback
            return result.model_copy(
                update={
                    "status": IllustratedGuideStatus.failed,
                    "error_message": self._redact_error(str(exc)),
                }
            )
    def _stops(self, *, guide: PetAuthoredGuide | None, plan: JourneyPlan) -> list[IllustratedGuideStop]:
        source = []
        if guide:
            source = [
                stop
                for stop in guide.guide_stops
                if stop.is_user_visible and stop.is_core
            ] or guide.guide_stops
        stops: list[IllustratedGuideStop] = []
        for index, stop in enumerate(source[:5], start=1):
            stops.append(
                IllustratedGuideStop(
                    index=index,
                    time=stop.planned_time,
                    name=stop.name,
                    label=self._label(stop.category, stop.name),
                    short_note=self._short_text(stop.pet_reason or stop.owner_tip, limit=22),
                    category=stop.category,
                )
            )
        if stops:
            return stops
        for index, stop in enumerate(plan.stops[:5], start=1):
            stops.append(
                IllustratedGuideStop(
                    index=index,
                    time=stop.planned_time,
                    name=stop.name,
                    label=self._label(stop.category, stop.name),
                    short_note=self._short_text(stop.detail, limit=22),
                    category=stop.category,
                )
            )
        seen_names = {stop.name for stop in stops}
        for place in plan.places:
            if len(stops) >= 5:
                break
            if place.name in seen_names:
                continue
            stops.append(
                IllustratedGuideStop(
                    index=len(stops) + 1,
                    time=None,
                    name=place.name,
                    label=self._label(place.category, place.name),
                    short_note=self._short_text(place.activity_hint or place.detail_hint, limit=22),
                    category=place.category,
                )
            )
        return stops
    def _pages(
        self,
        *,
        pet_name: str,
        city: str,
        title: str,
        theme: str,
        pet_thought: str,
        stops: list[IllustratedGuideStop],
        style: IllustratedGuideStyle,
    ) -> list[IllustratedGuidePage]:
        selected_stops = stops[:5]
        if not selected_stops:
            return []
        route_names = " → ".join(stop.name for stop in selected_stops)
        return [
            IllustratedGuidePage(
                index=1,
                title="手账封面",
                subtitle=f"{pet_name}在{city}慢慢生活的一天",
                intent="像线圈本第一页，介绍这座城市、今天的主题和几个关键停留。",
                page_type="cover",
                template_id="spiral_cover_overview",
                visual_style="线圈手账封面，水彩插画，贴纸和便签",
                composition="cover_overview",
                style_id=style.id,
                style_name=style.name_zh,
                image_prompt=self._prompt(
                    pet_name=pet_name,
                    city=city,
                    title=title,
                    theme=theme,
                    pet_thought=pet_thought,
                    stops=selected_stops,
                    style=style,
                    page_kind="cover_overview",
                    page_type="cover",
                    template_id="spiral_cover_overview",
                    extra=(
                        "Use a spiral binding on the left edge, a cute hand-drawn pet portrait near the top, "
                        "a taped travel snapshot of the city, a Day 1 note box, a horizontal five-stop route strip, "
                        "keyword bubbles, paw prints, flowers, washi tape, and one soft thought bubble."
                    ),
                ),
            ),
            IllustratedGuidePage(
                index=2,
                title="今日旅程图",
                subtitle=f"{city} · {len(selected_stops)} 站串联",
                intent="像手绘地图一样，让用户一眼看懂 TA 今天怎么慢慢走过这座城。",
                page_type="route_map",
                template_id="winding_route_map",
                visual_style="蜿蜒虚线路线，地点小插画，手写时间标签",
                composition="route_map",
                style_id=style.id,
                style_name=style.name_zh,
                image_prompt=self._prompt(
                    pet_name=pet_name,
                    city=city,
                    title="今日旅程图",
                    theme=theme,
                    pet_thought=pet_thought,
                    stops=selected_stops,
                    style=style,
                    page_kind="route_map",
                    page_type="route_map",
                    template_id="winding_route_map",
                    extra=(
                        f"Route line: {route_names}. Draw one winding dotted path from stop 1 to stop {len(selected_stops)}. "
                        "Each stop should have a small watercolor scene thumbnail, a round number marker, a short time badge, "
                        "and a tiny mood label. The path should feel hand-drawn, not like a precise transit map."
                    ),
                ),
            ),
            IllustratedGuidePage(
                index=3,
                title="时间线手账",
                subtitle="把慢慢走的一天摊开来看",
                intent="像日记时间轴，按时间记录 TA 在每一站停下来做了什么。",
                page_type="timeline",
                template_id="vertical_timeline_journal",
                visual_style="竖向时间线，小圆图，手写短句",
                composition="timeline",
                style_id=style.id,
                style_name=style.name_zh,
                image_prompt=self._prompt(
                    pet_name=pet_name,
                    city=city,
                    title="慢慢走的一天",
                    theme=theme,
                    pet_thought=pet_thought,
                    stops=selected_stops,
                    style=style,
                    page_kind="timeline",
                    page_type="timeline",
                    template_id="vertical_timeline_journal",
                    extra=(
                        "Use a vertical dotted timeline down the page. Put small circular watercolor vignettes on the left, "
                        "time badges and stop names on the right, and one short first-person note under each stop. "
                        "End with a gentle note box from the pet to the owner."
                    ),
                ),
            ),
        ]
    def _title(self, *, pet_name: str, city: str, guide: PetAuthoredGuide | None) -> str:
        title = (guide.title if guide else "").strip()
        if title and len(title) <= 22:
            return title
        return f"{pet_name}在{city}慢慢生活的一天"
    def _theme(self, *, guide: PetAuthoredGuide | None, plan: JourneyPlan) -> str:
        candidates = [
            guide.route_theme if guide else "",
            plan.transport_decision.reason,
            plan.summary,
        ]
        for candidate in candidates:
            text = self._short_text(candidate or "", limit=30)
            if text:
                return text
        return "不赶路，认真停下来，把这座城市慢慢看一遍。"
    def _pet_thought(self, *, guide: PetAuthoredGuide | None, plan: JourneyPlan) -> str:
        candidates = [
            guide.translation if guide else "",
            plan.next_postcard_hint or "",
            plan.summary,
        ]
        for candidate in candidates:
            text = self._short_text(candidate or "", limit=42)
            if text:
                return text
        return "我会先替你慢慢走一遍，把值得停下来的地方记下来。"
    def _label(self, category: str, name: str) -> str:
        text = f"{category} {name}"
        if any(token in text for token in ("山", "公园", "步道", "白鹭洲", "筼筜")):
            return "慢慢散步"
        if any(token in text for token in ("咖啡", "茶", "店")):
            return "坐一会儿"
        if any(token in text for token in ("八市", "市场", "小吃", "沙茶", "老街")):
            return "老城烟火"
        if any(token in text for token in ("海", "沙坡尾", "环岛", "白城", "黄厝")):
            return "海边的风"
        return "值得停下"
    def _short_text(self, text: str, *, limit: int) -> str:
        clean = " ".join(text.replace("\n", " ").split())
        clean = clean.replace("计划：", "").replace("可能", "").replace("系统", "")
        return clean[:limit].rstrip("，。；、 ")
    def _guide_id(self, *, pet_id: str, city: str, day: str) -> str:
        safe_city = "".join(ch for ch in city if ch.isalnum())[:24] or "city"
        return f"illustrated_{pet_id}_{safe_city}_{day}"
    def _redact_error(self, message: str) -> str:
        if self.settings.image_api_key:
            return message.replace(self.settings.image_api_key, "[REDACTED]")
        return message
