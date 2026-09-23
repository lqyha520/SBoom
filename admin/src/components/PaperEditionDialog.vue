<script setup lang="ts">
import { ref, watch } from 'vue'
import { attachImportedEdition, catalogDetail, type CatalogDetail, type CatalogPaper } from '../catalog'
import { editionSources, saveEdition, type EditionSource } from '../growth'
const props = defineProps<{ open: boolean; target: CatalogPaper | null; adminId: number }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const detail = ref<CatalogDetail | null>(null), sources = ref<EditionSource[]>([])
const loose = ref(false)
const uploadFile = ref<File | null>(null)
function chooseFile(event: Event) { uploadFile.value = (event.target as HTMLInputElement).files?.[0] || null }
const error = ref(''), notice = ref(''), busy = ref(false), loading = ref(false), q = ref(''), editionKind = ref<'student' | 'answers'>('answers'), sourceId = ref('none'), confirmed = ref(false)
let sequence = 0
const sourceChoices = ref<{ value: string; label: string }[]>([])
function rebuildChoices() {
  const candidates = loose.value ? sources.value : sources.value.filter(item => editionKind.value === 'student' ? item.mode === 'student' : ['answersOnly', 'withAnswers'].includes(item.mode))
  sourceChoices.value = [{ value: 'none', label: '不关联额外文件' }, ...candidates.map(item => ({
    value: item.id,
    label: `${item.title} · v${item.version} · ${item.mode === 'student' ? '练习版' : item.mode === 'answersOnly' ? '答案版' : '习题与答案版'}${item.owned_by ? `（已单独建条目「${item.owned_by}」，需先删除该条目）` : ''}`,
  }))]
}
function setEditionSelection() { sourceId.value = detail.value?.editions?.find(item => item.kind === editionKind.value)?.paper_id || 'none'; confirmed.value = false; uploadFile.value = null }
async function load() {
  if (!props.open || !props.target) return
  const current = ++sequence; loading.value = true; error.value = ''
  try {
    const [paper, alternatives] = await Promise.all([catalogDetail(props.target.id), editionSources(props.target.id, q.value)])
    if (current !== sequence) return
    detail.value = paper; sources.value = alternatives.items; loose.value = !!alternatives.loose; rebuildChoices(); setEditionSelection()
  } catch (cause) { if (current === sequence) error.value = cause instanceof Error ? cause.message : '加载失败' }
  finally { if (current === sequence) loading.value = false }
}
watch(() => props.open, value => { sequence++; detail.value = null; sources.value = []; notice.value = ''; q.value = ''; if (value) void load() })
watch(editionKind, () => { rebuildChoices(); setEditionSelection() })
async function save() {
  if (!detail.value || busy.value || loading.value) return
  const current = sequence; busy.value = true; error.value = ''; notice.value = ''
  try {
    const result = uploadFile.value ? await attachImportedEdition(props.adminId, detail.value.id, detail.value.revision, editionKind.value, uploadFile.value, undefined, confirmed.value) : await saveEdition(props.adminId, detail.value.id, { revision: detail.value.revision, kind: editionKind.value, paper_id: sourceId.value === 'none' ? null : sourceId.value, confirm_publication: confirmed.value })
    if (current !== sequence) return
    detail.value.revision = result.revision; detail.value.editions = result.editions; confirmed.value = false
    uploadFile.value = null
    notice.value = '打印版本已保存'
    emit('saved')
  } catch (cause) { if (current === sequence) error.value = cause instanceof Error ? cause.message : '保存失败' }
  finally { busy.value = false }
}
</script>
<template>
  <UModal :open="open" :title="'打印版本 · ' + (target?.title || '')" :dismissible="!busy" :close="!busy" @update:open="!$event && emit('close')"><template #body>
    <div class="field-stack">
      <UAlert v-if="error" :title="error" color="error" />
      <UAlert v-if="notice" :title="notice" color="success" />
      <p v-if="loading">正在读取资料</p>
      <template v-if="detail">
        <p class="text-sm text-muted">一份资料除了原稿，还可以关联「练习版」和「答案解析版」两份 PDF，读者在小程序下载时可选择版本。工作台习题要求题目一致、导出模式匹配；手动导入的 PDF 不做内容校验（不限年级科目），内容是否配套由导入人自行确认。</p>
        <div v-for="edition in detail.editions || []" :key="edition.kind" class="actions-row"><span class="text-sm">{{ edition.label }}{{ edition.kind === 'original' ? '（当前原稿）' : '' }}</span><UButton v-if="edition.url" :href="edition.url" label="查看 PDF" variant="link" size="xs" /></div>
        <UFormField label="要配置的版本"><USelect v-model="editionKind" :items="[{ value: 'student', label: '练习版' }, { value: 'answers', label: '答案解析版' }]" :disabled="busy" class="w-full" /></UFormField>
        <div class="actions-row"><UInput v-model="q" placeholder="搜索匹配的归档" :disabled="busy" @keydown.enter.prevent="load" /><UButton label="查找文件" variant="outline" :disabled="busy" :loading="loading" @click="load" /></div>
        <UFormField hint="工作台习题从同年级、学科与题量的归档中匹配；导入的 PDF 会列出全部导入归档。最多显示 50 份，可搜索缩小范围。更换修订稿后需重新关联。"><USelect v-model="sourceId" :items="sourceChoices" :disabled="busy || loading" class="w-full" aria-label="关联打印文件" /></UFormField>
        <UFormField label="或直接上传 PDF" hint="上传会替换所选打印版本，请先核对题目与答案是否配套。"><input type="file" accept="application/pdf,.pdf" :disabled="busy || loading" @change="chooseFile" /></UFormField>
        <UCheckbox v-if="detail.status === 'published'" v-model="confirmed" label="已核对文件和现有会员权限，确认更新已发布的打印版本" :disabled="busy" />
        <UButton label="保存打印版本" :disabled="busy || loading || (detail.status === 'published' && !confirmed)" :loading="busy" @click="save" />
      </template>
    </div>
  </template><template #footer><UButton label="刷新资料" color="neutral" variant="outline" :disabled="busy" @click="load" /><UButton label="完成" :disabled="busy" @click="emit('close')" /></template></UModal>
</template>
