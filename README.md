# 出题工作台

面向教师的出题与排版工作台、内容和会员管理后台，以及独立消费者账号体系的小程序。FastAPI提供统一服务，PostgreSQL保存业务数据，私有文件经过归属和权限校验后访问。

## 环境与启动

需要Python3.12、Node22.12+、pnpm10.14.0和PostgreSQL16。版本与哈希锁文件纳入仓库，更新依赖时同步更新锁文件。

```bash
python -m venv .venv
# 激活该环境后：
python -m pip install --require-hashes -r requirements-dev.lock
pnpm --dir web install --frozen-lockfile
pnpm --dir miniprogram install --frozen-lockfile
```

`admin/node_modules`复用`web/node_modules`。已有链接不要覆盖；全新Linux检出可执行`ln -s ../web/node_modules admin/node_modules`，Windows可使用目录联接或具备权限的符号链接。

首次从`.env.example`创建`.env`，已有文件不要覆盖。至少设置`DATABASE_URL`；应用和测试使用不同实例。日常开发库只需启动根Compose中的`db`服务：

```bash
docker compose up -d db
python -m app.migrations
pnpm --dir web build
pnpm --dir admin build
python run.py
```

默认工作台`http://127.0.0.1:8000/`，后台`/admin/`。模型和生图服务由管理员配置；生产关闭公开API文档，本地开发可访问`/docs`。小程序H5通过`pnpm --dir miniprogram dev:h5`启动，微信构建与发布要求见[小程序README](miniprogram/README.md)。

## 目录与入口

| 目录 | 职责 |
| --- | --- |
| `app/` | API、业务服务、PostgreSQL访问与版本迁移 |
| `web/` | 出题、草稿、排版、打印和私人归档 |
| `admin/` | 公共资料发布、用户、会员、订单、运营内容 |
| `miniprogram/` | 消费者浏览、收藏、预览、下载与账户服务 |
| `shared/`、`ui/` | 共用HTTP内核、接口类型、状态文案与主题 |
| `tests/` | 后端回归、独立数据库护栏与浏览器fixture |
| `scripts/` | [开发、备份、发布与维护命令](scripts/README.md) |
| `deploy/` | 生产Compose、代理、备份与监控模板 |
| `docs/` | 当前产品说明、部署手册与历史归档 |

## 验证

独立测试库监听`127.0.0.1:55432`，使用tmpfs；只允许创建/删除`lc_test_*`一次性数据库。`dev.py`去除继承的`DATABASE_URL`并设置专用测试管理连接，不会停止日常`db`服务。

```bash
python scripts/dev.py up
python scripts/dev.py test
python scripts/dev.py down
python -m ruff check app tests run.py scripts
python -m mypy app run.py scripts
```

测试的 `-n auto` 最多启动4个进程，避免高核数电脑把临时数据库挤满；独立测试库使用1GiB临时数据盘，并限制WAL检查点容量。

三端分别运行`typecheck`、`lint`、`test`、`build`；小程序构建命令为`build:mp-weixin`、`check:mp`和`build:h5`。HTTP契约验证先构建web/admin，再运行`python tests/run_ui_contracts.py`。完整首页浏览器验证还需以 `VITE_API_BASE_URL=/` 构建小程序H5、安装Playwright Chromium，然后运行 `python tests/run_ui_contracts.py --browser`；fixture只使用一次性测试数据，并拦截站外请求。CI还验证锁文件、接口类型、换行、依赖审计和运行镜像。

接口以本地`/openapi.json`和生成的[shared/api-schema.ts](shared/api-schema.ts)为准。修改输入模型后运行`python scripts/generate_api_types.py`，提交生成差异；无需在README重复维护所有请求体。

## 数据与权限

工作台标题修改默认仅作用于当前试卷，也可选择应用全部；主下载按钮明确导出学生卷，含答案文件从导出选项选择。笔记本短屏自动使用紧凑间距，搭建时可切换专注预览；知识点支持搜索、学期折叠和已选汇总。分页按大题缓存测量，撤销历史共享未变化的题目副本。

后台按工作台、内容资料、用户服务、会员交易、运营配置和系统设置分组，默认展开当前业务组，可搜索菜单并将最多6个常用入口固定到顶部菜单。首页展示平台概况、待办和生成用量；待办直接进入草稿、资料需求、反馈和退款列表。公共习题使用状态标签和组合筛选，筛选与页码保存在网址中，列表和统计独立加载。全屏资料编辑区集中基本信息、教学标签、打印版本和修订稿，角色预览按需展开，支持就地创建分类和创建后继续核对发布。文本与图片模型配置分标签展示，切换时保留草稿。专题支持拖动或上下移排序；编辑表单在关闭、Esc、切换页面与关闭浏览器时检查未保存内容。

后台采用墨绿导航与卡片布局，首页提供资料和内容数据快捷入口，并按服务端真实统计展示最近24小时请求状态分布。资料筛选、批量选择和编辑表单使用统一分组与反馈；入场、悬停和弹窗动效遵循系统“减少动态效果”设置，窄屏保留完整导航与固定保存操作。

工作台用户与小程序消费者使用独立登录态。服务端检查资料归属、发布状态、VIP与文件访问权限；关闭或禁用账号撤销其会话。Cookie写请求需携带当前账号校验信息，跨账号请求被拒绝。

生成试卷时留在搭建页显示进度，本批处理结束且有可用试卷后切换结果页；全部失败时留在搭建页查看错误或查询原请求。生成请求受并发、每日预算和幂等约束。`GENERATION_DAILY_LIMIT`默认每用户滚动24小时20次，试卷与图片共用额度，失败请求也计数；设为`0`可关闭该次数限制，并发和全站预算仍生效。流式中断或状态未知时应通过原请求标识恢复，不能无条件重发收费请求。浏览器草稿和历史按账号隔离并执行保留策略，保存失败需先导出保留副本。新建与重设密码至少8位，历史6位密码仍可登录并透明升级到60万次PBKDF2。

配置从[.env.example](.env.example)及[生产环境示例](deploy/.env.production.example)开始。生产保持`DB_AUTO_MIGRATE=false`，发布前单独迁移；provider默认禁止内网地址（`PROVIDER_ALLOW_PRIVATE=false`）。签名密钥和带编号的加密密钥环分别管理，禁止直接替换旧密钥而丢失历史密文解密能力。

出题提示词提供年级、科目、题数、知识点和对应人教版教材册次，题型使用中文名称。额外仅保留各大题题数、section_id及JSON字段格式，并要求题干简洁、答案解析分离，不附加教学目标、例题、字数限制、考法配额或随机批次。旧难度参数仍兼容接收和保存，但不再传入提示词。整卷、单题、流式及补题使用同一套规则。

教材目录唯一来源为 `app/data/pep_catalog.json`，按人教社官方当前公开册次逐册核对；英语只用 PEP 三年级起点。目录保存官方资源号、核对日期、单元页码与细分项来源页，资源号中的年份不冒充出版版次。旧范围文件已移除，历史数据库知识点停用且不再接受编辑，不改写历史试卷。当前目录整理尚未完成，`pending` 册次不提供知识点，也不使用旧清单兜底；完整替换上线前必须通过 `python scripts/check_pep_catalog.py --require-complete`。

接口字段区分题干与解析：计算题题干不含结果，填空题使用简短题干，解题步骤放解析。校验兼容全角数字和运算符，仍拦截错误答案。批量和单题生成缺题时返回 `422 generation_incomplete`，`partial_sections` 保留有效题目及具体剔除原因；同一请求查询或重放不重新计费。工作台将缺题试卷保留为待完成，手动补齐只请求缺少的题（阅读题整篇重生成，避免混入不同文章）。

所有支持的年级、知识点和题型的新出题请求统一调用模型；题干、答案与解析均由模型生成，本地程序只做校验、筛选与结果整理，不随机编题，也不在模型失败时用本地题目兜底。历史标签不再静默改写成当前教材标签，知识点自由输入保持原意。缺题时仅在既有预算内请求模型补齐，仍不足则明确提示；原请求查询与重放不重复调用模型。

新增大题、增加题数及只有配置的旧模板均不填充模拟题；未生成部分保持空白并显示待生成题量，明确点击生成后才请求模型。旧模板快照只恢复已有内容，不猜测缺失题目与答案。锁定题目保留原样；若某份试卷已全部锁定，则提示解锁并保留原卷，不把零模型调用的复制操作记为新生成。查看历史、查询原请求、预览出题说明及下载已有结果都不属于新出题。

结果处理保留字段、题型格式和可确定的答案检查；重复题只通过提示词“本次生成的题目不要重复”约束，不再本地去重、因重复补题或拒绝单题替换，也不读取前序分块来剔除重复题。取消历史相似度、计算关系次数、填空考法配额和预设凑十数值边界对结果的干预，不为这些原因补题，也不再自动调整判断或比较题的顺序。题意和教学适配由教师核对。补题沿用原有调用上限，不用本地题目凑数；原请求查询与重放保持原结果。

热门排序使用事务内维护的收藏与下载用户汇总，重复下载不重复计数。升级到数据库版本`2026100501`前执行`python -m app.migrations`，迁移会回填既有记录；迁移完成后再启动新版应用。

## 部署与维护

[部署与备份恢复](docs/deploy.md)说明现有环境核对、镜像发布、异地加密备份、回滚和小程序上线验收。[运维变更手册](docs/operations.md)说明密钥轮换、数据库扩展/收缩迁移、PostgreSQL升级与敏感产物迁移。[监控说明](deploy/monitoring/README.md)提供readyz、磁盘、TLS、备份时效和维护失败检查。

生产运行非root只读容器；镜像、应用日志和备份各自执行保留策略。本地应用日志写`data/logs/application.log`，脱离会话启动器独立轮转`data/logs/launcher.log`。`scripts/prune_artifacts.py`默认只列清单，永不自动清除备份、密钥、环境或本轮审查证据。

普通代码修改走`codex/*`分支与PR，必需检查通过后合并。协作规则见[CLAUDE.md](CLAUDE.md)与[CONTRIBUTING.md](CONTRIBUTING.md)。历史阶段记录和旧版接口详表保存在[docs/archive](docs/archive/README.md)，旧文档入口仍保留。
