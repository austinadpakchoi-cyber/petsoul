"""独立的世界任务进程：python -m app.web_worker

没人打开页面时推进世界（旅程事件、自主生活、到点回复、主动消息、驾校）并处理生图任务。
和 API 用同一份配置与数据库（同样的环境变量）；API 这边设 PETJOURNEY_WEB_WORLD_RUNNER=worker 就不再在进程内跑。
同一时刻只有一个进程推进世界（数据库租约）；本进程被停掉时释放租约，重启后接着跑——所有任务幂等，不会重复发工资、扣钱或发消息。
"""

from __future__ import annotations

import logging
import signal
import sys

from .config import load_settings
from .main import create_app

logger = logging.getLogger("petsoul.web_worker")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = load_settings()
    settings.web_world_runner = "worker"
    if settings.web_world_tick_seconds <= 0:
        logger.error("PETJOURNEY_WEB_WORLD_TICK_SECONDS <= 0：世界任务被关闭，任务进程不启动")
        return 2
    app = create_app(settings)
    web = app.state.web
    ticker, cognition = web.ticker, web.cognition
    for lane in (ticker, cognition):
        lane.lease.role = "worker"

    def stop(signum, frame) -> None:  # noqa: ARG001
        logger.info("收到停止信号，释放租约后退出")
        cognition.stop()
        ticker.stop()

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)
    if web.worker is not None:
        web.worker.start()  # 生图任务（只在供应商可用时存在）
    logger.info("世界任务进程启动：环境=%s 间隔=%ss 数据库=%s（世界线与认知线各一条，租约分开）",
                settings.web_environment, settings.web_world_tick_seconds, settings.database_path.name)
    cognition.start()  # 认知线单独一条线程：模型卡住不影响世界线的到期结算
    try:
        ticker.run_forever()
    finally:
        if web.worker is not None:
            web.worker.stop()
        cognition.stop()
        ticker.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
