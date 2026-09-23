"""既有引擎/存储 → 网页契约的适配层。

规则：适配器只读旧存储或调用旧引擎的公开方法，不修改旧 iOS 路由与表语义；
每个页面不自行解释旧接口差异，统一在这里转换。
"""

from .home_snapshot import LEGACY_MISSING_CAPABILITIES, build_legacy_home_snapshot, legacy_home_id

__all__ = ["LEGACY_MISSING_CAPABILITIES", "build_legacy_home_snapshot", "legacy_home_id"]
