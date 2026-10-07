<script setup lang="ts">
import { computed, onActivated, onDeactivated, ref } from 'vue'
import { ApiError, type UserInfo } from '../api'
import { useBeforeUnload } from '../unsaved'
import { siteDocuments, updateDocument, type SiteDocument } from '../site'

const props = defineProps<{ user: UserInfo }>()
const documents = ref<SiteDocument[]>([])
const kind = ref<'agreement' | 'privacy'>('agreement')
const loading = ref(false)
const error = ref('')
const notice = ref('')
const busy = ref(false)
const drafts = ref<Partial<Record<SiteDocument['key'], { title: string; body: string; revision: number }>>>({})
const conflict = ref(false)
const dirty = computed(() => {
  const draft = drafts.value[kind.value], server = current.value
  return !!draft && !!server && (draft.title !== server.title || draft.body !== server.body)
})
const anyDirty = computed(() => documents.value.some(server => {
  const draft = drafts.value[server.key]
  return !!draft && (draft.title !== server.title || draft.body !== server.body)
}))
useBeforeUnload(anyDirty)
let sequence = 0

const labels = { agreement: '用户协议', privacy: '隐私政策' }
const tabs = [{ label: '用户协议', value: 'agreement' }, { label: '隐私政策', value: 'privacy' }]
const current = computed(() => documents.value.find(item => item.key === kind.value) || null)
const title = computed({ get: () => drafts.value[kind.value]?.title || '', set: value => { const draft = drafts.value[kind.value]; if (draft) draft.title = value } })
const body = computed({ get: () => drafts.value[kind.value]?.body || '', set: value => { const draft = drafts.value[kind.value]; if (draft) draft.body = value } })
const message = (cause: unknown) => (cause instanceof Error ? cause.message : '操作失败，请重试')
const date = (stamp: number) => new Date(stamp * 1000).toLocaleString('zh-CN', { hour12: false })

/** 预览解析与小程序端一致：`## ` 开头的行是小标题，其余非空行是段落 */
const parsed = computed(() => body.value.split('\n').map(line => line.trim()).filter(Boolean)
  .map(line => (line.startsWith('## ')
    ? { heading: line.slice(3).trim(), text: '' }
    : { heading: '', text: line })))

async function load() {
  const current_ = ++sequence
  loading.value = true; error.value = ''
  try {
    const result = await siteDocuments()
    if (current_ !== sequence) return
    for (const item of result.items) {
      const old = documents.value.find(value => value.key === item.key)
      const draft = drafts.value[item.key]
      if (!draft || old && draft.title === old.title && draft.body === old.body) drafts.value[item.key] = { title: item.title, body: item.body, revision: item.revision }
    }
    documents.value = result.items
    return true
  } catch (cause) { if (current_ === sequence) error.value = message(cause) }
  finally { if (current_ === sequence) loading.value = false }
}
async function save() {
  const document = current.value
  if (!document || busy.value || !title.value.trim()) return
  if (body.value.length > 20000) { error.value = '正文最多 20000 字'; return }
  busy.value = true; error.value = ''
  try {
    const saved = await updateDocument(props.user.id, document.key, { revision: drafts.value[document.key]!.revision, title: title.value.trim(), body: body.value })
    documents.value = documents.value.map(item => (item.key === saved.key ? saved : item))
    drafts.value[saved.key] = { title: saved.title, body: saved.body, revision: saved.revision }; conflict.value = false
    notice.value = labels[document.key] + '已保存，小程序端立即生效'
  } catch (cause) { conflict.value = cause instanceof ApiError && cause.status === 409; error.value = message(cause) }
  finally { busy.value = false }
}
function restore() {
  const document = current.value
  if (!document) return
  if (dirty.value && !window.confirm('确认放弃当前文档未保存的修改？')) return
  drafts.value[document.key] = { title: document.title, body: document.body, revision: document.revision }; conflict.value = false
}

async function reloadConflict() {
  if (!await load()) return
  const document = current.value, draft = drafts.value[kind.value]
  if (document && draft) { draft.revision = document.revision; conflict.value = false; notice.value = '已载入最新版本，您的修改已保留，请核对后保存' }
}
onActivated(load)
onDeactivated(() => { sequence++; loading.value = false })
</script>

<template>
  <section class="admin-section" aria-label="协议与隐私页管理">
    <div class="section-toolbar">
      <div>
        <UTabs v-model="kind" :items="tabs" :content="false" />
      </div>
      <div class="actions-row">
        <UButton v-if="dirty" label="放弃修改" color="neutral" variant="ghost" :disabled="busy" @click="restore" />
        <UButton label="保存" icon="i-lucide-check" :loading="busy" :disabled="busy || !dirty || !title.trim()" @click="save" />
      </div>
    </div>
    <UButton v-if="conflict" label="载入最新并保留我的修改" @click="reloadConflict" /><UAlert v-if="error" :title="error" color="error" variant="soft" class="notice" />
    <UAlert v-if="notice" :title="notice" color="success" variant="soft" close class="notice" @update:open="notice = ''" />
    <div class="doc-meta">
      <span>{{ labels[kind] }}</span>
      <template v-if="current"><span>最后更新：{{ date(current.updated_at) }}</span><span>修订版本 v{{ current.revision }}</span></template>
      <span v-if="dirty" class="dirty-tag">有未保存的修改</span>
    </div>
    <div class="doc-editor" :aria-busy="loading">
      <div class="doc-pane">
        <label class="field-label" for="doc-title">标题</label>
        <UInput id="doc-title" v-model="title" maxlength="60" :disabled="busy || loading" class="w-full" />
        <label class="field-label" for="doc-body">正文<small>以「## 」开头是小标题，其余每一行是一个段落</small></label>
        <textarea id="doc-body" v-model="body" class="doc-textarea" maxlength="20000" spellcheck="false" :disabled="busy || loading" />
      </div>
      <div class="doc-pane preview">
        <span class="field-label" aria-hidden="true">小程序里的显示效果</span>
        <div class="doc-preview">
          <p class="preview-title">{{ title || '（未填写标题）' }}</p>
          <template v-for="(line, index) in parsed" :key="index">
            <p v-if="line.heading" class="preview-heading">{{ line.heading }}</p>
            <p v-else class="preview-text">{{ line.text }}</p>
          </template>
          <p v-if="!parsed.length" class="preview-empty">正文还是空的</p>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.doc-meta { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; margin-bottom: 16px; color: var(--ui-text-muted); font-size: 12px; }
.dirty-tag { color: var(--ui-warning); }
.doc-editor { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px; align-items: start; }
.doc-pane { min-width: 0; }
.field-label { display: block; margin: 0 0 8px; font-size: 12px; color: var(--ui-text-toned); }
.field-label:not(:first-child) { margin-top: 18px; }
.field-label small { display: block; margin-top: 4px; color: var(--ui-text-muted); font-size: 11px; }
.doc-textarea { width: 100%; min-height: 52dvh; padding: 14px; border: 1px solid var(--ui-border); border-radius: 6px; background: #fff; color: var(--ui-text-highlighted); font-family: inherit; font-size: 13px; line-height: 1.8; resize: vertical; }
.doc-textarea:disabled { background: #f8fafb; color: var(--ui-text-muted); }
.doc-preview { min-height: 52dvh; max-height: 70dvh; overflow: auto; padding: 18px; border: 1px solid var(--ui-border-muted); border-radius: 6px; background: #fbfcfc; }
.preview-title { margin: 0 0 18px; font-size: 19px; font-weight: 650; color: var(--ui-text-highlighted); }
.preview-heading { margin: 22px 0 10px; font-size: 15px; font-weight: 600; color: var(--ui-text-highlighted); }
.preview-text { margin: 0; font-size: 13px; line-height: 1.95; color: var(--ui-text-toned); overflow-wrap: anywhere; }
.preview-empty { margin: 0; color: var(--ui-text-muted); font-size: 12px; }
@media (max-width: 1100px) { .doc-editor { grid-template-columns: minmax(0, 1fr); } .doc-textarea, .doc-preview { min-height: 32dvh; } }
</style>
