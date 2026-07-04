from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .config import Settings
from .image_provider import ImageProvider
from .illustrated_guide_styles import (
    STYLE_PACK_VERSION,
    IllustratedGuideStyle,
    get_illustrated_guide_style,
    select_illustrated_guide_style,
)
from .schemas import (
    IllustratedGuide,
    IllustratedGuidePage,
    IllustratedGuideStatus,
    IllustratedGuideStop,
    JourneyPlan,
    PetAuthoredGuide,
)
from .storage import PetRecord


class IllustratedGuideEngine:
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
            model=self.settings.image_model,
            created_at=now,
        )
        if not generate_image or all_pages_ready:
            return result
        generated_pages: list[IllustratedGuidePage] = []
        provider = self.provider_name
        model = self.settings.image_model
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

    def _prompt(
        self,
        *,
        pet_name: str,
        city: str,
        title: str,
        theme: str,
        pet_thought: str,
        stops: list[IllustratedGuideStop],
        style: IllustratedGuideStyle,
        page_kind: str = "route",
        page_type: str = "cover",
        template_id: str = "sketchbook_route",
        extra: str = "",
    ) -> str:
        stop_lines = "\n".join(
            f"{stop.index}. {stop.time or ''} {stop.name}｜{stop.label}".strip()
            for stop in stops[:5]
        )
        extra_direction = self._short_generation_direction(extra, page_type=page_type)
        return f"""
Create ONE finished PetSoul illustrated travel-guide page.
Make it a real hand-drawn image, not app UI, not a wireframe, not a placeholder.
Canvas: vertical 9:16, 1024x1536. Language: simplified Chinese, short hand-lettered text only.

Pet {pet_name} in {city}.
Title: {title}
Theme: {theme}
Pet note: {pet_thought}

Use exactly these stops:
{stop_lines}

Layout: {self._concise_page_layout(page_type=page_type, template_id=template_id)}
Style: {style.name_zh}. {style.prompt}
Direction: {extra_direction}

Warm travel sketchbook feeling: cream paper, watercolor mini-scenes, paw prints, washi tape, soft route marks, cute pet mascot.
No backend/debug text, coordinates, scores, QR codes, watermark, real map UI, navigation UI, or extra destinations.
""".strip()

    def _short_generation_direction(self, extra: str, *, page_type: str) -> str:
        if page_type == "route_map":
            return (
                "Draw one simple winding dotted route through markers 1-5. Use tiny watercolor scenes, "
                "short place names, small time tags, and paw-print route marks. Keep text sparse and readable."
            )
        if page_type == "timeline":
            return (
                "Draw a quiet vertical timeline from morning to evening. Each stop has one small sketch, "
                "time, place name, and one short first-person note."
            )
        if page_type == "cover":
            return (
                "Draw a notebook cover page with large title, pet portrait, taped city snapshot, five-stop strip, "
                "keyword doodles, and one soft thought bubble."
            )
        return self._short_text(extra, limit=180)

    def _concise_page_layout(self, *, page_type: str, template_id: str) -> str:
        if page_type == "cover":
            return (
                "cover page with large title, city intro card, five-stop overview strip, keyword doodles, "
                "small taped city snapshot, cute pet near the title, and one thought bubble near the bottom."
            )
        if page_type == "route_map":
            return (
                "hand-drawn route map page with one winding dotted path connecting markers 1 to 5, "
                "small watercolor scene beside each stop, short time badges, and a route theme note."
            )
        if page_type == "timeline":
            return (
                "vertical timeline journal page with morning-to-evening entries, small circular sketches, "
                "time badges, stop names, one short first-person note per stop, and a closing pet thought box."
            )
        return self._template_style_brief(template_id)

    def _base_prompt(self, *, pet_name: str, city: str, title: str, theme: str, pet_thought: str) -> str:
        return f"""
Create a multi-page illustrated travel guide image page for the PetSoul app.

The image is based on structured itinerary data.
Use only the provided city, title, theme, pet name, stop names, stop order, time labels, short labels, and pet thought.
Do not invent extra places, routes, attractions, landmarks, or text.

The guide should feel like a warm, emotionally gentle pet travel guide.
It is not a realistic map screenshot and not a commercial tourist advertisement.
Chinese text must be short, clear, and readable on a mobile screen.
Use a vertical mobile composition, 9:16 ratio, 1024x1536.

Required content:
- Pet name: {pet_name}
- City: {city}
- Title: {title}
- Theme: {theme}
- Pet thought: {pet_thought}
""".strip()

    def _page_type_prompt(self, *, page_type: str, template_id: str, page_kind: str) -> str:
        if page_type == "cover":
            return f"""
Page type: Cover / Overview Page.
template_id: {template_id}
page_kind: {page_kind}

Layout:
- Large warm Chinese title at the top.
- Small subtitle/theme below the title.
- A cute illustration of the pet mascot near the title.
- A short intro card about the city and today's journey.
- A compact five-stop overview section.
- A keyword section with 4 to 5 small icon labels.
- A pet thought bubble near the bottom.

The page should feel like the opening page of a travel notebook.
Do not put too much route detail on this page.
""".strip()
        if page_type == "route_map":
            return f"""
Page type: Illustrated Route Map Page.
template_id: {template_id}
page_kind: {page_kind}

Layout:
- Title at the top: 今日旅程图.
- Subtitle: Pet name + city + 慢慢走过的路线.
- Middle area: a hand-drawn route line connecting the stops.
- Use numbered markers 1 to 5.
- Each stop must show stop number, exact stop name, short label, time label, and a small matching illustration or icon.
- Add small paw prints along the route.
- Add one small note box for the route theme.

The page should be visually clear and easy to follow.
""".strip()
        if page_type == "timeline":
            return f"""
Page type: Timeline Journal Page.
template_id: {template_id}
page_kind: {page_kind}

Layout:
- Title at the top: 慢慢走的一天.
- Subtitle: Pet name + city + 时间线手账.
- Use a vertical timeline from morning to evening.
- Each stop must show time, exact place name, one short sentence, and a small hand-drawn icon or vignette.
- Add a bottom note box titled: pet name + 的小想法.

The page should feel like a personal travel diary.
Prioritize readable Chinese text and emotional clarity.
""".strip()
        return self._template_style_brief(template_id)

    def _route_data_block(self, stops: list[IllustratedGuideStop]) -> str:
        stop_lines = "\n".join(
            f"{stop.index}. {stop.time or '时间待定'} {stop.name}｜{stop.label}｜{stop.short_note}".strip()
            for stop in stops
        )
        return f"""
Structured route data:
Stops in this exact order:
{stop_lines}
""".strip()

    def _negative_rules(self) -> str:
        return """
Negative rules:
- Use simplified Chinese.
- Keep all Chinese labels short and readable. Prefer 2-8 Chinese characters per label.
- Do not add extra long paragraphs or dense blocks.
- Do not add provider names, API names, backend fields, coordinates, scores, or debug text.
- Do not include real map UI, real navigation UI, QR codes, brand logos, watermarks, or official government-like marks.
- Do not mention death, heaven, afterlife, religion, spiritual proof, or medical claims.
- Do not invent fictional extra destinations.
- Keep the visual warm, gentle, readable, and suitable for the PetSoul app.
""".strip()

    def _template_style_brief(self, template_id: str) -> str:
        if template_id == "spiral_cover_overview":
            return (
                "Visual reference: a cute spiral-bound travel scrapbook cover page. "
                "Large relaxed handwritten Chinese title, pet illustration at the upper left, taped city polaroid at the upper right, "
                "a soft intro card, a five-stop strip with small watercolor thumbnails, keyword circles, and a pet thought bubble near the bottom."
            )
        if template_id == "winding_route_map":
            return (
                "Visual reference: a hand-drawn route map page. "
                "A winding dotted path travels through numbered stops, with watercolor mini-scenes around the path, time badges, paw marks, "
                "tiny transport/food/park doodles, and one small route-theme note box."
            )
        if template_id == "vertical_timeline_journal":
            return (
                "Visual reference: a vertical day timeline in a notebook. "
                "Left-side spiral binding, small circular sketches aligned to a dotted timeline, time labels, stop names, "
                "short first-person notes, small icons, and a closing pet thought card."
            )
        return (
            "Visual reference: loose multi-page travel sketchbook, soft watercolor thumbnails, hand lettering, washi tape, "
            "small paw prints, and casual route notes."
        )

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

    def _attach_cached_images(
        self,
        *,
        pet_id: str,
        guide_id: str,
        pages: list[IllustratedGuidePage],
    ) -> list[IllustratedGuidePage]:
        cached_pages: list[IllustratedGuidePage] = []
        for page in pages:
            media_path = self._cached_page_media_path(pet_id=pet_id, guide_id=guide_id, page_index=page.index)
            if not media_path:
                cached_pages.append(page)
                continue
            media_url = self._media_url(media_path)
            cached_pages.append(
                page.model_copy(
                    update={
                        "status": IllustratedGuideStatus.ready,
                        "image_url": media_url,
                        "thumbnail_url": media_url,
                    }
                )
            )
        return cached_pages

    def _cached_page_media_path(self, *, pet_id: str, guide_id: str, page_index: int) -> str | None:
        target_dir = self.settings.upload_dir / "illustrated_guides" / pet_id
        if not target_dir.exists():
            return None
        matches = list(target_dir.glob(f"{guide_id}_page{page_index}_*"))
        if not matches:
            return None
        latest = max(matches, key=lambda path: path.stat().st_mtime)
        return str(latest.relative_to(self.settings.upload_dir))

    def _active_style_manifest_path(self, *, pet_id: str, base_guide_id: str) -> Path:
        return self.settings.upload_dir / "illustrated_guides" / pet_id / f"{base_guide_id}_active_style.txt"

    def _read_active_style_id(self, *, pet_id: str, base_guide_id: str) -> str | None:
        path = self._active_style_manifest_path(pet_id=pet_id, base_guide_id=base_guide_id)
        if not path.exists():
            return None
        style_id = path.read_text(encoding="utf-8").strip()
        if not get_illustrated_guide_style(style_id):
            return None
        guide_id = f"{base_guide_id}_{style_id}"
        if not self._cached_page_media_path(pet_id=pet_id, guide_id=guide_id, page_index=1):
            return None
        return style_id

    def _write_active_style_id(self, *, pet_id: str, base_guide_id: str, style_id: str) -> None:
        if not get_illustrated_guide_style(style_id):
            return
        target = self._active_style_manifest_path(pet_id=pet_id, base_guide_id=base_guide_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(style_id, encoding="utf-8")

    def _save_image(self, *, pet_id: str, guide_id: str, page_index: int, image_bytes: bytes, mime_type: str) -> str:
        suffix = ".jpg" if mime_type in {"image/jpeg", "image/jpg"} else ".png"
        target_dir = self.settings.upload_dir / "illustrated_guides" / pet_id
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{guide_id}_page{page_index}_{uuid4().hex[:8]}{suffix}"
        target = target_dir / filename
        target.write_bytes(image_bytes)
        return str(target.relative_to(self.settings.upload_dir))

    def _media_url(self, media_path: str) -> str | None:
        if not self.settings.public_base_url:
            return None
        return f"{self.settings.public_base_url.rstrip('/')}/media/{media_path}"

    def _redact_error(self, message: str) -> str:
        if self.settings.image_api_key:
            return message.replace(self.settings.image_api_key, "[REDACTED]")
        return message
