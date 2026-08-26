"""图文攻略提示词构建 mixin（架构审计 P1-2 包化，自 illustrated_guide.py 原样迁入）。"""

from __future__ import annotations

from ..illustrated_guide_styles import IllustratedGuideStyle
from ..schemas import IllustratedGuideStop


class IllustratedGuidePromptMixin:
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
