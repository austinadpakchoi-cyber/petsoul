#!/usr/bin/env python3
"""爪爪驾校的跨语言样例与前端离线数据（由后端生成，前端不手改）。

生成物：
- ``PetJourneyWeb/tests/fixtures/driving-golden.json``：若干“场地配置 + 操作记录 → 逐 tick 快照摘要与判定事件”的标准样例。
  前端 ``tests/driving-sim.test.ts`` 用 TypeScript 版模拟逐位比对，保证服务端复算与前端实时驾驶结果一致。
- ``PetJourneyWeb/src/fixtures/driving-school.json``：fixture 模式与比赛现场体验版用的课程与场地（不含正式题库与答案）。

用法（仓库根目录）：
    python scripts/gen_driving_fixtures.py          # 重新生成
    python scripts/gen_driving_fixtures.py --check  # 生成物与代码不一致即 exit 1（后端测试也会调用）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "PetJourneyBackend"
GOLDEN_OUT = REPO_ROOT / "PetJourneyWeb" / "tests" / "fixtures" / "driving-golden.json"
OFFLINE_OUT = REPO_ROOT / "PetJourneyWeb" / "src" / "fixtures" / "driving-school.json"


def _setup() -> None:
    for path in (BACKEND_DIR, BACKEND_DIR / "tests"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def golden() -> dict:
    _setup()
    from app.web_driving.courses import course_for
    from app.web_driving.replay import Replay
    from driving_bots import Driver, curve_bot, reverse_park_bot, route_bot, side_park_bot

    def trace(course: dict, events: list[dict], ticks: int, every: int = 97) -> dict:
        replay = Replay(course)
        marks = []
        for start in range(0, ticks, every):
            upto = min(ticks, start + every)
            replay.apply([e for e in events if start <= e["t"] < upto], upto)
            car = replay.car
            marks.append({"tick": replay.tick, "car": [car.x, car.y, car.hx, car.hy, car.v, car.s, car.gear]})
            if replay.status != "running":
                break
        return {"marks": marks, "final": replay.snapshot()}

    cases = []
    scripted = [
        ("reverse_park.a", "reverse_park", "a", reverse_park_bot(2.8, 2.0, 1)),
        ("reverse_park.b", "reverse_park", "b", reverse_park_bot(2.8, 2.0, -1)),
        ("side_park.a", "side_park", "a", side_park_bot(3.8, 0.8, 1)),
        ("side_park.b", "side_park", "b", side_park_bot(3.8, 0.8, -1)),
        ("side_park.b.sloppy", "side_park", "b", side_park_bot(5.6, 0.62, -1)),
        ("curve.a", "curve", "a", curve_bot(1)),
        ("curve.b", "curve", "b", curve_bot(-1)),
        ("route.a", "route", "a", route_bot()),
        ("route.b.no_signals", "route", "b", route_bot(signals=False, invite_open=True)),
        ("route.a.red_light", "route", "a", route_bot(obey=False)),
    ]
    for name, item, variant, bot in scripted:
        course = course_for(item, variant)
        driver = Driver(course).run(bot)
        cases.append({"name": name, "course": course, "events": driver.events, "ticks": driver.tick, **trace(course, driver.events, driver.tick)})
    wild = course_for("reverse_park", "a")
    wild_events = [{"t": 0, "c": "t", "v": 1}, {"t": 5, "c": "s", "v": 12}, {"t": 40, "c": "g", "v": -1}, {"t": 70, "c": "s", "v": -12}, {"t": 120, "c": "b", "v": 1},
                   {"t": 121, "c": "t", "v": 0}, {"t": 150, "c": "g", "v": -1}, {"t": 150, "c": "b", "v": 0}, {"t": 151, "c": "t", "v": 1}, {"t": 300, "c": "s", "v": 3}]
    cases.append({"name": "reverse_park.a.wild", "course": wild, "events": wild_events, "ticks": 900, **trace(wild, wild_events, 900)})
    return {"generator": "scripts/gen_driving_fixtures.py", "cases": cases}


def offline() -> dict:
    _setup()
    from app.web_driving.courses import PRACTICE_ITEMS, VARIANTS, course_for
    from app.web_driving.curriculum import PET_LINES, curriculum

    items = sorted({item for names in PRACTICE_ITEMS.values() for item in names})
    return {"generator": "scripts/gen_driving_fixtures.py", "curriculum": {**curriculum(), "pet_lines": PET_LINES},
            "courses": {f"{item}.{variant}": course_for(item, variant) for item in items for variant in VARIANTS}}


def dump(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outputs = {GOLDEN_OUT: dump(golden()), OFFLINE_OUT: dump(offline())}
    stale = [path for path, text in outputs.items() if not path.exists() or path.read_text(encoding="utf-8") != text]
    if args.check:
        for path in stale:
            print(f"驾校样例已过期：{path.relative_to(REPO_ROOT)}（运行 python scripts/gen_driving_fixtures.py）")
        if not stale:
            print("驾校样例与后端一致。")
        return 1 if stale else 0
    for path, text in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"写入 {path.relative_to(REPO_ROOT)}（{len(text) // 1024} KB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
