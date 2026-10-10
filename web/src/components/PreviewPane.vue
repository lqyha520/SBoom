<script setup lang="ts">
import { computed, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { useExamStore } from '../stores/exam'
import type { PaperData } from '../types'
import { previewSampleData } from '../preview-samples'
import PaperView from './PaperView.vue'
import PaperEditToolbar from './PaperEditToolbar.vue'
import ZoomControl from './ZoomControl.vue'
import { useFitZoom } from '../useFitZoom'

defineEmits<{ 'open-settings': [] }>()
const store = useExamStore()
const previewSections = computed(() => store.sections.map(s => {
  const data = s.data || { questions: [] }
  const realQuestions = data.questions || []
  return {
    type: s.type,
    name: s.name,
    data: realQuestions.length
      ? data
      : { ...previewSampleData(s.type, s.count, s.id), missing_count: data.missing_count, topic: data.topic },
    layout: s.layout,
    _sid: s.id,
  }
}))
const hasFormatSamples = computed(() => store.sections.some(s => !(s.data?.questions?.length)))
const previewPaper = computed<PaperData>(() => ({
  grade: store.grade, subject: store.subject, keyword: store.keyword, title: store.title,
  titleHtml: store.titleHtml || undefined, difficulty: store.difficulty,
  sections: previewSections.value,
  hiddenElements: [...store.hiddenElements],
}))
const previewBox = ref<HTMLElement | null>(null)
const paperViewEl = ref<InstanceType<typeof PaperView> | null>(null)
const { zoom, manual, setManual } = useFitZoom(previewBox)
const layoutMode = computed({ get: () => store.layoutMode, set: value => { store.layoutMode = value } })
function leaveLayout() { if (store.layoutMode) store.finishLayout(true) }
onBeforeUnmount(leaveLayout)
onDeactivated(leaveLayout)
function toggleLayout() {
  if (!layoutMode.value) { store.beginLayout(); return }
  if (layoutMode.value) {
    const sections = paperViewEl.value?.applyLayout()
    if (sections) store.syncSections(sections)
  }
  store.finishLayout()
}
function cancelLayout() {
  store.finishLayout(true)
  paperViewEl.value?.repaginate()
}
const saveOpen = ref(false)
const saveName = ref('')
const overwrite = ref(false)
const saved = ref(false)
const saving = ref(false)
const saveError = ref('')
const saveMessage = ref('')
const saveSynced = ref(false)
const exists = computed(() => store.myTemplates.some(t => t.name === saveName.value.trim()))
watch(saveName, () => { overwrite.value = false })
function openSave() {
  saveName.value = store.title.slice(0, 20)
  overwrite.value = false
  saveError.value = ''
  saveOpen.value = true
}
async function save() {
  const name = saveName.value.trim()
  if (saving.value || !name || (exists.value && !overwrite.value)) return
  saving.value = true
  saveError.value = ''
  try {
    const result = await store.saveMyTemplate(name)
    if (!result.local && !result.synced) {
      saveError.value = '保存失败，请检查网络或浏览器存储空间后重试'
      return
    }
    saveSynced.value = result.synced
    saveMessage.value = result.synced ? '模板已保存并同步' : '已保存到本机；' + (store.myTemplates.find(template => template.name === name)?._syncError || '等待同步')
    saveOpen.value = false
    saved.value = true
  } catch (e: unknown) { saveError.value = e instanceof Error ? e.message : '模板保存失败' }
  finally { saving.value = false }
}
function onTitleEdited(title: string, html: string) { store.title = title; store.titleHtml = html }
</script>

<template>
  <section class="workspace-panel preview-panel" aria-labelledby="preview-title">
    <div class="panel-heading">
      <h2 id="preview-title"><UIcon name="i-lucide-file-text" class="size-4" />卷面预览</h2>
      <div class="actions-row">
        <UBadge color="neutral" variant="soft" size="xs">草稿</UBadge>
        <UTooltip text="卷面设置"><UButton icon="i-lucide-settings-2" color="neutral" variant="ghost" size="xs" aria-label="预览卷面设置" :disabled="store.layoutMode" @click="$emit('open-settings')" /></UTooltip>
      </div>
    </div>
    <PaperEditToolbar :layout-mode="layoutMode" :disabled="store.generating" :can-layout="!!store.sections.length" save-template @settings="$emit('open-settings')" @layout="toggleLayout" @cancel="cancelLayout" @save="openSave" />
    <div v-if="hasFormatSamples" class="preview-hint" role="status">
      <UIcon name="i-lucide-info" class="size-4" />
      <span>当前显示的是题型格式示例，点击生成后会替换为模型生成的正式题目。</span>
    </div>
    <div ref="previewBox" class="preview-fill">
      <PaperView ref="paperViewEl" :paper="previewPaper" :template="store.template" :style="store.style" :editable="true" :layout-mode="layoutMode" :zoom="zoom"
        @toggle-element="store.toggleHiddenElement($event)" @title-edited="onTitleEdited"
        @title-offset="(value: number) => store.setStyle({ titleOffsetY: value })"
        @layout-updated="(id, layout) => store.syncSectionLayout(id, layout)" />
    </div>
    <div class="preview-footer no-print">
      <span>A4 <span class="mx-1 text-dimmed">/</span> 210 × 297 mm</span>
      <ZoomControl :zoom="zoom" :manual="manual" @change="setManual" />
    </div>
    <UModal v-model:open="saveOpen" title="保存模板" :dismissible="!saving" :close="!saving">
      <template #body>
        <form id="save-template-form" class="field-stack" @submit.prevent="save">
          <UFormField label="模板名称" required><UInput v-model="saveName" maxlength="20" placeholder="例如：三年级口算练习" autofocus /></UFormField>
          <UAlert v-if="exists" color="warning" variant="soft" title="已存在同名模板" />
          <UCheckbox v-if="exists" v-model="overwrite" label="覆盖已有模板" />
          <UAlert v-if="saveError" :title="saveError" color="error" variant="soft" role="alert" />
        </form>
      </template>
      <template #footer><UButton color="neutral" variant="outline" label="取消" :disabled="saving" @click="saveOpen = false" /><UButton type="submit" form="save-template-form" label="保存模板" :loading="saving" :disabled="saving || !saveName.trim() || (exists && !overwrite)" /></template>
    </UModal>
    <UAlert v-if="saved" class="save-notice no-print" :color="saveSynced ? 'success' : 'warning'" variant="soft" :title="saveMessage" close @update:open="saved = false" />
  </section>
</template>

<style scoped>
.preview-hint {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 8px 16px 0;
  padding: 7px 9px;
  border: 1px solid var(--ui-color-primary-200, #bfdbfe);
  border-radius: 5px;
  color: var(--ui-color-primary-700, #1d4ed8);
  background: var(--ui-color-primary-50, #eff6ff);
  font-size: 12px;
  line-height: 1.5;
}
.save-notice { position: absolute; right: 20px; bottom: 50px; width: min(320px, calc(100vw - 40px)); z-index: 20; }
</style>
