"""照片导演测试的公共底座：禁网基类与注入替身。

放在 fixtures 里而不是 tests 根目录，是为了让每个 test_web_photo_director_*.py
保持在架构门禁的单文件定义数以内，同时只有一份替身实现。
"""
from __future__ import annotations

import json
import socket
import unittest

import builders

from app.web_photo_director import PhotoDirector

SCENE_KEYS = ("cafe", "train", "home", "flight_adventure")
ALL_SCENE_KEYS = tuple(builders.DATA["scenes"])


def no_network(*_args, **_kwargs):
    raise AssertionError("照片导演不应该发起任何网络连接")


class OfflineCase(unittest.TestCase):
    """禁网基类：任何一次真实连接尝试都会让用例失败，而不是静默通过。"""

    def setUp(self) -> None:
        self._saved = (socket.socket.connect, socket.create_connection, socket.getaddrinfo)
        socket.socket.connect = no_network
        socket.create_connection = no_network
        socket.getaddrinfo = no_network
        self.director = PhotoDirector()

    def tearDown(self) -> None:
        socket.socket.connect, socket.create_connection, socket.getaddrinfo = self._saved

    def direct(self, scene_key: str, pet_key: str = "fx-pet-amber", **kwargs):
        context = builders.build_context(scene_key, pet_key, **kwargs)
        return self.director.direct(context, builders.build_access(context))


class FakeResult:
    def __init__(self, text: str) -> None:
        self.text = text
        self.requested_model = "fx-director-model"
        self.effective_model = "fx-director-model-0930"
        self.latency_ms = 41
        self.prompt_tokens = 120
        self.completion_tokens = 18


class FakeChat:
    """禁网替身，签名与现有 WebChat.complete 一致。"""

    def __init__(self, *, text=None, raises=None, available: bool = True):
        self.available = available
        self.provider_label = "fx-chat"
        self._text = text
        self._raises = raises
        self.calls: list[dict] = []

    def complete(self, messages, *, max_tokens=200, temperature=0.7, json_mode=False):
        self.calls.append({"messages": messages, "json_mode": json_mode, "max_tokens": max_tokens})
        if self._raises is not None:
            raise self._raises
        return FakeResult(self._text or "")


class FakeBudget:
    def __init__(self, *, allow: bool = True) -> None:
        self.allow = allow
        self.reserved: list[str] = []
        self.settled: list[tuple[str, str]] = []

    def reserve(self, *, operation_id, pet_id, household_id):
        self.reserved.append(operation_id)
        return self.allow

    def settle(self, *, operation_id, outcome, prompt_tokens=None, completion_tokens=None):
        self.settled.append((operation_id, outcome))


class ModelPortCase(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = (socket.socket.connect, socket.create_connection, socket.getaddrinfo)
        socket.socket.connect = no_network
        socket.create_connection = no_network
        socket.getaddrinfo = no_network

    def tearDown(self) -> None:
        socket.socket.connect, socket.create_connection, socket.getaddrinfo = self._saved

    def direct(self, chat, budget, *, scene_key="cafe", allowed=True, **kwargs):
        context = builders.build_context(scene_key, **kwargs)
        access = builders.build_access(context, text_director=allowed)
        return PhotoDirector(chat=chat, budget=budget).direct(context, access)


def reply(**fields) -> str:
    return json.dumps(fields, ensure_ascii=False)


VALID_CAFE = reply(
    recipe="cafe_observe_selfie", expression="curious",
    visible_facts=["at_cafe", "weather_sunny"],
)
