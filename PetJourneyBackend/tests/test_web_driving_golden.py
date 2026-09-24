"""跨语言样例是否过期：后端改了模拟、场地或课程却没有重新生成前端样例时，这里会失败。

前端 tests/driving-sim.test.ts 用同一份样例比对 TypeScript 版模拟（服务端复算与前端实时驾驶结果一致）。

## 为什么不再逐字节比对

原先这里是 `assertEqual(path.read_text(), dump(golden()))`，**字符串逐位相等**。
它在 Windows 上一直是绿的，在 Linux 容器里必然红——而且红得完全合理：

    math.tan(2.5)   Windows  -0.7470222972386602   -0x1.7e79b4e00bb14p-1
                    Linux    -0.7470222972386603   -0x1.7e79b4e00bb15p-1   ← 位模式差 1 ULP

IEEE 754 **不要求**超越函数正确舍入，各家 libm 的 `tan/sin/cos` 末位可以不同。
样例在 Windows 上生成，拿到 Linux 重算必然对不上。

**所以逐位断言实际上断言的是「libm 在所有平台逐位可复现」——这比它想证明的
「模拟逻辑是对的」强了几个数量级，而且那个更强的命题是假的。**
把样例在 Linux 上重新生成不是修复，只会把失败挪到 Windows 和前端。

## 现在怎么比

**分三层，各钉各的，没有一层被放松：**

1. **格式**：把盘上数据用同一个 `dump()` 规则重新序列化，必须与盘上文本**逐字节相同**。
   这钉住分隔符、键顺序、末尾换行，且不受浮点影响（用的是盘上自己的数据）。
2. **结构与离散值**：键集合、数组长度、字符串、整数、布尔、None——**一律严格相等**。
   题目、答案、场地名、课程编号都在这一层，**一个字符都不许差**。
3. **浮点数值**：只有这一层用容差，界限来自实测而不是拍脑袋。

## 容差的依据

在 Linux 容器（glibc 2.41 / CPython 3.12.14）里重算全部样例，与 Windows 生成的盘上样例
逐字段比对，**实测**：

    浮点有差异的字段  196 个
    非浮点却不同的      0 个      ← 离散值跨平台零差异
    结构/键/长度差异    0 个
    ULP 差：最小 1，中位 2，**最大 42**；相对误差最大 9.22e-15

`MAX_ULPS = 128` 取实测最大值的约 3 倍并向上取到 2 的幂，相对量级约 2.8e-14。
**它比跨平台噪声大一个数量级，比任何有物理意义的改动小十个数量级**——
改场地坐标、车辆参数、时间步长，哪怕只改百万分之一，相对误差也在 1e-6 量级，
比这个容差大八个数量级。`test_a_real_change_is_still_caught` 就是钉这件事的。
"""

from __future__ import annotations

import copy
import importlib.util
import json
import struct
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "gen_driving_fixtures.py"

# 依据见模块 docstring：实测跨平台最大 42 ULP，取 3 倍余量并向上取到 2 的幂。
MAX_ULPS = 128
# 绝对下限：几何计算里落在这个量级的值就是"零"，此时 ULP 距离没有意义（会跨越非规格化数）。
NEAR_ZERO = 1e-12


def _ulps_apart(a: float, b: float) -> int:
    """两个 double 之间隔了几个可表示的数。

    按 ULP 而不是绝对值或相对值度量：绝对容差对大数太松、对小数太紧；相对容差在
    接近 0 处失效；而 libm 的误差本来就是按 ULP 规定的，这一层的成因就是 libm。
    """
    ia = struct.unpack("<q", struct.pack("<d", a))[0]
    ib = struct.unpack("<q", struct.pack("<d", b))[0]
    if ia < 0:
        ia = (1 << 63) - ia
    if ib < 0:
        ib = (1 << 63) - ib
    return abs(ia - ib)


def compare(expected, actual, path: str = "") -> list[str]:
    """逐字段比。返回问题清单；空表示一致。

    **只有 float 走容差**，其余一切（键、长度、str、int、bool、None）严格相等。
    `bool` 先于 `int` 判断——`isinstance(True, int)` 是真，漏掉这一步会让
    `True` 和 `1` 被当成同一个值。
    """
    problems: list[str] = []
    if isinstance(expected, bool) or isinstance(actual, bool):
        if expected is not actual:
            problems.append(f"{path}: 布尔 {expected!r} → {actual!r}")
    elif isinstance(expected, dict) and isinstance(actual, dict):
        missing, extra = sorted(set(expected) - set(actual)), sorted(set(actual) - set(expected))
        if missing:
            problems.append(f"{path}: 少了键 {missing[:5]}")
        if extra:
            problems.append(f"{path}: 多了键 {extra[:5]}")
        for key in sorted(set(expected) & set(actual)):
            problems += compare(expected[key], actual[key], f"{path}.{key}")
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            problems.append(f"{path}: 长度 {len(expected)} → {len(actual)}")
        else:
            for i, (x, y) in enumerate(zip(expected, actual)):
                problems += compare(x, y, f"{path}[{i}]")
    elif isinstance(expected, float) or isinstance(actual, float):
        x, y = float(expected), float(actual)
        if x == y:
            return problems
        if abs(x) < NEAR_ZERO and abs(y) < NEAR_ZERO:
            return problems
        gap = _ulps_apart(x, y)
        if gap > MAX_ULPS:
            problems.append(f"{path}: {x!r} → {y!r}（相差 {gap} ULP，上限 {MAX_ULPS}）")
    elif expected != actual:
        problems.append(f"{path}: {expected!r} → {actual!r}")
    return problems


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_driving_fixtures", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GoldenFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_generator()

    def test_generated_fixtures_are_up_to_date(self) -> None:
        """场地/课程/物理改了却没重新生成样例——这里会失败。浮点末位差异除外。"""
        cases = ((self.module.GOLDEN_OUT, self.module.golden()),
                 (self.module.OFFLINE_OUT, self.module.offline()))
        for path, fresh in cases:
            with self.subTest(path=path.name):
                self.assertTrue(path.exists(), f"缺少 {path}，运行 python scripts/gen_driving_fixtures.py")
                on_disk = json.loads(path.read_text(encoding="utf-8"))
                problems = compare(on_disk, fresh, path.name)
                self.assertEqual(
                    problems, [],
                    "样例已过期：运行 python scripts/gen_driving_fixtures.py\n" + "\n".join(problems[:10]))

    def test_fixture_files_keep_the_canonical_format(self) -> None:
        """格式这一层仍**逐字节**严格：分隔符、键顺序、末尾换行一个都不许变。

        用盘上自己的数据重新序列化来比，所以它只看格式，不受跨平台浮点差异影响。
        """
        for path in (self.module.GOLDEN_OUT, self.module.OFFLINE_OUT):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(
                    self.module.dump(json.loads(text)), text,
                    f"{path.name} 不再是 dump() 的规范形式（分隔符/键顺序/末尾换行）")

    def test_a_real_change_is_still_caught(self) -> None:
        """容差只放过浮点噪声，**放不过任何有物理意义的改动**。

        逐档试：1e-6（改千分之一毫米量级的场地尺寸）一直到 1e-13，都必须被抓到；
        只有落到 1e-15 这种纯末位噪声才放过。这条一旦失败，说明容差被放松到了
        看不见真实改动的地步。
        """
        on_disk = json.loads(self.module.GOLDEN_OUT.read_text(encoding="utf-8"))
        target = on_disk["cases"][0]["final"]["car"]
        index = next(i for i, v in enumerate(target) if isinstance(v, float) and abs(v) > NEAR_ZERO)
        original = target[index]

        for scale in (1e-6, 1e-9, 1e-12, 1e-13):
            with self.subTest(scale=scale):
                changed = copy.deepcopy(on_disk)
                changed["cases"][0]["final"]["car"][index] = original * (1 + scale)
                self.assertNotEqual(
                    compare(on_disk, changed, "golden"), [],
                    f"相对 {scale} 的改动没被抓到——容差太松了")

        near_noise = copy.deepcopy(on_disk)
        near_noise["cases"][0]["final"]["car"][index] = original * (1 + 1e-15)
        self.assertEqual(
            compare(on_disk, near_noise, "golden"), [],
            "1e-15 是跨平台末位噪声量级，不该被当成改动")

    def test_a_changed_discrete_value_is_never_tolerated(self) -> None:
        """离散值不走容差：题目、答案、场地名、编号、布尔——改一个字符就必须失败。"""
        on_disk = json.loads(self.module.OFFLINE_OUT.read_text(encoding="utf-8"))
        for mutate, why in (
            (lambda d: d.__setitem__("courses", {}), "整段课程被清空"),
            (lambda d: d["courses"].__setitem__("__extra__", {}), "多出一个课程键"),
        ):
            with self.subTest(why=why):
                changed = copy.deepcopy(on_disk)
                mutate(changed)
                self.assertNotEqual(compare(on_disk, changed, "offline"), [], f"{why} 没被抓到")

    def test_offline_data_has_no_formal_answers(self) -> None:
        text = (Path(__file__).resolve().parents[2] / "PetJourneyWeb" / "src" / "fixtures" / "driving-school.json").read_text(encoding="utf-8")
        self.assertNotIn('"answer"', text, "前端离线数据里不能带正式题库的答案")
        self.assertNotIn("s1.stop.1", text)


if __name__ == "__main__":
    unittest.main()
