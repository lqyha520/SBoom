<script setup lang="ts">
import { canAdmin } from '../permissions'
import { workflowTabs } from '../xhs-workflow'
import { computed, ref, watch } from 'vue'
import { cleanWorkflowData, workflowFingerprint, workflowVersions, workflowError, formatWorkflowDate, type BaseData, type PublicationData, type WorkflowRecord } from '../xhs-workflow'
import { publicationChecks } from '../xhs-publication'
const props = defineProps<{ record: WorkflowRecord<BaseData>; current?: BaseData; dirty?: boolean; readonly?: boolean; disabled?: boolean }>()
const emit = defineEmits<{ restore: [data: BaseData] }>()
const open = ref(false), loading = ref(false), error = ref(''), page = ref(1), total = ref(0)
const items = ref<{ revision: number; data: BaseData; created_at: string }[]>([])
const selected = ref<{ revision: number; data: BaseData } | null>(null)
const fieldLabels: Record<string, string> = { title: '名称', status: '状态', grade: '年级', subject: '科目', keyword: '知识点', audience: '目标读者', angle: '切入点', instructions: '使用说明', questions: '题目、答案与讲解', game_type: '题型', difficulty: '难度', question_count: '题数', headline: '发布标题', body: '正文', hashtags: '话题', cover_title: '封面标题', cover_subtitle: '封面副标题', cards: '内页', theme: '配图主题', notes: '备注', review_notes: '复核备注', accuracy_checked: '答案复核', scope_checked: '范围复核', layout_checked: '排版复核', account_profile: '账号定位', title_options: '备选标题', generation_request_id: '生成记录', source_material_revision: '来源资料版本' }
function display(value: unknown) {
  if (value === undefined || value === null || value === '') return '未填写'
  if (typeof value === 'boolean') return value ? '已确认' : '未确认'
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2)
  return text.length > 1200 ? text.slice(0, 1200) + '\n…内容较长，带入后可在编辑区查看全部。' : text
}
const differences = computed(() => {
  if (!selected.value) return []
  const before = cleanWorkflowData(props.current || props.record.data) as unknown as Record<string, unknown>
  const after = cleanWorkflowData(selected.value.data) as unknown as Record<string, unknown>
  return [...new Set([...Object.keys(before), ...Object.keys(after)])].filter(key => workflowFingerprint(before[key]) !== workflowFingerprint(after[key])).map(key => ({ key, label: fieldLabels[key] || key, before: display(before[key]), after: display(after[key]) }))
})
let sequence = 0
watch(() => props.record.id, () => { sequence++; open.value = false; loading.value = false; error.value = ''; items.value = []; selected.value = null })
async function load(value = 1) {
  if (props.disabled) return
  const seq = ++sequence; selected.value = null
  page.value = value; loading.value = true; error.value = ''
  try {
    const result = await workflowVersions(props.record.kind, props.record.id, page.value)
    if (seq !== sequence) return
    items.value = result.items; total.value = result.total; open.value = true
  } catch (cause) { if (seq === sequence) error.value = workflowError(cause) }
  finally { if (seq === sequence) loading.value = false }
}
function restore() {
  if (!selected.value || props.readonly || props.disabled) return
  if (props.dirty && !window.confirm('带入历史版本会替换当前未保存的编辑，是否继续？可取消后先保存当前内容。')) return
  emit('restore', cleanWorkflowData(selected.value.data)); open.value = false; selected.value = null
}
function publicationVersion(value: BaseData) {
  const data = value as PublicationData
  const content = data.source === 'custom' ? data.custom_content : data.draft_snapshot
  return ['发布账号：' + (data.account || '未填写'), '', content?.headline || '', content?.body || '', content?.hashtags || '', '',
    ...publicationChecks.map(item => (data[item.key] ? '已确认：' : '未确认：') + item.label), '', '复核说明：' + (data.review_notes || '未填写')].join('\n')
}
</script>
<template>
  <UButton label="版本历史" color="neutral" variant="outline" :loading="loading" :disabled="disabled" @click="load()" />
  <p v-if="error" role="alert">{{ error }}</p>
  <UModal v-model:open="open" title="版本历史" :ui="{content:'max-w-4xl'}"><template #body>
    <template v-if="selected && !readonly">
      <p class="workflow-hint">比较当前编辑与第 {{ selected.revision }} 版。确认后带入编辑区，点击保存才会生成新版本；资料需重新复核。</p>
      <UAlert v-if="dirty" title="当前有未保存的修改，带入历史版本会替换这些编辑。" color="warning" class="my-3" />
      <div class="version-differences">
        <div v-for="field in differences" :key="field.key" class="version-difference"><h3>{{ field.label }}</h3><div class="version-values"><div><strong>当前编辑</strong><pre>{{ field.before }}</pre></div><div><strong>历史版本</strong><pre>{{ field.after }}</pre></div></div></div>
      </div>
      <p v-if="!differences.length" class="workflow-hint">内容与当前编辑相同。</p>
      <div class="workflow-actions mt-4"><UButton label="返回版本列表" variant="outline" @click="selected=null" /><UButton v-if="canAdmin(workflowTabs[record.kind], 'update')" label="确认带入编辑" :disabled="disabled" @click="restore" /></div>
    </template>
    <template v-else>
      <p class="workflow-hint">{{ readonly ? '保留每次保存时的内容与复核记录；发布记录的历史版本仅供查看。' : '先比较历史版本与当前编辑，再确认是否带入。' }}</p>
      <div v-for="item in items" :key="item.revision" class="workflow-list-item"><div><strong>第 {{ item.revision }} 版</strong><small>{{ formatWorkflowDate(item.created_at) }}</small><p>{{ item.data.title }}</p><details v-if="readonly"><summary class="cursor-pointer text-sm">查看该版本文案与复核</summary><div class="workflow-preview mt-3">{{ publicationVersion(item.data) }}</div></details></div><UButton v-if="!readonly" label="带入编辑" size="sm" :disabled="disabled" @click="selected=item" /></div>
      <UPagination v-if="total > 20" :page="page" :total="total" :items-per-page="20" @update:page="load" />
    </template>
  </template></UModal>
</template>
<style scoped>
.version-differences{display:grid;gap:16px;max-height:55vh;overflow:auto}
.version-difference h3{font-size:14px;margin-bottom:6px}.version-values{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.version-values>div{min-width:0;padding:12px;background:var(--ui-bg-elevated);border-radius:8px}.version-values strong{font-size:12px}.version-values pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;font-size:13px;margin-top:8px}
@media(max-width:600px){.version-values{grid-template-columns:1fr}}
</style>
