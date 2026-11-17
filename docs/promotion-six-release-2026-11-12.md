# 推广运营与财务中心六项优化发布记录

六项优化已部署到 WSL Debian 和线上，最终核验于 2026-11-12 19:02（北京时间）完成。上个对话已完成两套部署和浏览器检查，本次补齐线上部署后数据核验，并复查两套环境的实际版本、健康、备份与回退镜像。

| 环境 | 部署时间（北京时间） | 应用状态 | 数据库版本 | 后台入口 |
| --- | --- | --- | --- | --- |
| WSL | 2026-11-12 18:55:36 | healthy，重启 0 次 | 2026111203 | https://localhost/admin/ |
| 线上 | 2026-11-12 18:58:14 | healthy，重启 0 次 | 2026111203 | https://sboom.bcxtech.cn/admin/ |

## 发布内容与验证

- 发布版本为 `promotion-six-20261112-r1`，包含 13 个推广与财务后端文件及后台构建文件。成本完整性、查询与导出一致、付款预检、原始凭据及附件、同周期活动比较和月末清单均已上线，功能及口径见[六项优化验收](promotion-six-2026-11-12.md)。
- 两套发布包分别基于各自实际运行镜像冻结，保留各环境原有出题程序及工作台。构建指纹为 `1e405f4de58305765f43d0b6192592b38427326a5b262d34bd2378a8cb35025f`。
- 发布前，两套冻结后端各通过 125 项测试及 19 项子测试；后台构建与新增 4 项浏览器回归通过。其余前序检查见六项优化验收记录。
- 实际网站的 7 个财务页面及月末清单、原始凭据、活动对比、付款批次预检通过桌面和手机布局检查，无页面异常、HTTP 错误或测试写入。WSL 有待付款单，单笔付款窗口检查通过；线上没有待付款单，该窗口的真实业务数据检查未执行。
- 最终复查两套应用的 `/health`、`/readyz` 均返回 200；12 个受保护业务读取接口返回 200 且包含 `no-store`，未登录读取成本数据返回 401。代码版本与数据库迁移记录均为 `2026111203`。
- 两套应用的实际镜像与本地、宿主发布清单和当前版本记录一致，发布文件哈希核验通过。用户、订单、推广奖励、结算、审计和原财务记录数量，以及结算金额与发布前一致；数据库、数据卷、端口及其他容器身份核验通过。

## 备份与回退

本次发布前的加密本地备份均已校验，回执为 `verified=true, offsite=false`。备份在各环境部署前分别 12 秒、17 秒完成；本记录仅确认本次发布前本地备份。

| 环境 | 快照 ID | 备份回执 |
| --- | --- | --- |
| WSL | `29846f7b1819471718ba65209d76323dc35887b328a8e0d9a17ececa613ba62f` | `/home/lqyha/learn-coach-local-ops/status/backup.json` |
| 线上 | `ef4f640bd7ef6a39ec9fd23fddffd20e00e2964bd5be14e9298053abec2fec69` | `/data/data1/learn-coach-ops/status/backup.json` |

兼容回退镜像保留原后台页面，采用本次已验证的完整财务后端和迁移。离线导入检查通过，发布时已检查其可读取升级后的数据库；最终复查确认镜像仍存在。

| 环境 | 当前应用镜像 ID | 兼容回退标签及镜像 ID |
| --- | --- | --- |
| WSL | `sha256:6e4e34769e3d7fcb03a8f05dc17a3efff6d820e7cc1c1aa34643a712a6942bd9` | `learncoach-app:promotion-six-20261112-r1-compatible-wsl`；`sha256:43d1ff3827d5759319f1f2a438b79494093d0566b8243c62b61a083a2d069e23` |
| 线上 | `sha256:17f5ebd0d29c7469190173e10d2985da55646d002b7768a36613da49e3d1387e` | `learncoach-app:promotion-six-20261112-r1-compatible-production`；`sha256:65dab12dcf9daad432a3e79686280e92131aec786ec43cebfa526db1410d9f21` |

如需回退，使用各宿主本次发布目录的 `rollback.json`，沿用现有 Compose 项目及环境文件，先检查迁移兼容，再仅切换 app 并核验健康。WSL 发布目录为 `/home/lqyha/learn-coach/releases/promotion-six-20261112-r1`，线上为 `/opt/learn-coach/releases/promotion-six-20261112-r1`。回退不恢复或覆盖业务数据库和文件。

冻结包、发布清单、数据对比、备份回执、浏览器结果与截图保存在 `outputs/promotion-six-deploy-20261112/`，两套环境的最终核验分别记录在 `wsl/final-verification.json` 和 `production/final-verification.json`，完整数据与接口核验见各自 `after.json`。宿主当前发布记录位于 `/var/lib/learn-coach/releases/current.json`。
