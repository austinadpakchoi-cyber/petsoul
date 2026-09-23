# PetSoul 香港首版团队体验部署

窗口：codex-20260922-product-refresh-c84a。部署日期：2026-09-22（Asia/Shanghai）。

## 入口与当前版本

- 团队入口：**https://petsoul.games**。每人自行注册独立账号，不共用管理员账号。
- 服务端：43.129.174.54，Tencent Lighthouse 香港，Ubuntu 26.04，4 vCPU / 8 GB 档 / 180 GB 档。
- 发布号：`team-v1-20260922T055010Z`。
- 来源：当前工作树的固定快照，491 个源文件；基底 HEAD `980feabc7710462a89c5df488c255d04e9e7de08` **不代表已提交本次全部内容**。
- 源包 SHA256：`4710bd18b95df5a8b871806828d46ab31c1b78eec3e7148808c871d17ffb55a6`。
- 运行快照不随 Windows 上其他窗口改动自动更新。没有执行整仓提交、拉取、清理或切换分支。
- `api.petsoul.games` 仍指向旧服务器 `150.109.157.174`，本轮未修改。

推荐初次体验：注册 → 自己的宠物（照片可选）→ 接待/确认叮嘱或跳过 → 入住 → 菜园、通讯 → 旅途里的海边咖啡馆。初始作物约 3 分钟成熟；咖啡馆单程约 6 分钟、往返总共 32 分钟，按真实经过时间推进。到店后回“家”，点击“TA 在店里，进去看看”，即可选座、点饮品。不要为了演示修改正式服务器时间。

## 当前范围

账号、归属、家园、种植/物资、旅行状态、通讯等通过同源正式 API 与持久数据库运行。网页为 `VITE_PETSOUL_DATA_MODE=live`，这里的 live 表示连接真实后端，**不代表真实外部地图、商家、班次或模型**。

本次没有上传付费供应商密钥。服务端 `PETJOURNEY_WEB_PROVIDERS=false`、意图层 off；接待为引导便笺，回信使用模板，示例地图/店铺/航线与测试媒体保留来源说明。真实 AI、地图、商家与时刻表接入由后续发布完成。没有声称已经具备完整比赛版能力。

领养角色仍为有限的原创专属池，领完后不能多人重复领取；团队成员也可直接建立自己的宠物。注册目前没有邮箱找回，请团队自行保存密码。QA 使用两个专用账号，没有占用领养名额、读取其他用户私密内容或调用付费生成。

## 部署与运行

```text
/opt/petsoul/releases/team-v1-20260922T055010Z/  固定源码、dist 与验证记录
/opt/petsoul/config/compose.yml                 正在使用的 Compose
/opt/petsoul/config/Caddyfile                   正在使用的路由配置
/opt/petsoul/config/release.env                 发布号与 Caddy 镜像摘要，root 600
/opt/petsoul/config/backend.env                 正式环境与独立随机密钥，root 600
/opt/petsoul/data/                             正式持久数据；更新不可覆盖
/opt/petsoul/backups/                          在线备份，root 700
/opt/petsoul/ops/                              备份与校验脚本，root 700
```

- Caddy 在 80/443 提供网页和 HTTPS，Let's Encrypt 自动管理证书；Tencent 云防火墙本轮仅新增 TCP 443 允许规则 `PetSoul HTTPS`。
- FastAPI 只在 Docker 内部 8000 提供服务，没有将数据库或后端端口公开。
- Caddy 转发 `/api/v1/web/*` 与 `/health`；旧 API、文档、原始媒体路径、环境文件等返回 404。
- 后端镜像 `petsoul-backend:team-v1-20260922T055010Z`。已记录实际 image ID、Python 依赖版本和前端文件 SHA256。
- Caddy 固定镜像摘要：`caddy@sha256:14a9c00d4e833ebc2b65d36515b37bde3b73f0b323a2663aaafc88953d8c4e3f`。
- 两个容器 restart=unless-stopped，Docker 开机启动；后端健康检查、日志轮转已配置。
- SSH 登录用户 `ubuntu`。密钥留在仓库外 `_credentials`，不粘贴进日志或发给团队。原 Downloads 私钥未修改；运行使用只允许当前 Windows 用户读取的安全副本。主机密钥已固定在独立 known_hosts。

维护命令（登录服务器后）：

```bash
cd /opt/petsoul/config
sudo docker compose --env-file release.env -f compose.yml ps
sudo docker compose --env-file release.env -f compose.yml logs --tail=100 backend
sudo systemctl start petsoul-backup.service
sudo systemctl list-timers petsoul-backup.timer
```

不要将 env 文件内容输出到共享日志。后续部署先读取黑板及本交接，用新的发布号打包、测试，备份数据，然后更新 `release.env` 并启动；不要原地覆盖现用 release。配置和源码必须分别记录摘要。本次是首个版本，没有已验收的旧网页版本可供回滚；不要把数据库回滚视为普通静态页面切换。

## 已验证的证据

| 检查 | 本轮结果与范围 |
| --- | --- |
| 香港实际 Linux 构建与测试 | Python 3.12 隔离容器 unittest 171 全通过；非正式库 |
| 公共契约 | 80 enums / 122 models / 66 routes 校验通过 |
| 前端 | typecheck、26 tests、production build 通过 |
| 产物完整性 | 源包、源文件与 dist 哈希核对通过；未夹带本地密钥/数据库/上传 |
| HTTPS 与路由 | 域名证书有效，首页/深链 200，受限路径 404，未登录写入被拒绝 |
| 公网真实双账号 | 注册/登录、私有图片读取与元数据去除、他人照片/通讯/行程隔离、CSRF、消息幂等通过；25 个检查项见 JSON |
| 后端重启持久化 | 重启后重新登录，同一 home/pet/wallet 与消息均保留 |
| 浏览器 | 独立 Chrome，注册 → 建宠 → 接待原话 → 私密叮嘱确认 → 入住 → 出发；家园成熟后收获 4 份豌豆，卖出增加 8 旅费；390/320 视口截图 |
| 实时推进与店内 | 14:09 出发，6 分钟后实际到店；从家园进入店内，选座与点饮品成功，插画中的宠物位置/饮品随操作更新；未等待整个 32 分钟返家周期 |
| 旅途媒体 | 点地图音符进入“一起听”；join/heartbeat 200、测试音频 Range 206；未做真实手机扬声器/跨设备同步验收 |
| 备份 | 在线 SQLite 备份 + 上传/私有媒体归档，SHA256 校验；独立临时目录恢复副本，integrity_check=ok，20 项迁移/65 张表；未覆盖正式数据 |

每日备份由 `petsoul-backup.timer` 在 UTC 20:10（北京时间次日 04:10，随机延后最多 5 分钟）启动。已实际执行 service，Result=success。首份服务验证备份：`/opt/petsoul/backups/petsoul-20260922T061241Z`。**当前是同机备份，尚未配置异地备份或自动清理保留策略；没有做正式灾难切换演练。**

本地证据：`PetJourneyBackend/data/deployments/team-v1-20260922T055010Z/`（已忽略，含 source、manifest、verification、public-checks.json、backup-verification.json、浏览器操作快照）。截图：`PetJourneyWeb/output/playwright/deploy-hk-*.png`。QA 密码只存在仓库外受限文件，不在证据或本文中。

## 后续窗口需要知道

- 本轮不修改业务源码。手机家园插画上的“出发站”与右下状态说明存在覆盖，见 `deploy-hk-home-390.png`，留给前端修正。
- 到店后地图目前仍展示上一段“已到站”，缺少直接进店入口；可以返回家园，通过“TA 在店里，进去看看”完成店内交互。这是已复现的导航缺口，未在本轮改写业务代码。
- 未入住时 home-welcome、未出发时 journey/map 返回预期 404；前端能继续主流程，但控制台会记录 failed resource，可优化空状态读取。
- 地图图标持续动画使自动化普通 click 等待 stable 超时；按已观测目标直接点击可以打开媒体面板，不能据此声称真实触屏误触率已通过。
- 本轮未完成实体 iPhone/Android、多人负载、大规模上传、异地备份、真实模型/地图/商家/班次验收。
- 体验团队可以开始使用；此交付不等于前端视觉定稿或全部产品方案实现。
