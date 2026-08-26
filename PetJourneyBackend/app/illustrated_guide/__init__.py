"""图文攻略引擎包（架构审计 P1-2：illustrated_guide.py 685 行 > 400 建包）。

历史导入面保持不变：`from app.illustrated_guide import IllustratedGuideEngine`；
实现按职责拆为 engine（编排）/ prompts（提示词）/ media（出图缓存）三个模块。
"""

from .engine import IllustratedGuideEngine

__all__ = ["IllustratedGuideEngine"]
