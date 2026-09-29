> 历史设计/验收记录，保留原内容供追溯。旧命令和状态不代表当前实现；入口见[项目README](../../README.md)。

# 小程序发布评估（2026-09-18）

面向问题：**现在可以发布了吗？还有什么需要优化？**

结论先说：**代码与产物质量已经达标，卡点全在配置侧**。发布前必须换掉 HTTPS 域名并完成备案/域名白名单，另外真机验收（微信头像选择、原生分享、订阅送达、真机打开 PDF）尚未做过。

## 一、本次实测（不是推断）

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 正式构建 | `node node_modules/@dcloudio/vite-plugin-uni/bin/uni.js build -p mp-weixin`（`miniprogram/`） | ✅ `DONE Build complete.` EXIT=0，15s |
| 结构门禁 | `node scripts/check-build.mjs` | ✅ **287 个文件 / 800.0 KiB**（上限 2048 KiB） |
| 发布门禁 | `node scripts/check-build.mjs --release` | ❌ `AssertionError: A public HTTPS API origin is required`（`'http:' !== 'https:'`） |

发布包内容核验：`components/` 共 20 个组件进包；**`PaperSkeleton`、`VirtualScroll` 未进包**；全包 `wd-skeleton` 引用 0 处 —— 也就是说今天在开发者工具里折腾的 `wd-skeleton.wxss / PaperSkeleton.wxml` 报错，**跟正式发布包完全无关**。

## 二、发布阻塞项（必须解决）

1. **API 必须是公网 HTTPS 域名**
   `miniprogram/.env.production.local` 目前是 `http://192.168.31.192:8000`（局域网）。真机不可能用，`check:release` 也会直接失败。
   改完后**必须重新 build** —— 门禁会校验产物 `services/api.js` 里的 origin 与配置一致。

2. **服务器域名白名单（两处，别漏）**
   同一个域名要同时加入「request 合法域名」和「**downloadFile 合法域名**」：PDF 走 `wx.downloadFile` + `wx.openDocument`，只配 request 会出现"能加载列表、点下载就失败"。

3. **ICP 备案 + 服务类目**
   微信要求小程序主体完成备案；类目建议「教育 → 在线教育 / 教育服务」。当前收费渠道未开通（支付默认关闭，会员页显示"咨询开通"），可先不接微信支付；一旦要开付费，需补商户号与类目资质。

4. **平台侧配置**
   - 订阅消息模板 ID（`pages/messages` 用 `requestSubscribeMessage`；未配置时业务结果仍落到站内消息中心，可接受）
   - 客服联系方式（会员页/服务页读取后台配置，未配置时只有留言通道）
   - 《小程序用户隐私保护指引》需在公众平台填写。代码侧已合规：登录页有协议勾选（`login/index.vue:113`），《用户协议》《隐私政策》页齐全，账号注销入口 `pages/closure` 也有。

5. **真机验收未完成**（`docs/mini-verification.md` 自己列的）
   微信头像选择面板与隐私提示、原生分享回传、订阅消息送达、真机打开 PDF。

6. **线上数据清理**
   后台「二年级」那条网盘链接填的是 `https://www.baicu.com`（baidu 拼成了 baicu）。发布前确认是否为测试数据。另外**外部网盘链接本身有版权与合规风险**，正式对外前建议梳理来源。

## 三、代码层待清理（低风险，10 分钟）

| 项 | 证据 | 建议 |
| --- | --- | --- |
| `components/PaperSkeleton.vue` 死代码 | 全项目引用 0 处；新构建不进包 | 删除 |
| `components/VirtualScroll.vue` 死代码 | 全项目引用 0 处；新构建不进包 | 删除 |
| `utils/performance.ts` 里一半是浏览器专用工具 | `preloadImage` 用 `new Image()`、`createIntersectionObserver` 用 `IntersectionObserver`，微信端没有这些对象 | 只保留 `debounce`（CatalogList 用）和 `vibrate`（PaperRow 用）；其余 browser-only 工具删除或标记禁用，避免以后被误调用 |
| `utils/performance.ts:285` `console.log` | `PerformanceMonitor.measure` | 无用则删 |
| 「临时」字样 | `pages/privacy/index.vue:42` 是正文用词（"会产生临时文件"） | 无需处理 |

其余体检干净：无 `TODO / FIXME / 占位` 文案；无障碍属性 `aria-*` 135 处、`role=` 198 处；`safe-area-inset` 17 处；骨架屏、空态、错误重试、下拉刷新、触底加载齐全。

## 四、UI / 交互优化建议（按性价比排序）

1. **分享链路不完整 —— 最高性价比**
   只有 `home / paper / topic` 声明了 `onShareAppMessage`。**习题库列表、收藏、下载记录都没有分享入口**，用户看到一份好资料没法顺手转给同事/家长群。
   另外全站没有 `onShareTimeline`（分享到朋友圈）。对内容型小程序，这是最便宜的自然增长。

2. **点击反馈不统一**
   全项目 `hover-class` 只出现 1 次（`AppTabBar`）。卡片、列表行这类自定义可点区域建议统一加 `hover-class`：微信端 `:active` 在部分机型上不触发，按下去没反馈会让人以为没点到。

3. **字号偏小**
   `font-size: 11px` 出现 44 处（`home` 9、`membership` 9、`account` 8…），多在辅助信息上。这个产品的用户包含家长群体，建议正文不低于 12px、把 11px 收敛到纯装饰性文字。

4. **列表图片懒加载（优先级低）**
   `PrivateImage` 已有占位图、失败重试、点击放大（做得好），但没有 `lazy-load`。由于图片最终走本地文件句柄，收益有限，可以先不做。

5. **薄页面空态确认**
   `downloads / favorites / recent / topic` 都是 12~15 行的壳页面，复用 `CatalogList`。发布前用未登录 + 无数据两种状态各看一眼，确认不会出现"白屏"观感。

6. **可选增强**
   深色模式未适配；未启用 `open-type="contact"` 微信客服（现有自建留言面板功能上够用）；`vibrate`（轻震动）已在工具里但基本没用起来，关键操作（下载完成、兑换成功）加一下体感更好。

## 五、建议的发布顺序

1. 域名与备案就绪 → 2. 改 `miniprogram/.env.production.local` 为公网 HTTPS → 3. `pnpm --dir miniprogram build:mp-weixin` + `check:release` 变绿 → 4. 开发者工具上传体验版 → 5. 按 `docs/mini-verification.md` 真机走一遍 → 6. 提交审核。

优化项建议排在发布之后：**分享链路 > 点击反馈 > 字号 > 死代码清理**。
