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

工作台用户与小程序消费者使用独立登录态。服务端检查资料归属、发布状态、VIP与文件访问权限；关闭或禁用账号撤销其会话。Cookie写请求需携带当前账号校验信息，跨账号请求被拒绝。

生成请求受并发、每日预算和幂等约束。流式中断或状态未知时应通过原请求标识恢复，不能无条件重发收费请求。浏览器草稿和历史按账号隔离并执行保留策略，保存失败需先导出保留副本。新建与重设密码至少8位，历史6位密码仍可登录并透明升级到60万次PBKDF2。

配置从[.env.example](.env.example)及[生产环境示例](deploy/.env.production.example)开始。生产保持`DB_AUTO_MIGRATE=false`，发布前单独迁移；provider默认禁止内网地址（`PROVIDER_ALLOW_PRIVATE=false`）。签名密钥和带编号的加密密钥环分别管理，禁止直接替换旧密钥而丢失历史密文解密能力。

## 部署与维护

[部署与备份恢复](docs/deploy.md)说明现有环境核对、镜像发布、异地加密备份、回滚和小程序上线验收。[运维变更手册](docs/operations.md)说明密钥轮换、数据库扩展/收缩迁移、PostgreSQL升级与敏感产物迁移。[监控说明](deploy/monitoring/README.md)提供readyz、磁盘、TLS、备份时效和维护失败检查。

生产运行非root只读容器；镜像、应用日志和备份各自执行保留策略。本地应用日志写`data/logs/application.log`，脱离会话启动器独立轮转`data/logs/launcher.log`。`scripts/prune_artifacts.py`默认只列清单，永不自动清除备份、密钥、环境或本轮审查证据。

普通代码修改走`codex/*`分支与PR，必需检查通过后合并。协作规则见[CLAUDE.md](CLAUDE.md)与[CONTRIBUTING.md](CONTRIBUTING.md)。历史阶段记录和旧版接口详表保存在[docs/archive](docs/archive/README.md)，旧文档入口仍保留。
