"""照片导演离线评测 + 真实成图执行单（默认不联网、不发任何请求）。

三种用法：

  # 1) 离线评测：每个 fixture 场景（含一例双宠）各编译一条指令，写出 JSON 与本地联系表
  TZ=UTC python scripts/evaluate_photo_director.py --out data/reviews/<目录>

  # 2) 新旧对照：同时渲染当前线上模板的提示词，供人工比较（仍然不发请求）
  TZ=UTC python scripts/evaluate_photo_director.py --out <目录> --compare-template

  # 3) dry-run 执行单：把"如果获批，会向供应商发什么"完整写下来，仍然不发
  TZ=UTC python scripts/evaluate_photo_director.py --out <目录> --dry-run

本脚本**永远不会**发起真实供应商调用，也不读取任何真实用户媒体。
真实成图必须由用户按执行单单独授权具体批次与金额上限后，另行执行。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "fixtures" / "photo_director"))

from app.web_photo_director import describe_gap  # noqa: E402
from app.web_photo_director.batch import validate_batch_cost  # noqa: E402
from app.web_photo_director.recipes import TARGET_SCENES  # noqa: E402

# 执行单必须由**真实测试宠物**的规格驱动。没有它，写出来的提示词还带着
# fixture 橘猫的毛色、绿眼和 fx- 编号，套到别的照片上就是错的。
PLACEHOLDER_PET = "（未指定：需要一只已获使用许可的测试宠物）"
REQUIRED_PET_FIELDS = ("label", "species", "appearance_tags", "reference_path",
                       "permission", "model", "size")
REQUIRED_COST_FIELDS = ("provider_quote", "batch_cap")


def block_network() -> None:
    def deny(*_args, **_kwargs):
        raise RuntimeError("evaluate_photo_director 不允许联网")

    socket.socket.connect = deny          # type: ignore[method-assign]
    socket.socket.connect_ex = deny       # type: ignore[method-assign]
    socket.create_connection = deny       # type: ignore[assignment]
    socket.getaddrinfo = deny             # type: ignore[assignment]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16].upper()


def source_fingerprints() -> dict[str, str]:
    package = ROOT / "app" / "web_photo_director"
    return {f"app/web_photo_director/{p.name}": digest(p) for p in sorted(package.glob("*.py"))}


def template_prompt(scene_key: str, builders) -> dict:
    """当前线上模板（A 持有的 web_journey/illustrations.py）的提示词，只读对照。

    导入失败时如实记录原因，不伪造一条"旧提示词"来凑对照。
    """
    try:
        from app.web_journey.illustrations import build_selfie_prompt
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": f"{type(exc).__name__}: {exc}"}
    spec = builders.DATA["scenes"][scene_key]
    pet = builders.DATA["pets"]["fx-pet-amber"]
    return {
        "available": True,
        "source": "app/web_journey/illustrations.py:build_selfie_prompt",
        "source_sha256_16": digest(ROOT / "app" / "web_journey" / "illustrations.py"),
        "prompt": build_selfie_prompt(
            species=pet["species"], name="（评测用虚构名）", place=spec["place_label"],
            city=spec["city"], scene=spec["place_label"], with_reference=True,
        ),
    }


def build_rows(*, compare_template: bool) -> list[dict]:
    import builders

    from app.web_photo_director import PhotoDirector

    director = PhotoDirector()  # 离线：没有注入模型端口，走规则导演
    cases: list[tuple[str, str | None]] = [(key, None) for key in builders.DATA["scenes"]]
    cases.append(("landmark", "fx-pet-mochi"))  # 双宠合影
    rows: list[dict] = []
    for scene_key, companion in cases:
        context = builders.build_context(scene_key, companion_key=companion)
        photo = director.direct(context, builders.build_access(context))
        row = {
            "scene": scene_key,
            "case": scene_key if companion is None else f"{scene_key}+duo",
            "review_points": list(photo.review_points),
            "story_mode": photo.story_mode,
            "evidence": photo.evidence(),
            "prompt": photo.prompt,
            "prompt_length": len(photo.prompt),
            "negative_prompt": photo.negative_prompt,
            "size": photo.size,
            "fact_input": [fact.token for fact in context.scene.facts if fact.verified],
            "captured_at": context.scene.captured_at.isoformat(),
        }
        if compare_template:
            row["current_template"] = template_prompt(scene_key, builders)
        rows.append(row)
    return rows


def _cost_block(pet, image_count: int) -> dict:
    """总估价 = 单价 x 张数，并做**真正的阻断校验**：金额、币种、总额都要过。"""
    quote = (pet or {}).get("provider_quote")
    cap = (pet or {}).get("batch_cap")
    block = {
        "provider_quote": quote or "未提供——不得写 0 元",
        "batch_cap": cap or "未提供",
        "image_requests": image_count,
        "director_text_requests": 0,
        "formula": "总估价 = provider_quote.unit x image_requests（文本调用 0 次，不计）",
    }
    if quote is None or cap is None:
        block["estimated_total"] = "无法计算：缺报价或上限"
        block["problems"] = ["provider_quote 或 batch_cap 未提供"]
        return block
    checked = validate_batch_cost(quote, cap, image_count)
    block.update({
        "estimated_total": checked.get("estimated_total", "无法计算"),
        "currency": checked.get("currency"),
        "cap_amount": checked.get("cap"),
        "within_cap": checked["ok"],
        "problems": checked["problems"],
    })
    return block


def load_pet_spec(path):
    """读真实测试宠物规格。缺字段就如实列出来，不补默认值。"""
    if not path:
        return None, ["未提供 --pet：执行单只能是占位稿"]
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    problems = [f"缺字段 {f}" for f in REQUIRED_PET_FIELDS if not spec.get(f)]
    problems += [f"缺字段 {f}" for f in REQUIRED_COST_FIELDS if not spec.get(f)]
    reference = spec.get("reference_path")
    if reference:
        source = Path(reference)
        if not source.exists():
            problems.append(f"参考照不存在：{reference}")
        else:
            # 只记摘要与大小，**不把照片复制进仓库**
            spec["reference_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            spec["reference_bytes"] = source.stat().st_size
    if spec.get("permission") is not True:
        problems.append("permission 不是 true：未确认这只宠物的照片可用于本批次")
    return spec, problems


def recompile_for_pet(spec, rows):
    """用真实宠物重新编译两组提示词，不拿 fixture 橘猫那份去套。"""
    import builders

    from app.web_photo_director import PhotoDirector
    from app.web_photo_director.contracts import IdentityReference, MediaReference

    director = PhotoDirector()
    out = {}
    for scene_key in TARGET_SCENES:
        base = builders.build_context(scene_key)
        identity = IdentityReference(
            pet_id=spec["label"], household_id=base.household_id,
            species=spec["species"], origin=spec.get("origin", "owner_original"),
            reference_id=spec.get("reference_id", "ref-1"),
            sha256=spec["reference_sha256"],
            version=base.versions.identity,
            appearance_tags=tuple(spec["appearance_tags"]),
        )
        media = MediaReference(
            reference_id=identity.reference_id, sha256=identity.sha256,
            role="pet_identity", source="owner_original",
            pet_id=identity.pet_id, household_id=identity.household_id,
            mime_type=spec.get("mime_type", "image/jpeg"), ready=True, authorized=True,
        )
        scene = builders.build_scene(scene_key, "fx-pet-amber", pet_id=identity.pet_id)
        context = base.__class__(
            pet_id=identity.pet_id, household_id=identity.household_id,
            versions=base.versions, identity=identity, dna=base.dna, scene=scene,
            references=(media,), companions=(), requested_camera="auto",
            config_version=base.config_version,
        )
        photo = director.direct(context, builders.build_access(context))
        template = next((r.get("current_template") for r in rows if r["scene"] == scene_key), None)
        out[scene_key] = {
            "new_prompt": photo.prompt,
            "new_recipe": photo.draft.recipe,
            "new_references": photo.evidence()["references"],
            "review_points": list(photo.review_points),
            "old_prompt": (template or {}).get("prompt"),
        }
    return out


def pairs_sheet(rows, pet=None, problems=None):
    """真实成图执行单：**恰好八项**，四个目标场景各一旧一新。

    刻意和 12 项离线评测分开：离线评测是为了看配方库编译得对不对，
    执行单是为了拿到能人审的对照图。混在一起会让"要发几次请求"说不清楚。
    """
    problems = list(problems or [])
    cost = _cost_block(pet, 2 * len(TARGET_SCENES))
    # 金额不合格要真正阻断，不只是在 cost 块里写一行。
    problems += [f"金额校验：{item}" for item in cost.get("problems", [])]
    ready = pet is not None and not problems
    compiled = recompile_for_pet(pet, rows) if ready else {}
    targets = [row for row in rows if row["scene"] in TARGET_SCENES and row["case"] == row["scene"]]
    targets.sort(key=lambda row: TARGET_SCENES.index(row["scene"]))
    items = []
    for row in targets:
        scene_key = row["scene"]
        fresh = compiled.get(scene_key) or {}
        template = row.get("current_template") or {}
        shared = {
            "scene": scene_key,
            "pet": pet["label"] if ready else PLACEHOLDER_PET,
            "reference_sha256": pet.get("reference_sha256") if ready else None,
            "size": pet["size"] if ready else row["size"],
            "model": pet["model"] if ready else "（未指定：需与现网一致）",
            "params": (pet.get("params") if ready else None) or {},
        }
        items.append({**shared, "arm": "old_template", "pair": scene_key,
                      "prompt": fresh.get("old_prompt") if ready else template.get("prompt"),
                      "prompt_source": template.get("source"),
                      "negative_prompt": None,
                      "references": [[0, "pet_identity"]]})
        items.append({**shared, "arm": "new_director", "pair": scene_key,
                      "prompt": fresh.get("new_prompt") if ready else row["prompt"],
                      "prompt_source": "web_photo_director / " + (
                          fresh.get("new_recipe") if ready else row["evidence"]["recipe"]),
                      "negative_prompt": row["negative_prompt"],
                      "references": fresh.get("new_references") if ready else row["evidence"]["references"],
                      "review_points": fresh.get("review_points") or row["review_points"]})
    return {
        "status": (
            "READY_FOR_AUTHORISATION — 已按真实测试宠物重新编译；仍未发送任何请求"
            if ready else
            "PLACEHOLDER_ONLY — 提示词仍带着 fixture 虚构宠物的特征，不可直接用于出图"
        ),
        "blocking": problems,
        "pet": {k: v for k, v in (pet or {}).items() if k != "reference_path"} if pet else None,
        "cost": cost,
        "stop_conditions": [
            "任何一张返回 unknown（结果未确认）：停下，不补发、不凑张数，把这一笔记进待对账",
            "连续两张被供应商当场拒绝（4xx）：停下，先查参数或配置，不要把剩下的也发完",
            "累计已发出的估价达到 batch_cap：立即停，哪怕还没拍满八张",
            "任一张的实际返回尺寸或模型与执行单不符：停下，这一组对照已经不成立",
            "人审在前两对就判定新旧都不像这只宠物：停下，先调提示词再花后面的钱",
        ],
        "adapter_capability_snapshot": describe_gap(),
        "_capability_note": (
            "上表是 2026-09-23 只读核对的现网能力。首批八张按现网单参考路径走，"
            "负面提示词**送不进去**——这一点会让新导演这一组少掉一层保护，人审时要把它算进去。"
        ),
        "design": "四个目标场景，每场景一旧一新，共八张；同一只宠物、同一张固定参考、同一模型与尺寸",
        "requires": [
            "用户明确授权本批次",
            "明确的金额上限（按实际供应商报价确认；未知不得写 0 元）",
            "一只已获使用许可的测试宠物与固定基准照",
        ],
        "batch": {
            "image_requests_total": len(items),
            "pairs": len(items) // 2,
            "director_text_requests": 0,
            "vision_review_calls": 0,
            "note": "首批固定为规则导演，文本调用 0 次；unknown 不补发、不凑张数，缺的那张就缺着",
        },
        "human_review": [
            "是不是同一只宠物（脸、花纹、体型）",
            "有没有保持真实动物外形（没有人手、人脸、人身）",
            "肢体与接触是否合理（承重、不穿透、器物落在台面上）",
            "场景与镜头是否成立（认得出地方；谁在拍说得通）",
        ],
        "items": items,
        "on_unknown_result": "结果未确认不自动重发、不补图凑张数；保留该笔记录与可能的费用",
        "record_after_run": [
            "请求ID", "耗时", "实际用量/账本", "失败样本", "逐张人审意见（接受/不接受及原因）",
        ],
    }


def offline_sheet(rows: list[dict]) -> dict:
    """12 项离线评测清单，另行保留，不是成图批次。"""
    return {
        "status": "OFFLINE_ONLY — 编译检查，不涉及任何图片请求",
        "cases": len(rows),
        "per_case": [
            {
                "case": row["case"],
                "scene": row["scene"],
                "story_mode": row["story_mode"],
                "review_points": row["review_points"],
                "prompt_version": row["evidence"]["prompt_version"],
                "config_version": row["evidence"]["config_version"],
                "context_key": row["evidence"]["context_key"],
                "identity_reference_id": row["evidence"]["identity_reference_id"],
                "identity_sha256": row["evidence"]["identity_sha256"],
                "references": row["evidence"]["references"],
                "size": row["size"],
                "fact_input": row["fact_input"],
            }
            for row in rows
        ],
    }


CONTACT_SHEET_CSS = """
body{font-family:system-ui,"PingFang SC","Microsoft YaHei",sans-serif;margin:24px;
background:#f6f4f0;color:#22201d}
h1{font-size:20px;margin:0 0 4px}.sub{color:#6b665f;font-size:13px;margin-bottom:20px}
.card{background:#fff;border:1px solid #e3ded6;border-radius:14px;padding:16px;margin-bottom:14px}
.scene{font-weight:600;font-size:15px;margin-bottom:8px}
.meta{font-size:12px;color:#6b665f;margin-bottom:10px;line-height:1.7}
.slot{display:inline-block;width:150px;height:150px;border:1px dashed #c9c2b6;border-radius:10px;
background:#faf8f5;color:#9c958a;font-size:12px;text-align:center;line-height:150px;margin-right:12px;
vertical-align:top}
.prompt{font-size:13px;line-height:1.8;white-space:pre-wrap;background:#faf8f5;
border-radius:10px;padding:12px;margin-top:8px}
.tag{display:inline-block;background:#eef1ea;border-radius:999px;padding:2px 9px;
font-size:11px;margin-right:6px;color:#4c5346}
.warn{background:#fff6e6;border-color:#e8d5a8;color:#6a5526;padding:10px 14px;border-radius:10px;
font-size:13px;margin-bottom:18px}
"""


def contact_sheet(rows: list[dict], generated_at: str) -> str:
    cards = []
    for row in rows:
        evidence = row["evidence"]
        tags = "".join(
            f'<span class="tag">{name}</span>' for name in evidence["prompt_checks"]
        )
        template = row.get("current_template")
        template_block = ""
        if template and template.get("available"):
            template_block = (
                '<div class="meta">当前线上模板（对照）</div>'
                f'<div class="prompt">{template["prompt"]}</div>'
            )
        elif template:
            template_block = f'<div class="meta">当前线上模板不可用：{template["reason"]}</div>'
        cards.append(
            f'<div class="card"><div class="scene">{row["case"]}</div>'
            f'<div class="meta">配方 {evidence["recipe"]} · 镜头 {evidence["camera"]} · '
            f'构图 {evidence["composition"]} · {evidence["story_mode"]} · '
            f'由 {evidence["directed_by"]} 导演<br>'
            f'参考 {evidence["references"]} · 提示版本 {evidence["prompt_version"]} · '
            f'{row["prompt_length"]} 字</div>'
            f'<div>{tags}</div>'
            f'<div class="meta" style="margin-top:8px">看真图时逐条核对（人审，不是程序结论）：'
            + "；".join(row["review_points"]) + "</div>"
            f'<div style="margin-top:10px"><span class="slot">旧模板出图<br>（未生成）</span>'
            f'<span class="slot">新导演出图<br>（未生成）</span></div>'
            f'<div class="prompt">{row["prompt"]}</div>{template_block}</div>'
        )
    return (
        f"<!doctype html><html lang=\"zh\"><meta charset=\"utf-8\">"
        f"<title>照片导演离线联系表</title><style>{CONTACT_SHEET_CSS}</style>"
        f"<h1>照片导演离线联系表</h1>"
        f'<div class="sub">生成于 {generated_at} · 包 P / claude-20260923-055300-ada5</div>'
        f'<div class="warn">图位全部为空：本页只是提示词与参数的人审底稿，'
        f'<b>没有调用任何供应商、没有产生任何图片或费用</b>。'
        f'视觉质量未验证——像不像它，必须由主人看真图来判断。</div>'
        + "".join(cards)
        + "</html>"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="照片导演离线评测（默认禁网、不发请求）")
    parser.add_argument("--out", required=True, help="输出目录")
    parser.add_argument("--compare-template", action="store_true", help="同时渲染当前线上模板提示词作对照")
    parser.add_argument("--dry-run", action="store_true", help="额外写出真实成图执行单（仍然不发送）")
    parser.add_argument("--pet", help="真实测试宠物规格 JSON；不给就只能生成占位稿")
    args = parser.parse_args()

    block_network()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = build_rows(compare_template=args.compare_template)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": generated_at,
        "network": "blocked",
        "provider_calls": 0,
        "director_mode": "rule (未注入模型端口)",
        "sources": source_fingerprints(),
        "scenes": rows,
    }
    report["offline_sheet"] = offline_sheet(rows)
    if args.dry_run:
        pet, problems = load_pet_spec(args.pet)
        sheet = pairs_sheet(rows, pet, problems)
        report["execution_sheet"] = sheet
        (out / "photo-director-pairs-sheet.json").write_text(
            json.dumps(sheet, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    (out / "photo-director-offline.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "photo-director-contact-sheet.html").write_text(
        contact_sheet(rows, generated_at), encoding="utf-8"
    )
    print(f"写出 {out / 'photo-director-offline.json'}")
    print(f"写出 {out / 'photo-director-contact-sheet.html'}")
    if args.dry_run:
        print(f"写出 {out / 'photo-director-pairs-sheet.json'} — {sheet['status'].split(chr(8212))[0].strip()}")
        for problem in sheet["blocking"]:
            print(f"  阻塞：{problem}")
    print(f"离线用例 {len(rows)} 个；供应商调用 0 次；费用 0；视觉质量未验证。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
