"""执行者（世界推进 / AI 思考两条线）现在是什么状态：**按运行配置判，不只看租约**（c84a 审查 ADM-HEALTH-02）。

- **按配置关着**（`web_world_runner=off`，或每轮间隔 ≤ 0）：不是故障，界面灰色；最后一次心跳照样保留供查询。
- **应该在跑、心跳有效**：在岗。
- **应该在跑、但心跳过期或根本没登记**：失联——照样标红。不能因为「也可能是有意关的」就一律掩盖：开着＋过期租约仍然报故障。

两条线都由同一个执行者启动（`app/main.py`：runner=embedded 在网站进程里跑，runner=worker 交给独立进程），所以「该不该在跑」对两条线是同一个判断。
「有意暂停」在这套系统里只有「新增 AI 调用」那个开关，它不停执行者，界面上在开关一栏单独显示。
"""

from __future__ import annotations

from typing import Any

LANE_NAMES = ("world", "cognition")
LANE_STATES = ("configured_off", "healthy", "lost")


def runner_configured(runner: str | None, tick_seconds: Any) -> bool:
    """按配置，执行者该不该在跑。"""
    try:
        tick = float(tick_seconds or 0)
    except (TypeError, ValueError):
        tick = 0.0
    return (runner or "embedded") in ("embedded", "worker") and tick > 0


def configured_from_settings(settings) -> bool:
    return runner_configured(getattr(settings, "web_world_runner", "embedded"), getattr(settings, "web_world_tick_seconds", 0))


def lane_state(configured: bool, alive: bool) -> str:
    if not configured:
        return "configured_off"
    return "healthy" if alive else "lost"
