"""真实成图批次执行器：四场景 x（旧模板 / 新导演）= 八张，**每次发送前先过金额闸门**。

它是唯一会真的花钱的脚本。默认什么都不做：

  # 干跑（不发任何请求，只把会发什么打出来）
  TZ=UTC python scripts/run_photo_director_batch.py --pet <spec.json> --out <dir>

  # 真发（需要同时满足：规格齐全 + permission=true + 金额校验通过 + 显式确认参数）
  TZ=UTC python scripts/run_photo_director_batch.py --pet <spec.json> --out <dir> --send --yes-spend

停批条件在代码里执行，不是文档里的说明：
  - 每次发送前 `BatchGuard.check_next()`：下一笔会越过上限就停，不发；
  - 任何一张 `unknown`（结果未确认）：**立刻停批**，不补发、不凑张数；
  - 连续两次被当场拒绝（4xx / rejected）：停批；
  - 返回的尺寸或模型与执行单不符：停批。

结果不明的那一笔按**最坏情况**计入已花——它可能已经计费。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "fixtures" / "photo_director"))

from app.web_photo_director.batch import BatchGuard, validate_batch_cost  # noqa: E402
from app.web_photo_director.recipes import TARGET_SCENES  # noqa: E402

MAX_CONSECUTIVE_REJECTS = 2


def build_plan(pet: dict) -> list[dict]:
    """两组提示词：旧模板一份、新导演一份，四场景各一对。"""
    import builders

    from app.web_journey.illustrations import build_selfie_prompt
    from app.web_photo_director import PhotoDirector
    from app.web_photo_director.contracts import IdentityReference, MediaReference

    director = PhotoDirector()
    items: list[dict] = []
    for scene_key in TARGET_SCENES:
        base = builders.build_context(scene_key)
        identity = IdentityReference(
            pet_id=pet["label"], household_id=base.household_id, species=pet["species"],
            origin=pet.get("origin", "owner_original"),
            reference_id=pet.get("reference_id", "ref-1"), sha256=pet["reference_sha256"],
            version=base.versions.identity, appearance_tags=tuple(pet["appearance_tags"]),
        )
        media = MediaReference(
            reference_id=identity.reference_id, sha256=identity.sha256, role="pet_identity",
            source="owner_original", pet_id=identity.pet_id, household_id=identity.household_id,
            mime_type=pet.get("mime_type", "image/jpeg"), ready=True, authorized=True,
        )
        scene = builders.build_scene(scene_key, "fx-pet-amber", pet_id=identity.pet_id)
        context = base.__class__(
            pet_id=identity.pet_id, household_id=identity.household_id, versions=base.versions,
            identity=identity, dna=base.dna, scene=scene, references=(media,),
            companions=(), requested_camera="auto", config_version=base.config_version,
        )
        photo = director.direct(context, builders.build_access(context))
        spec = builders.DATA["scenes"][scene_key]
        items.append({"pair": scene_key, "arm": "old_template",
                      "prompt": build_selfie_prompt(
                          species=pet["species"], name=pet["label"],
                          place=spec["place_label"], city=spec["city"],
                          scene=spec["place_label"], with_reference=True)})
        items.append({"pair": scene_key, "arm": "new_director", "prompt": photo.prompt,
                      "recipe": photo.draft.recipe, "review_points": list(photo.review_points),
                      "negative_prompt": photo.negative_prompt})
    return items


def load_secrets(path: str | None) -> str | None:
    """显式加载密钥文件。**默认不加载**。

    I 刻意没有把密钥放进 `PetJourneyBackend/.env`——那会让旧后端和既有测试自动加载、
    产生意外的付费调用（见其窗口日志）。所以这里也只在命令行明确指定时才读，
    读完只进本进程的 os.environ，不写任何文件、不打印任何值。
    """
    if not path:
        return None
    source = Path(path)
    if not source.exists():
        return f"密钥文件不存在：{path}"
    for line in source.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())
    return None


def make_illustrator(pet: dict):
    """构造真实供应商适配器，**和网页侧同一种构造方式**。

    注意 `DoubaoSeedreamImageProvider` 读的是 `volcengine_image_model`（旧 iOS 模型），
    网页侧是靠 `dataclasses.replace(settings, volcengine_image_model=settings.web_image_model)`
    覆盖过去的（`app/web_providers/__init__.py:50`）。照抄 settings 会发错模型。
    """
    import dataclasses

    from app.config import load_settings

    settings = load_settings()
    key = settings.doubao_api_key or settings.image_api_key
    if not key:
        return None, (
            "缺少生图密钥：DOUBAO_API_KEY / PETJOURNEY_IMAGE_API_KEY 未设置。"
            "用 --secrets 指定密钥文件，或设成环境变量；**不要贴进聊天**。"
        )
    target_model = pet.get("model") or settings.web_image_model
    if target_model != settings.web_image_model:
        return None, (
            f"模型不一致：执行单写的是 {target_model}，"
            f"当前配置解析出的 web_image_model 是 {settings.web_image_model}。"
            "对照批次必须用同一个模型，先对齐再跑。"
        )
    from app.image_provider.seedream import DoubaoSeedreamImageProvider

    effective = dataclasses.replace(settings, volcengine_image_model=target_model)
    return DoubaoSeedreamImageProvider(effective), None


def send_one(provider, item: dict, pet: dict, reference_bytes: bytes):
    """发一张。返回 (outcome, payload)；outcome ∈ ok / unknown / rejected。"""
    from app.image_provider.models import ImageReference
    from app.web_providers.images import failure_reason

    reference = ImageReference(
        image_bytes=reference_bytes, mime_type=pet.get("mime_type", "image/jpeg"),
        filename="pet-reference", role="pet_identity",
    )
    try:
        image = provider.generate_image_with_references(
            item["prompt"], references=[reference], size=pet["size"])
    except BaseException as exc:  # noqa: BLE001
        reason = failure_reason(exc)
        outcome = "unknown" if reason in {"timeout", "unconfirmed"} else "rejected"
        return outcome, {"reason": reason, "error": f"{type(exc).__name__}: {exc}"}
    returned_model = getattr(image, "model", None)
    if returned_model and pet.get("model") and returned_model != pet["model"]:
        return "mismatch", {"reason": "model_mismatch",
                            "expected": pet["model"], "returned": returned_model}
    return "ok", {"image": image, "returned_model": returned_model}


def main() -> int:
    parser = argparse.ArgumentParser(description="真实成图批次（默认干跑，不发请求）")
    parser.add_argument("--pet", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--send", action="store_true", help="真的发送请求（会产生费用）")
    parser.add_argument("--yes-spend", action="store_true", help="确认已获授权花费")
    parser.add_argument("--secrets", help="密钥文件路径（默认不加载任何密钥）")
    args = parser.parse_args()

    secrets_error = load_secrets(args.secrets)
    if secrets_error:
        print(secrets_error)
        return 2
    pet = json.loads(Path(args.pet).read_text(encoding="utf-8"))
    reference = Path(pet["reference_path"])
    if not reference.exists():
        print(f"参考照不存在：{reference}")
        return 2
    pet["reference_sha256"] = hashlib.sha256(reference.read_bytes()).hexdigest()

    items = build_plan(pet)
    cost = validate_batch_cost(pet.get("provider_quote"), pet.get("batch_cap"), len(items))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    blocking = list(cost["problems"])
    if pet.get("permission") is not True:
        blocking.append("permission 不是 true")
    if not blocking and not (args.send and args.yes_spend):
        blocking.append("干跑模式：要真的发送需要同时给 --send 与 --yes-spend")

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pet": {k: v for k, v in pet.items() if k != "reference_path"},
        "cost": cost, "planned": len(items), "blocking": blocking, "sent": [],
    }
    if blocking:
        (out / "batch-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("未发送任何请求。阻塞：")
        for item in blocking:
            print(f"  - {item}")
        return 1

    provider, missing = make_illustrator(pet)
    if provider is None:
        report["blocking"] = [missing]
        (out / "batch-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"未发送任何请求。{missing}")
        return 1

    guard = BatchGuard.from_spec(pet["provider_quote"], pet["batch_cap"], len(items))
    reference_bytes = reference.read_bytes()
    consecutive_rejects = 0

    for item in items:
        try:
            guard.check_next()          # 每次发送前的金额闸门
        except Exception as exc:        # noqa: BLE001
            report["stopped_before"] = f"{item['pair']}/{item['arm']}: {exc}"
            break
        outcome, payload = send_one(provider, item, pet, reference_bytes)
        guard.record(outcome, note=f"{item['pair']}/{item['arm']}")
        record = {"pair": item["pair"], "arm": item["arm"], "outcome": outcome}
        if outcome == "mismatch":
            guard.stop("model_mismatch")
            record.update(payload)
            report["sent"].append(record)
            report["stopped_after"] = f"{item['pair']}/{item['arm']}: model_mismatch"
            break
        if outcome == "ok":
            consecutive_rejects = 0
            record["returned_model"] = payload.get("returned_model")
            image = payload["image"]
            name = f"{item['pair']}-{item['arm']}.png"
            (out / name).write_bytes(image.image_bytes)
            record["file"] = name
            record["bytes"] = len(image.image_bytes)
        else:
            record.update(payload)
            if outcome == "rejected":
                consecutive_rejects += 1
                if consecutive_rejects >= MAX_CONSECUTIVE_REJECTS:
                    guard.stop("consecutive_rejects")
            else:
                consecutive_rejects = 0
        report["sent"].append(record)
        if guard.stopped:
            report["stopped_after"] = f"{item['pair']}/{item['arm']}: {guard.stopped}"
            break

    report["guard"] = guard.summary()
    (out / "batch-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(guard.summary(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
