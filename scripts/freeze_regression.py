"""冻结窗口里的那一次整体回归：跑之前和跑之后都按文件指纹存证，漂移就判为无法归属。

为什么要工具而不是手工跑：这次运行的价值全在"**它到底跑的是哪一版**"。
Python 进程在启动时把模块导入内存，之后磁盘上的改动它不会重新读取——所以
"结束时磁盘上是什么"并不等于"这次执行的是什么"。唯一站得住的说法是：
**跑之前和跑之后的指纹完全一致**，那才能把结果绑到那一组指纹上；只要有一份变了，
这次运行就只能记成"无法归属"，改期重跑，不能用"结束时版本通过"糊过去。

用法（在仓库根目录）：
    python scripts/freeze_regression.py --label batch-13 --known-failing Q-C10 Q-C11 Q-C13 Q-C19

产出（默认写到 data/reviews/freeze/<label>-<时间>/）：
    manifest-before.json / manifest-after.json / run.log / verdict.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "PetJourneyBackend"
# 进这次存证的范围：后端源码、测试、迁移。前端与文档不在内（冻结期间它们照常可以改）
WATCHED = ("app", "tests")
# 不只是 .py：用例真正读进去的数据同样是"这次跑的是什么"的一部分。
# 例如照片导演的 tests/fixtures/photo_director/scenes.json——它一改，同样的代码就会跑出不同结果。
WATCHED_SUFFIXES = (".py", ".json", ".yaml", ".yml", ".csv", ".txt", ".sql", ".png")


TOOL_VERSION = "freeze-regression/1.3"


def tool_fingerprint() -> str:
    """工具自己的指纹：换了工具就是换了口径，产物里要能看出来。"""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]


def manifest(base: Path | None = None, folders: tuple[str, ...] = WATCHED) -> dict[str, str]:
    """被测范围里每个源码与数据文件的指纹。键是相对 base 的路径，排序后写出，便于逐条比对。"""
    base = base or BACKEND
    files: dict[str, str] = {}
    for folder in folders:
        root = base / folder
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix.lower() not in WATCHED_SUFFIXES:
                continue
            files[str(path.relative_to(base)).replace("\\", "/")] = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return files


def aggregate(files: dict[str, str]) -> str:
    """整组指纹的单一摘要：记录里引用一个值就够，逐条清单在 manifest 文件里。"""
    blob = "\n".join(f"{name}:{digest}" for name, digest in sorted(files.items()))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def drift_between(before: dict[str, str], after: dict[str, str]) -> list[dict[str, str]]:
    changed: list[dict[str, str]] = []
    for name in sorted(set(before) | set(after)):
        old, new = before.get(name), after.get(name)
        if old != new:
            changed.append({"file": name, "before": old or "（新增）", "after": new or "（删除）"})
    return changed


def parse_commitment(raw: str) -> dict[str, object]:
    """`名字=起..止@文件范围` → 结构化。格式不对就原样记下并标为无效，不猜。"""
    name, _, rest = raw.partition("=")
    span, _, scope = rest.partition("@")
    start_text, _, end_text = span.partition("..")

    def at(text: str):
        try:
            return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
        except ValueError:
            return None

    start, end = at(start_text), at(end_text)
    return {"raw": raw, "window": name.strip(), "start": start, "end": end, "scope": scope.strip(),
            "valid": bool(name.strip()) and start is not None and end is not None and start < end and bool(scope.strip())}


def check_window(commitments: list[dict], parties: list[str], started: datetime, finished: datetime) -> dict[str, object]:
    """真的核验一遍，不是"填了字就算"。四件事任何一件不成立都不算可归属：

    1. 六方到齐（parties 里每一个都要有一条承诺）；
    2. 每条承诺格式有效，且**写明了文件范围**（空范围等于没承诺）；
    3. 各自区间存在**共同交集**；
    4. 这次运行的起止**整段落在交集里**——开跑早于交集起点、或跑完晚于交集终点（超时）都不行。
    """
    by_name = {c["window"]: c for c in commitments}
    missing = [p for p in parties if p not in by_name]
    invalid = [c["raw"] for c in commitments if not c["valid"]]
    problems: list[str] = []
    if missing:
        problems.append(f"缺少这些窗口的承诺：{', '.join(missing)}")
    if invalid:
        problems.append(f"这些承诺格式无效或没写文件范围：{invalid}")
    common_start = common_end = None
    if not missing and not invalid and commitments:
        common_start = max(c["start"] for c in commitments)
        common_end = min(c["end"] for c in commitments)
        if common_start >= common_end:
            problems.append(f"各窗口区间没有交集（最晚的起点 {_iso(common_start)} 不早于最早的终点 {_iso(common_end)}）")
        else:
            if started < common_start:
                problems.append(f"开跑（{_iso(started)}）早于共同区间起点 {_iso(common_start)}")
            if finished > common_end:
                problems.append(f"跑完（{_iso(finished)}）超出共同区间终点 {_iso(common_end)}——超时")
    return {"parties_required": parties, "committed": sorted(by_name), "missing": missing, "invalid": invalid,
            "common_start": _iso(common_start), "common_end": _iso(common_end),
            "run_started": _iso(started), "run_finished": _iso(finished),
            "problems": problems, "ok": not problems}


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def run_suite(log_path: Path) -> tuple[int, str, datetime, datetime]:
    """新起一个 python 进程跑全量。TZ=UTC 与 CI 对齐；完整输出落盘，不截断。"""
    env = {**os.environ, "TZ": "UTC", "PYTHONIOENCODING": "utf-8"}
    started = datetime.now(timezone.utc)
    result = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"],
                            cwd=BACKEND, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    finished = datetime.now(timezone.utc)
    output = (result.stdout or "") + (result.stderr or "")
    log_path.write_text(f"# started_at={started.isoformat()}\n# finished_at={finished.isoformat()}\n"
                        f"# returncode={result.returncode}\n\n{output}", encoding="utf-8")
    return result.returncode, output, started, finished


def summarise(output: str) -> dict[str, object]:
    """从测试报告里取结论行。以报告为准，不从输出里的点号推算用例数。"""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    ran = next((line for line in reversed(lines) if line.startswith("Ran ")), None)
    verdict = next((line for line in reversed(lines) if line.startswith(("OK", "FAILED"))), None)
    failures = [line for line in lines if line.startswith(("FAIL:", "ERROR:"))]
    return {"ran": ran, "result": verdict, "failures": failures}


def self_check() -> int:
    """在**临时小样本**上验证漂移检测：改动、新增、删除三种都要被认出来。

    不拿整仓回归来验工具——那既慢又会把别人正在编辑的文件卷进来，还证明不了漂移判定本身。
    """
    import shutil
    import tempfile

    base = Path(tempfile.mkdtemp(prefix="freeze-selfcheck-"))
    try:
        (base / "app").mkdir()
        (base / "tests").mkdir()
        (base / "tests" / "fixtures").mkdir()
        (base / "tests" / "fixtures" / "scenes.json").write_text('{"a": 1}', encoding="utf-8")
        (base / "app" / "keep.py").write_text("x = 1", encoding="utf-8")
        (base / "app" / "edit.py").write_text("y = 1", encoding="utf-8")
        (base / "tests" / "gone.py").write_text("z = 1", encoding="utf-8")
        before = manifest(base)

        (base / "app" / "edit.py").write_text("y = 2", encoding="utf-8")  # 改动
        (base / "tests" / "added.py").write_text("w = 1", encoding="utf-8")  # 新增
        (base / "tests" / "gone.py").unlink()  # 删除
        (base / "tests" / "fixtures" / "scenes.json").write_text('{"a": 2}', encoding="utf-8")  # 数据文件也算改动
        after = manifest(base)

        drift = {item["file"]: (item["before"], item["after"]) for item in drift_between(before, after)}
        checks = {
            "改动被认出": "app/edit.py" in drift and drift["app/edit.py"][0] != drift["app/edit.py"][1],
            "新增被认出": drift.get("tests/added.py", ("", ""))[0] == "（新增）",
            "删除被认出": drift.get("tests/gone.py", ("", ""))[1] == "（删除）",
            "没变的不报": "app/keep.py" not in drift,
            "数据文件（.json）也被纳入": "tests/fixtures/scenes.json" in drift,
            "整组摘要随之变化": aggregate(before) != aggregate(after),
        }
        checks.update(_window_checks())
        for name, ok in checks.items():
            print(f"  {'✔' if ok else '✘'} {name}")
        return 0 if all(checks.values()) else 1
    finally:
        shutil.rmtree(base, ignore_errors=True)


def _window_checks() -> dict[str, bool]:
    """小样本验证区间核验：齐备、缺人、没交集、超时、没写范围、格式错，六种都要判对。"""
    def at(text: str) -> datetime:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))

    parties = ["I", "A"]
    ok_pair = [parse_commitment("I=2026-09-23T00:00Z..2026-09-23T00:40Z@app+tests"),
               parse_commitment("A=2026-09-22T23:10Z..2026-09-23T01:10Z@A 的 14 份")]
    run = (at("2026-09-23T00:05Z"), at("2026-09-23T00:20Z"))
    late = (at("2026-09-23T00:05Z"), at("2026-09-23T00:50Z"))  # 跑过了交集终点
    early = (at("2026-09-22T23:50Z"), at("2026-09-23T00:20Z"))  # 交集还没开始就开跑
    no_overlap = [parse_commitment("I=2026-09-23T00:00Z..2026-09-23T00:10Z@app"),
                  parse_commitment("A=2026-09-23T00:20Z..2026-09-23T00:40Z@app")]
    no_scope = [parse_commitment("I=2026-09-23T00:00Z..2026-09-23T00:40Z@"),
                parse_commitment("A=2026-09-22T23:10Z..2026-09-23T01:10Z@A 的 14 份")]
    return {
        "区间齐备且运行落在交集内 → 可归属": check_window(ok_pair, parties, *run)["ok"],
        "少一个窗口 → 不可归属": not check_window(ok_pair[:1], parties, *run)["ok"],
        "区间没有交集 → 不可归属": not check_window(no_overlap, parties, *run)["ok"],
        "跑过了交集终点（超时）→ 不可归属": not check_window(ok_pair, parties, *late)["ok"],
        "开跑早于交集起点 → 不可归属": not check_window(ok_pair, parties, *early)["ok"],
        "承诺没写文件范围 → 不可归属": not check_window(no_scope, parties, *run)["ok"],
        "完全没有承诺 → 不可归属": not check_window([], parties, *run)["ok"],
    }


def _attribution_note(attributed: bool, drift: list, window: dict) -> str:
    if attributed:
        return ("结果可归属到 manifest-before.json 这一组指纹：运行前后一致，六方承诺齐备且本次运行整段落在共同区间内"
                f"（{window['common_start']} ～ {window['common_end']}）")
    reasons = []
    if drift:
        reasons.append(f"运行期间有 {len(drift)} 个文件变化")
    reasons += list(window["problems"])
    return "**无法归属**：" + "；".join(reasons) + "。这次结果不代表任何一版，需在冻结窗口内重跑"


def main() -> int:
    parser = argparse.ArgumentParser(description="冻结窗口里的整体回归（带版本归属）")
    parser.add_argument("--self-check", action="store_true", help="只在临时小样本上验证漂移检测，不跑任何测试")
    parser.add_argument("--commitment", nargs="*", default=[],
                        help="各窗口的冻结承诺，格式 名字=起..止@文件范围，例如 "
                             "I=2026-09-23T00:00Z..2026-09-23T00:40Z@app+tests+migrations")
    parser.add_argument("--parties", nargs="*", default=["I", "A", "B", "C", "Q", "P"],
                        help="本轮必须到齐的窗口；少一个就不算可归属")
    parser.add_argument("--label", help="这次冻结批次的名字，例如 batch-13")
    parser.add_argument("--known-failing", nargs="*", default=[], help="Q 已知失败的合同编号；单独记录，不被默认全绿覆盖")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")
    if args.self_check:
        return self_check()
    if not args.label:
        parser.error("--label 是必填的（除非只做 --self-check）")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.out) if args.out else BACKEND / "data" / "reviews" / "freeze" / f"{args.label}-{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    before = manifest()
    (out / "manifest-before.json").write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[冻结] 运行前：{len(before)} 个文件，整组指纹 {aggregate(before)}")

    code, output, started, finished = run_suite(out / "run.log")
    after = manifest()
    (out / "manifest-after.json").write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")

    drift = drift_between(before, after)
    # 前后哈希一致**只说明"跑完时和开跑时一样"**，排除不了中途改了又改回去。
    # 所以还要真的核验冻结承诺：六方到齐、都写了文件范围、区间有交集、这次运行整段落在交集里。
    commitments = [parse_commitment(raw) for raw in args.commitment]
    window = check_window(commitments, args.parties, started, finished)
    attributed = (not drift) and window["ok"]
    verdict = {
        "label": args.label,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "tool_version": TOOL_VERSION,
        "tool_fingerprint": tool_fingerprint(),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": sys.platform,
        "test_input": {"discover_start": "tests", "cwd": str(BACKEND), "pattern": "test*.py（unittest 默认）",
                       "watched_folders": list(WATCHED), "watched_suffixes": list(WATCHED_SUFFIXES), "tz": "UTC"},
        "freeze_commitments": [{k: v for k, v in c.items() if k != "start" and k != "end"} | {"start": _iso(c["start"]), "end": _iso(c["end"])} for c in commitments],
        "window_check": window,
        "command": "TZ=UTC python -B -m unittest discover -s tests（新进程，cwd=PetJourneyBackend）",
        "returncode": code,
        **summarise(output),
        "files_watched": len(before),
        "fingerprint_before": aggregate(before),
        "fingerprint_after": aggregate(after),
        "drift": drift,
        "attributable": attributed,
        "attribution_note": _attribution_note(attributed, drift, window),
        "known_failing_contracts": args.known_failing,
        "known_failing_note": "这些合同由 Q 独立判定，默认 discover 全绿不覆盖它们；要看它们的结论请查 Q 的记录",
    }
    (out / "verdict.json").write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[冻结] {verdict['ran']} / {verdict['result']}（退出码 {code}）")
    # 控制台与 verdict.json 说同一句话，不能一个说可归属、一个说不可归属
    print("[冻结] " + verdict["attribution_note"])
    for item in drift[:10]:
        print(f"        漂移 {item['file']}  {item['before']} → {item['after']}")
    if args.known_failing:
        print(f"[冻结] 另有 Q 的已知失败合同（不被本次全绿覆盖）：{', '.join(args.known_failing)}")
    print(f"[冻结] 证据目录：{out}")
    return 0 if attributed and code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
