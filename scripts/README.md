# 维护脚本

从仓库根目录、Python3.12环境执行。可复现依赖用`python -m pip install --require-hashes -r requirements-dev.lock`。先核对目标，生产密钥只放仓库外配置文件；不要将整份环境、数据库内容或命令响应贴入日志。

## 开发与检查

| 命令 | 用途与边界 |
| --- | --- |
| `python scripts/dev.py up` | 只启动根Compose的`test-db`，tmpfs、127.0.0.1:55432 |
| `python scripts/dev.py test -- -q` | 启动测试库后跑pytest；删除继承的DATABASE_URL，固定LC_TEST_PG_ADMIN |
| `python scripts/dev.py down` | 只停止`test-db`，保留日常db及业务容器 |
| `python scripts/dev.py test --dry-run` | 仅打印即将执行的命令 |
| `python scripts/serve_detached.py` | 独立监督进程启动run.py，等readyz通过 |
| `python scripts/serve_detached.py --status` | 检查监督进程与readyz，未就绪返回非零 |
| `python scripts/serve_detached.py --stop` | 通过随机令牌控制通道停止自己启动的子进程；不按旧PID盲目杀进程 |
| `python scripts/generate_api_types.py` | 从后端OpenAPI生成shared/api-schema.ts；CI检查生成差异 |
| `python scripts/admin_console_check.py --help` | 后台契约检查，先查看目标和fixture要求 |

启动器输出单独写`data/logs/launcher.log`，5MiB×3份轮转；应用写`data/logs/application.log`。旧纯数字`server.pid`不会自动转换或终止对应进程，先人工确认归属。Windows启动进程保持隐藏；生产使用Compose/systemd，不使用此开发启动器。

测试管理连接为`postgresql://postgres:postgres@127.0.0.1:55432/postgres`，业务测试由`tests/pg_support.py`创建`lc_test_*`。不得使用生产DATABASE_URL、业务容器、远端hostaddr或任意端口。浏览器联调使用`tests/run_ui_contracts.py`及其隔离fixture。

## 备份、发布、迁移

| 脚本 | 用途 |
| --- | --- |
| `release/prepare.py` | 从已提交Git版本构建app/ops镜像，输出镜像ID和校验和；可上传但不自动发布 |
| `release/release.py` | 先加密备份再迁移/更新app，readyz失败时在兼容条件下回滚镜像 |
| `release/ops.py backup` | 使用部署Compose启动加密异地备份容器 |
| `release/ops.py restore-check` | 在独立临时PG中恢复、核对，不覆盖业务库 |
| `release/prune.py` | 默认预览本项目旧镜像，保护容器使用、当前和回滚镜像；`--apply`才删除 |
| `ops_backup.py` | ops容器入口，init/backup/restore-check；成功备份后写BACKUP_STATUS_FILE回执 |
| `backup_restore.py` | 数据库、私有文件与配置一致性备份/隔离恢复，通常通过ops入口调用 |
| `rehearse-backup.py` | 备份恢复演练工具，先运行`--help`并确认临时目标 |
| `secure_archives.py` | Windows当前用户DPAPI保护密钥，AES-GCM分块加密点名旧备份；默认预览，`--apply`验哈希后移出仓库，`--restore`可恢复到仓库外新目录 |
| `rotate_encryption.py` | 默认只校验和统计拟迁移密文，`--apply`才原子写入；要求新旧密钥环均可读 |

完整命令、配置和迁移顺序见[部署手册](../docs/deploy.md)及[运维变更手册](../docs/operations.md)。生产关闭自动迁移，首次启动也要运行`python -m app.migrations`，不能依赖app启动修改结构。

## 监控与产物

```bash
python scripts/ops_check.py --help
python scripts/prune_artifacts.py --dry-run
python scripts/prune_artifacts.py --days 30 --archive-loose --dry-run
```

ops_check输出JSON、失败返回1，不发送通知。生产需要配置readyz、内部metrics可达路径、备份成功回执和TLS域名；定时器、外部拨测与验收见[监控说明](../deploy/monitoring/README.md)。直接执行不设state-file不会落盘，定时运行可显式保存维护计数基线。

prune默认只报告。`--archive-loose --apply`按日期移动过期顶层诊断，`--apply`删除过期诊断；删除前核对输出。备份、加密密钥、虚拟环境、符号链接和本轮审查证据永不自动删除。镜像包和不认识的后缀也保留。真实备份须先验证仓库外加密副本，详见运维变更手册。

## 压测与数据工具

`bench_api.py`、`bench_memory.py`、`bench_runtime.py`、`benchmark-catalog.py`与`check-metrics-workers.py`用于隔离环境测量。逐个查看`--help`，记录数据规模、并发、进程数与目标；不得默认向生产发压测流量。`import_demo_catalog.py`只导入隔离演示数据；`smoke_site.py`已接入pg_support护栏，只在本机创建和清理 `lc_test_site_*` 一次性库，日常回归优先pytest。

新增可复用脚本放本目录并补用法和安全边界；一次性排查脚本放`artifacts/日期-主题/`，不要放仓库根目录。
