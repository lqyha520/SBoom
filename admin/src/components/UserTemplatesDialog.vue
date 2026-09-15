<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import * as api from '../api'
import { TYPE_NAME } from '../typeNames'

const props = defineProps<{ user: api.AdminUser | null }>()
const emit = defineEmits<{ close: [] }>()
const templates = ref<api.UserTemplateMeta[]>([])
const loading = ref(false)
const error = ref('')
const selected = ref<api.UserTemplateMeta | null>(null)
type TemplateContent = Record<string, any>
const content = ref<TemplateContent | null>(null)
const contentLoading = ref(false)
const contentError = ref('')
const showJson = ref(false)
let listRequest = 0
let contentRequest = 0

async function load() {
  const request = ++listRequest
  ++contentRequest
  selected.value = null
  content.value = null
  error.value = ''
  templates.value = []
  if (!props.user) return
  loading.value = true
  try {
    const values = await api.fetchUserTemplates(props.user.id)
    if (request === listRequest) templates.value = values
  } catch (e: unknown) {
    if (request === listRequest) error.value = e instanceof Error ? e.message : '模板加载失败'
  } finally { if (request === listRequest) loading.value = false }
}
watch(() => props.user?.id, load, { immediate: true })
async function open(template: api.UserTemplateMeta) {
  if (!props.user) return
  const request = ++contentRequest
  selected.value = template
  content.value = null
  contentError.value = ''
  showJson.value = false
  contentLoading.value = true
  try {
    const value = await api.fetchUserTemplateContent(props.user.id, template.id)
    if (request === contentRequest) content.value = value
  } catch (e: unknown) {
    if (request === contentRequest) contentError.value = e instanceof Error ? e.message : '内容加载失败'
  } finally { if (request === contentRequest) contentLoading.value = false }
}
const summary = computed(() => {
  const value = content.value
  if (!value) return []
  const rows: { label: string; value: string }[] = []
  for (const [key, label] of [['grade', '年级'], ['subject', '科目'], ['keyword', '知识点'], ['title', '卷面标题']]) {
    if (value[key]) rows.push({ label, value: String(value[key]) })
  }
  if (value.difficulty) rows.push({ label: '难度', value: ({ easy: '简单', medium: '适中', hard: '困难' } as Record<string, string>)[value.difficulty] || String(value.difficulty) })
  const sections = Array.isArray(value.sections) ? value.sections : Array.isArray(value.cards) ? value.cards : []
  if (sections.length) rows.push({ label: '题型构成', value: sections.map((s: any) => (TYPE_NAME[s.type] || s.name || s.type) + ' × ' + (s.count ?? s.data?.questions?.length ?? 0)).join('、') })
  return rows
})
const questions = computed(() => {
  const out: string[] = []
  const sections = content.value?.sections
  if (!Array.isArray(sections)) return out
  for (const section of sections) {
    if (!Array.isArray(section.data?.questions)) continue
    for (const question of section.data.questions) {
      if (out.length === 8) return out
      const stem = question.stem || question.top || question.left_expr || question.type || ''
      const answer = question.answer == null ? '' : ' 【答：' + (Array.isArray(question.answer) ? question.answer.join('，') : String(question.answer)) + '】'
      out.push(String(stem) + answer)
    }
  }
  return out
})
</script>

<template>
  <UModal :open="!!user" :title="(user?.username || '') + ' 的模板'" :ui="{ content: 'max-w-4xl' }" @update:open="(value: boolean) => { if (!value) emit('close') }">
    <template #body>
      <div v-if="loading" class="empty-state" role="status"><UIcon name="i-lucide-loader-circle" class="size-6 animate-spin" /><h3>正在加载模板</h3></div>
      <UAlert v-else-if="error" :title="error" color="error" variant="soft" :actions="[{ label: '重试', onClick: load }]" />
      <div v-else-if="!templates.length" class="empty-state"><UIcon name="i-lucide-folder-open" class="size-8" /><h3>该用户暂无模板</h3></div>
      <div v-else class="template-browser">
        <nav class="template-list" aria-label="用户模板">
          <button v-for="template in templates" :key="template.id" :class="{ active: selected?.id === template.id }" :aria-pressed="selected?.id === template.id" @click="open(template)"><strong>{{ template.name }}</strong><time>{{ template.updated_at }}</time></button>
        </nav>
        <div class="template-detail">
          <div v-if="!selected" class="empty-state"><UIcon name="i-lucide-file-text" class="size-8" /><h3>尚未选择模板</h3></div>
          <div v-else-if="contentLoading" class="empty-state" role="status"><UIcon name="i-lucide-loader-circle" class="size-6 animate-spin" /><h3>正在加载内容</h3></div>
          <UAlert v-else-if="contentError" :title="contentError" color="error" variant="soft" :actions="[{ label: '重试', onClick: () => selected && open(selected) }]" />
          <template v-else-if="content">
            <h3 class="text-sm font-semibold mb-3 break-words">{{ selected.name }}</h3>
            <dl class="info-list"><template v-for="row in summary" :key="row.label"><dt>{{ row.label }}</dt><dd>{{ row.value }}</dd></template></dl>
            <ol v-if="questions.length" class="question-preview list-decimal"><li v-for="(question, index) in questions" :key="index">{{ question }}</li></ol>
            <UButton :icon="showJson ? 'i-lucide-chevron-up' : 'i-lucide-code'" :label="showJson ? '收起 JSON' : '原始 JSON'" color="neutral" variant="outline" size="xs" class="my-3" :aria-expanded="showJson" @click="showJson = !showJson" />
            <pre v-if="showJson" class="json-view" tabindex="0" aria-label="模板 JSON">{{ JSON.stringify(content, null, 2) }}</pre>
          </template>
        </div>
      </div>
    </template>
    <template #footer><UButton label="关闭" color="neutral" variant="outline" @click="emit('close')" /></template>
  </UModal>
</template>
