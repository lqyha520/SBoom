# 本地运行与数据迁移

## 固定入口

| 服务 | 地址 | 数据源 |
| --- | --- | --- |
| 出题工作台 | http://localhost:8000/ | 根目录 `.env` 配置的数据库 |
| 管理后台 | http://localhost:8000/admin/ | 与工作台相同，使用原管理员账号 |
| 小程序 H5 | http://localhost:5180/ | `/api` 代理到 `127.0.0.1:8000` |

`8110/8111` 是旧的临时 UI 测试服务，不是日常运行地址。`tests/ui_fixture.py` 每次启动都会
创建临时 SQLite，不可用它保存日常配置。小程序的本机代理地址位于已忽略的
`miniprogram/.env.local`，正常联调应设置 `VITE_BACKEND_URL=http://127.0.0.1:8000`。

```powershell
pnpm --dir web build
pnpm --dir admin build
python run.py
# 另一个终端，保持后端运行
pnpm --dir miniprogram dev:h5
```

启动入口先检查端口是否可用，避免 Windows 的地址复用让两个旧/新后端同时监听同一端口。
已有端口被占用时先确认进程确实属于本项目，再停止旧进程；不要清理其他项目、Codex 或 MCP 进程。

**2026-09-19 核对补充：** 当前机器的 8000 端口由 WSL 中的 `deploy-app-1` 转发，应用连接 `deploy-db-1`；Windows 根目录 `.env` 的 `127.0.0.1:5432` 则连接独立的 `learncoach-db` 开发库。两者不是同一份数据库，修改开发库不会出现在当前 8000 页面。维护运营内容前，应从实际服务容器读取数据，并与 `/api/v1/site/home` 的实时返回核对；不能仅凭“数据库主机是 localhost”判断目标正确。不要为了同步内容关闭容器或将一份数据库覆盖到另一份。
Windows 后台启动应使用隐藏窗口，并将输出重定向到本地日志。独立开发库的 PostgreSQL 容器为
`learncoach-db`，数据卷为 `learn-coach_pgdata`。重启保留卷，不执行 `down -v`。

## 持久数据

- `mini_users`、`mini_user_sessions`：独立小程序账号、会员及会话。
- `catalog_papers`、`catalog_access`：公共习题发布信息与逐份权限。
- `catalog_question_types`、`catalog_type_rules`：题型索引与观看、下载规则。
- `mini_catalog_favorites`、`mini_catalog_downloads`：账号收藏与下载记录。
- `mini_membership_events`：会员变更审计。
- `paper_archives`、`paper_assets`：原始快照和文件索引；文件实际保存在私有文件目录。

数据库初始化采用增量建表，PostgreSQL 多 worker 启动共用事务锁，防止并发建表竞争。
应用重启不会清库、重置会员或恢复默认权限。已下载到用户设备的文件无法远程撤回。
页面排版属于前端代码，Banner 和运营内容由后台保存到数据库。会员支付默认关闭，配置、订单、退款与对账流程见[功能扩展说明](mini-growth.md)；不提供自动续费。

## 一次性演示迁移

仅在用户明确要求保留演示数据时使用 `scripts/import_demo_catalog.py`。先停写入并备份
目标 PostgreSQL、服务密钥、临时 SQLite 快照以及配套的 `private-papers` 目录。
SQLite 快照必须通过 backup API 获取，不能遗漏 WAL 中的已提交数据。

```powershell
python -c "from app.db import init_db; init_db()"
python scripts/import_demo_catalog.py --source-db <备份数据库> --source-files <备份文件目录> --publisher-id <现有管理员ID>
# 核对 dry_run 后，使用同一组参数追加 --apply
```

导入器只接受本项目的隔离 UI 演示快照；公共习题的来源归档归属到明确指定的现有管理员。
不导入演示管理员、出题账号、私人文件夹、未创建公共条目的私人归档或模型配置。
小程序身份、会话、会员有效期、收藏、下载和权限保留；历史演示会员事件的管理员关联置空，
不会冒充真实管理员操作。PDF/JPEG 先核对大小和 SHA-256，再复制到固定私有目录。

目标已有小程序业务数据时拒绝自动合并。数据库写入在同一个事务中完成；
`app_config.local_demo_catalog_import_v1` 记录来源指纹。相同来源重复执行只返回
`already_imported`，不会覆盖导入之后的运营修改。
文件复制意外中断可能留下未引用文件，但不会暴露部分数据库记录，也不会覆盖已有文件。

演示账号仅供本地开发验收，公开部署前应清理演示内容并处理测试账号，不能将公开演示密码用于运营。
