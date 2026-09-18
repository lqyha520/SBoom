<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useExamStore } from '../stores/exam'
import type { PaperData } from '../types'
import PaperView from './PaperView.vue'
import FormatBar from './FormatBar.vue'
import ZoomControl from './ZoomControl.vue'
import { useFitZoom } from '../useFitZoom'

defineEmits<{ 'open-settings': [] }>()
const store = useExamStore()
const previewPaper = computed<PaperData>(() => ({
  grade: store.grade, subject: store.subject, keyword: store.keyword, title: store.title,
  titleHtml: store.titleHtml || undefined, difficulty: store.difficulty,
  sections: store.sections.map(s => ({ type: s.type, name: s.name, data: s.data || { questions: [] }, layout: s.layout, _sid: s.id })),
  hiddenElements: [...store.hiddenElements],
}))
const previewBox = ref<HTMLElement | null>(null)
const paperViewEl = ref<InstanceType<typeof PaperView> | null>(null)
const { zoom, manual, setManual } = useFitZoom(previewBox)
const layoutMode = computed({ get: () => store.layoutMode, set: value => { store.layoutMode = value } })
onBeforeUnmount(() => { store.layoutMode = false })
function toggleLayout() {
  if (!layoutMode.value) store.recordEdit()
  if (layoutMode.value) {
    const sections = paperViewEl.value?.applyLayout()
    if (sections) store.syncSections(sections)
  }
  layoutMode.value = !layoutMode.value
}
function cancelLayout() {
  layoutMode.value = false
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
        <UTooltip text="卷面设置"><UButton icon="i-lucide-settings-2" color="neutral" variant="ghost" size="xs" aria-label="预览卷面设置" @click="$emit('open-settings')" /></UTooltip>
      </div>
    </div>
    <div class="preview-toolbar no-print">
      <FormatBar />
      <div class="actions-row">
        <template v-if="!layoutMode">
          <UTooltip text="排版模式"><UButton icon="i-lucide-move" color="neutral" variant="ghost" aria-label="排版模式" :disabled="!store.sections.length" class="icon-tool" @click="toggleLayout" /></UTooltip>
          <div class="toolbar-divider"></div>
          <UButton icon="i-lucide-bookmark-plus" label="保存模板" color="neutral" variant="outline" size="xs" :disabled="!store.sections.length" @click="openSave" />
        </template>
        <template v-else>
          <UButton label="取消" color="neutral" variant="ghost" size="xs" @click="cancelLayout" />
          <UButton label="完成排版" icon="i-lucide-check" size="xs" @click="toggleLayout" />
        </template>
      </div>
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
.save-notice { position: absolute; right: 20px; bottom: 50px; width: min(320px, calc(100vw - 40px)); z-index: 20; }
</style>
