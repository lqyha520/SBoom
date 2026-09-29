<script setup lang="ts">
import { useRevisionConflict } from '../revision-conflict'
import { computed, ref, watch } from 'vue'
import { catalogDetail, catalogSources, type CatalogPaper, type CatalogSource, type CatalogDetail } from '../catalog'
import { reviseCatalog } from '../experience'
const props = defineProps<{ open: boolean; target: CatalogPaper | null; adminId: number }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const sources = ref<CatalogSource[]>([])
const detail = ref<CatalogDetail | null>(null)
const source = ref('')
const q = ref('')
const note = ref('')
const confirmed = ref(false)
const busy = ref(false)
const loading = ref(false)
const more = ref(false)
const error = ref('')
const recovery = useRevisionConflict(detail, catalogDetail, error)
let sequence = 0
const choices = computed(() => sources.value.map(item => ({ value: item.id, label: item.title + ' · ' + item.grade + ' · ' + (item.file_status === 'ready' ? '文件就绪' : '文件未完成'), disabled: item.file_status !== 'ready' })))
async function search(append = false) {
  const current = ++sequence; loading.value = true; error.value = ''
  try { const data = await catalogSources(q.value.trim(), append ? sources.value.length : 0); if (current === sequence) { sources.value = append ? [...sources.value, ...data.items] : data.items; more.value = data.has_more } }
  catch (cause) { if (current === sequence) error.value = cause instanceof Error ? cause.message : '加载失败' }
  finally { if (current === sequence) loading.value = false }
}
watch(() => props.open, async value => {
  sequence++; source.value = ''; note.value = ''; confirmed.value = false; error.value = ''; sources.value = []; q.value = ''; detail.value = null
  if (value && props.target) { void search(); const id = props.target.id; try { const result = await catalogDetail(id); if (props.open && props.target?.id === id) detail.value = result } catch (cause) { error.value = cause instanceof Error ? cause.message : '读取版本失败' } }
})
async function save() {
  if (busy.value || !props.target || !source.value) return
  busy.value = true; error.value = ''
  try { await reviseCatalog(props.adminId, detail.value || props.target, source.value, note.value.trim(), confirmed.value); emit('saved'); emit('close') }
  catch (cause) { recovery.capture(cause); error.value = cause instanceof Error ? cause.message : '更新失败' }
  finally { busy.value = false }
}
</script>
<template><UModal :open="open" :title="'修订资料 · ' + (target?.title || '')" :dismissible="!busy" :close="!busy" @update:open="!$event && emit('close')"><template #body><form id="catalog-revision" class="field-stack" @submit.prevent="save"><p>先在出题工作台保存新的原稿与 PDF，再在这里更新。公共条目、收藏与下载记录会保留；用户之后获取的是新版本。</p><div class="actions-row"><UInput v-model="q" placeholder="搜索自己的新归档" @keydown.enter.prevent="search()" /><UButton label="搜索" :loading="loading" @click="search()" /></div><UFormField label="修订稿" required><USelect v-model="source" :items="choices" placeholder="选择文件就绪的新归档" class="w-full" /><p v-if="!loading && !sources.length" class="text-sm text-muted mt-2">没有符合条件的新归档。请调整搜索条件，或先在出题工作台另存修订稿。</p></UFormField><UButton v-if="more" label="更多归档" variant="outline" :loading="loading" @click="search(true)" /><UFormField label="向用户说明本次更新" required><UTextarea v-model="note" minlength="2" maxlength="1000" required :rows="4" class="w-full" placeholder="例如：修正第 3 页第 5 题答案，补充解析" /></UFormField><UCheckbox v-if="target?.status === 'published'" v-model="confirmed" label="已检查新原稿及题型权限，确认更新已发布资料" /><UButton v-if="recovery.conflict.value" label="载入最新并保留我的修改" :loading="recovery.recovering.value" @click="recovery.reload" /><UAlert v-if="error" :title="error" color="error" /><div v-if="detail?.versions?.length"><h3>版本记录</h3><p v-for="version in detail.versions" :key="version.release_number" class="version-note">第 {{ version.release_number }} 版 · {{ new Date(version.created_at * 1000).toLocaleDateString() }}<br />{{ version.note || '首次发布' }}</p></div></form></template><template #footer><UButton label="取消" color="neutral" :disabled="busy" @click="emit('close')" /><UButton label="保存修订版" type="submit" form="catalog-revision" :loading="busy" :disabled="!source || note.trim().length < 2 || (target?.status === 'published' && !confirmed)" /></template></UModal></template>
<style scoped>.version-note { font-size:13px;line-height:1.7;margin-top:12px;white-space:pre-wrap; }</style>
