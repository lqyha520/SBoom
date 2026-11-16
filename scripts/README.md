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
| `python scripts/generate_api_types.py` | 从后端OpenAPI生成shared/api-schema.ts，包含请求体、路径/查询参数、按状态码区分的响应及ApiResponse成功类型；CI检查生成差异 |
| `python scripts/evaluate_image_generation.py --directory artifacts/<新目录>` | 在本机一次性库使用生产模型配置评测真实习题图片，检查历史错误样本并导出待人工评分记录；会产生生图及识图费用 |
| `python scripts/check_pep_catalog.py --require-complete` | 检查人教版教材目录来源、册次、页码与核实状态；未核实完整时禁止整体替换上线，不访问业务数据库 |
| `python scripts/admin_console_check.py --help` | 后台契约检查，先查看目标和fixture要求 |

启动器输出单独写`data/logs/launcher.log`，5MiB×3份轮转；应用写`data/logs/application.log`。旧纯数字`server.pid`不会自动转换或终止对应进程，先人工确认归属。Windows启动进程保持隐藏；生产使用Compose/systemd，不使用此开发启动器。

测试管理连接为`postgresql://postgres:postgres@127.0.0.1:55432/postgres`，业务测试由`tests/pg_support.py`创建`lc_test_*`。不得使用生产DATABASE_URL、业务容器、远端hostaddr或任意端口。浏览器联调使用`tests/run_ui_contracts.py`及其隔离fixture。

## 备份、发布、迁移

| 脚本 | 用途 |
| --- | --- |
| `release/prepare.py` | 从已提交Git版本构建app/ops镜像，输出镜像ID和校验和；可上传但不自动发布 |
| `release/release.py` | 按候选差异要求免出题、专项一轮或完整三轮；通过后加密备份、迁移/更新app，readyz失败时在兼容条件下回滚镜像 |
| `release/ops.py backup` | 使用部署Compose启动加密异地备份容器 |
| `release/ops.py restore-check` | 在独立临时PG中恢复、核对，不覆盖业务库 |
| `release/prune.py` | 默认预览本项目旧镜像，保护容器使用、当前和回滚镜像；`--apply`才删除 |
| `ops_backup.py` | ops容器入口，init/backup/restore-check；成功备份后写BACKUP_STATUS_FILE回执 |
| `backup_restore.py` | 数据库、私有文件与配置一致性备份/隔离恢复，通常通过ops入口调用 |
| `install_local_backup.py --base-image <已有ops镜像> --verify` | Windows 上为已有 WSL Docker 服务安装本机加密备份，安装后立即执行完整恢复演练 |
| `rehearse-backup.py` | 备份恢复演练工具，先运行`--help`并确认临时目标 |
| `secure_archives.py` | Windows当前用户DPAPI保护密钥，AES-GCM分块加密点名旧备份；默认预览，`--apply`验哈希后移出仓库，`--restore`可恢复到仓库外新目录 |
| `rotate_encryption.py` | 默认只校验和统计拟迁移密文，`--apply`才原子写入；要求新旧密钥环均可读 |

完整命令、配置和迁移顺序见[部署手册](../docs/deploy.md)及[运维变更手册](../docs/operations.md)。生产关闭自动迁移，首次启动也要运行`python -m app.migrations`，不能依赖app启动修改结构。

本地安装器默认使用 Debian 的 `deploy-app-1` / `deploy-db-1`，从已有容器识别网络、数据卷和部署目录；仅创建运维镜像、定时器和自己的临时恢复容器。北京时间每天 03:00 备份、每周日 04:00 恢复演练，最多延迟 5 分钟；定时器 `Persistent=true`。`--state-root` 默认 `/home/lqyha/learn-coach-local-ops`，保存 restic 加密仓库、不可替换的原密码文件和无凭据回执。保留最近 7 个日备份、4 个周备份及6个月备份，不清理旧的人工备份。仓库与密码同在本机，不能替代异地灾备。

```powershell
wsl -d Debian -u root -- systemctl list-timers 'learn-coach-local-*' --all
wsl -d Debian -u root -- systemctl start learn-coach-local-backup.service
wsl -d Debian -u root -- systemctl start learn-coach-local-restore.service
wsl -d Debian -u root -- journalctl -u learn-coach-local-backup.service -u learn-coach-local-restore.service -n 50 --no-pager
```

成功回执在状态目录的 `status/backup.json` 与 `status/restore.json`，后者的 `database_counts_checked=true` 表示已核对快照中全部公共表记录数量；恢复文件逐项复验 SHA-256。恢复服务只连接没有对外端口的临时 `lc_restore_probe` 数据库，退出时删除自己创建的恢复容器。再次安装会沿用原密码与仓库；原密码丢失时禁止生成新密码冒充恢复成功。回执只表示最后一次成功，失败时以 systemd 状态和日志为准。

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

### 可选真实模型诊断

`evaluate_generation.py` 使用 `tests/fixtures/generation-evaluation.json` 的16组固定条件，共58题，覆盖数学、语文、英语和三档难度，并检查数的分成、凑十、重复选项、语境和年级边界。先查看计划：

```bash
python scripts/evaluate_generation.py plan
```

真实运行前，向已部署本轮后端的测试环境配置真实模型；使用专用工作台账号，通过环境变量 `LC_EVAL_USERNAME`、`LC_EVAL_PASSWORD` 提供凭据，不把密码写到命令行。明确目标与费用后执行：

```bash
python scripts/evaluate_generation.py run --base-url https://测试域名 --model-label 配置中的模型版本 --build-id 本次构建摘要 --limit 16 --directory artifacts/quality-run-01 --confirm-paid
python scripts/evaluate_generation.py collect --base-url https://测试域名 --directory artifacts/quality-run-01
python scripts/evaluate_generation.py ratings --directory artifacts/quality-run-01 --output artifacts/quality-run-01/ratings.json
python scripts/evaluate_generation.py report --directory artifacts/quality-run-01 --ratings artifacts/quality-run-01/ratings.json --output artifacts/quality-run-01/report.json
```

`run` 默认只执行第一组，必须显式确认付费，不复用已有目录。每个编号在发送前落盘；未知状态时停止后续样本，`collect` 只查询已提交的原编号，绝不重发生成。尚未提交的样本需之后另建一轮，不能把查询不到当作可免费重试。登录/退出只影响本工具创建的会话；不读取本机 `.env` 密码、不直接调用供应商、不改业务配置。

请人工核对评分表中的题干、答案、解析、阅读依据和年级适配，将 `correct` 从 `null` 填为 `true/false`，错误题写明 `reason`。表中隐藏模型质量标签；评分绑定整轮结果摘要，结果变化必须重建评分表。报告列出各组返回数、缺题、人工覆盖率、正确率及首次HTTP请求耗时（不包含断线后查询恢复）；未评分不算正确。现有API不返回被剔除题原文，误剔除率保持未知，不以缺题率替代。

报告可同时传入 `--input-per-million`、`--output-per-million`，单位为同一种货币/百万token。仅对服务端完整上报的用量估算费用，不代表账单；缓存折扣、不同模型混用、按次计费须另对账。`--model-label` 是操作者填写的配置标签，运行期间应冻结模型配置。结果含合成试题，只保存在指定目录，不上传。

### 已有环境增量发布与运维

`release/incremental.py` 的 `--target wsl|production --release <版本名> --baseline <修改前文件目录> --output <记录目录> --file app/文件.py` 逐一核对运行文件指纹，复用现有镜像，仅复制指定后端文件和已构建的 web/admin 静态文件。构建后逐项核对全部发布文件的 SHA-256，包含 HTML 入口；切换后检查两个页面引用的脚本、样式与预加载资源均可访问。发布记录包含构建摘要、Git 提交、实际改动文件、当前及兼容回滚镜像；只在 Docker 内网启用指标端口，不增加公网端口映射。

新旧 schema 不同时，增量准备要求 `--rollback-image <已验收兼容镜像>`，在构建前校验其 schema 版本；不修改旧程序版本号来伪装兼容。回滚镜像须经实际读写测试，尤其 `2026111002` 起的小红书私有文件引用。完整镜像发布使用 `release/release.py --image <镜像> --manifest <release.json>`；`prepare.py` 在 `release.json` 中以不可变镜像 ID 提供 `image` 和 `build_id`。两个正式发布入口均不要求题目评测或人工评分。

只有后端改动时，`release/incremental.py` 使用 `--backend-only --file app/...`，保留运行镜像内的工作台和管理后台资源，避免夹带本地 `dist` 中其他构建内容。

2026-11-15 起按用户要求永久取消部署前的题目验证和人工评分。`release/quality_policy.py --manifest <部署记录>` 始终返回零轮计划；旧 `evaluate_candidate.py` 入口只输出取消状态，不创建数据库、不连接宿主、不调用模型，即使传入旧样本或思考模式参数也不会启动评测。通用和增量发布入口保留旧 `--run`、`--ratings` 参数兼容性，但不读取这些文件，不因旧评测失败或未评分阻塞发布。

独立诊断工具只在用户明确要求时手动使用，不参与部署门禁。诊断目录中的 `human-review.html` 可用于离线盲评；未评分保持 `null`，评分仍绑定对应的原始结果，不会冒充人工核对或自动用于发布。

数学方法填空允许最多4行、每行24字符以内的步骤，可含简短文字拆分。数字答案必须覆盖每一个空；连续等式与分行的独立步骤分别校验，避免去掉换行后误拼数字。隔离评测在 `quality-rejections.json` 保存合成题的被拒原文以定位误判，业务服务不记录这些题目正文。

生成和复核采用简洁解析提示，仍保留独立求解与质量校验。多音字题允许两个真实读音选项，避免为了凑三个而编造读音。完整响应的 JSON 语法错误，或明确正常结束但只有思考、没有正文的响应，最多使用整个任务共享的一次恢复额度。Qwen3 出题若明确结束且仅有推理而无正文（包括推理耗尽输出额度），此次恢复临时关闭深度思考；正常出题与独立复核沿用原设置，不修改后台配置。所有调用记入原请求追踪与 token 预算，且受原超时约束。`GENERATION_REPAIR_LIMIT=0` 时关闭该恢复。断线、超时、已有正文的截断、重复字段和多份歧义结果不走此重试；原请求查询和重放也不会触发额外调用。

英语代词题须明确指代对象，颜色题须提供文字条件；已能确认缺少必要条件或有多个正确选项时，复核应拒绝该题并进入既有的有限补题流程，无法可靠判断时仍标记待核对。比大小的 JSON 示例使用实际算式和单个带引号的符号。 独立诊断工具和运行时题目复核继续用于定位问题，部署流程不会自动调用它们。

发布执行 `release/deploy_existing.py --target wsl|production --manifest <对应部署记录>`。工具核对候选与当前基线，在宿主加锁执行备份，再关闭新生成任务准入并等待已有任务结束（最多20分钟）。新任务返回503及重试提示，缓存结果可重放；升级尚不支持暂停的旧应用时，独立守卫持有准入锁，停止旧应用后释放锁再迁移。失败取消切换并解除暂停，暂停标记有所有者与过期时间。发布不使用旧评测中的思考模式修改业务模型配置。发布前、发布后及成功回滚后刷新备份目录的 `candidate.json` 和 `current.json`，固定实际运行镜像，文件仅允许运维 uid 10001 读取。其他容器、数据卷和端口保持不变。`release/prune.py --keep 2` 默认预览按镜像 ID 去重的保留计划，`--apply` 才删除；当前镜像、回滚镜像、容器及运维镜像始终受保护。

`install_production_backup.py` 使用现有 SSH 配置（支持非22端口），需要 WSL/生产均具备 Python 3、rsync、Docker 和 systemd。生产每天03:10备份，WSL每天03:30拉取加密仓库并核验，周日05:00隔离恢复，均为北京时间；本机离线时异地同步会延后，生产仍可独立备份。`production_monitor.py` 每五分钟检查就绪、系统盘、数据盘、备份时效和维护指标，写入 `/var/lib/learn-coach-monitor/latest.json` 与 systemd 日志；当前不发送外部消息。

已有安装运行 `install_reliability_ops.py --public-url https://sboom.bcxtech.cn` 升级：不重置原密钥、密码或历史仓库。WSL 的 `source-cache/` 只作密文传输缓存，快照经 `restic copy` 导入另用密码的 `vault/` 独立仓库，并执行全量数据校验；源清理不会传播删除到独立仓库。保留至少最近3份、每日7份、每周4份、每月6份。原 `repository/` 保留，首次先导入上一次已验证快照。每次最多尝试3次，systemd另外在失败后5分钟重试，2小时内最多启动3次。成功回执和最新运行状态分开，失败或运行心跳超过20分钟都会变红，不覆盖上一次成功快照。

生产备份同时归档实际应用、数据库和运维镜像及校验值，镜像变更时才重新导出。`full_restore.py` 从固定独立快照恢复镜像、数据及配置，在仅内部连通的临时Docker网络中启动数据库和真实应用，核对数据行数、文件、就绪接口、工作台、后台和静态资源；不映射公网端口，结束清理自己创建的容器、网络和tmpfs卷。周日05:00自动演练；可用 `systemctl start learn-coach-production-restore.service` 手动执行。

WSL 的 `learn-coach-public-monitor.timer` 每5分钟拨测公网两个页面、全部入口资源和证书（至少剩14天）；生产监测还检查最新备份/恢复失败、备份时效≤27小时、完整恢复≤8天、外部拨测回执≤20分钟。状态分别在 WSL 的 `/home/lqyha/learn-coach-production-backup/status/` 与生产的 `/var/lib/learn-coach/ops-status/`；`latest.json` 为生产汇总。全部仅记录状态与日志，不发送外部通知。

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

新版模板（version 2）同时要求两类设备完成以下操作，并在 `checks` 逐项填入真实结果、附上录像。功能场景不要求无关的性能指标。旧版模板需要重新初始化，不将历史空表当作本次验收。

| 场景 | 操作与功能确认 |
| --- | --- |
| `sharing` | 收藏、下载、最近浏览页没有朋友圈入口；资料详情可分享好友及朋友圈；取消后可以再次分享，接收方打开同一份资料。 |
| `membership_recovery` | 单独阻断客服或套餐请求；客服失败不改变 iPhone 开通能力，套餐失败可重试，联系方式入口仍可进入。 |
| `referral_landing` | 正常扫码进入活动；响应延迟超过 1.5 秒、开始触摸/输入、离开再返回时不突然跳转；注册来源仍保留。 |
| `feedback_draft` | 关闭页面后恢复描述、类型和关联资料；切换账号隔离；成功提交清理草稿；存储失败有重试提示。 |
| `payment_return` | 用测试账号验证原生付款返回、切后台恢复、会员权益更新和没有重复付款入口；真实实付由测试者操作，自动脚本不发起付款。 |
