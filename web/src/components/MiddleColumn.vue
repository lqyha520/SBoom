<script setup lang="ts">
import { computed, ref } from 'vue'
import { useExamStore } from '../stores/exam'
import { TEMPLATES } from '../constants'
import TypePicker from './TypePicker.vue'
import SectionList from './SectionList.vue'
import PaperTemplateDialog from './PaperTemplateDialog.vue'
import CustomTypesDialog from './CustomTypesDialog.vue'
import RecoveryActions from './RecoveryActions.vue'

const store = useExamStore()
const emit = defineEmits<{ 'open-templates': []; preview: [] }>()
const showTemplate = ref(false)
const showCustom = ref(false)
const typesOpen = ref(true)
const templateItems = TEMPLATES.map(t => ({ label: t.name, value: t.id }))
const missingConditions = computed(() => [
  !store.grade && '年级', !store.subject && '科目', !store.keyword.trim() && '知识点',
].filter(Boolean).join('、'))
function pickTemplate(id: string) {
  store.setTemplate(id)
  if (id === 'custom') showTemplate.value = true
}
</script>

<template>
  <section class="workspace-panel structure-panel" aria-labelledby="structure-title">
    <div class="panel-heading">
      <h2 id="structure-title"><UIcon name="i-lucide-list-tree" class="size-4" />试卷结构</h2>
      <UBadge color="neutral" variant="soft" size="xs">02</UBadge>
    </div>
    <div class="builder-scroll">
      <div class="paper-fields field-stack">
        <UFormField label="试卷标题"><UInput :model-value="store.title" maxlength="40" placeholder="未命名试卷" :disabled="store.generating" @update:model-value="store.setTitle(String($event))" /></UFormField>
        <UFormField label="卷面模板">
          <div class="flex items-center gap-2">
            <USelect :model-value="store.templateId" :items="templateItems" class="flex-1" :disabled="store.generating" @update:model-value="pickTemplate(String($event))" />
            <UTooltip v-if="store.templateId === 'custom'" text="配置模板"><UButton icon="i-lucide-settings-2" color="neutral" variant="outline" aria-label="配置模板" @click="showTemplate = true" /></UTooltip>
          </div>
        </UFormField>
      </div>
      <UCollapsible v-model:open="typesOpen">
        <button class="builder-section-heading" :aria-expanded="typesOpen"><span>添加题型</span><UIcon :name="typesOpen ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'" class="size-3.5" /></button>
        <template #content><TypePicker @custom="showCustom = true" /></template>
      </UCollapsible>
      <div class="divider"></div>
      <div class="builder-section-heading">
        <span>卷面内容 <span class="section-total">{{ store.sections.length }}</span></span>
        <UTooltip text="从我的模板添加"><UButton icon="i-lucide-folder-open" color="neutral" variant="ghost" size="xs" aria-label="从我的模板添加" @click="emit('open-templates')" /></UTooltip>
      </div>
      <SectionList />
    </div>
    <div class="generation-footer">
      <div class="row-between mb-3">
        <label for="paper-count" class="text-xs text-toned">生成份数</label>
        <UInputNumber id="paper-count" :model-value="store.paperCount" :min="1" :max="20" :disabled="store.generating" size="sm" class="w-28" @update:model-value="store.paperCount = $event ?? 1" />
      </div>
      <div class="row-between mb-4">
        <UCheckbox v-model="store.addDayLabel" label="按天编号" :disabled="store.generating" size="sm" />
        <span class="text-xs text-muted numeric">{{ store.totalQuestions }} 题 / 份</span>
      </div>
      <p v-if="store.generateError" role="alert" class="mb-3 text-xs text-error break-words">{{ store.generateError }}</p>
      <p v-else-if="store.generationIssue" role="alert" class="mb-3 text-xs text-warning">{{ store.generationIssue }}</p>
      <p v-else-if="missingConditions" class="mb-3 text-xs text-muted">待补充：{{ missingConditions }}</p>
      <RecoveryActions />
      <p v-if="store.usage" class="mb-2 text-xs text-muted numeric">24 小时请求 {{ store.usage.requests }} / {{ store.usage.daily_limit }}</p>
      <div class="flex gap-2">
        <UButton icon="i-lucide-sparkles" :label="store.generating ? store.generateProgress || '正在生成试卷' : '生成试卷'" :loading="store.generating" :disabled="!store.canGenerate" block class="min-h-10 whitespace-normal" @click="store.generate()" />
        <UButton class="mobile-preview" icon="i-lucide-eye" color="neutral" variant="outline" aria-label="卷面预览" @click="emit('preview')" />
      </div>
    </div>
    <PaperTemplateDialog v-model:open="showTemplate" />
    <CustomTypesDialog v-model:open="showCustom" />
  </section>
</template>

<style scoped>
.builder-scroll { flex: 1; min-height: 0; overflow-y: auto; }
.paper-fields { padding: 20px; border-bottom: 1px solid var(--ui-border-muted); }
.builder-section-heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; width: 100%; min-height: 48px; padding: 10px 20px; font-size: 12px; font-weight: 600; color: var(--ui-text-toned); background: transparent; border: 0; text-align: left; }
.section-total { font-weight: 500; font-size: 11px; color: var(--ui-text-muted); margin-left: 4px; }
.generation-footer { flex: none; padding: 16px 20px; border-top: 1px solid var(--ui-border); background: #fcfdfd; }
.mobile-preview { display: none; }
@media (max-width: 1023px) { .mobile-preview { display: inline-flex; } }
</style>
