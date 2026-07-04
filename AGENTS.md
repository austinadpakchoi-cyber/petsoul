# PetSoul — 代理协作约定（Codex / Claude Code 共用）

所有 AI 编码代理（Codex、Claude Code 等）在本仓库工作前必须读完本文件。规则只在这里维护一份，`CLAUDE.md` 指向本文件。

## 项目是什么

PetSoul / PetJourney 是"宠物在平行世界继续生活"的**关系型**旅行产品。核心目标：让已去世宠物的主人感到 TA 仍然存在，并实现"宠物替主人去旅行"的替代自由感。**这不是 AI 陪聊工具**——所有功能决策都要服务于"TA 有自己的生活、路线、节奏，用户温柔地参与"，而不是即时应答的客服感。

产品模块：地图（开车倾向第一人称导航视角）、通讯器（微信式，按宠物真实状态决定马上回/晚点回/发位置/发照片）、朋友圈/旅途圈（宠物自发的轻量动态）、明信片（正式、私密、收藏级纪念）、回忆（"TA 确实生活过"的证据）、证件卡包（PetSoul 世界身份系统，护照只在跨境远行时出现）、世界杯球场彩蛋（地图上点亮美加墨球场，不放硬按钮）。

## 硬规则（违反即返工）

1. **UI 代码不允许写死"小福"或任何特定宠物的素材。** 小福只是测试样板宠物，只能出现在测试/Mock 数据里（`MockPetJourneyService.swift`）。所有界面围绕"当前宠物"（名字、照片、DNA、性格、旅行状态）动态生成。
2. **文案不得暴露内部机制**（如"第一版会做模拟识别"），保持仪式感。
3. **iOS 工程是经典 pbxproj**（objectVersion 56）：新建 Swift 文件必须同步登记进 `project.pbxproj`，否则 Xcode 不收录。优先往现有文件里加代码，不要随意新建文件。
4. **改动 iOS 代码后必须构建/测试通过**（命令见下）。

## 仓库结构

- `PetJourneyIOS/` — SwiftUI 主 App（约 2.3 万行）。大文件：`JourneyMapView.swift`（地图+世界杯）、`CommunicatorViews.swift`（Tab 结构+通讯器+朋友圈+回忆+卡包）、`SecondaryViews.swift`（攻略/明信片/纪念品/DNA）。**避免多个代理同时编辑这几个大文件。**
- `PetJourneyBackend/` — Python FastAPI 世界模拟引擎（pet_life_engine、travel_quest_engine、route_planner、photo_pipeline 等），`tests/` 含 LLM 评测用例。
- `petjourney-mvp/` — 早期 Next.js 网页 MVP，已被 iOS 取代，不要在里面开发新功能。
- `audits/` — UX 审计记录。

服务模式：`AppSessionStore` 在 DEBUG 下默认 remote，指向局域网 `http://192.168.31.237:8000`，可切 Mock。

## iOS 设计系统（DesignTokens.swift）

- 全部颜色通过 `Color(light:dark:)` 自适应：日间瓷白，夜间是"灯下暖夜"（深暖绿炭底），不是纯黑。
- 语义令牌：`surface`/`surfaceStroke` 用于卡片与玻璃表面；`deepInk` 用于承载白色文字的实心填充（主按钮、Toast）和**所有阴影**（`ink` 在深色模式会变浅，当阴影用会发白光）。
- `paper`/`paperShade`/`paperInk`/`paperSecondaryInk`/`paperAccent` 是**固定色**：明信片等纸质纪念物是"实物"，夜里也保持暖纸配深墨。
- 原生 `.white` 只允许用于：彩色填充上的文字/图标、镜面高光（卡面闪光、shimmer）、实物材质（拍立得相框）、地图上照片头像的贴纸式白圈。**表面职责一律用语义令牌，禁止硬编码 `.white` 作背景/卡片。**
- 圆角体系：`cardRadius`(18) 必须大于 `controlRadius`(14)——卡片比控件圆。
- 常驻动画（`TimelineView` 类：AmbientSignalField、SignalPulseRings、SignalBars、EnergyRing）必须响应 `accessibilityReduceMotion`，帧率上限 1/30。
- "信号"是品牌母题：连接状态用信号语言表达（"已送达 TA 的世界"），不用即时通讯范式（"正在输入…"）。Tab 命名"通讯器"，不叫"手机"。

## 构建与测试

iOS（改动后必跑）：

```bash
cd PetJourneyIOS
xcodebuild -project PetJourneyIOS.xcodeproj -scheme PetJourneyIOS \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' test
```

注意：模拟器测试偶发抽风失败，失败先重跑一次再排查。

后端（用 unittest，不是 pytest）：

```bash
cd PetJourneyBackend
pip install -r requirements.txt   # 首次
/opt/miniconda3/bin/python3.12 -m unittest discover -s tests
```

## 协作方式

- 用 git 分支隔离各自的工作，小步提交；合并前跑对应测试。
- 分工建议按模块/目录切，尤其不要同时改 `CommunicatorViews.swift`、`JourneyMapView.swift`、`SecondaryViews.swift` 这三个大文件。
- 对世界观/文案有疑问时，宁可保守：不确定的机制描述不要写进用户可见文案。
