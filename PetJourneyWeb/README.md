# PetJourneyWeb — PetSoul 2.0 手机网页（MVP）

手机网页优先的 React 客户端。首页是“共同的家”，四个主入口：**家 / 旅途 / 星球圈 / 通讯**。
契约见 `../docs/contracts/WEB-CONTRACT-v0.2.md`，模块接入见 `../docs/contracts/MODULE-MAP.md`，交接见 `../docs/coordination/MVP-HANDOFF.md`。

> 当前为 MVP：live 模式下注册/登录、上传与专属领养、接待与入住叮嘱、家园与菜园、串门互偷与巡院、仓库与集市（NPC）、出发站与演示线路（按真实时间推进）、地图上的一起听、寻味两种模式与改选、店内活动与明信片、冒险勋章、星球圈、私密通讯、收藏都已接通本地后端。没有接入的：真实地图底图、核验时刻表、接待/意图模型、生图、授权影音作品、真实商家资料、玩家挂牌交易——这些在 `/api/v1/web/meta` 与页面上如实显示“未配置/未开放”。fixture 模式仍是明确标注的演示数据。交接见 `docs/coordination/MVP-HANDOFF.md`。

## 版本（已锁定于 package-lock.json，`.npmrc` 设 `save-exact=true`、`engine-strict=true`）

| 依赖 | 版本 | 说明 |
|---|---|---|
| Node / npm | ≥22.12（本机 22.20.0 / 10.9.3） | Vite 8 最低要求 |
| react / react-dom | 19.3.0 | |
| react-router | 7.18.4 | 8.x 需要 Node ≥22.22，本机不满足，故锁 7.x |
| @tanstack/react-query | 5.103.2 | 统一远端状态 |
| vite / @vitejs/plugin-react | 8.3.0 / 6.1.1 | |
| typescript | 6.0.3 | 未采用 7.x（原生编译器生态兼容性待观察） |
| vitest / jsdom / @testing-library/react | 5.0.1 / 27.4.0 / 16.3.3 | jsdom 30 需 Node ≥22.22 |

升级依赖属于共享入口变更：在协作日志提出，由共享入口维护者串行执行 `npm install` 并更新本表。

## 运行

```bash
npm ci                      # 按 lockfile 安装
npm run dev:fixture         # 演示模式：不访问后端，页面顶部常驻“演示模式”标识（http://127.0.0.1:5287）
npm run dev:live            # live 模式：只走 /api/v1/web，经 Vite 代理到本地后端
node scripts/dev-backend.mjs  # 另开终端：隔离的本地后端（127.0.0.1:18761，数据在 ../PetJourneyBackend/data/web-dev/）
npm run typecheck
npm test                    # vitest；同时把 fixture 导出到 .runtime/contract-examples/
npm run build               # 类型检查 + 生产构建到 dist/
npm run contract:check      # 契约生成物是否最新 + 用后端 Pydantic 校验 fixture 导出
npm run contract:gen        # 修改后端 app/schemas/web 后重新生成 src/shared/contracts/generated.ts
```

`scripts/dev-backend.mjs` 会：使用独立 SQLite/上传目录；全部供应商 mock；关闭调度器；把所有供应商密钥变量置空（即使 `PetJourneyBackend/.env` 有真实密钥也不会读取）；开启 Apple mock 登录以便本地拿 Bearer 调试——**仅限本地，绝不能用于任何部署**。可用 `PETSOUL_DEV_BACKEND_PORT`、`PETSOUL_DEV_DATA_DIR`、`PETSOUL_PYTHON` 调整。

环境变量见 `.env.example`。`VITE_*` 会进入客户端 bundle，只能放公开配置；地图/模型/生图密钥只存在于后端。

## 数据模式

- `fixture`：每个模块的 fixture 服务，数据来自 `src/fixtures/`（文件头写明来源），页面标注“演示数据”。交通场景可在旅途页切换（飞机·听歌 / 火车·看剧 / 轮船·无活动 / 驾车·只听 / 暂停 / 加载失败 / 到站·已保存）。
- `live`：统一客户端访问后端；没有 live 实现或后端返回 501 的能力显示“这里还在搭建中”，**不回退 fixture**。live 模式带入口守卫：未登录去欢迎页，入住未完成回到对应步骤；会话过期自动回欢迎页。

## 目录

```
src/
  app/           组合根：模块发现、路由（含冲突/禁止路由检查）、四个固定 Tab、错误页（框架维护）
  shared/        唯一 API 客户端、生成的契约类型、服务边界与注册表、插槽、地图/媒体/时间/记忆策略镜像、UI 组件与 tokens（框架维护）
  features/<m>/  业务模块：module.ts(x) 默认导出 defineModule({routes, bareRoutes, services, slots})
  fixtures/      显式 fixture（只在 fixture 模式使用）
public/fixtures/media/  R0 用 ffmpeg 合成的自制测试音视频（见 README.txt）
tests/           模块接入、API 客户端、领域镜像、fixture 契约导出
scripts/dev-backend.mjs 本地隔离后端
```

## 新增或实现一个模块

1. 在 `src/features/<module>/module.ts(x)` 导出 `defineModule(...)`；路由路径需在 MODULE-MAP 登记，不能与现有冲突，不能注册舱室/交通场景页，不能新增底部 Tab。
2. 服务：实现 `shared/services/types.ts` 中对应接口的 `fixture` 与 `live` 版本；live 只用 `ServiceContext.api`。
3. 插槽：用 `slot(name, id, Component, order)` 贡献到 `shared/slots/names.ts` 已定义的插槽。
4. 写操作：一次用户动作生成一个 `newIdempotencyKey(scope)`，失败重试复用；成功后按 MODULE-MAP 的失效规则 invalidate。
5. 不直接读写别的模块的服务实现、不自建钱包/世界状态/fetch。

## 手机适配

- 视口 `viewport-fit=cover`，安全区变量 `--safe-*`；底部 Tab 高度含 `env(safe-area-inset-bottom)`；输入框字号 16px 防 iOS 放大；触控目标 ≥44px；尊重 `prefers-reduced-motion` 与深色模式。
- 已在浏览器模拟 320×640、390×844、430×932 检查：无横向滚动、导航/刷新/前进后退可用。**这不等于 iOS Safari / Android Chrome 真机验证**。
