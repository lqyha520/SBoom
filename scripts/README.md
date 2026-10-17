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
| `python scripts/check_pep_catalog.py --require-complete` | 检查人教版教材目录来源、册次、页码与核实状态；未核实完整时禁止整体替换上线，不访问业务数据库 |
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

## 质量与真机验收

### 真实模型评测

`evaluate_generation.py` 使用 `tests/fixtures/generation-evaluation.json` 的8组固定条件，覆盖数学、语文、英语和三档难度，每组3题。先查看计划：

```bash
python scripts/evaluate_generation.py plan
```

真实运行前，向已部署本轮后端的测试环境配置真实模型；使用专用工作台账号，通过环境变量 `LC_EVAL_USERNAME`、`LC_EVAL_PASSWORD` 提供凭据，不把密码写到命令行。明确目标与费用后执行：

```bash
python scripts/evaluate_generation.py run --base-url https://测试域名 --model-label 配置中的模型版本 --limit 8 --directory artifacts/quality-run-01 --confirm-paid
python scripts/evaluate_generation.py collect --base-url https://测试域名 --directory artifacts/quality-run-01
python scripts/evaluate_generation.py ratings --directory artifacts/quality-run-01 --output artifacts/quality-run-01/ratings.json
python scripts/evaluate_generation.py report --directory artifacts/quality-run-01 --ratings artifacts/quality-run-01/ratings.json --output artifacts/quality-run-01/report.json
```

`run` 默认只执行第一组，必须显式确认付费，不复用已有目录。每个编号在发送前落盘；未知状态时停止后续样本，`collect` 只查询已提交的原编号，绝不重发生成。尚未提交的样本需之后另建一轮，不能把查询不到当作可免费重试。登录/退出只影响本工具创建的会话；不读取本机 `.env` 密码、不直接调用供应商、不改业务配置。

请人工核对评分表中的题干、答案、解析、阅读依据和年级适配，将 `correct` 从 `null` 填为 `true/false`，错误题写明 `reason`。表中隐藏模型质量标签；评分绑定整轮结果摘要，结果变化必须重建评分表。报告列出各组返回数、缺题、人工覆盖率、正确率及首次HTTP请求耗时（不包含断线后查询恢复）；未评分不算正确。现有API不返回被剔除题原文，误剔除率保持未知，不以缺题率替代。

报告可同时传入 `--input-per-million`、`--output-per-million`，单位为同一种货币/百万token。仅对服务端完整上报的用量估算费用，不代表账单；缓存折扣、不同模型混用、按次计费须另对账。`--model-label` 是操作者填写的配置标签，运行期间应冻结模型配置。结果含合成试题，只保存在指定目录，不上传。

### 微信真机验收

```bash
python scripts/check_device_acceptance.py init artifacts/device-run-01/acceptance.json
python scripts/check_device_acceptance.py check artifacts/device-run-01/acceptance.json
```

模板默认全部未验收。分别在低端安卓和 iOS 的可重复弱网条件下，记录设备/系统/微信版本、构建commit、网络限速/延迟及测试时间；用专用测试账号和40页资料，保存录像或开发者工具性能trace到同一目录。每个场景完成至少5次测量：

| 场景 | 操作与功能确认 | 当前阈值 |
| --- | --- | --- |
| `cold_start` | 彻底退出后冷启动，确认首屏文字和封面可用，每次复制故障记录 | `home_cold` 每个会话p95最大值≤5000ms |
| `reader_40_pages` | 连续前后翻页、跨组选页、缩放，确认无白页、错页、卡死；用trace另查掉帧 | `reader_image` ≤1500ms |
| `pdf_open` | 下载并打开PDF，再从微信菜单另存且重新打开核验 | `pdf_open` ≤15000ms |
| `foreground_resume` | 返回首页后切后台30秒再恢复，确认原账号、资料和交互状态正常 | `home_warm` ≤3000ms |

上述是初始验收预算，不是实测成绩；固定测试PDF大小和网络参数后再比较版本。`home_cold/home_warm` 只计数据就绪，不代表图片绘制或前台全部业务恢复；`pdf_open` 只计微信打开回调，不代表另存成功。完整功能必须人工确认，H5不能替代微信原生文件验证。

将“服务与反馈 → 复制故障记录”的JSON分别放入目录，在对应记录的 `diagnostics` 列出相对文件名，`evidence` 列出录像/trace相对文件名，完整操作成功后才填 `functional_pass: true`。多份诊断按最大会话p95校验，不伪称合并后的整体p95；相同文件不能重复凑样本。缺测量、异常/内存告警、缺文件或超阈值均返回非零。既有诊断包含历史错误计数，复测前使用干净测试安装并保留旧失败证据。校验只证明记录完整，不证明设备或录像真实性，最终由测试者签收。
