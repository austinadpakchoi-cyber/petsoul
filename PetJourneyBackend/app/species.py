from __future__ import annotations

from .schemas import PetType


def species_display_name(pet_type: PetType) -> str:
    return {
        PetType.dog: "狗狗",
        PetType.cat: "猫咪",
        PetType.parrot: "鹦鹉",
        PetType.rabbit: "兔兔",
        PetType.hamster: "仓鼠",
        PetType.bird: "小鸟",
        PetType.other: "小动物",
    }.get(pet_type, "小动物")


def species_image_subject(pet_type: PetType) -> str:
    return {
        PetType.dog: "beloved dog",
        PetType.cat: "beloved cat",
        PetType.parrot: "beloved parrot",
        PetType.rabbit: "beloved rabbit",
        PetType.hamster: "beloved hamster",
        PetType.bird: "beloved small bird",
        PetType.other: "beloved companion animal",
    }.get(pet_type, "beloved companion animal")


def species_language_style(pet_type: PetType) -> str:
    return {
        PetType.dog: "dog_vocalization_with_hidden_translation",
        PetType.cat: "cat_vocalization_with_hidden_translation",
        PetType.parrot: "parrot_chirp_with_hidden_translation",
        PetType.rabbit: "rabbit_soft_signal_with_hidden_translation",
        PetType.hamster: "hamster_soft_signal_with_hidden_translation",
        PetType.bird: "bird_chirp_with_hidden_translation",
        PetType.other: "companion_animal_signal_with_hidden_translation",
    }.get(pet_type, "companion_animal_signal_with_hidden_translation")


def species_surface_language_label(pet_type: PetType) -> str:
    return {
        PetType.dog: "汪汪/呜汪",
        PetType.cat: "喵喵/喵呜/呼噜",
        PetType.parrot: "啾啾/咕咕/短句模仿",
        PetType.rabbit: "轻轻鼻音、嗅嗅声和爪爪轻碰",
        PetType.hamster: "细小吱吱声和嗅嗅声",
        PetType.bird: "啾啾/咕咕",
        PetType.other: "适合这个小动物的声音或非语言信号",
    }.get(pet_type, "适合这个小动物的声音或非语言信号")


def species_vocalization(pet_type: PetType, tone: str) -> str:
    pattern_map = {
        PetType.dog: {
            "connecting": "汪...呜汪。汪汪。",
            "connected": "汪呜！汪汪，呜。",
            "selfie": "汪呜汪，汪汪！呜汪。",
            "guide_saved": "汪汪。呜汪，汪呜汪。",
            "guide_skipped": "呜。汪呜汪，汪。",
            "default": "汪呜...汪汪。呜。",
        },
        PetType.cat: {
            "connecting": "喵...喵呜。喵喵。",
            "connected": "喵呜！喵喵，喵。",
            "selfie": "喵呜喵，喵喵！呼噜。",
            "guide_saved": "喵喵。喵呜，呼噜呼噜。",
            "guide_skipped": "喵。喵呜喵，喵。",
            "default": "喵呜...喵喵。喵。",
        },
        PetType.parrot: {
            "connecting": "啾...咕咕。啾啾。",
            "connected": "啾！你好呀，啾啾。",
            "selfie": "咔哒，啾啾！咕。",
            "guide_saved": "啾啾。好地方，啾。",
            "guide_skipped": "咕。先飞过，啾。",
            "default": "啾啾...咕咕。啾。",
        },
        PetType.rabbit: {
            "connecting": "嗅嗅...轻轻蹭。嗒。",
            "connected": "嗅嗅。耳朵动了一下。",
            "selfie": "嗒嗒，嗅嗅。轻轻靠近。",
            "guide_saved": "嗅嗅。爪爪轻轻点了点。",
            "guide_skipped": "嗒。耳朵慢慢转过去。",
            "default": "嗅嗅...轻轻蹭。嗒。",
        },
        PetType.hamster: {
            "connecting": "吱...嗅嗅。吱吱。",
            "connected": "吱吱！小爪子动了动。",
            "selfie": "吱，咔哒。嗅嗅。",
            "guide_saved": "吱吱。抱住一颗小光点。",
            "guide_skipped": "吱。先藏进软软的地方。",
            "default": "吱吱...嗅嗅。吱。",
        },
        PetType.bird: {
            "connecting": "啾...咕。啾啾。",
            "connected": "啾！啾啾，咕。",
            "selfie": "啾啾，咔哒！",
            "guide_saved": "啾啾。咕咕。",
            "guide_skipped": "咕。啾。",
            "default": "啾啾...咕。啾。",
        },
        PetType.other: {
            "connecting": "沙沙...轻轻靠近。",
            "connected": "小小的信号亮了一下。",
            "selfie": "咔哒。TA 轻轻动了一下。",
            "guide_saved": "信号闪了闪，像是记住了。",
            "guide_skipped": "信号慢慢变轻，TA 先按自己的节奏走。",
            "default": "小小的信号，轻轻亮了一下。",
        },
    }
    patterns = pattern_map.get(pet_type, pattern_map[PetType.other])
    return patterns.get(tone, patterns["default"])
