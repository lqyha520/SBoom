# 部署到 Linux 云服务器（Docker 方案）

整套编排 = **app（FastAPI，含 web/admin 静态托管）+ db（PostgreSQL 16）+ caddy（自动 HTTPS 反代）**。

## 0. 前置条件

- 一台 Linux 服务器（2C4G 起步足够），装好 Docker + Docker Compose 插件
- 一个**已备案**的域名，A 记录指到服务器公网 IP（微信小程序正式包要求 HTTPS + 合法域名）
- 服务器安全组放行 80 / 443

## 1. 上传代码

服务器上从 GitHub 拉取（私有库，建议用 Deploy Key 或 Personal Access Token）：

```bash
git clone git@github.com:lqyha520/SBoom.git learn-coach
cd learn-coach
```

## 2. 配置环境

```bash
cd deploy
cp .env.production.example .env.production
vim .env.production   # 至少填：DOMAIN、POSTGRES_PASSWORD、SECRET_KEY、ADMIN_*、微信凭证
```

必填项速查：

| 变量 | 说明 |
| --- | --- |
| `DOMAIN` | 你的域名，Caddy 据此自动签 Let's Encrypt 证书 |
| `POSTGRES_PASSWORD` | 数据库密码，改成强密码 |
| `SECRET_KEY` | 会话签名密钥，`python3 -c "import secrets;print(secrets.token_urlsafe(48))"` 生成 |
| `ADMIN_USERNAME/PASSWORD` | 后台种子管理员（首次启动创建，之后可删掉这两行） |
| `WECHAT_APP_ID/SECRET` | 小程序凭证（与 `miniprogram/src/manifest.json` 的 mp-weixin.appid 一致） |
| `WECHAT_PAY_*` | 走支付才需要；商户私钥/平台公钥放到 `appdata` 卷（容器内 `/app/data/wechat/`） |

> LLM 配置：后台「系统设置 → 模型配置」存在数据库里，优先于 `.env`；新库需要先在后台配一次，或直接填 `LLM_API_KEY` 兜底。

## 3. 启动

```bash
docker compose up -d --build
docker compose logs -f app        # 出现 "Uvicorn running on http://0.0.0.0:8000" 即成功
curl https://你的域名/health       # {"status":"ok"}（需要后端返回的真实字段）
```

首次启动自动幂等建表，无需手动迁移。之后更新版本：

```bash
git pull && docker compose up -d --build   # 只重建应用层，前端 dist 在镜像内构建
```

## 4. 数据与备份

| 卷 | 内容 | 备份建议 |
| --- | --- | --- |
| `pgdata` | PostgreSQL 全部业务数据 | `docker compose exec db pg_dump -U learncoach learncoach | gzip > backup.sql.gz` |
| `appdata` | 试卷 PDF/图片实体、secret_key、支付密钥 | 直接 tar 这个卷 |
| `caddy_data` | TLS 证书 | 不需要 |

## 5. 小程序端收尾

1. `miniprogram/.env.production.local` 写 `VITE_API_BASE_URL=https://你的域名`（发布门禁会强制校验）
2. `node node_modules/@dcloudio/vite-plugin-uni/bin/uni.js build -p mp-weixin`，再 `node scripts/check-build.mjs --release`
3. 微信公众平台 → 开发管理 → 服务器域名，把 `https://你的域名` 填进 request 合法域名
4. 微信支付商户平台配置回调域名与密钥（如启用支付）

## 6. 已知限制 / 注意

- **多 worker 只在 Linux 可用**：`WORKERS=2` 在容器里没问题；Windows 本机仍是单 worker。
- **COS 存储未内置**：`ARCHIVE_STORAGE=cos` 需要在 `requirements.txt` 加 `cos-python-sdk-v5` 后重新构建镜像，否则切换会 503。小规模用默认 `local`（文件落 `appdata` 卷）即可。
- 域名必须备案，否则 443 会被云厂商拦截。
- `.env.production` 含密钥，已在 `.gitignore` 排除，不要提交。
