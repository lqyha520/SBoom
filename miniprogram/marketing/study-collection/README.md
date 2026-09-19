# 学习专题运营素材

三套可编辑的运营素材，使用项目已授权的 3dicons 笔记本插画和 Cinthya Gonzalez 的学习照片重新排版；没有调用图片生成 API，也不在用户打开页面时请求第三方资源。

| 主题 | Banner | 专题海报 | 配色 |
| --- | --- | --- | --- |
| 每日练习 | `daily-banner.jpg` | `daily-topic.jpg` | 鼠尾草绿 |
| 阅读与积累 | `reading-banner.jpg` | `reading-topic.jpg` | 浅蓝 |
| 单元巩固 | `unit-banner.jpg` | `unit-topic.jpg` | 暖米色 |

- Banner 为 **1200 × 500** JPEG，约 20–26 KiB；对应后台的 12:5 图片区，选择“完整展示”。
- 专题海报为 **900 × 600** JPEG，约 21–24 KiB，可用于运营宣传。它们不充当真实资料预览。
- 每张图都保留同名 SVG 源稿，包含所用栅格素材，便于单独编辑与重导出。
- `campaigns.json` 保存配套标题、副标题、按钮文字与目标分类名称；跨环境时按分类名解析真实 ID，不硬编码部署数据库 ID。
- Banner 中仅保留大标题与配图；辅助说明交由小程序真实文字控件显示，避免缩放后出现不可读的小字。
- 小程序专题卡片使用 `TopicCard.vue`，复用已有本地笔记本插画并显示后台真实标题、说明与资料数；不把后台文字烘焙进卡片图中。
- 此目录不在 `src/static` 下，**不会整体打入微信主包**。Banner 由后台上传并返回版本化图片地址。

## 重新生成

在仓库根目录执行：

```powershell
pnpm --dir miniprogram assets:editorial
```

先在 `scripts/build-editorial-assets.mjs` 编辑文案和色彩，再重新生成 SVG、JPEG 与 `campaigns.json`。脚本仅使用本地素材，不下载外部文件。

## 初始运营安排

首页仅上线“口算练习，随时开始”；阅读、单元两张 Banner 保留为下线草稿，可在后台替换主推荐。三个专题分别编排真实已发布 PDF，数量由接口返回；当前部署库分别为 14、2、5 份。

后台入口：小程序管理 → 首页 Banner / 专题合集。Banner 跳到对应分类，专题按后台资料顺序展示。不要把“免费”“提分”等未经资料权限或内容验证的承诺放进图中。

授权来源及原始作者见 [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md)。源插画为 CC0，照片遵循 Unsplash License；本目录不包含字体文件。
