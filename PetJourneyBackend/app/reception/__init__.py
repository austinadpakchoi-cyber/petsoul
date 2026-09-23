"""接待与受控记忆领域（R0：边界 + MemoryPolicy 纯函数；业务实现待用户分配）。

拆分说明：新领域按 AGENTS.md 建包；旧 ``memory_store`` / ``repositories.memory`` 不改，
接待草稿与 CareNote/MemoryGrant 使用独立新表（迁移 0300–0399）。
"""

from .policy import NEVER_PROJECTED_KINDS, POLICY_VERSION, build_home_welcome, project_memory
from .service import ReceptionService

__all__ = [
    "NEVER_PROJECTED_KINDS",
    "POLICY_VERSION",
    "ReceptionService",
    "build_home_welcome",
    "project_memory",
]
