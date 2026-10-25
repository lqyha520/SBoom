<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type Sortable from 'sortablejs'
import { useExamStore } from '../stores/exam'
import { MAX_QUESTIONS_PER_TYPE, TYPE_NAME } from '../constants'
import type { Section } from '../types'
import QuestionManager from './QuestionManager.vue'

const store = useExamStore()
const list = ref<HTMLElement | null>(null)
const layoutSection = ref<Section | null>(null)
const retryTarget = ref<Section | null>(null)
const questionTarget = ref('')
let sortable: Sortable | undefined
let disposed = false
onMounted(async () => {
  const el = list.value
  if (!el) return
  // sortablejs 按需加载，不进入工作台首屏 bundle。
  const { default: SortableCtor } = await import('sortablejs')
  if (disposed) return
  sortable = new SortableCtor(el, {
    animation: matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 150,
    handle: '.drag-handle', draggable: '.section-item', ghostClass: 'sortable-ghost',
    onEnd: event => {
      if (event.oldIndex != null && event.newIndex != null) store.moveSection(event.oldIndex, event.newIndex)
    },
  })
})
watch(() => store.generating, value => sortable?.option('disabled', value))
onBeforeUnmount(() => { disposed = true; sortable?.destroy() })
function actions(section: Section, index: number) {
  return [[
    { label: '生成 / 重新生成大题', icon: 'i-lucide-sparkles', onSelect: () => { retryTarget.value = section } },
    { label: '管理题目 / 单题替换', icon: 'i-lucide-list-checks', onSelect: () => { questionTarget.value = section.id } },
    { label: '调整版式', icon: 'i-lucide-columns-2', onSelect: () => { layoutSection.value = section } },
    { label: '上移', icon: 'i-lucide-arrow-up', disabled: index === 0, onSelect: () => store.moveSection(index, index - 1) },
    { label: '下移', icon: 'i-lucide-arrow-down', disabled: index === store.sections.length - 1, onSelect: () => store.moveSection(index, index + 1) },
  ], [{ label: '删除大题', icon: 'i-lucide-trash-2', color: 'error' as const, onSelect: () => store.removeSection(section.id) }]]
}
const fontSizes = [{ label: '默认', value: 'default' }, ...['9pt', '10pt', '10.5pt', '11pt', '12pt'].map(value => ({ label: value, value }))]
async function retry() {
  const id = retryTarget.value?.id
  retryTarget.value = null
  if (id) await store.retrySection(id)
}
</script>

<template>
  <div class="section-list">
    <QuestionManager v-if="questionTarget" :section-id="questionTarget" @close="questionTarget = ''" />
    <div v-if="!store.sections.length" class="empty-state">
      <UIcon name="i-lucide-list-plus" class="size-8" />
      <h3>尚未添加题型</h3>
      <p>0 个大题 / 0 道题目</p>
    </div>
    <div ref="list" class="section-items">
      <article v-for="(section, index) in store.sections" :key="section.id" class="section-item" :data-section-id="section.id">
        <div class="section-topline">
          <button class="drag-handle" :disabled="store.generating" :aria-label="'调整第 ' + (index + 1) + ' 大题顺序'" title="拖动排序" @keydown.up.prevent="store.moveSection(index, index - 1)" @keydown.down.prevent="store.moveSection(index, index + 1)"><UIcon name="i-lucide-grip-vertical" class="size-4" /></button>
          <span class="section-index">{{ String(index + 1).padStart(2, '0') }}</span>
          <h3>{{ section.name || TYPE_NAME[section.type] || section.type }}</h3>
          <UDropdownMenu :items="actions(section, index)"><UButton icon="i-lucide-ellipsis" color="neutral" variant="ghost" size="xs" :disabled="store.generating" :aria-label="'第 ' + (index + 1) + ' 大题操作'" /></UDropdownMenu>
        </div>
        <div class="section-controls">
          <span class="text-xs text-muted">题目数量</span>
          <UInputNumber :model-value="section.count" :min="1" :max="MAX_QUESTIONS_PER_TYPE" size="sm" :disabled="store.generating" :aria-label="'第 ' + (index + 1) + ' 大题题目数量'" class="section-count" @update:model-value="store.setSectionCount(section.id, $event ?? 1)" />
          <UTooltip text="调整版式"><UButton icon="i-lucide-columns-2" color="neutral" variant="ghost" size="xs" :disabled="store.generating" :aria-label="'第 ' + (index + 1) + ' 大题版式'" @click="layoutSection = section" /></UTooltip>
        </div>
        <div v-if="section.status === 'loading'" class="section-status" role="status"><UIcon name="i-lucide-loader-circle" class="size-3 animate-spin" />正在生成</div>
        <div v-else-if="section.status === 'error'" class="section-status text-error" role="alert"><span>{{ section.error || '生成失败' }}</span><UButton v-if="section.pendingGeneration" label="查询" color="neutral" variant="link" size="xs" :disabled="store.generating" @click="store.retrySection(section.id, 'recover')" /><UButton label="重试" color="error" variant="link" size="xs" :disabled="store.generating" @click="retryTarget = section" /></div>
        <div v-else-if="section.warn" class="section-status text-warning"><span>{{ section.warn }}</span><UTooltip text="重新生成大题"><UButton icon="i-lucide-refresh-cw" color="warning" variant="ghost" size="xs" :disabled="store.generating" :aria-label="'重新生成第 ' + (index + 1) + ' 大题'" @click="retryTarget = section" /></UTooltip></div>
        <div v-else-if="(section.data?.questions.length || 0) < section.count" class="section-status text-muted">
          待生成 {{ section.count - (section.data?.questions.length || 0) }} 道题
        </div>
      </article>
    </div>
    <UModal :open="!!layoutSection" title="大题版式" @update:open="value => { if (!value) layoutSection = null }">
      <template #body>
        <div v-if="layoutSection" class="field-stack">
          <div class="field-grid">
            <UFormField label="题目分栏"><USelect v-model="layoutSection.layout.qCols" :items="[1, 2, 3, 4, 5]" /></UFormField>
            <UFormField label="选项分栏"><USelect v-model="layoutSection.layout.optCols" :items="[1, 2, 3, 4, 5]" /></UFormField>
            <UFormField label="表格线"><USelect v-model="layoutSection.layout.tableBorder" :items="[{ label: '无', value: 'none' }, { label: '实线', value: 'solid' }, { label: '虚线', value: 'dashed' }]" /></UFormField>
            <UFormField label="字号"><USelect :model-value="layoutSection.layout.fontSize || 'default'" :items="fontSizes" @update:model-value="layoutSection.layout.fontSize = $event === 'default' ? '' : String($event)" /></UFormField>
          </div>
          <USwitch v-model="layoutSection.layout.showNo" label="显示题号" />
        </div>
      </template>
      <template #footer><UButton label="完成" @click="layoutSection = null" /></template>
    </UModal>
    <UModal :open="!!retryTarget" title="重新生成大题" description="新的模型请求可能产生费用，其他大题保持不变；仍在处理的请求不会重复发送。" @update:open="value => { if (!value) retryTarget = null }">
      <template #footer><UButton label="取消" color="neutral" variant="outline" @click="retryTarget = null" /><UButton icon="i-lucide-refresh-cw" label="确认生成" @click="retry" /></template>
    </UModal>
  </div>
</template>

<style scoped>
.section-list { padding: 0 20px 16px; }
.section-items { display: flex; flex-direction: column; gap: 8px; }
.section-item { padding: 10px 12px; border: 1px solid var(--ui-border); border-radius: 6px; background: #fff; }
.section-item:hover { border-color: #c5d5ce; }
.section-topline { display: flex; align-items: center; gap: 7px; }
.section-topline h3 { min-width: 0; flex: 1; margin: 0; font-size: 14px; font-weight: 600; overflow-wrap: anywhere; }
.section-index { font-size: 12px; font-weight: 600; color: #82918b; font-variant-numeric: tabular-nums; }
.drag-handle { display: flex; align-items: center; padding: 0; border: 0; background: transparent; color: #b2bdc4; cursor: grab; flex: none; }
.drag-handle:active { cursor: grabbing; }
.section-controls { display: flex; align-items: center; gap: 8px; padding-top: 10px; }
.section-count { margin-left: auto; width: 104px; }
.section-status { font-size: 12px; padding-top: 8px; display: flex; gap: 5px; align-items: center; }
.section-status > span { flex: 1; min-width: 0; overflow-wrap: anywhere; }
@media (max-width: 620px) {
  .section-topline button, .section-controls button, .section-status button { min-height: 44px; min-width: 44px; }
  .section-item { padding: 8px; }
}
</style>
