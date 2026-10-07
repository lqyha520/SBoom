<script setup lang="ts">
import { useRevisionConflict } from '../revision-conflict'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { catalogDetail, type CatalogDetail, type CatalogPaper } from '../catalog'
import { assignTags, getTags, tagKinds, type CatalogTag, type TagKind } from '../growth'
const props = defineProps<{ open: boolean; target: CatalogPaper | null; adminId: number }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const detail = ref<CatalogDetail | null>(null), tags = ref<CatalogTag[]>([]), selected = ref<string[]>([])
const error = ref(''), notice = ref(''), busy = ref(false), loading = ref(false), knowledgeQuery = ref('')
const recovery = useRevisionConflict(detail, catalogDetail, error)
let sequence = 0
const knowledge = computed(() => tags.value.filter(item => item.kind === 'knowledge' && item.name.toLowerCase().includes(knowledgeQuery.value.toLowerCase())))
function options(kind: TagKind) { return [{ value: 'none', label: '未设置' }, ...tags.value.filter(item => item.kind === kind).map(item => ({ value: item.id, label: item.name + (item.is_visible ? '' : '（隐藏）') }))] }
function selectedOne(kind: TagKind) { return selected.value.find(id => tags.value.some(tag => tag.id === id && tag.kind === kind)) || 'none' }
function selectOne(kind: TagKind, value: string) { selected.value = selected.value.filter(id => !tags.value.some(tag => tag.id === id && tag.kind === kind)); if (value !== 'none') selected.value.push(value) }
function toggleKnowledge(id: string, checked: boolean) { selected.value = selected.value.filter(item => item !== id); if (checked) selected.value.push(id) }
async function load() {
  if (!props.open || !props.target) return
  const current = ++sequence; loading.value = true; error.value = ''
  try { const [paper, labels] = await Promise.all([catalogDetail(props.target.id), getTags()]); if (current !== sequence) return; detail.value = paper; tags.value = labels.items; selected.value = paper.tags?.map(item => item.id) || [] }
  catch (cause) { if (current === sequence) error.value = cause instanceof Error ? cause.message : '加载失败' }
  finally { if (current === sequence) loading.value = false }
}
watch(() => props.open, value => { sequence++; detail.value = null; tags.value = []; selected.value = []; notice.value = ''; knowledgeQuery.value = ''; if (value) void load() })
onBeforeUnmount(() => { sequence++ })
async function save() {
  if (!detail.value || busy.value || loading.value) return
  const current = sequence; busy.value = true; error.value = ''; notice.value = ''
  try {
    const result = await assignTags(props.adminId, detail.value.id, detail.value.revision, selected.value)
    if (current !== sequence) return
    detail.value.revision = result.revision; detail.value.tags = result.tags; notice.value = '资料标签已保存'
    emit('saved')
  } catch (cause) { recovery.capture(cause); if (current === sequence) error.value = cause instanceof Error ? cause.message : '保存失败' }
  finally { busy.value = false }
}
</script>
<template>
  <UModal :open="open" :title="'教学标签 · ' + (target?.title || '')" :dismissible="!busy" :close="!busy" @update:open="!$event && emit('close')"><template #body><div class="field-stack"><UButton v-if="recovery.conflict.value" label="载入最新并保留我的修改" :loading="recovery.recovering.value" @click="recovery.reload" /><UAlert v-if="error" :title="error" color="error" /><UAlert v-if="notice" :title="notice" color="success" /><p v-if="loading">正在读取资料</p><template v-if="detail"><div class="tag-single-grid"><UFormField v-for="kind in tagKinds.filter(item => item.value !== 'knowledge')" :key="kind.value" :label="kind.label"><USelect :model-value="selectedOne(kind.value)" :items="options(kind.value)" :disabled="busy" class="w-full" @update:model-value="selectOne(kind.value, String($event))" /></UFormField></div><UFormField label="知识点（最多 20 个）"><UInput v-model="knowledgeQuery" placeholder="搜索知识点" class="w-full mb-3" /><div class="knowledge-options"><UCheckbox v-for="tag in knowledge" :key="tag.id" :label="tag.name + (tag.is_visible ? '' : '（隐藏）')" :model-value="selected.includes(tag.id)" :disabled="busy || (!selected.includes(tag.id) && selected.filter(id => tags.some(tag => tag.id === id && tag.kind === 'knowledge')).length >= 20)" @update:model-value="toggleKnowledge(tag.id, !!$event)" /><p v-if="!knowledge.length" class="text-sm text-muted">暂无匹配知识点，请先在标签管理中添加。</p></div></UFormField><UButton label="保存资料标签" :loading="busy" :disabled="busy || loading" @click="save" /></template></div></template><template #footer><UButton label="刷新资料" color="neutral" variant="outline" :disabled="busy" @click="load" /><UButton label="完成" :disabled="busy" @click="emit('close')" /></template></UModal>
</template>
<style scoped>.tag-single-grid { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px; }.knowledge-options { display:grid;gap:12px;max-height:180px;overflow:auto; }@media(max-width:600px){.tag-single-grid{grid-template-columns:1fr}}</style>
