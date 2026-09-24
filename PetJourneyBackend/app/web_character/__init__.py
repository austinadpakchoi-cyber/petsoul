"""世界角色（CR-PLAYER-CHARACTER-01）：主人上传的原照 → TA 在世界里的专属形象。

  - `service`：自动触发、执行、校验、原子发布、纯读状态；
  - `poses`：批次二的五个姿态（以同一套已生效的中性姿态为参考；**开关默认关**）；
  - `prompts`：角色指令（临时自持，P 的角色用途到位后只换 `CharacterService.compile_prompt` 那一处）；
  - `validate`：不依赖 Pillow 的 PNG 校验（真有没有 alpha、主体框、单一主体、落地点）；
  - `flatten`：把带 alpha 的参考图压到中性灰底上再发（同样不依赖 Pillow）；
  - `model`：状态、原因码与对外资产结构。

`install_character_service` 是唯一的装配入口：它**顺带把上传成功的钩子接上**（函数名里的 install 就是这个意思）。
这样组合根只需要在 `WebServices(...)` 里加一个传参，不必另外写接线行。
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..storage import JourneyStorage
from ..web_platform.tasks import WebTaskQueue
from .model import CharacterAsset, CharacterView
from .service import CharacterService

logger = logging.getLogger("petsoul.web.character")

__all__ = ["CharacterAsset", "CharacterService", "CharacterView", "ImageWorkPump", "install_character_service"]


class ImageWorkPump:
    """把几条生图链路挂在**同一个进程内线程**上。`IllustrationWorker` 只认一个 `run_pending()`，这就是那一个。

    为什么需要它：`illustrations.run_pending()` 里写死的是 `run_once(self.tasks, {KIND: self}, ...)`，
    `KIND == "illustration"`。角色任务的 kind 是 `"pet_character"`，**永远不会被它领取**——
    上传会排队、库里真有行，但生产里没有任何线程去执行。
    这种故障最难发现：**数据库看起来一切正常，任务就是不动。**
    （不去改 `illustrations.py` 让它多泵一种，是因为那个文件正好 30 个 def/class，顶在 `arch_gate` 上限。）

    **顺序：插画在前、角色在后。** 插画是"用户刚做完某件事"的即时产物（拍了照、写了手账），
    等待的人正盯着；角色是一次性的身份资产，晚几秒没人察觉。
    代价说清楚：插画大量积压时角色会**延后**——但每条链路每轮各自算 `limit`，所以只是晚，不会永远轮不到。

    **逐个 try，一条抛出去不许带走另一条。** `IllustrationWorker._loop` 自己那层 except 在**整轮之外**：
    插画抛一次，本轮的角色就整个被吞掉，而且同样是静默的——和"根本没人泵角色任务"是同一种形状的故障。
    所以兜底必须在这里、按服务逐个兜。

    `worker_id` 收下但**不往下传**：两条链路各用自己的默认值（`web-illustrations` / `web-characters`），
    领取凭据上看得出是谁领的；合成一个 id 只会让排查时分不清。
    """

    def __init__(self, *services) -> None:
        # 服务自己声明"还要顺带泵谁"（`pumped_with`）：角色服务挂着证件照服务。
        # 这样组合根仍只传 `(illustrations, character)`，证件照任务也有人领；而 `character.run_pending` 保持只领角色任务。
        self.services = tuple(item for service in services for item in (service, *getattr(service, "pumped_with", ())))

    def run_pending(self, worker_id: str = "web-images", limit: int = 5) -> int:
        handled = 0
        for service in self.services:
            try:
                handled += service.run_pending(limit=limit) or 0
            except Exception:  # noqa: BLE001 - 一条链路这一轮出错，不该让另一条也停摆
                logger.exception("image work pump: %s failed this round", type(service).__name__)
        return handled


def install_character_service(storage: JourneyStorage, media_root: str | Path, tasks: WebTaskQueue, *,
                              pets, illustrator=None, settings=None, meter=None) -> CharacterService:
    """建好角色服务，并把它接到"上传成功"那个事务里。

    `pets.on_pet_photo_stored` 是 `web_pets/service.py::create_own` 在**它自己的写事务里、建好家之后**
    调的钩子。**仍然必须是建家之后**：角色任务登记前要确认这只宠物属于某个家庭
    （没有家的宠物，角色不属于任何人、也没人有权读它），家还没建出来就判不出来。
    ——原先这里的理由是"要回落到建家人的授权设置"，用户 2026-09-23 取消逐次询问后理由换了，
    **结论没换**：这个钩子的位置不能往前挪。

    额度上限与插画链路**同源同取法**（见 `web_agent/brain_wiring.py`）：全局那层取配置，
    计量表接上了以它为准（供应商自己的上限更硬）；**0 表示该层不限**，那是显式选择，不是默认。
    """
    image_cap = ((meter.caps.get("image") if meter is not None else None)
                 or int(getattr(settings, "web_image_daily_cap", 0) or 0))
    per_pet_cap = int(getattr(settings, "web_image_per_pet_daily_cap", 0) or 0)
    character = CharacterService(storage, Path(media_root), tasks, per_pet_daily=per_pet_cap, global_daily=image_cap)
    character.illustrator = illustrator
    # 适配器**真的会把 `background` 发出去**才为真（GPT 为真；Seedream 的参数表里没有它，为假）。
    # 读能力标记而不是 isinstance：换实现时不必回头改这里。不声明就是不支持——**不猜**。
    character.transparency_requested = bool(getattr(illustrator, "requests_transparent_background", False))
    # 批次二的五个姿态：**默认关**（用户 2026-09-24 决定，不新增付费调用）。
    # 字段由 config 的持有人加；没有这个字段时 `getattr` 回落 False，与"显式关"是同一个结果。
    character.poses.enabled = bool(getattr(settings, "web_character_extra_poses", False))
    # 证件照的**自动**生成：**默认开**（用户 2026-09-24 定：新宠物自动生成；存量不批量补）。只管自动触发，主人点重画不受它管。
    # 没有这个字段就是开；config 里眼下还没有它，运维要关得先由 config 的持有人加字段。
    character.id_photo.auto = bool(getattr(settings, "web_id_photo_auto", True))
    character.character_of = lambda pet_id: _character_of(pets, pet_id)
    character.reference_photo_of = lambda pet_id: _reference_photo_of(pets, pet_id)
    character.reference_origin_of = lambda pet_id: _reference_origin_of(pets, pet_id)

    def on_pet_photo_stored(conn, pet_id: str, user_id: str, species: str, photo_ref: str, content_type, now) -> None:
        character.request_in(conn, pet_id, user_id, species, photo_ref, now=now)
        character.id_photo.request_in(conn, pet_id, user_id, now=now)  # 同一事务：证件照也登记上

    def on_pet_adopted(conn, pet_id: str, user_id: str, now) -> None:
        # 领养**只登记证件照**：角色的自动触发范围（上传成功）不变。有没有照片、能不能画，由证件照服务自己判断
        character.id_photo.request_in(conn, pet_id, user_id, now=now)

    pets.on_pet_photo_stored = on_pet_photo_stored
    pets.on_pet_adopted = on_pet_adopted
    return character


def _character_of(pets, pet_id: str):
    record = pets.profile(pet_id)
    return None if record is None else (record.species.value, record.name, None)


def _reference_photo_of(pets, pet_id: str):
    found = pets.photo_path(pet_id)
    if found is None:
        return None
    path, content_type = found
    return (path.read_bytes(), content_type)


def _reference_origin_of(pets, pet_id: str) -> str | None:
    """这张参考照是哪来的。**不知道就返回 None**，调用方据此拒绝——
    绝不把来源不明（或本来就是我们生成）的图冒名成主人原照。

    与 `web_composition.py::reference_origin_of` 同口径；那一份服务的是照片链路，这一份服务角色链路，
    判定依据都是 `photo_generated` 与 `PetOrigin`，没有第二套规则。
    """
    from ..schemas.web.pets import PetOrigin

    if pets.photo_path(pet_id) is None:
        return None
    if pets.photo_generated(pet_id):
        return "original_companion"
    record = pets.profile(pet_id)
    if record is None:
        return None
    return {PetOrigin.own_pet: "owner_original", PetOrigin.adopted_real_archive: "real_archive"}.get(record.origin)
