> 历史设计/验收记录，保留原内容供追溯。旧命令和状态不代表当前实现；入口见[项目README](../../README.md)。

# 本地 WSL Docker 更新记录

- 时间：2026-09-21；WSL Debian；Compose 项目 `deploy`。
- 新镜像：`deploy-app:optimization-20260921-112904`。
- 原镜像保留：`deploy-app:image-ui-20260920-230412`，另有 `deploy-app:rollback-optimization-20260921-112904` 标签。
- 只替换 `deploy-app-1`，沿用数据库和文件卷；PostgreSQL、Caddy 容器未重建。
- 增量迁移完成。更新前后均为 4 个用户、37 份归档、31 条目录、29 条已发布资料。
- 双 worker、Secure Cookie 和原配置保留，启用容器内部监控，9090 未向宿主机开放。
- WSL `/home/lqyha/learn-coach/deploy/docker-compose.override.yml` 已指向新镜像；构建目录改为 `/mnt/f/开源项目/learn-coach`，避免后续使用 WSL 旧源码副本。

## 验证

工作台 https://localhost/ 和后台 https://localhost/admin/ 正常。HTTPS 验证使用现有 Caddy 本地 CA，未跳过证书验证。HTML 与新镜像一致，16 个关联资源请求通过。管理员登录、会话、后台目录接口、Secure/HttpOnly Cookie、就绪检查、搜索、热门列表、窗口恢复、私有资产鉴权和监控均通过。

86 个后端源码文件与当前工作区哈希一致；镜像 pip check 通过。文件检查无缺失或哈希不匹配；旧资料封面已通过有配额保护的任务回填。未调用付费模型或真实支付，小程序独立客户端未发布。

## 备份与回滚

切换前短暂停止应用，备份 PostgreSQL、文件卷、环境配置和密钥，SHA-256 校验通过。WSL 备份目录：

`/home/lqyha/learn-coach-backups/optimization-20260921-112904`

目录权限 700，数据库和文件包权限 600。包含 database.dump、appdata.tar.gz、service.env、原 Compose 文件及 SHA256SUMS，不要提交或公开。

回滚应用时恢复备份中的 docker-compose.override.yml，再使用原环境文件和两个 Compose 文件执行 `up -d --no-deps --no-build --wait app`。增量表可保留，不要自动覆盖数据库，以免丢失更新后新增数据。

构建、部署和验证日志：`artifacts/deploy-wsl/optimization-20260921-112904/`。关键结果：host-validation.json、container-validation.json、thumbnail-validation.json。
