# 习题平台：独立消费者与会员权限

## 产品边界

`web/` 是出题工作台，负责生成、排版和私人归档；`admin/` 管理公共发布、小程序用户和题型权限；
`miniprogram/` 是独立消费者客户端，提供检索、预览、收藏分组、下载、最近浏览和问题反馈。三个客户端只共享版本化 HTTP 契约，不共享 UI。

小程序底部为「首页 / 习题库 / 收藏 / 我的」，没有私人空间、文件夹或工作台账号绑定。
详情展示保存时的原稿图片，不提供独立阅读模式和答案开关。每个条目仍是一份包含多道题的资料，不是逐题作答题库。
首页使用真实公共库数据，精选优先并按发布时间排序；习题库支持最新、热门和仅免费筛选。Banner 与专题合集使用后台配置，没有 Banner 时显示简洁的选题入口。后台「小程序管理 → 首页 Banner」可直接上传图片并预览，推荐 1200 × 500；图片与文案分区展示，支持完整展示或居中裁切，换图后重新进入首页或下拉刷新即可更新。

## 账号隔离

- 出题用户仍位于 `users`，使用 HttpOnly Cookie，保留私人归档与模板。
- 消费者位于 `mini_users`，使用独立 UUID、密码哈希或微信标识摘要，没有管理员或出题角色。
- `username` 保持为固定登录名，`nickname` 单独保存并可重复；兼容旧资料编辑参数时也只修改昵称。
- H5 和微信统一使用 `mini_user_sessions` 的不透明 `lc_reader_` Bearer token，服务端仅存 SHA-256 摘要。
- 公共列表不接受工作台 Cookie；私人归档不接受小程序 Bearer token。
- `X-Mini-User` 防止消费账号切换后的旧请求误写，工作台仍用 `X-Workspace-User`。
- 消费者会话最多保留最近 10 个，退出撤销当前会话，后台禁用撤销全部会话，重新启用不复活旧会话。
- 微信 code 由服务端交换，不返回 OpenID、session_key 或 AppSecret；常规 HTTPX 日志过滤微信 URL 敏感参数。
- `MINI_REGISTRATION_ENABLED` 独立控制消费者注册，出题端继续使用 `REGISTRATION_ENABLED`。

新增表与已有 SQLite/PostgreSQL 数据兼容。旧账号、归档及旧关联表保留，但不再复用旧绑定和 `lc_mini_` 会话。
不自动把旧共享身份、公共收藏或下载记录复制给新消费者，避免错误关联私人账号。正式升级前须备份并明确迁移方案。
新用户始终是普通消费者；管理员只能通过现有出题端管理体系授权。

## 发布与权限

公共条目使用 `catalog_papers` 引用一个不可覆写的出题归档版本，保存不等于发布。

1. 管理员用自己的工作台账号生成并保存内容、PDF 和预览图片，或在后台导入 PDF / 图片。仅提供网盘资源时，也可直接添加链接与资料元数据，不要求先上传 PDF。
2. 在「公共习题」选择自己保存的归档，填写标题、分类、简介和访问权限，创建草稿。
3. 核对内容、答案、文件版权与学生隐私，确认后发布。PDF 模式必须文件全部 `ready`；网盘模式必须配置有效链接。
4. 后续可编辑元数据、精选、权限，或下架。修改原稿先保存新归档，再用「修订」替换同一公共条目的当前原稿并填写更新说明。

管理员不能从源选择器获取其他出题用户的私人归档。编辑/删除条目使用 revision，过期写入返回 409。
删除公共条目删除相关消费收藏与下载记录，但保留源归档；仍被引用的源归档和所属出题账号不能删除。
修订使用 `catalog_versions` 保留不可修改的历史原稿引用，公共 ID、收藏、下载、专题关联及逐份权限不变；旧文件 URL 不再对消费者提供，新请求使用新版文件。
批量操作最多 50 份；先校验全部 revision，再在同一事务修改。任一冲突整体回滚，发布仍须确认，并检查所选下载方式的文件或链接是否就绪。

消费者分普通用户和 VIP。`membership=vip` 且到期时间为空或晚于当前时间才具有 VIP 权限。
后台可开通、续期、取消会员和禁用账号，更新带 revision，并写入 `mini_membership_events` 审计记录。
快捷续期从有效到期日或当前时间累加；拒绝旧 revision 重放和长期会员续期，保留账号禁用状态。后台可筛选 7 天内到期与已过期用户。
会员支持管理员配置和可选的微信支付。套餐默认不上架、支付默认关闭；启用后的订单、全额退款和对账流程见[功能扩展说明](mini-growth.md)。不提供自动续费。

权限由 `catalog_access` 的逐份覆盖和 `catalog_type_rules` 的题型默认规则共同决定：

- 观看和下载分别为 `free` 或 `vip`；逐份设置另支持 `inherit`。
- `catalog_question_types` 从保存快照的 section.type 提取，支持内置和已发布的自定义题型；启动时补齐旧公共条目的题型索引。
- 混合题型继承最严格规则。逐份明确设置优先于继承，观看需要 VIP 时 PDF 下载与网盘链接获取也必须需要 VIP。
- 支持普通用户看原稿、VIP 才能下载。只编辑标题而省略权限字段不会把 VIP 重置为普通。
- 游客可浏览已发布资料的标题、标签和免费预览；VIP 受限条目的缩略图地址为空。收藏、下载与个人记录需登录。
- 受限详情只返回元数据与权限标记，`snapshot=null`、受限 assets 不返回，不泄露答案或题目原文。
- 原稿/JPEG、PDF 直链和下载请求均实时校验状态、会员有效性和文件归属；不能从旧链接绕过权限。
- 管理员有独立的审核文件接口，不受消费者 VIP 限制。小程序会话不能访问该接口。

`mini_catalog_favorites` 和 `mini_catalog_downloads` 属于消费者，不影响出题端的收藏。
可以收藏锁定的习题，但后续内容访问仍需权限。下载记录只表示请求过 PDF 或获取过网盘链接，并不证明设备成功另存或完成网盘下载。
个人列表按操作时间排序；下架条目隐藏，重新发布后既有记录仍保留。已另存文件无法远程撤回。

收藏分组最多 50 个，删除分组保留收藏；最近浏览每账号最多 100 份。专题最多 100 份资料，消费者只看到已展示专题中已发布且所选下载方式就绪的条目。
反馈按账号隔离，每账号每小时最多提交 10 条；资料纠错/下载问题必须关联可见资料。公开回复和内部备注分开，完成/关闭反馈必须填写回复。
活跃用户和下载结果、无结果搜索按北京时间汇总最近 30 天。活跃按账号/日去重，使用事件滚动保留 60 天；下载结果是客户端报告，不代表设备保存凭据。
前端按账号保留最近 12 条搜索及年级/科目偏好。未登录可读取正式协议和公开服务联系方式。

## 归档与文件

出题端 `schema_version=1` 快照包含完整 paper、template、style 和 export_options，保留编辑、布局、日期和 PDF 答案模式。
先保存快照，再由网页渲染器生成 PDF 和连续 JPEG，以 ZIP 上传；手机不能重新渲染文件。

- 快照最多 2 MB，每份 1 至 1500 题、最多 60 个大题。
- ZIP 默认最多 40 MB、展开最多 64 MB、最多 40 页；PDF 最多 32 MB、输入 JPEG 每张最多 3 MB。
- 服务端只接受 paper.pdf 与连续 page-N.jpg，不解压用户路径，检查数量、尺寸、JPEG 解码并清理元数据。
- 每出题账号默认 1000 份归档、512 MB 文件空间和 100 个文件夹。
- request_id 与来源/内容哈希去重；内容变化递增版本，删除新版不复用版本号。
- 快照和已完成文件不可覆盖，标题/收藏/文件夹仅改变元数据。
- 单批逐份保存，失败不回滚其他成功项，重试跳过完成项。

文件状态为 pending/uploading/failed/ready。使用随机目录、180 秒上传租约和空间预留，全部写入后事务提交清单。
文件未就绪不暴露 API；过期上传可在电脑重试。渲染期间切换账号或关闭组件会停止后续上传。
私人文件夹删除后资料保留在未分类。所有这些操作仅属于出题工作台，小程序不提供入口。

## API 契约

| 接口 | 作用 | 凭证 |
| --- | --- | --- |
| `POST /api/v1/mini/register` | 创建普通消费者账号 | 消费用户名/密码 |
| `POST /api/v1/mini/login-password` | H5 消费者登录 | 消费用户名/密码 |
| `POST /api/v1/mini/login` | 微信登录或首次开户 | 真实微信 code |
| `POST /api/v1/mini/login-public` | 同上，保留路径兼容 | 真实微信 code |
| `GET /api/v1/mini/me` | 身份、有效会员状态、到期时间 | 消费者 token |
| `POST /api/v1/mini/logout` | 撤销会话 | 消费者 token |
| `GET /api/v1/catalog/papers` | 搜索、筛选、分页与权限标记 | 消费者 token |
| `GET /api/v1/catalog/summary` | 内容数量、个人收藏/下载数量 | 消费者 token |
| `GET /api/v1/catalog/papers/{id}` | 元数据、授权后的快照与文件清单 | 消费者 token |
| `PUT /api/v1/catalog/papers/{id}/favorite` | 收藏/取消收藏 | 消费者 token |
| `POST /api/v1/catalog/papers/{id}/download` | 实时鉴权并登记 PDF / 网盘链接请求 | 消费者 token |
| `GET /api/v1/catalog/papers/{id}/assets/{asset_id}` | 实时鉴权的 JPEG/PDF | 消费者 token |
| `/api/v1/admin/catalog/papers`、`sources`、`summary` | 公共内容发布与审核 | 管理员 Cookie |
| `GET /api/v1/admin/catalog/type-rules` | 全部题型及权限 | 管理员 Cookie |
| `PUT /api/v1/admin/catalog/type-rules/{type}` | 按 revision 更新题型权限 | 管理员 Cookie |
| `GET/POST /api/v1/admin/mini-users` | 消费者列表、创建普通账号 | 管理员 Cookie |
| `PUT /api/v1/admin/mini-users/{id}` | 按 revision 修改会员/到期/启用状态 | 管理员 Cookie |
| `POST /api/v1/admin/mini-users/{id}/renew`、`GET .../events` | 快捷续期、分页审计记录 | 管理员 Cookie |
| `POST /api/v1/admin/catalog/batch`、`POST .../papers/{id}/revision` | 原子批量操作、保留条目的修订 | 管理员 Cookie |
| `GET /api/v1/admin/catalog/papers/{id}/preview` | `membership=regular/vip` 权限预览 | 管理员 Cookie |
| `/api/v1/mini/feedback`、`favorite-groups`、`history`、`events` | 反馈、收藏组织、浏览与使用记录 | 消费者 token |
| `/api/v1/admin/experience/support`、`feedback`、`topics`、`analytics` | 服务设置、问题处理、专题与使用趋势 | 管理员 Cookie |
| `GET /api/v1/site/topics` | 可见专题与有序资料 | 消费者 token |
| `GET /api/v1/site/documents/{key}`、`GET /api/v1/site/support` | 协议、隐私政策、联系方式 | 无需登录 |
| `/api/v1/library/papers`、`folders`、`summary`、文件接口 | 既有私人归档操作 | 出题工作台 Cookie |

旧 `/mini/bind/*` 与 `/me/mini-binding(s)` 路由已移除。
权限不足返回 403 和 `vip_required`；未登录/过期返回 401，账号切换和并发编辑返回 409。

## 部署与运维

文件存储固定为本地磁盘（data/paper-files，可用 ARCHIVE_LOCAL_DIR 调整），不能作为静态目录公开。
持久化数据库、data/secret_key.txt 和文件目录；多实例需要共享存储。数据库迁移追加建表，部署前仍应备份。

反向代理支持至少 40 MB ZIP 和 180 秒上传超时；上述账号、会员、资料 API 全部禁止公共缓存。
不要记录 Authorization、Cookie、微信 code、密码或请求正文。HTTPS 部署开启 FORCE_HTTPS。
微信后台需配置 request 和 downloadFile 合法域名，本机地址不能作为真机服务端。

删除或上传失败仅尽力回收文件；断电、存储故障可能留下不可通过 API 访问的孤立文件，但仍占物理空间。
目前没有持久清理队列/自动扫描器，上线前需制定备份、停写核对与清理方案，不能给有效归档前缀设置短期自动过期。
配额统计不是存储账单。COS、PostgreSQL 多实例并发和故障恢复需目标环境验收；进程内限流应在大规模部署前改为共享限流。

## 验证与边界

后端覆盖账号隔离、旧绑定不复用、普通/VIP 内容与文件鉴权、到期/撤销/禁用、混合题型、逐份覆盖、
元数据更新保留权限、并发冲突、收藏/下载隔离、上传校验、配额、去重与发布下架。
小程序覆盖 10 页路由、Wot 插槽契约、VIP UI、首页分组、筛选、偏好隔离、请求顺序及文件生命周期。
本地 H5 验证普通用户锁定态、VIP 原稿加载、账号切换，以及后台会员编辑与题型保存；检查手机窄屏和桌面布局。

```bash
python -m unittest discover -s tests -p 'test_backend_*.py' -v
pnpm --dir web typecheck
pnpm --dir web test
pnpm --dir web build
pnpm --dir admin typecheck
pnpm --dir admin build
pnpm --dir miniprogram typecheck
pnpm --dir miniprogram test
pnpm --dir miniprogram build:mp-weixin
pnpm --dir miniprogram check:mp
pnpm --dir miniprogram build:h5
```

演示数据为 22 份已发布内容和 2 份草稿，含普通、VIP 专享和免费预览/VIP 下载样例。
见 [小程序运行说明](../miniprogram/README.md#隔离演示)。演示生成器和导入器仅可用于隔离测试服务，不能导入正式库/COS。
教师的私人数据仅在出题工作台可用。
新增流程可通过 `tests/test_backend_experience.py` 在 SQLite 验证；设置指向本机临时 `lc_verify*` 数据库的 `LC_TEST_PG_DSN` 后运行 `tests/postgres_experience.py`，逐例隔离 schema 并清理。详见 [本轮验收说明](mini-optimization.md)。

当前没有在线付款、普通投稿、在线答题/批改、逐题组题、手机 AI 出题、扫码分享或完整离线备份。
真实微信登录、设备文件保存、HTTPS/COS 部署、运营主体/隐私信息、微信审核尚需实际配置与验收。
编译、API 或浏览器预览通过不等于已经正式商用上线。

网盘资料使用 `download_mode=external`；默认和历史资料为 `pdf`。下载请求根据模式返回 PDF 资产或 `{kind: "external", url, extraction_code}`，消费者列表和详情不包含网盘链接、提取码。具体操作与兼容规则见[后台添加习题流程](publication-workflow.md)。
