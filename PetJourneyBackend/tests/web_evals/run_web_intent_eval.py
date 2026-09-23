"""网页意图判断层离线对照（手动运行，不属于单元测试，不在 CI 里调用付费接口）。

用法（在 PetJourneyBackend 目录）：
  python tests/web_evals/run_web_intent_eval.py --provider rule
  python tests/web_evals/run_web_intent_eval.py --provider configured_llm --env-file data/secrets/web-providers.env --report ../docs/contracts/INTENT-EVAL-20260922.md

判定：expect 中的信号都出现、forbid 中的都不出现；forbid_unquoted 表示该类信号只能以 quoted=true 出现；
forbid_current_command 表示该类信号不能标成当前命令；expect_any 至少出现其一。只报告通过数与逐条结果，不宣称正确率可外推。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from app.intent_layer import RuleIntentJudge  # noqa: E402
from app.intent_layer.judge import JudgeUnavailable  # noqa: E402
from app.intent_layer.llm_judge import PROMPT_VERSION, ConfiguredLLMJudge  # noqa: E402
from app.web_providers.llm import OpenAICompatibleChat  # noqa: E402


class _CountingMeter:
    def __init__(self) -> None:
        self.calls = 0
        self.failures = 0

    def allow(self, provider: str) -> bool:
        return self.calls < 60  # 本脚本自限：一次运行最多 60 次模型调用

    def record(self, provider: str, ok: bool, error: str | None = None) -> None:
        self.calls += 1
        self.failures += 0 if ok else 1


def load_env(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def check(case: dict, signals) -> tuple[bool, list[str]]:
    kinds = {s.kind.value for s in signals}
    problems = [f"缺少 {k}" for k in case.get("expect", []) if k not in kinds]
    problems += [f"不该有 {k}" for k in case.get("forbid", []) if k in kinds]
    problems += [f"{k} 未标引用" for k in case.get("forbid_unquoted", []) if any(s.kind.value == k and not s.quoted for s in signals)]
    problems += [f"{k} 被当成当前命令" for k in case.get("forbid_current_command", []) if any(s.kind.value == k and s.temporal.value == "current_command" for s in signals)]
    if case.get("expect_any") and not (kinds & set(case["expect_any"])):
        problems.append("应至少出现 " + "/".join(case["expect_any"]))
    return not problems, problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["rule", "configured_llm"], default="rule")
    parser.add_argument("--env-file")
    parser.add_argument("--report")
    args = parser.parse_args()
    cases = json.loads((HERE / "web_intent_cases.json").read_text(encoding="utf-8"))
    meter = _CountingMeter()
    requested_model = None
    if args.provider == "rule":
        judge = RuleIntentJudge()
    else:
        env = load_env(args.env_file) if args.env_file else dict(os.environ)
        requested_model = env.get("PETJOURNEY_AGENT_MODEL", "deepseek-chat")
        chat = OpenAICompatibleChat(base_url=env.get("PETJOURNEY_OPENAI_BASE_URL", "https://api.deepseek.com/v1"), api_key=env["OPENAI_API_KEY"],
                                    model=requested_model, timeout=30, meter=meter)  # type: ignore[arg-type]
        judge = ConfiguredLLMJudge(chat)
    rows, passed, latencies, effective = [], 0, [], set()
    for case in cases:
        started = time.perf_counter()
        try:
            result = judge.judge(case["text"], [])
            ok, problems = check(case, result.signals)
            summary = ", ".join(f"{s.kind.value}/{s.temporal.value}{'/引' if s.quoted else ''}{'/限' if s.usage_limits else ''}" for s in result.signals)
            if result.effective_model:
                effective.add(result.effective_model)
        except JudgeUnavailable as exc:
            ok, problems, summary = False, [f"不可用：{exc.reason}"], "-"
        latencies.append(int((time.perf_counter() - started) * 1000))
        passed += ok
        rows.append((case["id"], case["text"], summary, "通过" if ok else "未过：" + "；".join(problems)))
    lat = sorted(latencies)
    header = [
        f"- 判断器：{args.provider}" + (f"（请求模型 {requested_model}；服务端返回 {', '.join(sorted(effective)) or '未知'}；提示版本 {PROMPT_VERSION}）" if requested_model else "（本地规则基线）"),
        f"- 用例：{len(cases)} 条（tests/web_evals/web_intent_cases.json，人工标注）；通过 {passed} 条",
        f"- 耗时：中位 {lat[len(lat) // 2]} ms，最慢 {lat[-1]} ms；模型调用 {meter.calls} 次（失败 {meter.failures}）",
    ]
    table = ["| 用例 | 原句 | 输出信号 | 结果 |", "|---|---|---|---|"] + [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in rows]
    text = "\n".join(header + [""] + table) + "\n"
    print(text)
    if args.report:
        report = Path(args.report)
        existing = report.read_text(encoding="utf-8") if report.exists() else "# 网页意图判断层离线对照\n\n"
        report.write_text(existing.rstrip() + f"\n\n## {args.provider}\n\n" + text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
