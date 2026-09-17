<script setup lang="ts">
import { ref, watch } from 'vue'
import type { CatalogPaper } from '../catalog'
import { batchCatalog } from '../experience'
import { getTags, tagKinds, type CatalogTag, type TagKind } from '../growth'
const props = defineProps<{ open: boolean; adminId: number; items: CatalogPaper[]; categories: { value: string; label: string }[] }>()
const emit = defineEmits<{ close: []; saved: [count: number] }>()
const action = ref('category')
const category = ref('')
const viewAccess = ref('inherit')
const downloadAccess = ref('inherit')
const confirmed = ref(false)
const busy = ref(false)
const error = ref('')
const policies = [{ label: '继承题型权限', value: 'inherit' }, { label: '普通用户与 VIP', value: 'free' }, { label: '仅 VIP', value: 'vip' }]
const tags = ref<CatalogTag[]>([])
type SingleTagKind = Exclude<TagKind, 'knowledge'>
const singleKinds = tagKinds.filter((item): item is { value: SingleTagKind; label: string } => item.value !== 'knowledge')
const singles = ref<Record<SingleTagKind, string>>({ textbook: '', term: '', unit: '' })
const knowledgePicked = ref<string[]>([])
const knowledgeQuery = ref('')
const knowledge = ref<CatalogTag[]>([])
watch(() => props.open, () => { action.value = 'category'; category.value = ''; viewAccess.value = 'inherit'; downloadAccess.value = 'inherit'; confirmed.value = false; error.value = ''; singles.value = { textbook: '', term: '', unit: '' }; knowledgePicked.value = []; knowledgeQuery.value = '' })
watch(action, value => { confirmed.value = false; if (value === 'tags' && !tags.value.length) { getTags().then(result => { tags.value = result.items; knowledge.value = result.items.filter(item => item.kind === 'knowledge') }).catch(() => {}) } })
watch(knowledgeQuery, value => { const query = value.trim().toLowerCase(); knowledge.value = tags.value.filter(item => item.kind === 'knowledge' && item.name.toLowerCase().includes(query)) })
watch(viewAccess, value => { if (value === 'vip') downloadAccess.value = 'vip' })
function tagOptions(kind: TagKind) { return [{ value: '', label: '不修改' }, ...tags.value.filter(item => item.kind === kind).map(item => ({ value: item.id, label: item.name + (item.is_visible ? '' : '（隐藏）') }))] }
function tagIds(): string[] {
  const ids: string[] = []
  for (const { value: kind } of singleKinds) if (singles.value[kind]) ids.push(singles.value[kind])
  return [...ids, ...knowledgePicked.value]
}
async function save() {
  if (busy.value || !props.items.length) return
  if (action.value === 'published' && !confirmed.value) { error.value = '请先确认发布'; return }
  if (action.value === 'category' && !category.value) { error.value = '请选择目标分类'; return }
  if (action.value === 'tags' && !tagIds().length) { error.value = '请至少选择一个要设置的标签'; return }
  busy.value = true; error.value = ''
  try { const result = await batchCatalog(props.adminId, props.items, { action: action.value, category_id: category.value, view_access: viewAccess.value, download_access: downloadAccess.value, confirm_publication: confirmed.value, tag_ids: tagIds() }); emit('saved', result.updated); emit('close') }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '批量操作失败' }
  finally { busy.value = false }
}
</script>
<template><UModal :open="open" title="批量管理资料" :dismissible="!busy" :close="!busy" :ui="{ content: 'max-w-3xl' }" @update:open="!$event && emit('close')"><template #body><form id="batch-catalog" class="field-stack" @submit.prevent="save"><p>已选择 {{ items.length }} 份资料</p><USelect v-model="action" aria-label="批量操作类型" :items="[{ label: '修改分类', value: 'category' }, { label: '批量打标签', value: 'tags' }, { label: '发布', value: 'published' }, { label: '下架', value: 'withdrawn' }, { label: '修改访问权限', value: 'access' }]" /><UFormField v-if="action === 'category'" label="目标分类"><USelect v-model="category" :items="categories" :disabled="!categories.length" placeholder="选择分类" /><p v-if="!categories.length" class="text-sm text-muted mt-2">暂无可用分类，请先到「分类管理」创建并展示一个分类。</p></UFormField><template v-if="action === 'tags'"><div class="tag-single-grid"><UFormField v-for="kind in singleKinds" :key="kind.value" :label="kind.label + '（不选则保留原值）'"><USelect v-model="singles[kind.value]" :items="tagOptions(kind.value)" class="w-full" /></UFormField></div><UFormField label="知识点（追加到所选资料，合并后每份最多 20 个）"><UInput v-model="knowledgeQuery" placeholder="搜索知识点" class="w-full mb-3" /><div class="knowledge-options"><UCheckbox v-for="tag in knowledge" :key="tag.id" :label="tag.name + (tag.is_visible ? '' : '（隐藏）')" :model-value="knowledgePicked.includes(tag.id)" :disabled="busy" @update:model-value="value => { knowledgePicked = value ? [...knowledgePicked, tag.id] : knowledgePicked.filter(id => id !== tag.id) }" /><p v-if="!knowledge.length" class="text-sm text-muted">暂无匹配知识点，请先在「教材与知识点」中添加。</p></div></UFormField><p class="text-sm text-muted">单选类标签会覆盖所选资料的原有同类标签；知识点在原有基础上追加。任一资料合并后超限，整批取消。</p></template><template v-if="action === 'access'"><UFormField label="原稿观看"><USelect v-model="viewAccess" :items="policies" /></UFormField><UFormField label="PDF 下载"><USelect v-model="downloadAccess" :items="policies" :disabled="viewAccess === 'vip'" /></UFormField></template><UCheckbox v-if="action === 'published'" v-model="confirmed" label="已核对所选资料原稿与普通用户/VIP 权限，确认发布" /><p class="text-sm text-muted">若有资料被其他管理员修改，本批操作会整体取消；发布操作还会检查文件是否就绪。</p><UAlert v-if="error" :title="error" color="error" /></form></template><template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="busy" @click="emit('close')" /><UButton label="应用到所选资料" type="submit" form="batch-catalog" :loading="busy" :disabled="!items.length || (action === 'published' && !confirmed) || (action === 'category' && !category)" /></template></UModal></template>
<style scoped>.tag-single-grid { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px; }.knowledge-options { display:grid;gap:12px;max-height:180px;overflow:auto; }@media(max-width:600px){.tag-single-grid{grid-template-columns:1fr}}</style>
