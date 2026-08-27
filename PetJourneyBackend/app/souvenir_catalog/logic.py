"""纪念品模板构建逻辑（架构审计 P1-2 包化）。"""

from __future__ import annotations

import hashlib

from ..schemas import SouvenirItemType, TravelQuest, TravelQuestStop, TravelQuestType
from .data import BAG_PRESETS, CITY_PRESETS, GLOBAL_TEMPLATES, PLACE_PRESETS, WORLDCUP_TEMPLATES
from .models import SouvenirPreset, SouvenirTemplate

def build_souvenir_templates(
    *,
    quest: TravelQuest,
    stop: TravelQuestStop,
    bag_hint: str,
    bag_tags: list[str],
) -> list[tuple[str, SouvenirItemType, str, str, str, str, str]]:
    if quest.quest_type == TravelQuestType.worldcup:
        return _render(WORLDCUP_TEMPLATES, quest=quest, stop=stop, bag_hint=bag_hint)

    primary_context = _primary_context_text(quest=quest, stop=stop, bag_tags=bag_tags)
    context = _context_text(quest=quest, stop=stop, bag_tags=bag_tags)
    selected: list[SouvenirTemplate] = []
    for preset in CITY_PRESETS:
        if _matches(primary_context, preset.keywords):
            selected.extend(preset.templates)
            break

    for preset in BAG_PRESETS:
        if _matches(primary_context, preset.keywords):
            selected.extend(preset.templates)

    for preset in PLACE_PRESETS:
        if _matches(context, preset.keywords):
            selected.extend(preset.templates)

    selected.extend(GLOBAL_TEMPLATES)
    return _render(_dedupe(selected)[:3], quest=quest, stop=stop, bag_hint=bag_hint)



def _primary_context_text(*, quest: TravelQuest, stop: TravelQuestStop, bag_tags: list[str]) -> str:
    return " ".join(
        [
            quest.destination,
            quest.owner_message,
            stop.city,
            stop.name,
            stop.role,
            " ".join(stop.source_notes),
            " ".join(bag_tags),
        ]
    ).lower()



def _context_text(*, quest: TravelQuest, stop: TravelQuestStop, bag_tags: list[str]) -> str:
    stop_text = " ".join(
        f"{guide_stop.city} {guide_stop.name} {guide_stop.role} {' '.join(guide_stop.source_notes)}"
        for guide_stop in (quest.guide.stops if quest.guide else [])
    )
    return " ".join(
        [
            quest.destination,
            quest.owner_message,
            stop.city,
            stop.name,
            stop.role,
            " ".join(stop.source_notes),
            stop_text,
            " ".join(bag_tags),
        ]
    ).lower()



def _matches(context: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword.lower() in context for keyword in keywords)



def _render(
    templates: list[SouvenirTemplate] | tuple[SouvenirTemplate, ...],
    *,
    quest: TravelQuest,
    stop: TravelQuestStop,
    bag_hint: str,
) -> list[tuple[str, SouvenirItemType, str, str, str, str, str]]:
    return [template.render(quest=quest, stop=stop, bag_hint=bag_hint) for template in templates]



def _dedupe(templates: list[SouvenirTemplate]) -> list[SouvenirTemplate]:
    seen: set[str] = set()
    result: list[SouvenirTemplate] = []
    for template in templates:
        if template.title in seen:
            continue
        seen.add(template.title)
        result.append(template)
    return result


