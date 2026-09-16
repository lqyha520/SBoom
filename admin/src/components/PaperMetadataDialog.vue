<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { catalogDetail, type CatalogDetail, type CatalogPaper } from '../catalog'
import { assignTags, editionSources, getTags, saveEdition, tagKinds, type CatalogTag, type EditionSource, type TagKind } from '../growth'
const props = defineProps<{ open: boolean; target: CatalogPaper | null; adminId: number }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const detail = ref<CatalogDetail | null>(null), tags = ref<CatalogTag[]>([]), selected = ref<string[]>([]), sources = ref<EditionSource[]>([])
const error = ref(''), notice = ref(''), busy = ref(false), loading = ref(false), q = ref(''), knowledgeQuery = ref(''), editionKind = ref<'student' | 'answers'>('answers'), sourceId = ref('none'), confirmed = ref(false)
let sequence = 0
const knowledge = computed(() => tags.value.filter(item => item.kind === 'knowledge' && item.name.toLowerCase().includes(knowledgeQuery.value.toLowerCase())))
const sourceChoices = computed(() => [{ value: 'none', label: '不关联额外文件' }, ...sources.value.filter(item => editionKind.value === 'student' ? item.mode === 'student' : ['answersOnly', 'withAnswers'].includes(item.mode)).map(item => ({ value: item.id, label: `${item.title} · v${item.version} · ${item.mode === 'student' ? '练习版' : item.mode === 'answersOnly' ? '答案版' : '习题与答案版'}` }))])
function options(kind: TagKind) { return [{ value: 'none', label: '未设置' }, ...tags.value.filter(item => item.kind === kind).map(item => ({ value: item.id, label: item.name + (item.is_visible ? '' : '（隐藏）') }))] }
function selectedOne(kind: TagKind) { return selected.value.find(id => tags.value.some(tag => tag.id === id && tag.kind === kind)) || 'none' }
function selectOne(kind: TagKind, value: string) { selected.value = selected.value.filter(id => !tags.value.some(tag => tag.id === id && tag.kind === kind)); if (value !== 'none') selected.value.push(value) }
function toggleKnowledge(id: string, checked: boolean) { selected.value = selected.value.filter(item => item !== id); if (checked) selected.value.push(id) }
function setEditionSelection() { sourceId.value = detail.value?.editions?.find(item => item.kind === editionKind.value)?.paper_id || 'none'; confirmed.value = false }
async function load() {
  if (!props.open || !props.target) return
  const current = ++sequence; loading.value = true; error.value = ''
  try { const [paper, labels, alternatives] = await Promise.all([catalogDetail(props.target.id), getTags(), editionSources(props.target.id, q.value)]); if (current !== sequence) return; detail.value = paper; tags.value = labels.items; selected.value = paper.tags?.map(item => item.id) || []; sources.value = alternatives.items; setEditionSelection() }
  catch (cause) { if (current === sequence) error.value = cause instanceof Error ? cause.message : '加载失败' }
  finally { if (current === sequence) loading.value = false }
}
watch(() => props.open, value => { sequence++; detail.value = null; tags.value = []; sources.value = []; selected.value = []; notice.value = ''; q.value = ''; knowledgeQuery.value = ''; if (value) void load() })
watch(editionKind, setEditionSelection)
onBeforeUnmount(() => { sequence++ })
async function save(kind: 'tags' | 'edition') {
  if (!detail.value || busy.value || loading.value) return
  const current = sequence; busy.value = true; error.value = ''; notice.value = ''
  try {
    if (kind === 'tags') { const result = await assignTags(props.adminId, detail.value.id, detail.value.revision, selected.value); if (current !== sequence) return; detail.value.revision = result.revision; detail.value.tags = result.tags; notice.value = '资料标签已保存' }
    else { const result = await saveEdition(props.adminId, detail.value.id, { revision: detail.value.revision, kind: editionKind.value, paper_id: sourceId.value === 'none' ? null : sourceId.value, confirm_publication: confirmed.value }); if (current !== sequence) return; detail.value.revision = result.revision; detail.value.editions = result.editions; confirmed.value = false; notice.value = '打印版本已保存' }
    emit('saved')
  } catch (cause) { if (current === sequence) error.value = cause instanceof Error ? cause.message : '保存失败' }
  finally { busy.value = false }
}
</script>
<template>
  <UModal :open="open" :title="'标签与打印 · ' + (target?.title || '')" :dismissible="!busy" :close="!busy" :ui="{ content: 'max-w-3xl' }" @update:open="!$event && emit('close')"><template #body><div class="field-stack"><UAlert v-if="error" :title="error" color="error" /><UAlert v-if="notice" :title="notice" color="success" /><p v-if="loading">正在读取资料</p><template v-if="detail"><h3 class="font-semibold">教学标签</h3><div class="tag-single-grid"><UFormField v-for="kind in tagKinds.filter(item => item.value !== 'knowledge')" :key="kind.value" :label="kind.label"><USelect :model-value="selectedOne(kind.value)" :items="options(kind.value)" :disabled="busy" class="w-full" @update:model-value="selectOne(kind.value, String($event))" /></UFormField></div><UFormField label="知识点（最多 20 个）"><UInput v-model="knowledgeQuery" placeholder="搜索知识点" class="w-full mb-3" /><div class="knowledge-options"><UCheckbox v-for="tag in knowledge" :key="tag.id" :label="tag.name + (tag.is_visible ? '' : '（隐藏）')" :model-value="selected.includes(tag.id)" :disabled="busy || (!selected.includes(tag.id) && selected.filter(id => tags.some(tag => tag.id === id && tag.kind === 'knowledge')).length >= 20)" @update:model-value="toggleKnowledge(tag.id, !!$event)" /><p v-if="!knowledge.length" class="text-sm text-muted">暂无匹配知识点，请先在标签管理中添加。</p></div></UFormField><UButton label="保存资料标签" :loading="busy" :disabled="busy || loading" @click="save('tags')" />
      <div class="edition-section field-stack"><h3 class="font-semibold">练习版与答案版</h3><p class="text-sm text-muted">在工作台为同一份资料保存练习版与答案版 PDF，再选择对应文件。只有题目内容一致、导出模式匹配的归档可以关联。</p><div v-for="edition in detail.editions || []" :key="edition.kind" class="actions-row"><span class="text-sm">{{ edition.label }}{{ edition.kind === 'original' ? '（当前原稿）' : '' }}</span><UButton v-if="edition.url" :href="edition.url" label="查看 PDF" variant="link" size="xs" /></div><UFormField label="要配置的版本"><USelect v-model="editionKind" :items="[{ value: 'student', label: '练习版' }, { value: 'answers', label: '答案解析版' }]" :disabled="busy" class="w-full" /></UFormField><div class="actions-row"><UInput v-model="q" placeholder="搜索匹配的归档" :disabled="busy" @keydown.enter.prevent="load" /><UButton label="查找文件" variant="outline" :disabled="busy" :loading="loading" @click="load" /></div><USelect v-model="sourceId" :items="sourceChoices" :disabled="busy || loading" class="w-full" aria-label="关联打印文件" /><p class="text-sm text-muted">从最近 500 份同年级、学科与题量的归档中匹配，最多显示 50 份，可搜索缩小范围。更换修订稿后需重新关联。</p><UCheckbox v-if="detail.status === 'published'" v-model="confirmed" label="已核对文件和现有会员权限，确认更新已发布的打印版本" :disabled="busy" /><UButton label="保存打印版本" :disabled="busy || loading || (detail.status === 'published' && !confirmed)" :loading="busy" @click="save('edition')" /></div></template></div></template><template #footer><UButton label="刷新资料" color="neutral" variant="outline" :disabled="busy" @click="load" /><UButton label="完成" :disabled="busy" @click="emit('close')" /></template></UModal>
</template>
<style scoped>.tag-single-grid { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px; }.knowledge-options { display:grid;gap:12px;max-height:180px;overflow:auto; }.edition-section { border-top:1px solid var(--ui-border);padding-top:20px;margin-top:6px; }@media(max-width:600px){.tag-single-grid{grid-template-columns:1fr}}</style>
