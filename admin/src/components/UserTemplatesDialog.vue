<script setup lang="ts">
import { ref, watch } from 'vue'
import * as api from '../api'
import type { AdminUser, UserTemplateMeta } from '../api'
import { TYPE_NAME } from '../typeNames'

const props = defineProps<{ user: AdminUser | null }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const templates = ref<UserTemplateMeta[]>([])
const loading = ref(false)
const error = ref('')
const selected = ref<UserTemplateMeta | null>(null)
const content = ref<any>(null)
const contentLoading = ref(false)
const showJson = ref(false)

watch(
  () => props.user,
  async u => {
    selected.value = null
    content.value = null
    error.value = ''
    templates.value = []
    if (!u) return
    loading.value = true
    try {
      templates.value = await api.fetchUserTemplates(u.id)
    } catch (e: any) {
      error.value = e?.message || '加载失败'
    } finally {
      loading.value = false
    }
  },
)

async function open(t: UserTemplateMeta) {
  if (!props.user) return
  selected.value = t
  content.value = null
  showJson.value = false
  contentLoading.value = true
  try {
    content.value = await api.fetchUserTemplateContent(props.user.id, t.id)
  } catch (e: any) {
    content.value = { error: e?.message || '内容加载失败' }
  } finally {
    contentLoading.value = false
  }
}

/** 把模板 JSON 转成人类可读的摘要行 */
function summarize(c: any): { k: string; v: string }[] {
  if (!c || typeof c !== 'object') return []
  const out: { k: string; v: string }[] = []
  const push = (k: string, v: string) => out.push({ k, v })
  if (c.grade) push('年级', c.grade)
  if (c.subject) push('科目', c.subject)
  if (c.keyword) push('知识点', c.keyword)
  if (c.difficulty) push('难度', c.difficulty === 'easy' ? '简单' : c.difficulty === 'hard' ? '困难' : '中等')
  if (c.title) push('卷面标题', c.title)
  if (c.templateId) push('卷面模板', c.templateId)
  const secs = c.sections || []
  if (secs.length) {
    push('题型构成', secs.map((s: any) => `${TYPE_NAME[s.type] || s.type}×${s.count ?? (s.data?.questions?.length || '?')}`).join('、'))
    const totalQ = secs.reduce((n: number, s: any) => n + (s.data?.questions?.length || 0), 0)
    push('题目总数', String(totalQ))
  } else if (c.cards?.length) {
    push('题型构成', c.cards.map((x: any) => `${TYPE_NAME[x.type] || x.type}×${x.count}`).join('、'))
  }
  return out
}

/** 抽取题目预览（前 N 题） */
function questionPreview(c: any, limit = 8): string[] {
  const out: string[] = []
  for (const s of c?.sections || []) {
    for (const q of s?.data?.questions || []) {
      if (out.length >= limit) return out
      const stem = q.stem || q.top || q.left_expr || `（${q.type}）`
      const ans = q.answer != null ? `【答：${Array.isArray(q.answer) ? q.answer.join('，') : q.answer}】` : ''
      out.push(`${stem} ${ans}`.trim())
    }
  }
  return out
}
</script>

<template>
  <teleport to="body">
    <div v-if="user" class="modal-mask" @click.self="emit('close')">
      <div class="modal">
        <div class="modal-head">
          <h3>📄 {{ user.username }} 的模板（{{ templates.length }}）</h3>
          <button class="x-btn" @click="emit('close')">✕</button>
        </div>
        <div class="modal-body tpl-body">
          <div v-if="loading" class="empty">加载中…</div>
          <div v-else-if="error" class="empty err">{{ error }}</div>
          <div v-else-if="!templates.length" class="empty">该用户还没有保存过模板</div>

          <template v-else>
            <div class="tpl-list">
              <button
                v-for="t in templates" :key="t.id"
                class="tpl-item" :class="{ on: selected?.id === t.id }"
                @click="open(t)"
              >
                <b>{{ t.name }}</b>
                <span class="tpl-time">{{ t.updated_at }}</span>
              </button>
            </div>

            <div class="tpl-detail">
              <div v-if="!selected" class="empty">← 点击左侧模板查看内容</div>
              <div v-else-if="contentLoading" class="empty">内容加载中…</div>
              <template v-else-if="content">
                <div v-if="content.error" class="empty err">{{ content.error }}</div>
                <template v-else>
                  <h4 class="tpl-title">{{ selected.name }}</h4>
                  <dl class="kv">
                    <template v-for="row in summarize(content)" :key="row.k">
                      <dt>{{ row.k }}</dt><dd>{{ row.v }}</dd>
                    </template>
                  </dl>
                  <div v-if="questionPreview(content).length" class="q-preview">
                    <div class="q-head">题目预览（前 {{ questionPreview(content).length }} 题）</div>
                    <div v-for="(q, i) in questionPreview(content)" :key="i" class="q-line">{{ i + 1 }}. {{ q }}</div>
                  </div>
                  <div class="json-toggle">
                    <button class="btn mini" @click="showJson = !showJson">
                      {{ showJson ? '收起' : '展开' }}原始 JSON
                    </button>
                  </div>
                  <pre v-if="showJson" class="json-view">{{ JSON.stringify(content, null, 2) }}</pre>
                </template>
              </template>
            </div>
          </template>
        </div>
      </div>
    </div>
  </teleport>
</template>

<style scoped>
.modal-mask {
  position: fixed; inset: 0; z-index: 300;
  background: rgba(20, 26, 44, 0.45);
  display: flex; align-items: center; justify-content: center;
}
.modal {
  background: #fff; border-radius: 14px;
  width: min(860px, 94vw); max-height: 88vh;
  display: flex; flex-direction: column;
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.25);
}
.modal-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid #eef1f8;
}
.modal-head h3 { margin: 0; font-size: 16px; color: #22314f; }
.x-btn { border: 0; background: transparent; font-size: 16px; cursor: pointer; color: #7b869e; }
.modal-body { padding: 16px 20px; overflow: auto; }
.tpl-body { display: flex; gap: 16px; min-height: 320px; }
.empty { color: #97a1b7; font-size: 13px; padding: 28px 0; text-align: center; }
.empty.err { color: #c0392b; }

.tpl-list {
  width: 220px; flex-shrink: 0;
  display: flex; flex-direction: column; gap: 6px;
  max-height: 60vh; overflow: auto;
}
.tpl-item {
  text-align: left; border: 1px solid #e2e7f2; background: #f8fafd;
  border-radius: 10px; padding: 10px 12px; cursor: pointer;
  display: flex; flex-direction: column; gap: 3px;
}
.tpl-item:hover { border-color: #4b6ef5; }
.tpl-item.on { border-color: #4b6ef5; background: #eef2ff; }
.tpl-item b { font-size: 13px; color: #2c3550; }
.tpl-time { font-size: 11px; color: #97a1b7; }

.tpl-detail { flex: 1; min-width: 0; }
.tpl-title { margin: 0 0 12px; font-size: 15px; color: #22314f; }
.kv { display: grid; grid-template-columns: 84px 1fr; gap: 7px 12px; margin: 0 0 14px; font-size: 13px; }
.kv dt { color: #7b869e; }
.kv dd { margin: 0; color: #2c3550; word-break: break-all; }

.q-preview {
  background: #f6f8fc; border-radius: 10px; padding: 12px 14px;
  font-size: 13px; color: #2c3550;
}
.q-head { font-weight: 600; color: #5c6880; margin-bottom: 8px; font-size: 12px; }
.q-line { padding: 3px 0; border-bottom: 1px dashed #e6eaf3; word-break: break-all; }
.q-line:last-child { border-bottom: 0; }

.json-toggle { margin: 12px 0 8px; }
.json-view {
  background: #1e2433; color: #c9d4ea; border-radius: 10px;
  padding: 14px; font-size: 11px; line-height: 1.6;
  max-height: 280px; overflow: auto; white-space: pre-wrap; word-break: break-all; margin: 0;
}
</style>
