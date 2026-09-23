"""把现有的 DNA 记录转成读取端口要的共用层快照（纯函数）：集成窗口实现 ContextReader.shared_dna 时直接调用。

web_pets.dna.PetDNAStore.saved() 已经去掉个人层，这里再去掉一次称呼与小暗号。还没保存过共用 DNA 时，
给全家的决策要用 draft(None, pet_id)（只含领养资料 / 简介），不能用某位家人的草稿；此时 versions.dna_version 请给 0。
"""

from __future__ import annotations

from .ports import DnaSnapshot

SHARED_DNA_FIELDS = ("personality", "voice_style", "catchphrase", "nicknames", "favorite_foods", "favorite_places", "hobbies", "habits", "fears")


def dna_snapshot(record) -> DnaSnapshot | None:
    """record：web_pets.dna.DNARecord（共用层或给全家的草稿）；None → None。"""
    if record is None:
        return None
    fields: dict[str, tuple[str, ...]] = {}
    for name in SHARED_DNA_FIELDS:
        value = getattr(record.dna, name, None)
        values = tuple(str(v) for v in (value if isinstance(value, list) else [value]) if v)
        if values:
            fields[name] = values
    sources = list(getattr(record, "sources", None) or [])
    source = next((s for s in ("owner", "owner_bio", "adoption_profile") if s in sources), "owner" if record.confirmed else "adoption_profile")
    return DnaSnapshot(fields=fields, confirmed=bool(record.confirmed), source=source)
