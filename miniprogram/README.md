# 公共习题小程序

独立的消费者客户端，面向普通用户和 VIP 会员。小程序账号、登录会话、收藏和下载记录均与出题工作台分离。
出题、排版和私人归档仍由 `web/` 负责，发布和会员运营由 `admin/` 负责。
小程序没有私人习题空间、文件夹、重命名、删除归档或绑定工作台账号的入口。

## 技术与目录

`miniprogram/` 有独立的依赖、锁文件、Vite 配置和构建输出，仅通过 HTTP 调用 FastAPI，不导入网页 UI。

- uni-app Vue 3 CLI `3.0.0-5020420260813003`，编译器 5.24。
- Vue 3.5.42、TypeScript 6、Wot UI 2.3.2（`@wot-ui/ui`）。
- uni-app 当前编译链要求 Vite 5.2.8 和 vue-i18n 9，不单独升级某个 `@dcloudio/*` 包。
- 微信使用原生请求、临时文件、图片预览和 PDF API。没有独立阅读模式或答案开关。
- 控件统一使用 Wot，主题在 `src/theme.scss`；不是复制的付费商业模板。
- 首页和登录页使用本地 3dicons 笔记本插画；与保留的 Banner 照片、Lucide/Wot 图标授权一起见 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)。

```text
src/pages/        home, library, favorites, downloads, account, paper, login, privacy
src/components/   Banner、自定义导航、会员弹层、鉴权图片、习题卡片、搜索和筛选
src/services/     API、消费者会话、文件生命周期、请求顺序保护
src/static/       插画、Banner、标签栏图标、字体、授权声明
tests/            页面契约、首页分组、筛选、文件和请求回归
scripts/          素材生成、微信包检查、发布配置检查
```

底部为「首页 / 习题库 / 收藏 / 我的」，采用 Wot 悬浮胶囊导航。原生 tabBar 保留路由配置但隐藏，
仍使用 `switchTab`；多个弹层同时存在时，最后一个关闭后才恢复自定义底栏。所有页面使用自定义导航，
`PageChrome` 在微信端预留状态栏和系统胶囊区域，H5 不显示多余标题。

首页按所选年级请求最多 12 份真实习题，每次展示 2 份，可以换一组；
「为你精选」使用后台精选排序，「最近上新」使用 `sort=latest` 按发布时间排序。
收藏和下载列表始终按账号操作时间排序，不受该开关影响。Banner 为固定的双页专题，可滑动或点击切换。
首页搜索、学科和专题会携带年级并清除无关的旧筛选条件，再切换习题库。

详情首屏仅展示原稿封面和文件信息；点开预览弹层后每次显示 4 页，可继续加载和放大。
所有图片均来自受权限保护的真实原稿，不用演示插图替代习题。PDF 操作保留微信原生打开与 H5 下载分支。
「我的」使用账号资料、会员状态、收藏与下载入口，退出登录位于设置弹层；没有私人空间和在线购买入口。

## 账号与会员权限

H5 和微信均使用独立消费者 Bearer 会话，不使用工作台 Cookie。后端只保存 token 摘要。
H5 的账号登录/注册表单位于底部弹层，使用 `/api/v1/mini/register` 和 `/api/v1/mini/login-password`；
微信端仅显示「微信一键登录」，以 `uni.login` 获取真实 code 后调用 `/api/v1/mini/login`。
浏览器不能模拟小程序微信授权；两端均默认不勾选协议，登录中的重复点击和离开页面后的迟到响应不会触发跳转。
`MINI_REGISTRATION_ENABLED=false` 关闭小程序注册和微信首次开户，不影响出题端 `REGISTRATION_ENABLED`。

后台入口：

1. **小程序用户**：创建普通账号、搜索与筛选，设置普通/VIP、长期有效或到期时间、启用/禁用。
2. **题型权限**：分别设置完整原稿观看和 PDF 下载权限，默认所有登录用户可用。
3. **公共习题**：每份可继承题型规则，或单独指定普通用户/VIP 权限。

同一份资料有多个题型时，继承规则取最严格权限。VIP 观看必然要求 VIP 下载，不能用 PDF 绕过观看限制。
支持「普通用户可预览，VIP 才能下载」。逐份明确覆盖优先于题型规则；只改标题不会重置原权限。
会员到期自动失效，后台撤销会员不需要重新登录；禁用账号撤销全部会话，重新启用后需要重新登录。
会员修改带 revision 冲突检查并保留审计记录。目前没有支付、订单或自动续费，会员由后台开通。

普通账号仍可浏览 VIP 习题的标题、分类和标签，也可收藏，但不能拿到受限的题目快照、答案、缩略图、预览图或 PDF。
文件直链也实时检查会员、发布状态和文件归属，不能靠隐藏前端按钮实现权限控制。
下载记录表示请求过 PDF，不保证设备已经另存成功；已保存到设备的文件不能因到期或下架而撤回。

## 本机开发

需要 Node.js 22.12+、pnpm 10.14 和运行中的后端。

```bash
pnpm --dir miniprogram install --frozen-lockfile
pnpm --dir miniprogram dev:h5
```

默认地址 `http://127.0.0.1:5180`，API 代理到 `http://127.0.0.1:8000`。H5 推荐同源代理：

```dotenv
VITE_API_BASE_URL=
VITE_BACKEND_URL=http://127.0.0.1:8000
```

本机配置在 `.env.local`，已被 Git 忽略，不要直接用模板覆盖。端口占用时指定 `--port 5181`。
执行 `build:h5` 后，将 `dist/build/h5` 部署到独立域名根路径并反向代理 `/api`。

### 持久化联调

日常使用应启动根目录 `python run.py`，并将小程序 `VITE_BACKEND_URL` 指向
`http://127.0.0.1:8000`。后台地址为 `http://localhost:8000/admin/`，出题工作台为
`http://localhost:8000/`，小程序 H5 为 `http://localhost:5180/`。
三个入口共用根目录 `.env` 配置的数据库；配置了 `DATABASE_URL` 就使用 PostgreSQL，
没有配置时才使用 SQLite。小程序用户与出题用户仍然是不同的表和登录体系。

账号、会员到期时间、题型权限、单份习题权限、发布状态、收藏和下载记录保存在数据库中；
本地 PDF/JPEG 保存在 `data/paper-files/`（或 `ARCHIVE_LOCAL_DIR`），数据库保存文件索引与校验值。
正常重启不会重新生成账号或清空数据，也不会自动导入演示内容。首页 Banner 仍为前端静态资源。

已有临时演示数据的明确迁移流程见 [本地运行与数据迁移](../docs/local-runtime.md)。
正式后台继续使用原管理员账号，隔离演示的 `admin_console` 不能用于正式数据库。

### 隔离演示

测试服务仅用临时 SQLite 和本机临时文件，不访问生产数据、不调用付费模型、不写入 COS。
重启会重建演示库，不能用这些账号正式部署。已有服务占用端口时换端口，不要关闭用户原有服务。

```bash
pnpm --dir web build
pnpm --dir admin build
# 已有 artifacts/miniprogram/demo/manifest.json 时无需重新生成文件。
python tests/render_library_demo.py
python tests/ui_fixture.py --port 8111 --demo-library artifacts/miniprogram/demo
```

演示文件生成器需要 ReportLab、pypdfium2、Pillow 和中文 TrueType 字体；后端只读取生成后的文件。
将 H5 的 `VITE_BACKEND_URL` 设为 `http://127.0.0.1:8111`。后台访问 `http://admin.localhost:8111/admin/`。

| 账号 | 密码 | 用途 |
| --- | --- | --- |
| `ui_reader` | `reader-pass-123` | 普通小程序用户 |
| `ui_vip` | `vip-pass-123` | 30 天 VIP，小程序中有 6 个收藏与 3 条下载记录 |
| `admin_console` | `admin-pass-123` | 管理后台和发布工作台 |
| `ui_teacher` | `teacher-pass-123` | 仅出题工作台，不是小程序账号 |

演示库有 22 份已发布习题和 2 份草稿，均就绪条目有真实 PDF/JPEG。
阅读理解题型默认 VIP 观看/下载；「五年级数学 小数专项练习」为普通可预览、VIP 下载。
出题教师仍有 24 份私人归档和 4 个文件夹，但小程序不能访问。
重复导入不会覆盖用户修改、下架状态、收藏选择或已经配置的题型权限。

## 微信发布

1. `src/manifest.json` 的 `mp-weixin.appid` 设置真实微信 AppID。
2. `.env.production.local` 设置 `VITE_API_BASE_URL=https://你的API域名`，仅填源地址，不含路径或 AppSecret。
3. 后端 `.env` 配置相同的 `WECHAT_APP_ID`、对应的 `WECHAT_APP_SECRET`。
4. 使用 HTTPS，启用 `FORCE_HTTPS=true`，配置微信 request 和 downloadFile 合法域名。
5. 将构建产物导入微信开发者工具，在真机验证登录、VIP 权限、图片预览及 PDF 保存。

```bash
pnpm --dir miniprogram typecheck
pnpm --dir miniprogram test
pnpm --dir miniprogram build:h5
pnpm --dir miniprogram build:mp-weixin
pnpm --dir miniprogram check:mp
pnpm --dir miniprogram check:release
```

`check:mp` 检查 8 个页面、资源、组件、原生 PDF 分支和小于 2 MiB 的主包，并禁止私人页面和绑定入口。
`check:release` 额外检查真实格式的 AppID 和已编译的 HTTPS 源地址。缺少配置时应失败，不能关闭域名校验。
目前主包约 595 KiB，以实际构建检查输出为准。编译/API/H5 测试不代表微信真机登录、设备文件保存或审核发布已经完成。

素材可分别通过 `pnpm --dir miniprogram assets` 与 `node miniprogram/scripts/build-notebook.mjs` 重建。
后者使用固定版本的 CC0 来源，生成 512 像素本地 PNG，不增加运行时外链依赖。

## 旧版升级

新增 `mini_users` 等独立表，保留已有出题账号、归档、文件及旧表，不自动复制或合并身份。
旧 `lc_mini_` token、工作台绑定接口和 H5 Cookie 登录不再被小程序接受，需要重新注册/微信登录。
旧共享账号的公共收藏/下载记录不自动迁入新账号。部署到已有运营环境前应备份，并明确迁移通知与人工核验方案。
后台公共习题默认继承题型规则；没有规则时保持普通用户可用，不会把历史私人内容自动发布。

正式上线前仍须确认用户协议正文，并补全隐私政策中的运营主体、联系方式、存储区域、注销流程和备份保留期限。
`pages/privacy/index?kind=agreement` 当前展示服务说明草稿，不代表商用协议已经完成。
普通投稿、在线答题/批改、逐题组题、支付、扫码分享、手机 AI 出题和离线资料包不在当前版本范围。
详见 [架构与部署](../docs/paper-library.md)。
