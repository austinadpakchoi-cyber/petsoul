# agent_engine 模块化拆分记录

> 面向后续维护 `app/agent_engine/` 的开发者。本文记录 2026-08-13 完成的 God File
> 拆分方案、关键设计决策与验证方法，供后续新增 / 修改旅程引擎时遵循。

## 1. 背景与目标

`app/agent_engine.py` 原为单一 God File：单类 `JourneyEngine` 约 1548 行、75 个方法，
`import` 21 个模块，承载了旅行攻略、背包、纪念品、经济、世界模拟、照片、记忆、反馈、
主人交互等几乎所有业务编排。这与项目在 `providers/`、`repositories/`、`routers/`、
`schemas/` 上已确立的「按资源域拆分」惯例相悖。

**目标**：把 `JourneyEngine` 拆分为按场景域组织的独立 mixin，同时保证对外 API 与
75 个方法的行为**逐字一致**，不破坏任何历史调用方。

## 2. 拆分方案：多重继承 mixin 聚合

采用与 `repositories/` 完全相同的模式——**每个场景一个 mixin 文件，门面类通过 Python
多重继承把它们组合回 `JourneyEngine`**：

```python
# app/agent_engine/__init__.py（节选）
class JourneyEngine(
    JourneyEngineBaseMixin,
    JourneyEngineHelpersMixin,
    TraceMixin,
    LifecycleMixin,
    MemoryRecordingMixin,
    TravelQuestMixin,
    TravelBagMixin,
    SouvenirsMixin,
    EconomyMixin,
    WorldSimulationMixin,
    PhotoMixin,
    MemoryMixin,
    FeedbackMixin,
    OwnerInteractionMixin,
):
    pass

__all__ = [
    "JourneyEngine",
    "PetNotFoundError",
    "ThoughtNotFoundError",
    "TravelQuestNotFoundError",
]
```

## 3. 文件清单与职责

| 文件 | 基类 | 方法数 | 职责 |
|------|------|:---:|------|
| `base.py` | `JourneyEngineBaseMixin` | 2 | 连接 + schema 注入 |
| `helpers.py` | `JourneyEngineHelpersMixin` | 13 | 共享辅助 |
| `trace.py` | `TraceMixin` | 4 | 引擎轨迹 |
| `lifecycle.py` | `LifecycleMixin` | 8 | 生命周期 |
| `memory_recording.py` | `MemoryRecordingMixin` | 8 | 记忆落盘 |
| `travel_quest.py` | `TravelQuestMixin` | 6 | 旅行攻略编排 |
| `travel_bag.py` | `TravelBagMixin` | 2 | 旅行小包 |
| `souvenirs.py` | `SouvenirsMixin` | 4 | 纪念品 |
| `economy.py` | `EconomyMixin` | 5 | 经济 / 背包 / 出售 |
| `world.py` | `WorldSimulationMixin` | 4 | 世界模拟 / 街景排行 |
| `photo.py` | `PhotoMixin` | 2 | 照片任务 / 自拍 |
| `memory.py` | `MemoryMixin` | 9 | 记忆 CRUD / DNA / 心译 |
| `feedback.py` | `FeedbackMixin` | 1 | 反馈 |
| `owner_interaction.py` | `OwnerInteractionMixin` | 7 | 主人交互 + 私有辅助 |
| `exceptions.py` | —（仅异常定义） | 0 | `PetNotFoundError` 等三个异常 |
| `__init__.py` | `JourneyEngine`（门面） | — | 聚合 + re-export |

合计 **75 个方法**，与拆分前一致，无缺失、无多余。

## 4. 关键设计决策（务必遵循）

1. **包优先于同名模块**：Python 解析 `import app.agent_engine` 时，`app/agent_engine/`
   目录（包）优先于 `app/agent_engine.py` 单文件。因此拆分时新建包即可「遮蔽」旧文件，
   旧文件随后删除，不会出现二义性。**勿再新建 `app/agent_engine.py` 单文件**。

2. **门面 re-export 保持历史导入面**：调用方仍写
   `from app.agent_engine import JourneyEngine`，以及三个异常
   `PetNotFoundError` / `ThoughtNotFoundError` / `TravelQuestNotFoundError`。
   这些在 `__init__.py` 顶部 re-export，新增异常须同样在此登记。

3. **异常集中到 `exceptions.py`**：避免 mixin 与门面之间的循环 import（与 `records.py`
   在 `repositories/` 中的作用一致）。

4. **跨 mixin 调用走 MRO**：某 mixin 调用另一 mixin 的方法（如 `claim_pet` → `get_pet`）
   通过 `self.xxx()` 在运行时沿 MRO 解析，无需显式 import 其它 mixin。**不要**在 mixin
   之间互相 `from .foo import FooMixin` 引用具体类。

5. **局部变量注解从简**：拆分时个别方法体的局部注解（如 `steps: list[EngineStepTrace]`
   简化为 `steps: list`）刻意保留简单形式，避免每个场景文件重复 import `EngineStepTrace`。
   二者运行时等价，业务逻辑逐字未动。

6. **`__init__.py` 只做聚合**：不放业务方法，不写 `__init__` 构造逻辑（依赖注入由
   `base.py` 的 `__init__` 提供 18 个参数，不含 self）。

## 5. 验证方法（复验清单）

后续若再次改动引擎，按以下顺序验证零破坏：

1. **方法集对比**：`ast.parse` 解析旧类与新包（`inspect.getmembers` + `__mro__` 去重），
   断言二者方法名集合完全一致（本次：75 = 75）。
2. **函数体 diff**：对每个同名方法做 `ast.unparse` 逐字比对，排除上文第 5 条的局部注解
   简化后应完全一致。
3. **编译**：`python -m compileall app/` 全量通过（无 ImportError / NameError）。
4. **门面自检**：`JourneyEngine.__init__` 依赖注入参数应为 18 个（不含 self）；MRO 顶层
   为 `JourneyEngine`。
5. **引用点导入**：`app.dependencies` / `app.http_utils` / `app.main` /
   `app.routers.pets` / `app.scheduler` 等引用模块 `import` 全部通过。

## 6. 遗留事项

- 本次拆分**尚未 `git commit`**（工作区状态：`D app/agent_engine.py` +
  `?? app/agent_engine/`）。提交时建议沿用项目历史风格：`refactor(backend): ...`。
- 环境说明：本机测试为 `unittest`（非 pytest）；Windows 下全量回归存在已知的
  `WinError 32`（sqlite 占用）与 URL 反斜杠类环境错误，与本次重构无关。

## 7. 新增方法放哪里

| 新方法属于哪类业务 | 放进 |
|------|------|
| 旅行攻略 / 行程编排 | `travel_quest.py` |
| 背包 / 打包 | `travel_bag.py` |
| 纪念品 | `souvenirs.py` |
| 经济 / 背包出售 / 资金 | `economy.py` |
| 世界模拟 / 街景 | `world.py` |
| 照片 / 自拍 | `photo.py` |
| 记忆 CRUD / DNA / 心译 | `memory.py` |
| 主人消息 / 交互 | `owner_interaction.py` |
| 反馈 | `feedback.py` |
| 跨场景共享工具 | `helpers.py` |
| 生命周期 / 引擎启停 | `lifecycle.py` |
| 轨迹 / 事件流水 | `trace.py` |
| 记忆落盘 | `memory_recording.py` |

新方法加进对应 mixin 后，门面 `__init__.py` **无需改动**（多重继承自动继承新方法）。
仅当新增异常类型时才需要同步更新 `exceptions.py` 与 `__init__.py` 的 `__all__`。
