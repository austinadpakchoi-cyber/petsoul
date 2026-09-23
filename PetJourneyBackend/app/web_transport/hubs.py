"""交通枢纽参考记录（web_transport/hubs.json）：码头名称、坐标与来源（高德 POI 检索结果 + 运营方的码头资料）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).resolve().parent / "hubs.json"


@dataclass(frozen=True)
class Hub:
    hub_id: str
    name: str
    official_name: str
    city: str
    timezone: str
    lat: float
    lng: float
    kind: str
    source: dict

    def node(self) -> dict:
        return {"node_id": f"hub:{self.hub_id}", "name": self.name, "kind": self.kind, "timezone": self.timezone, "lat": self.lat, "lng": self.lng,
                "verified": True}


@lru_cache(maxsize=1)
def load_hubs() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8"))


def hub(hub_id: str) -> Hub:
    data = load_hubs()["hubs"][hub_id]
    return Hub(hub_id=hub_id, name=data["name"], official_name=data["official_name"], city=data["city"], timezone=data["timezone"], lat=data["lat"],
               lng=data["lng"], kind=data["kind"], source=data["source"])


def anchor(anchor_id: str) -> dict:
    return load_hubs()["anchors"][anchor_id]
