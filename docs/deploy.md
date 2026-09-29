# 部署与备份恢复

现有生产环境使用 `docker-compose.server.yml` + `docker-compose.prod.yml`；运维命令再叠加 `docker-compose.ops.yml`。不要用单独的默认 compose 覆盖现有部署，也不要为了发布执行 `down`、重建数据库或网络。此文中的服务器命令需在 `/opt/learn-coach` 执行，路径不同则同步修改 systemd 单元。

## 1. 核对现有环境

升级前只读核对 `docker inspect` 的数据库镜像 ID、RepoDigests、数据卷、网络和 app 端口，记录原 app 镜像 ID。不要把包含环境变量的 inspect 全量输出贴入日志或聊天。

- 新安装、CI 使用 PostgreSQL 16 bookworm（glibc）。已有 Alpine（musl）数据卷继续使用原镜像；跨发行版或大版本必须逻辑 dump/restore 到新卷后验证，不能直接挂旧卷或仅依赖 REINDEX。
- prod 覆盖文件只适用于已核实的 bookworm 生产卷。`POSTGRES_IMAGE` 必须填写核实过的 `postgres:16-bookworm@sha256:...`，不要复制未经核实的 digest。
- 外部网络和卷必须事先存在。`COMPOSE_PROJECT_NAME` 必须与现有 app/db 容器所属项目一致，否则会另建容器。
- `FORWARDED_ALLOW_IPS` 填实测代理来源 IP（例如现有网桥网关），禁止 `*`。从两个不同客户端检查日志中的来源地址，确认没有全站共用一个限流桶。
- app 仅监听宿主 `127.0.0.1:33403`，远程 HTTPS 反代通过 SSH/TLS 回源。Nginx 模板见 `deploy/nginx/learn-coach.conf.example`；SSH 隧道单元见 `deploy/learn-coach-tunnel.service.example`。在实际代理主机上替换端口、主机、密钥与域名，执行 `nginx -t` 后再 reload。

服务器配置放仓库外的 `/etc/learn-coach/`：

| 文件 | 来源与内容 | 权限 |
| --- | --- | --- |
| `release.env` | `deploy/release.env.example`，填现有项目/网络/卷、镜像、可信代理、数据库和签名密钥 | root:root 600 |
| `service.env` | `deploy/.env.production.example`，应用完整环境，保留现有 SECRET_KEY、微信/支付/模型配置 | root:10001 640 |
| `ops.env` | `deploy/ops.env.example`，restic S3 凭据、数据库连接、告警地址 | root:root 600 |
| `restic-password` | 新生成的强随机仓库密码，单行，另存密码管理器 | root:10001 640 |

备份容器 uid/gid 为 10001，需要读取挂载的 `service.env` 和 `restic-password`；不要设成只有 root 可读后直接挂载。数据库密码需 URL 安全，三个配置文件中的值保持一致。`release.env` 由 Compose 解析，含特殊字符的值按 Compose env 语法引用；无需在 shell 中 source 密钥文件。宿主需 Python 3.12+、Docker Compose 2.24.4+（支持 `!reset`），构建机需 Python 3.12+。

先做纯配置验证（不会启动或重建服务）：

```bash
docker compose --env-file /etc/learn-coach/release.env -f deploy/docker-compose.server.yml -f deploy/docker-compose.prod.yml -f deploy/docker-compose.ops.yml config --quiet
```

`REGISTRATION_ENABLED=false` 默认关闭工作台公开注册，管理员开通教师账号；小程序读者注册独立配置。默认每账号并发 2、全站并发 6、每账号滚动 24 小时 20 次，全站预算 2,000,000 token 和 100 张图片。环境变量为 `GENERATION_USER_CONCURRENCY`、`GENERATION_GLOBAL_CONCURRENCY`、`GENERATION_DAILY_LIMIT`、`GENERATION_GLOBAL_DAILY_TOKENS`、`GENERATION_GLOBAL_DAILY_IMAGES`。token 按输入字节与最大输出保守预留，未知计费和失败调用不退款；后台统计展示的仍是模型实际报告用量。修改上限后重启 app 才生效。

## 2. 构建、上传、发布与回滚

先完成仓库检查并将版本提交到 Git；快照构建只包含指定提交，不包含工作区未提交文件、密钥和数据。Linux/WSL 构建机执行：

```bash
python3 scripts/release/prepare.py --ref HEAD --output /secure/releases
# 可选上传到已存在的私有目录；不会在服务器自动发布
python3 scripts/release/prepare.py --ref COMMIT --output /secure/another-release --host deploy@server --remote-dir /secure/incoming
```

输出包含应用/运维镜像 `images.tar`、SHA-256 和 `release.json`（Git 提交与镜像 ID）。服务器校验后载入：

```bash
cd /secure/incoming
sha256sum -c images.tar.sha256
docker load -i images.tar
cd /opt/learn-coach
# 同步该提交的 deploy/ 与 scripts/；首次配置 OPS_IMAGE 为本次运维镜像
python3 scripts/release/release.py --image learncoach-app:COMMIT前12位
```

发布脚本先做加密异地备份，成功后用待发布镜像单次执行 `python -m app.migrations`，通过后只执行 app 的 `up --no-deps --no-build --wait` 并检查 `/readyz`。失败自动恢复原 app 的镜像 ID；成功更新 `release.env` 中的 APP_IMAGE，并在 `/var/lib/learn-coach/releases/current.json` 记录当前与上一版本。镜像标签应唯一、禁止覆盖复用。整个发布窗口只运行一个发布进程。

主动回滚使用同一发布脚本，将 `--image` 换成记录中的 previous 镜像 ID。回滚仅适用于数据库向后兼容的版本；恢复数据库是单独的事故处理流程，不会自动覆盖生产数据。

```bash
python3 scripts/release/prune.py              # 先查看候选，默认保留最新 5 个版本
python3 scripts/release/prune.py --apply      # 只清理本项目提交标签
```

清理脚本保护所有容器使用的镜像以及登记的当前/回滚镜像，不做全局 prune。历史镜像包可在异地备份和回滚验证完成后按组织保留期人工归档。

## 3. 加密异地备份方案

推荐 restic + Cloudflare R2 的独立私有 bucket（也可换任意 S3 兼容存储）。restic 在上传前加密并校验；建议存储账号独立于应用服务器账号、开启 MFA，仅发放该 bucket 的凭据。R2 账号、存储空间与告警服务需要另行开通，本仓库不包含真实凭据，也不会自动开通付费资源。

在 R2 控制台创建私有 bucket，S3 凭据和 endpoint 填入 `ops.env`；将随机 restic 密码保存在服务器外的密码管理器。丢失密码无法恢复。首次初始化仓库：

```bash
docker compose --env-file /etc/learn-coach/release.env -f deploy/docker-compose.server.yml -f deploy/docker-compose.prod.yml -f deploy/docker-compose.ops.yml run --rm --no-deps backup init
python3 scripts/release/ops.py backup
python3 scripts/release/ops.py restore-check
```

备份通过同一组业务锁获得数据库一致性快照，复制登记表引用的所有私有文件（包含 Banner）、`service.env`、备用签名密钥和 `/app/data/wechat` 支付密钥，生成 SHA-256 清单。明文只在容器 tmpfs 中；restic 保留每日 7 份、每周 4 份、每月 6 份，上传后执行 `check`。支付密钥若配置在其他目录，先调整挂载与备份目录。

当前备份 tmpfs 上限 1 GiB，隔离恢复 tmpfs 为 2 GiB；数据增长时先增大这些值并核对服务器内存，超限会失败而不会写出不完整的成功备份。保留策略无法防止拥有存储删除凭据的入侵者删除备份；需要更强保障时增加独立账户的复制/保留锁策略，设置前确认 restic prune 的兼容性。

告警推荐使用飞书群自定义机器人：将完整 webhook 填入 `BACKUP_FEISHU_WEBHOOK`，开启机器人“签名校验”后，将签名密钥填入 `BACKUP_FEISHU_SECRET`。如果设置了关键词校验，可使用消息固定包含的 `learn-coach`。企业微信仍可通过 `BACKUP_ALERT_WEBHOOK` 配置；两者可任选或同时配置，各自独立发送，一个失败不会跳过另一个。失败消息区分备份和恢复演练，不含密钥；脚本检查渠道业务状态码，HTTP 200 但被机器人拒绝也会报错。凭据只写入仓库外的 `ops.env`，不要发到聊天或提交 Git。

`BACKUP_HEARTBEAT_URL` 配置为 Healthchecks 等服务的独立每日检查地址（成功请求本地址、失败请求 `/fail`），在服务端设置 24 小时周期和合理宽限，并配置通知联系人及飞书等通知集成；Docker/宿主完全不可用时也能通过漏心跳报警。直接机器人通知依赖运维容器能启动，不能替代漏跑监控。恢复演练使用单独的 `RESTORE_HEARTBEAT_URL`（月周期），避免掩盖每日备份漏跑。尚未填入告警地址时不能把备份运维视为已完成。

在 `release.env` 配置仓库外 `OPS_STATUS_DIR`（例如 `/var/lib/learn-coach/ops-status`），创建目录并授权uid10001写、监控组读。backup在restic上传及check成功后原子写入 `backup.json`，字段包含completed_at、verified和offsite，供[只读监控](../deploy/monitoring/README.md)判断备份时效。回执失败同样算备份流程失败，不可只看远端有文件。

先手动完成备份与恢复，再在服务器启用定时器：

```bash
sudo install -m 644 deploy/learn-coach-backup.service deploy/learn-coach-backup.timer deploy/learn-coach-backup-alert.service deploy/learn-coach-restore.service deploy/learn-coach-restore.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now learn-coach-backup.timer learn-coach-restore.timer
systemctl list-timers 'learn-coach-*'
journalctl -u learn-coach-backup.service -u learn-coach-restore.service --since today
```

每日 03:00（随机延迟最多 10 分钟）备份、每月 1 日 04:00 恢复演练，按宿主机时区执行。手动验证告警需操作者主动触发一次测试失败，并确认飞书（或企业微信）与漏心跳通知可达。

恢复演练只创建独立的 `restore-db`（无发布端口、临时内存数据目录），恢复程序再次限定目标为本地空白 `lc_restore_*` 数据库，校验清单和用户/Banner 表后删除这个临时容器。不会替换现有 app、db 或数据卷。事故恢复应先在隔离环境完整验证数据库、密钥和文件，再制定切换方案；不要把备份环境文件直接载入生产做试验。

## 4. 新安装与旧卷权限

全新 Caddy 部署可以使用 `deploy/docker-compose.yml`：复制 `.env.production.example`，填写域名、数据库密码、SECRET_KEY、管理员、微信配置。生产保持 `DB_AUTO_MIGRATE=false`；首次空库也先执行迁移，在 deploy 目录运行：

```bash
docker compose --env-file .env.production build app
docker compose --env-file .env.production up -d --wait db
docker compose --env-file .env.production run --rm --no-deps app python -m app.migrations
docker compose --env-file .env.production up -d --wait app caddy
```

域名须满足微信平台要求，放行80/443；后续按上述流程建立固定生产配置和备份。结构变更须遵循[扩展与收缩迁移流程](operations.md#数据库扩展与收缩迁移)，破坏性DDL后不能直接回滚旧镜像。

应用以 uid/gid 10001 运行，appdata 卷必须归该用户。旧 root 卷升级先备份，再仅对已核实的 appdata 卷做一次属主迁移，不要碰 PG 卷。`/readyz` 只验证数据库，迁移后还需验证文件写入。Linux 支持多 worker，Windows 开发环境只用单 worker。

## 5. 小程序发布验证

配置 HTTPS API 域名，执行 `pnpm --dir miniprogram build:mp-weixin` 和 `check:release`；公众平台配置 request/download 合法域名及头像、昵称、剪贴板用途的隐私保护指引。通过微信开发者工具和 Android/iOS 真机验证同意、拒绝、再次授权、切后台及离线退出。iOS 未启用虚拟支付时不展示会员价格、卡密兑换或站外开通引导。仓库构建与模拟测试不能替代平台隐私审核和真机验证。

## 6. 2026-09-28 本机 WSL 发布状态

在用户明确授权后，WSL Debian 的 Compose 项目 `deploy` 已仅更新 app 为 `deploy-app:p1-20260928-125837`。继续使用 `/home/lqyha/learn-coach/deploy/docker-compose.yml` 与该目录原有的 `docker-compose.override.yml`；数据库维持现有 `postgres:16-alpine` 及 `deploy_pgdata` 卷。此环境不能套用第 1 节面向 bookworm 卷的 prod 覆盖文件。数据库、Caddy 和独立开发数据库容器均未重建。

发布前完整备份位于 WSL `/home/lqyha/learn-coach-backups/p1-20260928-125837`，包含数据库 dump、完整文件卷、原 Compose/环境配置及 SHA-256 清单；目录权限 700、文件权限 600。发现的 3 张缺失 Banner 已从 9 月 21 日备份恢复，原备份包校验值、图片格式和数据库记录的字节数均已核对，仅恢复缺失文件。此备份是本机发布回退副本，未上传 R2。

发布后验证：应用 healthy、无重启；91 个后端源码文件哈希与工作区一致；HTTPS 工作台/后台和 12 个引用资源可用；租约、预算迁移、3 张 Banner 文件完整性及已公开的图片接口通过检查。更新前后均为 4 个用户、37 份归档、31 条目录和 3 个 Banner。工作台公开注册已关闭，单账号并发 2、每日请求 20，全站预算及 16384 输出上限已生效。

原应用镜像 `deploy-app:rollback-p1-20260928-125837` 已保留。需要回滚时，先恢复上述备份中的 `docker-compose.override.yml`，再使用原环境文件与两个 Compose 文件执行 `up -d --no-deps --no-build --wait app`；不覆盖数据库和文件卷。发布和验证记录位于本工作区 `artifacts/p1-2026-09-28/wsl-release-result.json` 与 `wsl-validation-result.json`，不包含凭据。

运维镜像 `learncoach-ops:p1-20260928-125837` 包含飞书告警代码，但真实 R2、飞书/心跳通知及定时器尚未配置启用。微信小程序客户端尚未发布，仍需第 5 节的平台配置与真机验收。

## 7. P1 验收清单（对应 2026-09-26 审查第 3–21 项）

验收分为当前 WSL 页面操作、模拟故障回归、外部环境验收三部分。代码测试通过不代表飞书已经送达，也不代表微信客户端已经发布。先在浏览器刷新当前版本：工作台 https://localhost/，后台 https://localhost/admin/。排版和确认框可以使用本机历史中的试卷，不需要重新调用模型；上传、连续保存使用测试草稿，卡密操作使用测试卡密。

| 原编号 | 如何验证 | 通过标准与当前边界 |
| --- | --- | --- |
| 3 登录限流 | 运行后端回归 A；模拟同 IP 更换用户名、满表和 IPv6 地址变化。 | 已超限 IP 不再增加用户名键；表满仍可接纳新键；同 /64 地址归为同桶。不要用大量请求冲击当前站点。 |
| 4 注册与预算 | 检查应用运行配置；后台回归 A 模拟多账号并发和预算耗尽。 | 当前工作台公开注册关闭；单用户并发 2、每日请求 20、全站并发 6；预算不足时拒绝调用。小程序读者注册是独立开关。 |
| 5 图片和 ZIP 内存 | 回归 A 模拟忙碌闸门和超过 400 万像素的图片。 | 忙时在读取上传内容前返回 429；超像素图片在解码前拒绝。图片/ZIP 并发闸门在每个 worker 内生效。 |
| 6 API 缓存 | 浏览器 F12 → Network，查看登录态查询或个人数据请求的 Response Headers；也可运行回归 A。 | 私有 API 的 Cache-Control 包含 no-store，可能同时有 private；公共图片的显式缓存策略允许保留。 |
| 7 生产编排 | 只读查看 Docker 容器镜像、卷和 Compose 路径；对照第 1、6 节。 | 本机现有 Alpine 数据卷继续使用原镜像；bookworm 生产覆盖文件需核实并显式配置卷、网络、代理。此次部署仅验证本机 WSL，不能代表远端服务器已更新。 |
| 8 异地备份与飞书告警 | 回归 A 验签、业务错误码和多通道独立发送；真实配置后按第 3 节做上传、失败通知、漏心跳和隔离恢复。 | 远端存在加密快照、隔离恢复成功、飞书群收到失败通知、漏跑有独立告警、定时器生效，才可勾选完成。目前真实 R2/飞书/定时器未启用。 |
| 9 发布与回滚 | 核对第 6 节版本和备份路径；回归 A 模拟健康检查失败后的回滚。 | 只更新 app，保留准确的旧镜像 ID，备份与配置可追溯；不要为验收在业务环境故意触发停机或回滚。 |
| 10 草稿失败不计费 | 回归 B 模拟草稿保存失败，覆盖整卷、单大题和单题替换。 | 显示保存失败，生成 API 没有被调用，请求仍可在恢复存储后继续。无需手动填满或删除浏览器存储。 |
| 11 输出上限和截断 | 后台“模型配置”只查看“模型最大输出 token”，当前为 16384；回归 A/B 模拟截断。 | 每批最多 30 道；完整大题被保留，手动补齐只请求未完成部分；查询原请求不追加生成调用。查看配置无需点“测试连接”。 |
| 12 崩溃后的名额释放 | 回归 A 模拟过期租约、续期和重复终态写入。 | 有效续期保留 running；过期可回收；已成功结果不被后续 unknown 覆盖。不要杀当前容器或修改业务记录来模拟。 |
| 13 资源更新与白屏 | Network 查看文档响应和 assets 下带哈希的 JS/CSS；回归 B 模拟加载失败和刷新保护。 | HTML 为 no-cache，哈希资源含 immutable；加载失败有恢复提示，草稿保存失败时不刷新，重复错误不循环刷新。 |
| 14 取消排版 | 从历史打开一份试卷，记住题序；点“排版模式”，移动、删除、调整尺寸，再点“取消”；查看打印预览。 | 题目、顺序、尺寸恢复，预览与打印一致。回归 E 在真实浏览器中覆盖取消排版。 |
| 15 重新生成与空结果 | 打开已有结果，点“重新生成”，在确认框点“取消”；进度和全部失败状态由回归 B 覆盖。 | 确认框包含条件、份数和费用提示；取消后不新增生成请求；尚无试卷时仍有进度、错误和恢复操作。点击确认会调用付费模型，本验收不需要确认。 |
| 16 后台登录提示 | 用未登录的独立浏览器窗口打开后台，输错一次密码；回归 C 覆盖 401/403。 | 显示账号密码错误或后端明确原因，不误报“登录已过期”；不要反复试密码触发限流。 |
| 17 打印版本二次保存 | 后台选测试草稿 → 打印版本 → 上传新 PDF → 保存；随后不更改关联再次保存并重新打开。 | 已上传版本仍有关联，不退回“不关联额外文件”；上传与关联模式明确，上传有校验/进度。回归 C 用模拟接口验证相同流程。 |
| 18 卡密管理 | 在卡密页切换状态、搜索现有尾号，查看分页与日期；点“作废”后取消。完整生成/导出和多页场景使用回归 C 或测试卡密。 | 筛选立即刷新，尾号匹配，分页可用；取消作废不改变状态；到期按北京时间所选日 23:59:59；离开页面清除新生成的明文展示。总数不足 51 时下一页禁用是正常的。 |
| 19 微信隐私授权 | 先回归 D，再在指引配置完成后的微信测试版中分别同意、拒绝头像/昵称/剪贴板授权。 | 拒绝时明确提示且不执行受保护操作；再次同意可重试；弹窗只在当前页面显示。浏览器测试不能替代微信真机验收。 |
| 20 iOS 会员入口 | 回归 D；在未启用 iOS 虚拟支付的微信测试版中查看会员页与会员弹层。 | 不显示价格、套餐购买、卡密兑换或站外开通引导，保留权益说明。目前新版客户端未发布。 |
| 21 会话续期和退出 | 回归 A 验证剩余不足两天的会话续期/撤销；回归 D 或微信测试版验证断网退出、重新进入后的协议状态。 | 有效会话续期而不重放写请求；已撤销会话仍拒绝；离线也能立即退出；协议同意按版本保存。不要手改业务会话过期时间。 |

### 自动化回归入口

以下命令在 Windows PowerShell、项目根目录执行。当前机器已具备依赖及专用 Python 检查环境。A 使用本机开发 PG 上的 lc_test_* 一次性数据库，模型/通知为模拟；不要把 LC_TEST_PG_ADMIN 改成业务库连接。B/C/D 使用测试桩；E 启动独立预览服务，接口使用固定响应，不调用付费模型，也不重启 WSL 服务。

~~~powershell
Set-Location 'F:\开源项目\learn-coach'

# A：后端、限流、生成恢复、备份及飞书告警
& .\artifacts\p1-2026-09-28\check-env\Scripts\python.exe -X utf8 -m pytest tests/test_backend_p1.py tests/test_backend_rate_limit.py tests/test_backend_reliability.py tests/test_backend_ops_p1.py -q

# B：工作台，包括保存失败、截断恢复、确认框及加载失败
pnpm --dir web test

# C：后台，包括登录、打印版本连续保存、卡密筛选和日期
pnpm --dir admin test

# D：小程序逻辑与组件契约；不等于真机验收
pnpm --dir miniprogram test

# E：真实浏览器回归。先构建；构建失败则不继续运行。
pnpm --dir web build
if ($LASTEXITCODE -eq 0) { pnpm --dir web exec playwright test --headed }
~~~

每组都应以退出码 0、全部 passed 收尾，不能只看页面是否能打开。浏览器失败截图和 trace 保存在 artifacts/browser-tests/。测试依赖警告与失败不同，判断以退出码和 failed 数为准。要再次只读核对当前已部署版本，可运行以下脚本；源码在发布后继续修改时，哈希不一致会提示需重新核对部署版本，而不是自动发布。

~~~powershell
& .\artifacts\p1-2026-09-28\check-env\Scripts\python.exe -X utf8 .\artifacts\p1-2026-09-28\verify_wsl_p1.py
~~~

最终验收记录需分别注明“自动化通过”“WSL 页面通过”“外部环境待验收”。尤其第 8 项和第 19–21 项的微信真机部分，目前不能标记为完整验收通过。
