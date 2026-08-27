"""纪念品模板模型（架构审计 P1-2 包化）。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from ..schemas import SouvenirItemType, TravelQuest, TravelQuestStop, TravelQuestType

@dataclass(frozen=True)
class SouvenirTemplate:
    item_type: SouvenirItemType
    title: str
    subtitle: str
    story_template: str
    pet_voice: str
    rarity: str = "common"
    template_id: str | None = None

    def render(self, *, quest: TravelQuest, stop: TravelQuestStop, bag_hint: str) -> tuple[str, SouvenirItemType, str, str, str, str, str]:
        values = {
            "bag_hint": bag_hint,
            "city": stop.city or quest.destination,
            "destination": quest.destination,
            "place": stop.name,
        }
        title = self.title.format(**values)
        subtitle = self.subtitle.format(**values)
        story = self.story_template.format(**values)
        pet_voice = self.pet_voice.format(**values)
        template_id = self.template_id or _stable_template_id(self.item_type, title)
        return (template_id, self.item_type, title, subtitle, story, pet_voice, self.rarity)


@dataclass(frozen=True)
class SouvenirPreset:
    keywords: tuple[str, ...]
    templates: tuple[SouvenirTemplate, ...]


def _stable_template_id(item_type: SouvenirItemType, title: str) -> str:
    return hashlib.sha1(f"{item_type.value}:{title}".encode("utf-8")).hexdigest()[:16]
