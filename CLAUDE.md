# learn-coach 工作约定（给 Claude Code / 协作者）

## 仓库布局
- `app/`：FastAPI 后端（`app/main.py` 入口；`services/` 业务、`routers/` 路由、`db.py` PostgreSQL 访问层）。
- `web/`：出题工作台（Vue 3 + Vite），`admin/`：管理后台（独立 Vite 项目，`admin/node_modules` 是指向 `web/node_modules` 的符号链接）。
- `miniprogram/`：uni-app 小程序（H5 + 微信）。`shared/`、`ui/`：三个前端共用的类型/主题配置（Docker 构建阶段会一起拷贝）。
- `tests/`：后端测试（`test_backend_*.py`）与 UI 契约/fixture 脚本；`scripts/`：正式维护脚本（备份、压测、演示数据导入、后台自检）。
- `deploy/`：生产 compose（Caddy 版 `docker-compose.yml`、加密回源版 `docker-compose.server.yml`）、systemd 备份单元；根 `docker-compose.yml` 只起本机 PG。
- `docs/`：设计与验收记录；`artifacts/`：截图/压测/临时脚本归档，整个目录不入库。

## 环境准备
```bash
pip install -r requirements-dev.txt        # 运行时依赖 + pytest/pytest-xdist/mypy/pip-audit/ruff
cp -n .env.example .env                    # 至少配 DATABASE_URL；本机 PG 用根目录 docker compose up -d
pnpm --dir web install --frozen-lockfile   # admin 复用 web/node_modules（符号链接），不要单独 install 覆盖它
pnpm --dir miniprogram install --frozen-lockfile
```

## 检查命令（提交前至少跑改动涉及的那一组）
| 组件 | 命令 |
| --- | --- |
| 后端 | `ruff check app tests run.py scripts`、`mypy app run.py scripts`、`python -m pytest -n auto`（需本机可达的 PostgreSQL，见下） |
| web / admin | `pnpm --dir <web|admin> typecheck`、`pnpm --dir <web|admin> test`、`pnpm --dir <web|admin> build`（有 lint 脚本时再 `pnpm --dir <x> run lint`） |
| miniprogram | `pnpm --dir miniprogram typecheck`、`test`、`build:mp-weixin`、`check:mp`、`build:h5` |
| 全栈契约 | `python tests/run_ui_contracts.py`（需先 build web/admin） |
| 镜像 | `docker build --target runtime -t learncoach .`（BuildKit；国内可加 `--build-arg PIP_INDEX_URL=...`） |

CI（`.github/workflows/ci.yml`）跑的就是这些，另加 `pip-audit`、`pnpm audit` 与镜像构建冒烟。

## 测试数据库红线
- 测试只允许连本机实例，并且只创建/删除 `lc_test_*` 前缀的一次性库；管理连接由 `LC_TEST_PG_ADMIN` 指定（默认 `postgresql://learncoach:learncoach@127.0.0.1:5432/postgres`），护栏在 `tests/pg_support.py`。
- 绝不把 `DATABASE_URL` / `LC_TEST_PG_ADMIN` 指向业务库、生产库或 `deploy-db-1` 这类容器；不要写"临时"脚本直接改业务库状态（如把 paper 置为 published）。
- 本机 WSL 里跑着 `deploy-app-1` / `deploy-db-1` / `learncoach-db` 等类生产容器，只读查看，不要 stop/rm/down。

## 仓库整洁
- 仓库根不放一次性脚本：能复用的进 `scripts/`（带用法说明），排查用的放 `artifacts/<日期-主题>/`。`.gitignore` 已拦截根目录 `check_*.py` / `update_*.py` / `verify_*.py` / `*.sql` / `_*.py`，被拦截说明放错了地方，而不是该去改规则。
- 不要提交 `.env*`、`data/`、`server.log*`、`*.pid`、前端 `dist/`。
- 注释与文档用中文；不新增 README 之外的总结性 markdown，除非任务明确要求。

## 换行与编码
- `.gitattributes`：全部文本 LF 入库并 LF 检出（`*.cmd/*.bat/*.ps1` 例外为 CRLF），`.editorconfig` 同步（py 4 空格，ts/vue/json/yaml 2 空格）。
- 修改已有文件时保持它当前的换行风格；历史 CRLF 文件的统一规范化（`git add --renormalize .`）留给一次专门的提交，见 CONTRIBUTING.md。

## 部署与运维注意
- 镜像以非 root（uid 10001）运行，`/app/data` 归该用户；升级旧卷、固定网段、`FORWARDED_ALLOW_IPS` 的取值见 `docs/deploy.md`。
- PostgreSQL 统一 `postgres:16-alpine`（根/deploy 两个 compose 与 CI 一致）；不要在 glibc 与 alpine 变体之间切换已有 pgdata 卷。

## 历史记录
- 2026-09-21 优化交付：`docs/optimization-2026-09-21.md`、`docs/project-audit-2026-09-21.md`、`docs/miniprogram-optimization-2026-09-21.md`、`docs/local-wsl-deployment-2026-09-21.md`。
- 2026-09-22 仓库治理（本文件、CI/compose/Dockerfile 加固、根目录脚本归档到 `artifacts/root-scripts-archive-2026-09-22/`）：见 `CONTRIBUTING.md` 与 git 记录。
