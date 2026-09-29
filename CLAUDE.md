# learn-coach 工作约定（给 Claude Code / 协作者）

## 仓库布局
- `app/`：FastAPI 后端（`app/main.py` 入口；`services/` 业务、`routers/` 路由、`db.py` PostgreSQL 访问层）。
- `web/`：出题工作台（Vue 3 + Vite），`admin/`：管理后台（独立 Vite 项目，`admin/node_modules` 是指向 `web/node_modules` 的符号链接）。
- `miniprogram/`：uni-app 小程序（H5 + 微信）。`shared/`、`ui/`：三个前端共用的类型/主题配置（Docker 构建阶段会一起拷贝）。
- `tests/`：后端测试（`test_backend_*.py`）与 UI 契约/fixture 脚本；`scripts/`：正式维护脚本（备份、压测、演示数据导入、后台自检）。
- `deploy/`：生产 compose（Caddy 版 `docker-compose.yml`、加密回源版 `docker-compose.server.yml`）、systemd 备份单元；根 `docker-compose.yml` 提供日常 db 与 tests profile 的独立 test-db。
- `docs/`：设计与验收记录；`artifacts/`：截图/压测/临时脚本归档，整个目录不入库。

## 环境准备
```bash
python -m pip install --require-hashes -r requirements-dev.lock  # Python 3.12；含开发工具的哈希锁文件
cp -n .env.example .env                    # 至少配 DATABASE_URL；日常 PG 用根目录 docker compose up -d db；测试用 python scripts/dev.py up
pnpm --dir web install --frozen-lockfile   # admin 复用 web/node_modules（符号链接），不要单独 install 覆盖它
pnpm --dir miniprogram install --frozen-lockfile
```

## 检查命令（提交前至少跑改动涉及的那一组）
| 组件 | 命令 |
| --- | --- |
| 后端 | `ruff check app tests run.py scripts`、`mypy app run.py scripts`、`python -m pytest -n auto`（需本机可达的 PostgreSQL，见下） |
| web / admin | `pnpm --dir <web|admin> typecheck`、`pnpm --dir <web|admin> test`、`pnpm --dir <web|admin> build`、`pnpm --dir <x> run lint` |
| miniprogram | `pnpm --dir miniprogram typecheck`、`lint`、`test`、`check:overrides`、`build:mp-weixin`、`check:mp`、`build:h5` |
| 全栈契约 | `python tests/run_ui_contracts.py`（需先 build web/admin） |
| 镜像 | `docker build --target runtime -t learncoach .`（BuildKit；国内可加 `--build-arg PIP_INDEX_URL=...`） |

CI（`.github/workflows/ci.yml`）跑的就是这些，另加 `pip-audit`、`pnpm audit` 与镜像构建冒烟。

## 测试数据库红线
- 测试只允许连本机实例，并且只创建/删除 `lc_test_*` 前缀的一次性库；管理连接由 `LC_TEST_PG_ADMIN` 指定（推荐通过 `scripts/dev.py` 固定为 `postgresql://postgres:postgres@127.0.0.1:55432/postgres`；直接pytest保留历史本机5432兼容），护栏在 `tests/pg_support.py`。
- 绝不把 `DATABASE_URL` / `LC_TEST_PG_ADMIN` 指向业务库、生产库或 `deploy-db-1` 这类容器；不要写"临时"脚本直接改业务库状态（如把 paper 置为 published）。
- 本机 WSL 里跑着 `deploy-app-1` / `deploy-db-1` / `learncoach-db` 等类生产容器，只读查看，不要 stop/rm/down。

## 仓库整洁
- 仓库根不放一次性脚本：能复用的进 `scripts/`（带用法说明），排查用的放 `artifacts/<日期-主题>/`。`.gitignore` 已拦截根目录 `check_*.py` / `update_*.py` / `verify_*.py` / `*.sql` / `_*.py`，被拦截说明放错了地方，而不是该去改规则。
- 不要提交 `.env*`、`data/`、`server.log*`、`*.pid`、前端 `dist/`。
- 注释与文档用中文；不新增 README 之外的总结性 markdown，除非任务明确要求。

## 换行与编码
- `.gitattributes`：全部文本 LF 入库并 LF 检出（`*.cmd/*.bat/*.ps1` 例外为 CRLF），`.editorconfig` 同步（py 4 空格，ts/vue/json/yaml 2 空格）。
- 新建和修改文本一律使用 LF（上述 Windows 脚本例外）；不要把历史 CRLF/混合换行继续带入新增行。全仓规范化仍单独安排，不对未涉及文件批量重写，见 CONTRIBUTING.md。

## 分支与审查
- 新工作使用 `codex/` 前缀分支，通过PR和必需检查后合并；分支保护需仓库管理员在托管平台启用，不能因本地有配置而视作已经生效。
- 提交前运行 `git diff --check`，仓库提供pre-commit hooks检查ruff、行尾、大文件和私钥；不要通过跳过检查掩盖失败。

## 部署与运维注意
- 生产 `DB_AUTO_MIGRATE=false`，首次安装和升级均先运行 `python -m app.migrations`；密钥环、扩展/收缩迁移、PG升级见 `docs/operations.md`。
- 监控、备份与通知只有完成实际配置和验收才算启用，不能把模板落库当作上线完成。
- 镜像以非 root（uid 10001）运行，`/app/data` 归该用户；升级旧卷、固定网段、`FORWARDED_ALLOW_IPS` 的取值见 `docs/deploy.md`。
- 新安装和 CI 使用 `postgres:16-bookworm`；生产通过 prod 覆盖文件固定已核实的镜像 digest。现有本地 Alpine 数据卷继续使用原镜像，切换发行版必须 dump/restore 到新卷，绝不可直接替换镜像。

## 历史记录
- 2026-09-21 优化交付：`docs/optimization-2026-09-21.md`、`docs/project-audit-2026-09-21.md`、`docs/miniprogram-optimization-2026-09-21.md`、`docs/local-wsl-deployment-2026-09-21.md`。
- 2026-09-22 仓库治理（本文件、CI/compose/Dockerfile 加固、根目录脚本归档到 `artifacts/root-scripts-archive-2026-09-22/`）：见 `CONTRIBUTING.md` 与 git 记录。
