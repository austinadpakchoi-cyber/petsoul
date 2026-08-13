"""Repository mixins：按聚合根拆分 JourneyStorage 的方法。

原 app/storage.py 单类 1672 行 / 90 方法 / 22 表，属 God File 反模式。
这里每个 mixin 对应一个资源域，`JourneyStorage` 在 storage.py 中通过多重继承聚合，
对外 API 保持不变（调用方仍 `from app.storage import JourneyStorage`）。
"""
