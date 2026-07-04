# PetSoul 后端云部署

目标形态：任意云服务器（阿里云 / 腾讯云 / AWS Lightsail，2C2G 起步即可）+ Docker Compose + Caddy 自动 HTTPS。

## 一次性准备

1. 服务器装好 Docker 与 Docker Compose 插件（Ubuntu：`apt install docker.io docker-compose-v2`）。
2. 域名加一条 A 记录（如 `api.yourdomain.com` → 服务器公网 IP），并把 [Caddyfile](Caddyfile) 里的域名换掉。
3. 把本地 `PetJourneyBackend/.env` 与 `.env.features` 合并成一份 `deploy/backend.env` 传到服务器（含 LLM/地图 key、APNs 四件套、`PETJOURNEY_PUBLIC_BASE_URL=https://api.yourdomain.com`）。**backend.env 不进 git。**
4. 云厂商安全组放行 80/443。

## 部署 / 更新

```bash
# 在服务器上
git clone <你的私有仓库> petsoul && cd petsoul/deploy
docker compose up -d --build

# 之后每次更新
git pull && docker compose up -d --build
```

## 数据

- sqlite 与上传文件在 `petjourney-data` 卷中，`docker compose down` 不会丢。
- 备份：`docker run --rm -v petsoul_petjourney-data:/d -v $PWD:/b alpine tar czf /b/petjourney-data-$(date +%F).tgz -C /d .`

## iOS 侧切换

部署完成后，把 App 的 baseURL 换成 `https://api.yourdomain.com`（AppSessionStore 的 DEBUG 默认值，或应用内服务设置），Release 构建应默认指向公网地址。
