# 网页部署包（MVP，未部署）

目标：香港单实例，**同源 HTTPS**：静态网页 + FastAPI（`/api/v1/web`）。本目录只提供示例与脚本；**不修改现有 `deploy/docker-compose.yml`、`deploy/Caddyfile`（当前服务 api.petsoul.games）**。真实域名、服务器、容量与发布需用户逐项授权后执行——本窗口没有执行任何公网部署。

| 文件 | 用途 |
|---|---|
| `docker-compose.web.example.yml` | backend（现有 Dockerfile）+ Caddy，数据卷、健康检查、`releases/current` 静态目录 |
| `Caddyfile.web.example` | 只暴露 `/api/v1/web/*` 与 `/health`；旧 `/api/v1/*`、`/docs`、`/openapi.json`、`/media/*` 对公网 404；SPA 深链接回退；安全响应头 |
| `backend.web.env.example` | 后端环境模板（无真实值；复制为 `backend.web.env`，不进 git） |
| `scripts/release.sh` | 把 live 构建的 `dist/` 复制到 `releases/<标签>`，扫描疑似密钥，原子切换 `current` |
| `scripts/rollback.sh` | 网页切回上一版；可选把 backend 切回上一镜像标签（迁移只增不删） |
| `scripts/backup.sh` / `restore.sh` | SQLite 在线一致备份（`.backup` + integrity_check）+ 上传/私有媒体打包 + SHA256；恢复前导出并在恢复后**重放撤回记录** |
| `scripts/smoke.sh` | 部署后冒烟：meta、能力诚实性、深链接、旧接口不公开、未登录写被拒、HSTS |
| `DEMO-SCRIPT.md` | 现场演示脚本（真实时间推进；提前出发的演示账号） |

## 1. 构建

```bash
cd PetJourneyWeb
npm ci
VITE_PETSOUL_DATA_MODE=live VITE_PETSOUL_API_BASE=/api/v1/web npm run build   # 产物 dist/
```

- 生产必须 `live` 模式；fixture 构建只用于明确的演示站（页面有演示标识）。
- bundle 中不得出现密钥：`scripts/release.sh` 会扫描常见密钥模式，命中即停止。

## 2. 发布与回滚

```bash
cd deploy/web
cp backend.web.env.example backend.web.env        # 在服务器上填写真实值
./scripts/release.sh "$(git rev-parse --short HEAD)"
PETSOUL_RELEASE="$(git rev-parse --short HEAD)" docker compose -f docker-compose.web.example.yml up -d --build
./scripts/smoke.sh https://<已授权域名>
# 出问题：
./scripts/rollback.sh                    # 网页回到上一版
./scripts/rollback.sh <网页标签> <后端镜像标签>
```

- 数据库迁移只增不删（`app/web_platform/migrations`，启动时自动应用、可重复执行），旧版本代码可以在新库上运行，因此回滚不需要反向迁移。
- 每次发布前先 `scripts/backup.sh`。恢复：停服务 → `scripts/restore.sh <备份目录>` → 启动 → `smoke.sh`。
- 恢复旧备份时，入住叮嘱的撤回/删除不能被“复活”：`restore.sh` 先从当前库导出撤回记录，恢复后重放。

## 3. 后端环境（关键项）

| 变量 | 生产要求 |
|---|---|
| `PETJOURNEY_AUTH_SECRET` | 必填，≥32 字节随机值，只在服务器 secrets 中；更换会使所有会话失效 |
| `PETJOURNEY_WEB_COOKIE_SECURE` | `true`（HTTPS） |
| `PETJOURNEY_LEGACY_API_POLICY` | 纯网页：`closed`；与 iOS 共用：`owner_bearer`（先实测 iOS 是否带 Bearer）。**禁止 `open`** |
| `PETJOURNEY_APPLE_AUTH_MODE` | `live`（绝不能是 `mock`） |
| `PETJOURNEY_DB_PATH` / `PETJOURNEY_UPLOAD_DIR` / `PETJOURNEY_WEB_PRIVATE_MEDIA_DIR` | 持久卷；SQLite 单实例，不开多副本 |
| `PETJOURNEY_SCHEDULER_ENABLED` | 只在一个实例开启 |
| `PETJOURNEY_INTENT_LAYER_MODE` | 默认 `off`；`shadow`/`assist` 需评审后开启 |
| 供应商密钥 | 仅在获得付费/调用授权后配置；未配置时能力显示 `not_configured`，页面如实提示 |

## 4. 上线前检查（未完成即不得宣称已上线）

1. 本地已通过：`npm run typecheck && npm test && npm run build && npm run contract:check`；后端 `TZ=UTC python -m unittest discover -s tests`；`scripts/arch_gate.py`、`dependency_gate.py`、`contract_diff.py`（PYTHONIOENCODING=utf-8）。服务器（Linux）上需复跑一遍。
2. 旧接口策略切换为 `closed`/`owner_bearer` 并验证 iOS；Caddy 配置 `caddy validate` 并实测 handle 顺序。
3. 备份/恢复演练在目标服务器上走一遍（本地已演练，见交接文档）。
4. 实机：iOS Safari、Android Chrome 的登录、安全区、键盘、音视频手势播放、后台恢复、弱网——**尚未进行**（需要真机）。
5. 记录实际部署版本 SHA、HTTPS、域名与时间。
