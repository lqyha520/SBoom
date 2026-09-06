# Learning Coach API

> AI+教育 课堂互动系统 —— 后端服务

基于 FastAPI 的轻量后端，核心逻辑：接收前端请求 → 组装 Prompt（注入知识范围约束）→ 调用 LLM 生成趣味题目/知识游戏 → 返回结构化 JSON。

---

## 目录

- [快速开始](#快速开始)
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
- [缓存机制](#缓存机制)
- [错误处理](#错误处理)
- [知识范围覆盖](#知识范围覆盖)
- [前端对接指引](#前端对接指引)

---

## 快速开始

### 环境要求

- Python 3.9+
- 已配置的 OpenAI 兼容 LLM API（如 DeepSeek / 通义千问 / GPT）

### 安装与启动

```bash
cd backend

# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量（复制模板并编辑）
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY=your-key

# 3. 构建前端（需要 Node.js 20+ 和 pnpm）
cd web
pnpm install
pnpm build        # 产物输出到 web/dist/
cd ..

# 4. 启动服务
python run.py
```

访问 `http://127.0.0.1:8000` 使用出题工作台，`http://127.0.0.1:8000/docs` 查看 Swagger 文档。

> 前端开发模式：`cd web && pnpm dev`（Vite 端口 5173，`/api` 自动代理到 8000）。

---

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
│   ├── cache/question_cache.py         # 内存 LRU 缓存
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
  "question_count": 5,
  "use_cache": true
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `grade` | `string` | ✅ | - | 年级，见[枚举值速查表](#枚举值速查表) |
| `subject` | `string` | ✅ | - | 科目，见[枚举值速查表](#枚举值速查表) |
| `keyword` | `string` | ✅ | - | 知识点关键词，1-100 字符 |
| `game_type` | `string` | - | `"quiz"` | 交互类型，见[枚举值速查表](#枚举值速查表) |
| `difficulty` | `string` | - | `"medium"` | 难度，`"easy"` / `"medium"` / `"hard"` |
| `question_count` | `int` | - | `5` | 生成题目数，范围 1-10 |
| `use_cache` | `bool` | - | `true` | 是否使用缓存（相同参数命中缓存会瞬时返回） |

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
  "pass_score": 60,
  "from_cache": false
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
| `from_cache` | `bool` | 是否来自缓存 |

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

> **注意**：流式接口**不使用缓存**，每次都会调用 LLM。最终前端需要自行将 tokens 拼接后做 JSON.parse。

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
  "game_id": "cache_key_xxx",
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
  "model": "deepseek-chat",
  "cache": {
    "size": 12,
    "max_size": 500,
    "ttl_seconds": 86400
  }
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

## 缓存机制

- **缓存 key**：由 `grade + subject + keyword + game_type + difficulty + question_count` 六元组生成 SHA256 哈希
- **缓存策略**：LRU 淘汰，默认最大 500 条、24 小时过期
- **缓存命中**：响应中 `from_cache: true`，几乎瞬时返回（无需等待 LLM）
- **跳过缓存**：请求中设置 `"use_cache": false`
- **注意**：流式接口（`/generate/stream`）不使用缓存

前端建议：
1. 热门知识点（如"九九乘法表"、"分数初步"）首次加载后有缓存，后续相同请求秒级返回
2. 可以使用 `cache_key` 字段追踪某次生成是否命中缓存

---

## 错误处理

| HTTP 状态码 | 含义 | 响应格式 |
|-------------|------|----------|
| `200` | 成功 | 正常业务数据 |
| `400` | 请求参数错误（年级/科目不支持、参数校验失败） | `{"detail": {"error": "...", "detail": "..."}}` |
| `422` | 请求体格式校验失败（FastAPI 自动校验） | Pydantic 标准格式 |
| `500` | 服务端内部错误 | `{"detail": {"error": "...", "detail": "..."}}` |
| `502` | LLM 调用失败（API Key 错误、网络超时、返回格式异常） | `{"detail": {"error": "...", "detail": "..."}}` |

前端应统一处理 `detail` 字段，对 502 错误给出"生成失败，请重试"的用户提示。

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

4. **缓存预热**：首次进入某知识点页面时会有 LLM 调用延迟（通常 3-8 秒），建议在前端展示 loading 动画或骨架屏。同一知识点的后续请求会命中缓存，瞬时返回。

5. **流式降级**：如 `/generate/stream` 前端实现复杂，可先用 `/generate`，在响应回来前展示 loading 动画即可。

6. **CORS**：开发阶段后端已开放全来源 CORS（`allow_origins=["*"]`），生产环境需限制为前端实际域名。

---

## 配置说明

`.env` 文件关键配置项：

```ini
# LLM 服务（必填）
LLM_API_KEY=sk-your-key           # API 密钥，必须配置
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-pro

# 生成参数
LLM_TEMPERATURE=0.4               # 0-1，越低越稳定
LLM_MAX_TOKENS=4096

# 缓存
CACHE_ENABLED=true                # 是否启用缓存
CACHE_MAX_SIZE=500                # 最大缓存条数
CACHE_TTL_SECONDS=86400           # 过期时间（秒），默认 24h

# 服务
HOST=127.0.0.1
PORT=8000
```
