> 历史设计/验收记录，保留原内容供追溯。旧命令和状态不代表当前实现；入口见[项目README](../../README.md)。

# 全项目优化交付 · 2026-09-21

本轮落实审查中的 14 项改进，保留原工作目录的功能开发。数据库迁移采用增量建表/补列；没有部署生产、修改现有业务库、调用付费模型或发送实际支付请求。

## 变更对应表

| 审查项 | 已实现行为 |
| --- | --- |
| 1 健康检查 | `/health` 只表示进程存活；`/readyz`、`/health/detail` 共用有时限的数据库探针，失败返回 503。供应商连通性明确标为 `not_probed`。Docker 改查 `/readyz`。 |
| 2 导入阻塞 | 最后一步入库也在线程执行；重复 PDF 在渲染前复用归档；每 worker 只允许一个 PDFium 导入，忙时返回 429 和 Retry-After，避免排队保留大文件。 |
| 3 监控 | ASGI 中间件记录完整响应耗时，URL 使用路由模板，未匹配请求共用固定标签。模型实际尝试、成功/失败、token、生成结果、连接池和锁等待已接入；exporter 与 HTTPS 解耦，多进程由启动器统一汇总。 |
| 4 答案上传 | 后台打印版本对话框支持直接上传，传入 revision 和发布确认；已发布资料在读取 PDF 前校验。失败重试复用原文件归档，版本冲突需刷新后再确认。 |
| 5 部署入口 | server compose 默认仅绑定回环端口，启用 Secure Cookie，可信代理 IP 改为环境配置。上线前先配置加密回源，迁移步骤见下文。 |
| 6 缩略图 | 新发布文件生成 320×480 边界内的 JPEG；列表优先使用缩略图，详情继续原页。旧资料由有配额保护的任务分批补齐，沿用原资料访问权限。 |
| 7 长列表 | 返回时刷新首批与一次批量窗口校验，20/200/1000 条均固定两次列表请求。权限、收藏和下架情况重新校验；筛选/账号变更清空窗口；列表内容变动时回到第一页。 |
| 8 缓存/取消 | 首页配置、专题使用 60 秒缓存并合并并发请求；强制刷新绕过旧请求，写操作和账号切换失效。引用计数保证最后一个消费者离开才取消共用请求。个人统计不进入公开配置缓存。 |
| 9 生图存储 | 新结果放入私有文件，数据库和恢复 API 只返回元数据；按用户预留容量，默认 512 MiB，与结果期限一起清理；防重复调用的请求记录保留。旧 Base64 结果仍可读，浏览器历史改存 Blob。 |
| 10 锁/清理 | 浏览与事件改用用户级内容锁；批量过期清理移到独立维护任务，每轮限量，支付未启用时也能运行。 |
| 11 规模性能 | 热门排序改为聚合连接；跨表搜索拆成候选 ID 并集，补 trigram 索引。撤销快照序列化结果复用，避免反复序列化整个撤销栈。 |
| 12 元数据/复核 | 导入保留知识点、题型、申报题量，不伪造可编辑题目；无题型时采用明确的导入默认策略。发布/修订/答案确认记录人工复核者和时间，显示答案文件状态。已有纠错入口继续使用。 |
| 13 依赖/CI | jsPDF 4.2.1；uni 编译器 5.26、Vite 6.4.3 和必要传递依赖完成兼容升级；三端完整扫描为 0 告警。CI 新增官方源扫描，高危及以上阻断。Docker/CI 升级 pip。 |
| 14 清理/备份 | 删除意图在删除记录的事务内入队，失败退避重试；孤立文件扫描保留 24 小时宽限期。提供一致性备份、仅向空白隔离库恢复的脚本及定时器模板；已演练文件与加密数据恢复。 |

## 测量结果

`python scripts/benchmark-catalog.py artifacts/optimization-2026-09-21/catalog-benchmark-repeat.json` 仅创建并自动删除本机 `lc_test_*` 库，保留 EXPLAIN ANALYZE/BUFFERS 原始结果。以下为最终复测，每项取三次查询中位数；首次测量保存在同目录的 `catalog-benchmark.json`，结果趋势一致：

| 样本 | 热门原查询 → 聚合查询 | 原搜索 → 并集搜索 + trigram |
| --- | ---: | ---: |
| 10,000 资料 | 33.81 → 8.51 ms | 6.32 → 0.85 ms |
| 100,000 资料 | 363.34 → 74.56 ms | 45.58 → 6.94 ms |

这是本机合成样本的 SQL 基准，不代表生产端到端延迟或并发容量。trigram 扩展权限不足时记录告警，查询仍正确；由数据库管理员预装 `pg_trgm` 后重启即可补索引。大库首次建索引应安排维护窗口。

封面先前 5 页样本由 840,091 B 缩到 98,019 B，减少 88.3%；本轮已将对应缩略图路径接入业务。微信构建 312 文件，约 855 KiB，仍低于 2 MiB。

## 运维配置

- `METRICS_ENABLED=true` 单独启用监控；默认监听 `127.0.0.1:9090`。容器内供私网采集时设置 `METRICS_HOST=0.0.0.0`，仅在内部网络暴露。多 worker 必须通过 `python run.py` 启动；每次启动独立 metrics 目录，由父进程统一 exporter。`python scripts/check-metrics-workers.py` 验证两进程 400 个请求聚合为两组路由标签。
- `MAINTENANCE_ENABLED=true` 默认每分钟运行。单轮最多清理 500 条旧事件、100 条生成结果、50 张过期图片、50 个删除任务，扫描 500 个目录项并补 5 张缩略图。通过独立 PG 锁选出当前维护进程。可用 `python -m app.services.maintenance` 手动推进一轮；失败见日志和 `maintenance_failures_total`。
- `IMAGE_STORAGE_MB=512` 为每用户生图配额，入场时为每个运行任务预留 12 MiB；`GENERATION_RESULT_DAYS` 同时控制新图片保留期限。过期后保留请求墓碑，重放返回 410，避免再次计费。浏览器已有 Blob 副本仍能下载。
- `IMPORT_DEFAULT_VIEW_ACCESS` / `IMPORT_DEFAULT_DOWNLOAD_ACCESS` 为无题型资料的默认权限，可设 free 或 vip；创建时写成明确策略。已存在资料的权限不批量变更。
- 生成图像的题量仍是申报值；人工复核不等于 OCR 或数学正确性验证。旧发布资料显示“尚未记录”，可在后台核对后补确认，不伪造历史复核记录。

## HTTPS 回源迁移

新版 `deploy/docker-compose.server.yml` 将应用端口改为 `127.0.0.1:33403`，`FORCE_HTTPS=true`。先完成以下配置，再重建切换；本轮没有直接运行生产 compose。

1. 将现有反代到应用的连接改为 TLS 或 SSH 隧道。一个可用方案是在 HTTPS nginx 主机上运行受 systemd 管理的 SSH 本地转发：`ssh -N -L 127.0.0.1:33404:127.0.0.1:33403 app-server`；nginx upstream 使用本机 `http://127.0.0.1:33404`，跨主机部分由 SSH 加密。
2. nginx 覆写 Host、X-Forwarded-Proto=https 和 X-Forwarded-For。把容器实际看到的隧道/代理来源地址加入 `FORWARDED_ALLOW_IPS`，不要填 `*`。Docker 桥接下该地址可能是网关，应实测确认。
3. 验证 HTTPS 登录、Secure Cookie、小程序请求、`/readyz`、日志中的真实客户端 IP；从另一主机确认 33403 不再可直连。故障时回滚镜像/入口配置，保留数据库和文件；不通过关闭 Cookie Secure 长期维持公网明文登录。

## 备份与隔离恢复

`python scripts/backup_restore.py --help`。运行环境需安装 requirements 与匹配 PostgreSQL 主版本的 `pg_dump` / `pg_restore`；也支持在指定本机数据库容器内运行工具（`--pg-container`），Windows 可通过 WSL Docker 调用。

```sh
# DATABASE_URL 指向被备份的数据库；脚本不自动读取 --env-file 作为连接配置。
python scripts/backup_restore.py backup --destination /backup/20260921T030000Z --files-root /srv/learn-coach/paper-files --env-file /etc/learn-coach/service.env --secret-file /srv/learn-coach/secret_key.txt

# LC_RESTORE_DATABASE_URL 必须为本机 lc_restore_* 或 lc_test_* 空库。
python scripts/backup_restore.py restore --source /backup/20260921T030000Z --destination /srv/learn-coach-restore/20260921
```

备份持有业务及维护锁后导出 PG snapshot，按同一份清单复制不可变文件，包含 `service.env`、密钥文件及 SHA-256 清单。期间写操作可能等待，应选择业务低谷；读取不受业务锁限制。若同时存在环境密钥和历史 secret_key.txt，两者都要备份。仅使用环境密钥且确实没有历史密钥文件时可省略 `--secret-file`。

备份集含密钥，使用受限目录和加密磁盘/对象存储。脚本不上传、不自动删除旧备份。为恢复验证创建新的空数据库和文件目录，绝不覆盖生产。恢复的 service.env 仅供核对密钥；启动恢复实例时必须显式覆盖数据库 URL 和存储目录，关闭支付/订阅维护。

`python scripts/rehearse-backup.py` 在本机 `learncoach-db` 测试容器上创建两份一次性数据库，生成文件、备份、恢复、校验下载文件路径和密文解密，最后只删除这两个测试库。本轮已通过。

`deploy/learn-coach-backup.{service,timer}` 与告警 service 是可安装模板，默认凌晨 3 点执行，失败进入 systemd 日志。先设置 `/etc/learn-coach/backup.env` 中的 DATABASE_URL、BACKUP_ROOT、ARCHIVE_LOCAL_DIR、SERVICE_ENV_FILE、SERVICE_SECRET_FILE，并保证 PostgreSQL 工具与数据库可达、文件根对应实际卷路径；验证一次手动备份后再由运维启用 timer。本轮未启用定时任务。

## 兼容性与跨层核对

- 工作台、后台和 API 应同步发布；更新前已打开的旧工作台请刷新，新图片恢复结果使用私有资产 URL。旧 Base64 历史继续兼容。
- 核对了生图 → 计费记录 → 私有文件 → 账号鉴权 → Blob/PDF 导出，以及导入 → 公共目录 → 会员权限 → 缩略图/原稿交付的读写链路。
- 题型、权限、发布确认和修订号在前后端保持一致；失败、离页、账号变化和未知计费结果有对应回归用例。
- 数据库迁移幂等；删除队列与记录删除处于同一事务；备份校验失败或非空恢复目标会停止，不覆盖现有目录。
- Vite/uni 和传递依赖的固定覆盖集中在 `miniprogram/package.json`，并以 H5、微信构建和交互测试作为兼容依据。后续升级 uni 时应重新验证并移除上游已修复的覆盖。

## 最终验证

共 **621 项自动化测试通过**，另有 8 项 UI/API 契约测试和 12 项后台检查通过。完整日志和产物位于 `artifacts/optimization-2026-09-21/`。

| 范围 | 最终结果 | 日志 |
| --- | --- | --- |
| 后端完整回归 | 343 项通过，364.6 秒 | `backend-verified.log` |
| 工作台 | 124 项通过，类型检查、生产构建通过 | `web-test-final.log`、`web-type-final.log`、`web-build.log` |
| 管理后台 | 31 项通过，类型检查、生产构建通过 | `admin-test2.log`、`admin-type-final.log`、`admin-build.log` |
| 小程序 | 123 项通过，类型检查、微信/H5 构建通过 | `mini-test-final.log`、`mini-type-final.log`、`mini-weixin-build.log`、`mini-h5-build.log` |
| 静态检查 | mypy 检查 85 个源文件通过；`git diff --check` 通过 | `mypy-final.log` |
| UI/API 契约 | 8 项测试及 12 项后台检查通过，使用本轮新构建 | `ui-contracts.log` |
| 启停与监控 | 应用启动、维护、就绪探针、采集和关闭通过；两进程 400 个请求正确聚合为两组标签 | `startup-smoke.log`、`metrics-workers.log` |
| 依赖扫描 | 三端完整依赖扫描均为 0 告警；Python 扫描未发现已知漏洞 | `web-audit-final.json`、`admin-audit-final.json`、`mini-audit-final2.json`、`python-audit.log` |
| 备份恢复 | 隔离恢复 3 个文件，下载路径和历史密文解密通过 | `backup-rehearsal.log` |

## 验证边界

完整测试、构建、审计、恢复、SQL 计划日志位于 `artifacts/optimization-2026-09-21/`。UI/API 契约运行时明确指向本轮新构建。浏览器控制工具此前返回授权不可用，本轮没有新的视觉截图、LCP/INP、浏览器峰值内存或微信真机测量；这些指标不能用单元测试替代。生产 HTTPS 切换、防火墙、设备验收与备份定时器启用属于上线工作，未在本机擅自执行。
