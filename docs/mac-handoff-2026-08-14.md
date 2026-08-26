# 交接文档：从 Windows 开发环境切回 Mac（2026-08-14）

> 给回到 Mac 继续开发的人（包括未来的 AI 代理）。所有结论以 git 为准：本仓库 main 已全部推送到 GitHub，
> 在 Mac 上直接 clone/pull 即可获得与 Windows 工作区完全一致的最新代码。

## 0. 当前仓库状态（截止 2026-08-14）

- 最新提交：f06d4ce（本地与 origin/main 完全同步，无未推送提交）。
- CI 全绿：Architecture Gate ✅、iOS Build & Test（macOS 真机编译+测试）✅（head dcc0807b/f06d4ce）。
- 后端测试：82 个全绿（unittest），架构门禁（scripts/arch_gate.py，800 行/30 类型）通过。

## 1. 本阶段已完成的全部工作（按时间顺序）

### 后端（PetJourneyBackend）
1. **God File 拆分**：transport_schedule / memory_store / pet_guide_engine / travel_research /
   travel_quest_engine / world_simulation / providers.map_providers / pet_life_engine /
   place_interactions 全部拆成包/mixin，门面 re-export 保持历史导入面，AST 逐方法验证零差异。
2. **测试环境修复**：sqlite 连接随 with 关闭（_ClosingConnection）、URL 用 posix 分隔符——
   Windows 上的 29 个 WinError 32 + 1 个反斜杠失败全部消除。
3. **DeepSeek 迁移**：三个文本大脑 + 交通班次全部单路径 /chat/completions；json_schema strict →
   json_object + schema 内嵌 prompt；删除 reasoning.effort；显式 max_tokens（512/900/1600/1200）；
   默认模型 deepseek-chat、base_url https://api.deepseek.com/v1。**豆包语音/社媒层保留不动**。
4. **省钱 P0**：photo_mission 30min 缓存、pet_guide 每日缓存、自拍冷却前置到 LLM 之前、
   agent_turn_interval 900→1800s、usage token 记账字段（/api/v1/agent_brain/config 与
   /api/v1/photo_mission_brain/config 新增 last_remote_prompt_tokens/completion_tokens）。
5. **国内生图**：DoubaoSeedreamImageProvider（Ark /images/generations，多参考图角色透传
   pet_identity/place_environment），PETJOURNEY_IMAGE_PROVIDER=volcengine 分派，6 项单测。
   image_provider.py 拆成 6 文件包。
6. illustrated_guide.model 取实际 provider 模型（volcengine 下不再报 gpt-image-2）。

详细方案见 docs/llm-cost-and-deepseek-migration.md（调用点清单/重复黑洞/迁移步骤/预期省钱
$100→$10-30 量级，需以 usage 日志校准）。

### iOS（PetJourneyIOS）
深度审计（audits/ios-deep-audit/ 三份报告）后全部落地：
- **P0 健壮性**：Outbox 队头阻塞修复（attempts 上限 5 + 死信）、401 → sessionExpired + 信号文案、
  缓存 TTL 按 13 种 kind 分级（快照 30min～图示 24h）。均带测试。
- **硬规则**：9 处常驻动画 reduceMotion + 1/30 上限；MemoryEditor 内部字段 #if DEBUG 门控；
  33 处「手机」→「通讯器」（5 处物理设备语境保留）；供应商名/模型名清理；脱敏正则扩充。
- **契约补齐**：LifeTickResult.observation/retrieved_memories、PhotoMission.quality_report 系列、
  OwnerMessageResponse.owner_intent、SouvenirItem 来源字段、PetAuthoredGuide.selected_places 系列、
  PlaceEvidencePacket.provider_evidence、PlaceSignal.raw；新增 ContractDecodingTests fixture 护栏。
- **架构回潮**：CommunicatorViewModel/MemoryHubViewModel 迁入 ViewModels/；WorldStoryViewModel 走
  APIClient；NPC 身份收敛 NPCSociety.cast；分钟数共享 Date.petSoulMinuteOfDay；凭据死代码清理；
  卡面尺寸真相源集中。
- **P2**：Info.plist 文案、机制词仪式化（识别/生成/真实）、annotation.cardSurface 令牌、
  阴影 deepInk、账号措辞、灵魂世界→平行世界、minimumScaleFactor≥0.8。

## 2. Mac 上要做的环境准备

### 后端
```bash
cd PetJourneyBackend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# .env：照 .env.example 填（见 §3），把 DeepSeek key 放 OPENAI_API_KEY
python -m unittest discover -s tests     # 应 82 个全绿
uvicorn app.main:app --reload           # 本地起服务
```

### iOS
```bash
xcodebuild -project PetJourneyIOS.xcodeproj -scheme PetJourneyIOS   -destination 'platform=iOS Simulator,name=iPhone 17 Pro' test
python scripts/arch_gate.py   # 应通过（Swift 侧同样受 800 行/30 类型约束）
```

### 关键 .env 切换点（生产部署同样适用）
```env
PETJOURNEY_OPENAI_BASE_URL=https://api.deepseek.com/v1
PETJOURNEY_AGENT_MODEL=deepseek-chat
PETJOURNEY_AGENT_DEEP_MODEL=deepseek-chat
PETJOURNEY_AGENT_FAST_MODEL=deepseek-chat
PETJOURNEY_TRANSLATION_MODEL=deepseek-chat
PETJOURNEY_PHOTO_MISSION_MODEL=deepseek-chat
OPENAI_API_KEY=<DeepSeek 的 key>
# 可选：生图切 Seedream（火山方舟同 key 体系）
PETJOURNEY_IMAGE_PROVIDER=volcengine
PETJOURNEY_VOLCENGINE_IMAGE_MODEL=doubao-seedream-4-0-250828
DOUBAO_API_KEY=<火山方舟 key>
# 豆包语音层保持原样即可
```

## 3. 待 Mac 验证清单（这是切回 Mac 的核心目的）

1. **DeepSeek 真实输出质量**：各大脑 JSON 合规率（失败会静默回退本地规则，不会崩）；
   宠物口吻质量；观察 /api/v1/agent_brain/config 的 token 记账字段，校准实际省钱幅度。
2. **Seedream 出图**：宠物脸一致性、暖调风格、尺寸（1024x1024 默认）与 UI 宽高比的兼容。
3. **「手机→通讯器」等全部文案改动的真机/模拟器观感**（系统权限弹窗文案也改了，见 Info.plist）。
4. **可选：DSH iOS 模拟器插件**（强烈推荐）：
   `dsh plugin --profile web add @zseven-w/dsh-ios@latest` 后重启 dsh web，
   即可在对话里 ios_sim_build_run 编译运行 PetJourneyIOS、实时面板点按、OCR/无障碍树驱动 UI、
   日志/backtrace/leaks、SwiftUI preview 热重载。**仅 macOS+完整 Xcode 可用**（Windows 上工具会报错）。
   详细文档：https://github.com/ZSeven-W/dsh-ios（本机留了一份 README 在 E:\petsoul-audit\tools\dsh-ios-readme.md）。

## 4. 注意事项

- **wire 契约红线**：TravelGuideResearchProvider 枚举 raw value（doubao_social/openai_web_search）
  前后端一致，**不要单方面改**；要改必须前后端同一提交一起改。
- iOS 新文件必须登记 pbxproj（scripts/register_swift_file.py）；改动后跑 CI（push 触发 ios-build.yml）
  或本地 xcodebuild。
- 后端改动后必须 python -m unittest discover -s tests 全绿 + scripts/arch_gate.py 通过。
- 产品硬规则见 AGENTS.md（不写死宠物名/不暴露机制/通讯器语音/DesignTokens/动画 reduceMotion）。
- git 凭据在 Mac 上需自行配置（Windows 的 GCM token 不带过去）。
- Windows 工作区根目录的 _recover_backup/ 是拆分事故旧备份，迁移时可忽略。
