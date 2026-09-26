# Learning Coach API

> AI 教育出题工作台、会员习题小程序、管理后台与 FastAPI 服务

基于 FastAPI 的轻量后端，核心逻辑：接收前端请求 → 组装 Prompt（注入知识范围约束）→ 调用 LLM 生成趣味题目/知识游戏 → 返回结构化 JSON。

---

## 目录

- [快速开始](#快速开始)
- [多用户与数据隔离](#多用户与数据隔离)
- [后台管理](#后台管理)
- [习题小程序](#习题小程序)
- [项目结构](#项目结构)
- [API 接口文档](#api-接口文档)
  - [1. 生成题目/游戏 `POST /api/v1/generate`](#1-生成题目游戏-post-apiv1generate)
  - [2. 流式生成 `POST /api/v1/generate/stream`](#2-流式生成-post-apiv1generatestream)
  - [3. 查询知识范围 `GET /api/v1/scope`](#3-查询知识范围-get-apiv1scope)
  - [4. 可用年级科目列表 `GET /api/v1/scope/available`](#4-可用年级科目列表-get-apiv1scopeavailable)
  - [5. 超纲校验 `POST /api/v1/validate`](#5-超纲校验-post-apiv1validate)
  - [6. 用户反馈 `POST /api/v1/feedback`](#6-用户反馈-post-apiv1feedback)
  - [7. 健康检查 `GET /health`](#7-健康检查-get-health)
- [枚举值速查表](#枚举值速查表)
- [各游戏类型的响应结构](#各游戏类型的响应结构)
- [生成策略与请求恢复](#生成策略与请求恢复)
- [草稿与模板](#草稿与模板)
- [开发验证](#开发验证)
- [错误处理](#错误处理)
- [知识范围覆盖](#知识范围覆盖)
- [前端对接指引](#前端对接指引)

---

## 快速开始

### 环境要求

- Python 3.11+（生成请求截止时间使用 `asyncio.timeout_at`）
- Node.js 22.12+、pnpm 10
- PostgreSQL 16（唯一支持的数据库，通过 `DATABASE_URL` 配置；本地可用 Docker 一键起库）
- 已配置的 OpenAI 兼容 LLM API（如 DeepSeek / 通义千问 / GPT）

### 安装与启动

```bash
# 在仓库根目录运行

# 1. 安装依赖
pip install -r requirements.txt

# 2. 首次部署时创建配置，已有 .env 不要覆盖
cp -n .env.example .env
# 在 .env 中配置数据库连接（必填）：
# DATABASE_URL=postgresql://learncoach:learncoach@127.0.0.1:5432/learncoach
# 本地开发可用 Docker 起 PG：docker run -d --name learncoach-db -p 127.0.0.1:5432:5432 \
#   -e POSTGRES_USER=learncoach -e POSTGRES_PASSWORD=learncoach -e POSTGRES_DB=learncoach postgres:16-alpine
# 密钥可在 /admin/ 的「模型配置」中保存，.env 仅作兜底

# 3. 构建前端（需要 Node.js 22.12+ 和 pnpm）
pnpm --dir web install --frozen-lockfile
pnpm --dir admin install --frozen-lockfile
pnpm --dir web build
pnpm --dir admin build

# 4. 启动服务
python run.py
```

访问 `http://127.0.0.1:8000` 使用出题工作台，`http://127.0.0.1:8000/docs` 查看 Swagger 文档。

---

## 多用户与数据隔离

系统支持多用户，每个账号的私人数据独立保存；游客可浏览管理员明确发布的公共试卷及免费预览，下载和个人操作需要小程序登录：

| 数据 | 隔离方式 |
|------|----------|
| 账号密码 | PostgreSQL（`DATABASE_URL`），密码 PBKDF2-SHA256 哈希存储 |
| 会话 | JWT（HS256）签名，httpOnly Cookie 下发（30 天有效），防 XSS 窃取 |
| 我的模板 | 每用户独立（`user_templates` 表按 `user_id` 隔离），跨设备同步 |
| 浏览器本地数据 | localStorage 按 `lc_u{用户id}_` 前缀命名空间隔离 |
| 草稿与试卷历史 | IndexedDB 按账号隔离，每个页面使用独立草稿 ID |
| 生成请求与用量 | 数据库按用户隔离请求 ID、执行状态和结果 |
| 私人试卷与文件夹 | 按所有者鉴权，不会因升级或管理员发布其他试卷而自动公开 |
| 公共试卷 | 已发布且文件就绪的条目对游客可见；VIP 内容受限，收藏和下载需登录且记录按账号隔离 |

**认证端点**：`POST /api/v1/auth/register|login|logout`、`GET /api/v1/auth/me`。
所有业务 API（生成/范围查询/模板）均需登录，未登录返回 401。

**模型服务由管理员统一配置**（见下方「后台管理」）：全体用户共用一份全局 LLM 配置，
密钥 Fernet 加密存在服务端，前端不保存、接口不回传明文。配置优先级：
后台「模型配置」> `.env` 兜底。生成接口不接受客户端指定接口地址、模型或密钥。

**单用户 → 多用户自动迁移**：老用户首次登录新版本时，本地 `lc_*` 数据自动
拷贝到个人命名空间；本地遗留的 LLM 明文密钥自动清除；「我的模板」自动同步。
升级到「模型配置收归后台」版本时，老部署里用户自配的 LLM 会自动迁移为全局配置。

**相关环境变量**：

```env
SECRET_KEY=        # 留空自动生成 data/secret_key.txt；生产建议固定
CORS_ORIGINS=      # 跨域白名单，留空=仅同源
FORCE_HTTPS=false  # HTTPS 部署时设 true，为会话 Cookie 添加 Secure
```

**运维提示**：`data/` 目录（secret_key.txt 等）包含加密密钥等敏感数据，
已被 .gitignore 排除。**请纳入备份，且绝不能提交到 git**；使用固定 `SECRET_KEY` 时也需安全备份该配置。
更换有效密钥会使会话失效，并可能使已存 API Key 无法解密。旧版本忽略 `.env` 中
`SECRET_KEY` 的问题已修复：升级后可能需要重新登录，旧文件密钥仅用于兼容解密历史配置。
确认旧密文已重新保存前，请保留 `data/secret_key.txt`。

多用户回归请使用下文的隔离测试服务，勿将修改数据的测试指向现有用户数据库。

---

## 后台管理

后台管理是**独立系统**，与出题工作台完全分离（独立前端应用、独立构建、专属登录页）：

```
用户端（出题工作台）：http://127.0.0.1:8000/
后台管理系统：        http://127.0.0.1:8000/admin
```

- 后台登录页**仅管理员可登录**（非管理员账号会被拒绝并提示）
- 管理员在工作台顶栏也有「🛠 后台管理」链接跳转过去
- 同源部署下两边会话互认（同一个 Cookie），无需重复登录
- 后台请求携带当前页面账号标识；其他标签页切换账号时停止旧页面操作，迟到的响应不会覆盖当前状态。退出登录只有服务端成功后才清理登录状态，网络失败会提示重试。

功能：

| 功能 | 说明 |
|------|------|
| ⚙ 模型配置 | **全局 LLM 服务**（接口地址/模型/密钥/超时），全体用户共用，密钥服务端加密存储，支持连通性测试 |
| 📊 概览 | 用户/模板统计、24 小时生成用量、供应商上报 token、部署安全提示 |
| 👥 用户管理 | 搜索、创建用户、重置密码、启用/禁用、提升/降级管理员、删除（级联清理其数据）；**📄 查看任意用户的模板**（列表 + 内容预览 + 原始 JSON，用于排查与协助） |
| 📄 系统日志 | 默认查看启动终端或容器日志；单进程启用 LOG_TO_FILE 后可在线查看 server.log 尾部 |
| 公共试卷 | 从管理员自己的归档创建草稿、预览、分类、推荐、发布与下架，查看收藏和下载人数 |

**模型配置说明**：模型服务由管理员在后台统一配置，普通用户无需也无法自行配置——
所有账号的题目生成共用这一份配置（密钥加密存于 `app_config` 表，接口不回传明文）。
未配置时生成请求会返回明确提示「请联系管理员配置模型服务」。
老部署升级后，用户此前自配的 LLM 会在启动时自动迁移为全局配置。

**如何成为管理员**：所有公开注册（包括第一个用户）都只创建普通账号。已有管理员不受升级影响。
1. 在 `.env` 配置种子管理员（每次启动自动创建/对齐）：
   ```env
   ADMIN_USERNAME=boss
   ADMIN_PASSWORD=strong-password
   ```
2. 由现有管理员在后台「用户管理」中提升

**安全护栏**：
- 所有 `/api/v1/admin/*` 端点要求管理员角色（403），未登录 401
- 管理员不能删除/禁用/降级**自己**（防止锁死系统）
- 被禁用用户的现有会话**立即失效**（每次请求校验账号状态）
- 删除用户时其模板、个人数据级联删除；仍有源试卷被公共库引用时须先处理公共条目

**独立构建**（admin/ 是独立 Vite 项目，可与 web/ 分开部署或单独迭代）：

```bash
cd admin
pnpm install
pnpm build          # 产物输出到 admin/dist/，由 FastAPI 挂载在 /admin
# 开发模式（热更新，端口 5174，/api 代理到后端）：
pnpm dev
```

测试：
- `python tests/run_ui_contracts.py`：自动启动隔离服务，检查权限、归档、公共发布和后台资源，不改真实数据库
- `python scripts/admin_console_check.py` — 独立后台页面/资源/权限（12 项）
- `python test_multiuser.py` — 多用户隔离回归（29 项）

> 前端开发模式：`cd web && pnpm dev`（Vite 端口 5173，`/api` 自动代理到 8000）。

工作台与管理后台采用 Vue 3、Nuxt UI 4、Tailwind CSS 4 和 Vite 8，共享 `ui/` 中的主题配置。
同时启动两个前端开发服务后，可通过 `http://127.0.0.1:5173/admin/` 进入后台，保持同源会话。
选型依据、迁移边界和验收记录见 [UI 重构说明](docs/ui-refactor.md)，
生成可靠性、存储边界和部署检查见 [可靠性优化说明](docs/reliability.md)。
题目管理、生成任务、后台导航及下载体验的更新与验收见 [功能与交互优化](docs/interaction-optimization.md)。
公共习题的逐份导入、失败恢复和发布衔接见 [后台添加习题流程](docs/publication-workflow.md)。
PDF 导入在读取上传内容前检查当前进程的处理槽；繁忙时直接返回 429 和 `Retry-After`，避免堆积完整文件。请求取消后仍等渲染结束才释放处理槽。

---

## 习题小程序

第一版位于独立的 `miniprogram/` 目录，使用 uni-app、Vue 3、TypeScript 和 Wot UI，
有自己的依赖、锁文件、配置和构建产物，不从 `web/` 或 `ui/` 导入代码。

面向独立的小程序账号，底部导航为「首页、习题库、收藏、我的」。支持年级、学科和分类筛选、
搜索、分页、原稿预览、PDF 获取、收藏分组、最近浏览和服务反馈。年级/科目偏好与搜索历史按账号保存在本机，
支持最新、热门、仅免费筛选、教材/学期/单元/知识点组合筛选与后台专题合集。资料与专题可微信分享，登录后回原页面。
另有私人消息、资料需求、练习/答案 PDF 版本、账号注销申请；小程序不提供私人习题、文件夹或工作台绑定。

习题列表每组最多保留 200 条，通过「上一组 / 下一组」继续浏览。返回列表时核验当前组资料并恢复位置，
切换筛选或账号回到第一组；首页和列表隐藏时释放图片引用，隐藏期间不再下载 Banner 或资料封面。隐藏页收到内存警告时进一步释放列表及首页资料，下次进入重新加载。

消息列表与已读回执独立加载，回执失败保留本次会话内的重试队列。未读角标按请求顺序更新，已读操作前及操作期间的旧查询不会覆盖新状态；未读列表发生变化后重新读取首页，避免分页跳过消息。
消息、订单、会员、资料需求和注销页面离开或切换账号时取消读取请求，已提交的写操作继续执行并校验结果归属。
首页、专题和教学标签共享 60 秒公共缓存，重复请求合并；浏览记录、已读回执等个人操作不再清空公共缓存。手动刷新、缓存过期和账号切换仍会获取最新数据，个人统计与权限数据不进入该缓存。

管理员用自己的出题账号在工作台生成并「保存到云端」，再到 `/admin/` 的「公共习题」中
选择归档、创建草稿、检查文件并明确确认发布。未完成文件不能发布，下架后停止新访问。
第一版不开放普通用户投稿或未经登录的公开下载。

小程序用户分普通用户和 VIP，后台可设置会员有效期、禁用账号，按题型配置观看和下载权限，也可逐份覆盖。
VIP 原稿、答案、缩略图和 PDF 均由服务端鉴权；支持免费预览、VIP 下载。会员支持后台开通及可配置的微信支付，含套餐、订单、全额退款与交易对账；支付默认关闭，不预置上架价格。
后台支持批量分类与上下架、普通用户/VIP 预览、保留原链接及收藏的资料修订、快捷续期及操作记录、反馈回复与使用趋势。
登录账号保持固定，展示昵称独立编辑；正式协议在登录前即可查看。功能规则与验收方式见 [优化说明](docs/mini-optimization.md) 和 [功能扩展与支付配置](docs/mini-growth.md)。
出题用户的私人归档继续仅保留在电脑工作台，不自动公开，也不复制给小程序用户。

```bash
pnpm --dir miniprogram install --frozen-lockfile
pnpm --dir miniprogram dev:h5
# 本机预览默认 http://127.0.0.1:5180，API 代理到 8000
pnpm --dir miniprogram build:mp-weixin
pnpm --dir miniprogram check:mp
```

本机 H5 可登录或注册独立的小程序账号，不接受工作台登录 Cookie。微信真机需要真实 AppID、服务端 AppSecret、HTTPS API 域名；
首次微信登录自动创建普通小程序账号。旧版绑定入口已移除，旧小程序会话不再有效，历史出题数据保留。
没有真实配置时不会绕过微信认证；正式发布还需完成隐私指引、合法域名和真机验收。
详见 [小程序运行说明](miniprogram/README.md) 和 [习题库架构与部署](docs/paper-library.md)。

## 项目结构

```
backend/
├── run.py                              # 启动入口
├── requirements.txt                    # 依赖
├── .env                                # 环境变量（需自行创建）
├── app/
│   ├── main.py                         # FastAPI 应用 + CORS + 静态服务
│   ├── config.py                       # 配置管理
│   ├── models/__init__.py              # 全部 Pydantic 模型 & 枚举
│   ├── routers/generate.py             # API 路由（6 个端点）
│   ├── services/
│   │   ├── knowledge_scope.py          # 知识范围约束服务
│   │   ├── prompt_builder.py           # Prompt 组装器
│   │   └── llm_client.py               # LLM API 客户端（流式+非流式）
│   ├── routers/generate.py             # API 路由（生成/范围/校验/反馈端点）
│   └── data/knowledge_scope.json       # 知识范围数据
└── web/                                # 出题工作台前端（Vue 3 + TS + Vite）
    ├── src/
    │   ├── App.vue                     # 外壳：顶栏 + 三步向导
    │   ├── stores/exam.ts              # Pinia 全局状态
    │   ├── api.ts / types.ts / constants.ts / utils.ts
    │   ├── exporter.ts                 # PDF/PNG/ZIP/打印导出
    │   ├── components/
    │   │   ├── StepConditions.vue      # 第 1 步：年级/科目/知识点/模板
    │   │   ├── StepSections.vue        # 第 2 步：题型 + 大题列表
    │   │   ├── StepResult.vue          # 第 3 步：预览/导出/排版模式
    │   │   ├── PaperView.vue           # A4 分页渲染 + 排版模式
    │   │   ├── PaperPage.vue           # 单页 A4 纸
    │   │   ├── SectionBlock.vue        # 大题块（全题型）
    │   │   ├── QuestionItem.vue        # 单题渲染（可编辑）
    │   │   ├── AdvancedDrawer.vue      # 高级设置（卷面风格等）
    │   │   └── LlmDialog.vue           # 模型配置弹窗
    │   └── styles/                     # tokens / base / paper 样式
    └── dist/                           # 构建产物（后端 serve 这个目录）
```

---

## API 接口文档

### 基础信息

- **Base URL**: `http://127.0.0.1:8000/api/v1`
- **Content-Type**: `application/json`
- **响应编码**: UTF-8

---

### 1. 生成题目/游戏 `POST /api/v1/generate`

**核心接口**，根据年级、科目、知识点关键词和交互类型生成一套趣味题目。

#### 请求体

```json
{
  "grade": "小学三年级",
  "subject": "数学",
  "keyword": "分数初步",
  "game_type": "quiz",
  "difficulty": "easy",
  "question_count": 5
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `grade` | `string` | ✅ | - | 年级，见[枚举值速查表](#枚举值速查表) |
| `subject` | `string` | ✅ | - | 科目，见[枚举值速查表](#枚举值速查表) |
| `keyword` | `string` | ✅ | - | 知识点关键词，1-100 字符 |
| `game_type` | `string` | - | `"quiz"` | 交互类型，见[枚举值速查表](#枚举值速查表) |
| `difficulty` | `string` | - | `"medium"` | 难度，`"easy"` / `"medium"` / `"hard"` |
| `question_count` | `int` | - | `5` | 生成题目数，范围 1-30 |

#### 响应（200）

```json
{
  "game_type": "quiz",
  "topic": "分数的初步认识",
  "difficulty": "easy",
  "grade": "小学三年级",
  "subject": "数学",
  "questions": [
    {
      "id": 1,
      "type": "multiple_choice",
      "stem": "妈妈把一个蛋糕平均分成8块。小乐吃了3块，小乐吃了这个蛋糕的几分之几？",
      "options": ["八分之三", "八分之二", "五分之三", "二分之一"],
      "answer": 0,
      "analysis": "蛋糕被平均分成了8块，每块就是八分之一。小乐吃了3块，也就是3个八分之一，合起来就是八分之三，写作 3/8。",
      "tags": ["分数的初步认识", "几分之几"]
    },
    {
      "id": 2,
      "type": "multiple_choice",
      "stem": "一条彩带被剪成了同样长的5段，用了其中2段，用掉了彩带的几分之几？",
      "options": ["四分之二", "五分之二", "五分之一", "二分之五"],
      "answer": 1,
      "analysis": "彩带被平均分成5段，每段是五分之一。用了2段，就是2个五分之一，合起来是五分之二，写作 2/5。",
      "tags": ["分数的初步认识", "几分之几"]
    }
  ],
  "total_score": 100,
  "pass_score": 60
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `game_type` | `string` | 交互类型 |
| `topic` | `string` | 题目主题 |
| `difficulty` | `string` | 难度 |
| `grade` | `string` | 年级 |
| `subject` | `string` | 科目 |
| `questions` | `array` | 题目列表 |
| `questions[].id` | `int` | 题号（从 1 开始） |
| `questions[].type` | `string` | 题型，根据 game_type 不同 |
| `questions[].stem` | `string` | 题干 |
| `questions[].options` | `array` | 选项列表（选择题才有，其他题型为 null） |
| `questions[].answer` | `int/string` | **正确答案**。选择题为选项索引（从 0 开始），填空题为答案文字 |
| `questions[].analysis` | `string` | 详细解析，用学生能理解的语言书写 |
| `questions[].tags` | `array` | 关联的知识点标签 |
| `total_score` | `int` | 总分，默认 100 |
| `pass_score` | `int` | 及格线，默认 60 |

#### 响应（400 — 年级/科目不支持）

```json
{
  "detail": {
    "error": "暂不支持 小学三年级 的 物理 科目",
    "detail": "知识范围库中未定义该年级和科目的内容"
  }
}
```

#### 响应（502 — LLM 调用失败）

```json
{
  "detail": {
    "error": "LLM 返回格式异常，请重试",
    "detail": "..."
  }
}
```

---

### 2. 流式生成 `POST /api/v1/generate/stream`

请求参数与 `/generate` 完全相同，但响应为 **SSE（Server-Sent Events）**格式，逐 token 推送生成内容。

#### SSE 事件格式

每条 `data` 行包含一个 JSON 对象：

```json
{"token": "{"}
{"token": "\n"}
{"token": "  \"game_type\"..."}
...
```

流结束时发送：
```
data: [DONE]
```

发生错误时：
```json
{"error": "错误信息"}
```

#### 前端 SSE 消费示例

```javascript
// 使用 fetch + ReadableStream
const response = await fetch('/api/v1/generate/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    grade: '小学三年级',
    subject: '数学',
    keyword: '周长',
    game_type: 'quiz',
    difficulty: 'easy',
    question_count: 5
  })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  buffer += decoder.decode(value, { stream: true });
  const lines = buffer.split('\n');
  buffer = lines.pop() || '';

  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const data = line.slice(6);
      if (data === '[DONE]') {
        console.log('流式传输完成');
      } else {
        const parsed = JSON.parse(data);
        if (parsed.error) {
          console.error('流出错:', parsed.error);
        } else {
          // parsed.token 是 LLM 生成的一个文本片段
          appendToUI(parsed.token);
        }
      }
    }
  }
}
```

> **注意**：流式接口每次都会真实调用 LLM。最终前端需要自行将 tokens 拼接后做 JSON.parse。

---

### 3. 查询知识范围 `GET /api/v1/scope`

获取指定年级和科目的知识范围（允许和禁止的知识点清单），前端可用于提示用户或做输入联想。

#### 请求参数

| 参数 | 类型 | 必填 | 示例 |
|------|------|------|------|
| `grade` | `string` | ✅ | `小学三年级` |
| `subject` | `string` | ✅ | `数学` |

#### 响应

```json
{
  "grade": "小学三年级",
  "subject": "数学",
  "allowed": [
    "万以内的加减法",
    "多位数乘一位数",
    "除数是一位数的除法",
    "分数的初步认识",
    "长方形和正方形的周长"
  ],
  "forbidden": [
    "多位数乘多位数",
    "除数是两位数的除法",
    "方程",
    "负数",
    "小数乘除法",
    "立体几何"
  ]
}
```

---

### 4. 可用年级科目列表 `GET /api/v1/scope/available`

查询系统已覆盖的年级和科目，前端用于构建下拉菜单等选择器。

#### 响应

```json
{
  "available": {
    "小学一年级": ["数学", "语文", "英语", "科学"],
    "小学二年级": ["数学", "语文", "英语", "科学"],
    "小学三年级": ["数学", "语文", "英语", "科学"],
    "小学四年级": ["数学", "语文", "英语", "科学"],
    "小学五年级": ["数学", "语文", "英语", "科学"],
    "小学六年级": ["数学", "语文", "英语", "科学"],
    "初中一年级": ["数学", "语文", "英语", "物理", "生物"],
    "初中二年级": ["数学", "语文", "英语", "物理", "生物"],
    "初中三年级": ["数学", "语文", "英语", "物理", "化学"]
  }
}
```

> **说明**：当用户选择了年级后，只有当该年级的对应科目在 `available` 列表中存在时，`/generate` 接口才能正常工作。否则会返回 400 错误。

---

### 5. 超纲校验 `POST /api/v1/validate`

让 AI 判断指定题目内容是否超出年级知识范围，可用于题目生成后的二次校验。

#### 请求体

```json
{
  "grade": "小学三年级",
  "subject": "数学",
  "question_content": "解方程：2x + 3 = 7，求 x 的值。"
}
```

#### 响应

```json
{
  "is_oob": true,
  "oob_points": ["方程"],
  "suggestion": "建议将方程改为：找规律填空 2×? + 3 = 7，引导学生逆向思考。"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `is_oob` | `bool` | 是否超纲 |
| `oob_points` | `array` | 超纲的具体知识点 |
| `suggestion` | `string/null` | 不超纲时的修改建议 |

---

### 6. 用户反馈 `POST /api/v1/feedback`

收集用户对生成题目的反馈（主要用于超纲举报）。

#### 请求体

```json
{
  "game_id": "game_xxx",
  "is_oob": true,
  "comment": "涉及了负数的计算，对三年级学生太难了"
}
```

#### 响应

```json
{
  "status": "ok",
  "message": "反馈已记录，感谢您的帮助！"
}
```

---

### 7. 健康检查 `GET /health`

```json
{
  "status": "healthy",
  "model": "deepseek-chat"
}
```

---

## 枚举值速查表

### 年级 `grade`

| 值 | 说明 |
|----|------|
| `"小学一年级"` | 一年级 |
| `"小学二年级"` | 二年级 |
| `"小学三年级"` | 三年级 |
| `"小学四年级"` | 四年级 |
| `"小学五年级"` | 五年级 |
| `"小学六年级"` | 六年级 |
| `"初中一年级"` | 初一 |
| `"初中二年级"` | 初二 |
| `"初中三年级"` | 初三 |

### 科目 `subject`

| 值 | 说明 | 覆盖年级 |
|----|------|----------|
| `"数学"` | 数学 | 全部 |
| `"语文"` | 语文 | 全部 |
| `"英语"` | 英语 | 全部 |
| `"科学"` | 科学 | 小学 1-6 年级 |
| `"物理"` | 物理 | 初中 1-3 年级 |
| `"化学"` | 化学 | 初中 3 年级 |
| `"生物"` | 生物 | 初中 1-2 年级 |

### 交互类型 `game_type`

| 值 | 说明 | 适合场景 |
|----|------|----------|
| `"quiz"` | 选择题（4选1） | 通用知识点检测 |
| `"fill_blank"` | 填空题 | 语文诗词、英语单词、数学公式 |
| `"match_pair"` | 连线配对 | 概念与定义配对、中英文配对 |
| `"challenge"` | 闯关模式 | 由易到难的综合挑战 |
| `"oral_math"` | 口算挑战 | 数学四则运算、限时心算 |
| `"reading"` | 阅读理解 | 短文+理解性问题 |

### 难度 `difficulty`

| 值 | 说明 |
|----|------|
| `"easy"` | 简单 |
| `"medium"` | 中等（默认） |
| `"hard"` | 困难 |

---

## 各游戏类型的响应结构

不同 `game_type` 返回的 `questions[].type` 和额外字段不同，前端需要按类型渲染。以下是各类型的完整结构：

### quiz（选择题）

```json
{
  "id": 1,
  "type": "multiple_choice",
  "stem": "题干",
  "options": ["选项A", "选项B", "选项C", "选项D"],
  "answer": 0,
  "analysis": "解析文字",
  "tags": ["标签1", "标签2"]
}
```

- `options` 固定 4 个选项
- `answer` 为选项索引（0-3）

### fill_blank（填空题）

```json
{
  "id": 1,
  "type": "fill_blank",
  "stem": "中国古代四大发明包括造纸术、____、火药和印刷术。",
  "answer": "指南针",
  "acceptable_answers": ["指南针", "司南"],
  "analysis": "解析文字",
  "tags": ["四大发明"]
}
```

- 题干中用 `____` 标记填空位置
- `answer` 为主正确答案
- `acceptable_answers` 为可接受的其他等价答案（用于前端模糊匹配判分）
- 没有 `options` 字段

### match_pair（连线配对）

```json
{
  "id": 1,
  "type": "match_pair",
  "left_items": ["光合作用", "呼吸作用", "蒸腾作用"],
  "right_items": ["吸收二氧化碳释放氧气", "消耗氧气释放二氧化碳", "水分以水蒸气形式散失"],
  "answer": [[0, 0], [1, 1], [2, 2]],
  "analysis": "解析文字",
  "tags": ["植物生理"]
}
```

- `left_items` 和 `right_items` 是左右两列待配对的内容
- `answer` 是配对关系数组，`[leftIndex, rightIndex]` 格式
- 没有 `options` 字段

### challenge（闯关模式）

```json
{
  "id": 1,
  "type": "multiple_choice",
  "difficulty_level": 1,
  "stem": "简单题题干...",
  "options": ["A", "B", "C", "D"],
  "answer": 0,
  "analysis": "解析",
  "tags": ["标签"]
}
```

- 每道题多一个 `difficulty_level` 字段（1=简单，逐题递增）
- 题目按 `difficulty_level` 由低到高排列
- 前端应实现"答对当前题才能进入下一题"的闯关逻辑

### oral_math（口算挑战）

```json
{
  "id": 1,
  "type": "oral_math",
  "stem": "计算：36 ÷ 4 = ？",
  "answer": 9,
  "expected_time_seconds": 15,
  "analysis": "口算技巧说明",
  "tags": ["表内除法"]
}
```

- `expected_time_seconds` 为建议答题时限（秒），前端可据此实现倒计时
- `answer` 为数字
- 没有 `options` 字段

### reading（阅读理解）

```json
{
  "game_type": "reading",
  "topic": "阅读理解主题",
  "passage": "短文内容...（一段完整的文字）",
  "questions": [
    {
      "id": 1,
      "type": "multiple_choice",
      "stem": "根据短文，主人公去了哪里？",
      "options": ["图书馆", "公园", "学校", "超市"],
      "answer": 0,
      "analysis": "文中第一段提到...",
      "tags": ["细节理解"]
    }
  ]
}
```

- 最外层响应中**多了一个 `passage` 字段**（阅读文章内容）
- `questions` 中的题目基于 `passage` 出题
- 前端应先展示短文，再逐题展示问题

---

## 生成策略与请求恢复

新请求实时调用 LLM，不按题目条件复用旧试卷；同一账号的同一 `X-Request-ID` 则只执行一次，
用于防止网络重发造成重复调用。请求 ID 应在发送前保存，相同 ID 不能用于不同条件。

- `/generate-batch`、`/generate`、`/generate/stream`、`/validate` 共用额度、并发控制和请求去重。
- 非流式成功结果默认保留 7 天；流式只记录状态，不重放 token。过期请求不会再次调用模型。
- `GET /api/v1/me/generations/{request_id}` 只查询原请求结果，不消耗生成额度。
- `GET /api/v1/me/usage` 返回滚动 24 小时用量。默认每账号 100 个请求、3 个并发，全站 6 个并发。
- 工作台超时或断网后不自动重发。手动补齐会先查询原请求，跳过已完成部分，再以新 ID 提交未完成部分；可能产生新的模型费用。
- 单次批量 API 最多 10 个大题，每大题 1-30 道题。工作台按大题 ID 映射结果，重复题型保持独立，超过 10 个大题分批发送。
- 结构校验、确定性算术检查与重复过滤后，仍不足的题目返回 `missing_count` 和 `quality_warnings`，不伪造题干。
- 缺题修复默认每请求最多追加 3 次模型调用，可设置 `GENERATION_REPAIR_LIMIT=0` 关闭；阅读题保留原文，不用另一篇文章补题。
- token 统计仅使用供应商实际返回的 `usage`，不等于费用结算，也不覆盖供应商未报告的消耗。

## 草稿与模板

草稿自动保存到本机 IndexedDB，包含题目、富文本、卷面样式及未完成请求。历史记录可手动保存，
生成后自动归档，恢复旧版本前先保存当前版本。不同账号隔离，不同页面不覆盖彼此草稿。
历史列表每页读取 20 条摘要，搜索覆盖全部历史；恢复某个版本时才读取完整快照。旧数据库首次打开时自动补建摘要，保留原始内容。
支持 Web Locks 的浏览器在刷新时复用本页草稿，复制标签页时分配独立草稿；不支持时继续使用独立 ID，旧副本不会自动删除。
在「本机历史 → 整理草稿」中可分页查看并确认删除旧副本，当前页面草稿会保留；支持 Web Locks 时还会阻止删除其他页面正在使用的草稿。清理前请先关闭其他工作台页面。
本机存储不是云备份；清理浏览器数据会删除这些记录。保存失败时页面保留内容并给出提示。

草稿按字段独立监听，修改标题或样式不遍历未变化的题目。连续编辑防抖 350ms，写入期间的新编辑合并为下一次最新快照，
未变化的草稿不重复写入。付费生成前仍等待请求记录保存成功；图片响应接收中断时保留原请求 ID，先查询结果再决定是否重新生成。
生图批次的每张图片也必须先保存请求记录；保存失败立即暂停发送，恢复存储后可继续未完成部分，已生成的图片不会重做。

模板使用服务端版本号检查更新和删除。离线修改保留在本地，重连后同步；同名版本冲突时保留本地内容，
可另存为新模板。旧版批量迁移仅创建不存在的模板，不覆盖服务端较新版本。

## 开发验证

工作台认证加载与业务界面分开挂载；网络故障保留账号标识并可重试。草稿、生成任务、模板同步分别位于 `web/src/stores/exam-{draft,generation,templates}.ts`，撤销逻辑位于 `web/src/workspace-history.ts`。分页算法位于 `web/src/paper-pagination.ts`。浏览器回归使用固定 API 响应和真实 IndexedDB，不访问业务库或付费模型；失败截图和 trace 写入 `artifacts/browser-tests/`。

图片出题支持点选推荐知识点、一键安排 8 / 12 题及展开自定义题型。手机生成后进入结果页，可直接暂停、查询和继续；结果始终标明原批次条件，支持复用设置、历史恢复、逐张下载和 PDF 合并。图片交互回归见 `web/browser-tests/image-workbench.spec.ts`，覆盖上述流程且不调用付费模型；完整说明见 [图片出题](docs/image-workbench.md)。

后端同步路由与异步入口的阻塞操作统一使用 AnyIO 线程容量，按 `max(40, DB_POOL_MAX * 2)` 配置。异步入口通过 `app.blocking.run_sync` 提交任务，`thread_wait_seconds` 记录进入工作线程前的等待，可与数据库连接池和锁等待指标一起排查排队。

在仓库根目录执行（先安装前后端依赖）：

```bash
pnpm --dir web typecheck
pnpm --dir web test
pnpm --dir web build
pnpm --dir web exec playwright install chromium # 首次安装浏览器；Linux CI 另加 --with-deps
pnpm --dir web test:browser # 生产构建上的编辑、分页、PDF、断网和跨标签页回归
pnpm --dir admin typecheck
pnpm --dir admin test
pnpm --dir admin build
pnpm --dir miniprogram typecheck
pnpm --dir miniprogram test
pnpm --dir miniprogram build:mp-weixin
pnpm --dir miniprogram check:mp
pnpm --dir miniprogram build:h5
python -m unittest discover -s tests -p 'test_backend*.py' -v
python tests/run_ui_contracts.py
git diff --check
```

`run_ui_contracts.py` 自动创建一次性 PostgreSQL 测试库、启动随机本机端口、运行 8 项 API 契约与
12 项管理后台检查，结束后关闭测试服务。不调用付费模型，不读取或修改现有用户数据库。
单测同样运行在一次性 PG 测试库上（`tests/pg_support.py` 自动建库/清理，需本机有可达的 PostgreSQL）。
GitHub Actions 工作流见 `.github/workflows/ci.yml`，覆盖以上前后端检查；远程 CI 需推送后执行。

---

## 错误处理

| HTTP 状态码 | 含义 | 响应格式 |
|-------------|------|----------|
| `200` | 成功 | 正常业务数据 |
| `400` | 请求参数错误（年级/科目不支持、参数校验失败） | `{"detail": {"error": "...", "detail": "..."}}` |
| `409` | 原请求处理中、请求 ID 冲突、账号变化或模板版本冲突 | `{"detail": {"error": "..."}}` |
| `410` | 原请求结果已过期或不支持重放 | `{"detail": {"error": "..."}}` |
| `422` | 请求体格式校验失败（FastAPI 自动校验） | Pydantic 标准格式 |
| `429` | 请求额度或并发达到上限 | `{"detail": {"error": "...", "code": "..."}}` |
| `500` | 服务端内部错误 | `{"detail": {"error": "...", "detail": "..."}}` |
| `502` | LLM 调用失败（API Key 错误、网络超时、返回格式异常） | `{"detail": {"error": "...", "detail": "..."}}` |
| `503` / `504` | 请求中断或模型超时，结果可能不确定 | `{"detail": {"error": "...", "request_id": "..."}}` |

前端应统一处理 `detail` 字段，保留 `request_id`；遇到超时、网络断开或 5xx 时先查询原请求，
不要自动创建新请求。仅 LLM 建立连接失败（`ConnectError`）允许有限重试，读写和协议异常不自动重发。

---

## 知识范围覆盖

| 年级 | 数学 | 语文 | 英语 | 科学 | 物理 | 化学 | 生物 |
|------|:----:|:----:|:----:|:----:|:----:|:----:|:----:|
| 小学一年级 | ✅ | ✅ | ✅ | ✅ | - | - | - |
| 小学二年级 | ✅ | ✅ | ✅ | ✅ | - | - | - |
| 小学三年级 | ✅ | ✅ | ✅ | ✅ | - | - | - |
| 小学四年级 | ✅ | ✅ | ✅ | ✅ | - | - | - |
| 小学五年级 | ✅ | ✅ | ✅ | ✅ | - | - | - |
| 小学六年级 | ✅ | ✅ | ✅ | ✅ | - | - | - |
| 初中一年级 | ✅ | ✅ | ✅ | - | ✅ | - | ✅ |
| 初中二年级 | ✅ | ✅ | ✅ | - | ✅ | - | ✅ |
| 初中三年级 | ✅ | ✅ | ✅ | - | ✅ | ✅ | - |

---

## 前端对接指引

### 推荐的调用流程

```
1. 页面加载 → GET /scope/available → 填充年级/科目下拉菜单

2. 用户选择年级+科目 → GET /scope?grade=xxx&subject=xxx → 展示允许的知识点提示

3. 用户输入关键词 → POST /generate（或 /generate/stream）→ 获取题目

4. 用户答题完毕 → 前端本地判分（对比 answer 字段）

5. 用户遇到明显超纲题 → POST /feedback 上报
```

### 注意事项

1. **answer 字段判分**
   - 选择题：`answer` 是 `int`，对标 `options` 索引（0-3），前端直接比较索引
   - 填空题：`answer` 是 `string`，建议同时匹配 `answer` 和 `acceptable_answers` 列表做模糊判定
   - 连线配对：`answer` 是 `[[leftIdx, rightIdx]]` 二维数组

2. **render 逻辑**：前端应根据 `questions[].type` 字段动态切换渲染组件：
   - `"multiple_choice"` → 四选一按钮组
   - `"fill_blank"` → 输入框 + 提交按钮
   - `"match_pair"` → 拖拽或点击连线的左右配对
   - `"oral_math"` → 输入框 + 倒计时器

3. **reading 类型特殊处理**：响应中多了顶层 `passage` 字段，需要先渲染文章区域再展示题目

4. **生成延迟**：新请求耗时取决于模型、题量和修复次数；展示进度，保存请求 ID，不按固定等待时间自动重发。

5. **流式降级**：如 `/generate/stream` 前端实现复杂，可先用 `/generate`，在响应回来前展示 loading 动画即可。

6. **CORS**：默认仅同源。开发时通过 Vite 代理，跨域部署时用 `CORS_ORIGINS` 明确列出前端来源。

---

## 配置说明

`.env` 文件关键配置项：

```ini
# LLM 服务（后台配置优先；密钥可留空并在后台保存）
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat

# 生成参数
LLM_TEMPERATURE=0.4               # 0-1，越低越稳定
LLM_MAX_TOKENS=4096
GENERATION_DAILY_LIMIT=100
GENERATION_USER_CONCURRENCY=3
GENERATION_GLOBAL_CONCURRENCY=6
GENERATION_REPAIR_LIMIT=3
GENERATION_LEASE_SECONDS=3600
GENERATION_RESULT_DAYS=7

# 服务
HOST=127.0.0.1
PORT=8000
FORCE_HTTPS=false                 # HTTPS 部署时设 true
```

完整配置见 `.env.example`。升级前备份数据库与密钥，再重启后端使新增接口和增量数据库迁移生效。
