"""跨语言样例是否过期：后端改了模拟、场地或课程却没有重新生成前端样例时，这里会失败。

前端 tests/driving-sim.test.ts 用同一份样例逐位比对 TypeScript 版模拟（服务端复算与前端实时驾驶结果一致）。
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "gen_driving_fixtures.py"


class GoldenFixtureTests(unittest.TestCase):
    def test_generated_fixtures_are_up_to_date(self) -> None:
        spec = importlib.util.spec_from_file_location("gen_driving_fixtures", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for path, text in ((module.GOLDEN_OUT, module.dump(module.golden())), (module.OFFLINE_OUT, module.dump(module.offline()))):
            with self.subTest(path=path.name):
                self.assertTrue(path.exists(), f"缺少 {path}，运行 python scripts/gen_driving_fixtures.py")
                self.assertEqual(path.read_text(encoding="utf-8"), text, "样例已过期：运行 python scripts/gen_driving_fixtures.py")

    def test_offline_data_has_no_formal_answers(self) -> None:
        text = (Path(__file__).resolve().parents[2] / "PetJourneyWeb" / "src" / "fixtures" / "driving-school.json").read_text(encoding="utf-8")
        self.assertNotIn('"answer"', text, "前端离线数据里不能带正式题库的答案")
        self.assertNotIn("s1.stop.1", text)


if __name__ == "__main__":
    unittest.main()
