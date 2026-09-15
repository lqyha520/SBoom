<script setup lang="ts">
import { computed, onActivated, onDeactivated, ref, watch } from 'vue'
import type { UserInfo } from '../api'
import { siteDocuments, updateDocument, type SiteDocument } from '../site'

const props = defineProps<{ user: UserInfo }>()
const documents = ref<SiteDocument[]>([])
const kind = ref<'agreement' | 'privacy'>('agreement')
const loading = ref(false)
const error = ref('')
const notice = ref('')
const busy = ref(false)
const dirty = ref(false)
let sequence = 0

const labels = { agreement: '用户协议', privacy: '隐私政策' }
const tabs = [{ label: '用户协议', value: 'agreement' }, { label: '隐私政策', value: 'privacy' }]
const current = computed(() => documents.value.find(item => item.key === kind.value) || null)
const title = ref('')
const body = ref('')
const message = (cause: unknown) => (cause instanceof Error ? cause.message : '操作失败，请重试')
const date = (stamp: number) => new Date(stamp * 1000).toLocaleString('zh-CN', { hour12: false })

/** 预览解析与小程序端一致：`## ` 开头的行是小标题，其余非空行是段落 */
const parsed = computed(() => body.value.split('\n').map(line => line.trim()).filter(Boolean)
  .map(line => (line.startsWith('## ')
    ? { heading: line.slice(3).trim(), text: '' }
    : { heading: '', text: line })))

watch([title, body], () => { dirty.value = true })
watch(current, value => {
  if (!value) return
  title.value = value.title
  body.value = value.body
  // 赋值本身会触发 dirty，这里在下一帧清掉
  queueMicrotask(() => { dirty.value = false })
}, { immediate: true })

async function load() {
  const current_ = ++sequence
  loading.value = true; error.value = ''
  try {
    const result = await siteDocuments()
    if (current_ !== sequence) return
    documents.value = result.items
    const active = result.items.find(item => item.key === kind.value)
    if (active) { title.value = active.title; body.value = active.body; queueMicrotask(() => { dirty.value = false }) }
  } catch (cause) { if (current_ === sequence) error.value = message(cause) }
  finally { if (current_ === sequence) loading.value = false }
}
async function save() {
  const document = current.value
  if (!document || busy.value || !title.value.trim()) return
  busy.value = true; error.value = ''
  try {
    const saved = await updateDocument(props.user.id, document.key, { revision: document.revision, title: title.value.trim(), body: body.value })
    documents.value = documents.value.map(item => (item.key === saved.key ? saved : item))
    dirty.value = false
    notice.value = labels[document.key] + '已保存，小程序端立即生效'
  } catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}
function restore() {
  const document = current.value
  if (!document) return
  title.value = document.title; body.value = document.body
  queueMicrotask(() => { dirty.value = false })
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
    <UAlert v-if="error" :title="error" color="error" variant="soft" class="notice" />
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
        <textarea id="doc-body" v-model="body" class="doc-textarea" spellcheck="false" :disabled="busy || loading" />
      </div>
      <div class="doc-pane preview">
        <span class="field-label" aria-hidden="true">小程序里的显示效果</span>
        <div class="doc-preview" aria-live="polite">
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
