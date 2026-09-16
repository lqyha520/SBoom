<script setup lang="ts">
import { computed, onActivated, onDeactivated, ref, watch } from 'vue'
import CatalogBatchDialog from './CatalogBatchDialog.vue'
import CatalogRevisionDialog from './CatalogRevisionDialog.vue'
import PaperMetadataDialog from './PaperMetadataDialog.vue'
import { previewCatalog } from '../experience'
import type { UserInfo } from '../api'
import { catalogDetail, catalogList, catalogSources, catalogStats, createPublication, deletePublication, updatePublication,
  type CatalogDetail, type CatalogPaper, type CatalogSource, type CatalogStats, type PublicationEdit, type PublicationStatus } from '../catalog'
import { siteCategories } from '../site'

const props = defineProps<{ user: UserInfo }>()
const items = ref<CatalogPaper[]>([])
const selectedIds = ref<string[]>([])
const selectedItems = computed(() => items.value.filter(item => selectedIds.value.includes(item.id)))
const batchOpen = ref(false)
const revisionOpen = ref(false)
const metadataOpen = ref(false)
const metadataTarget = ref<CatalogPaper | null>(null)
const revisionTarget = ref<CatalogPaper | null>(null)
function toggleSelection(id: string) { selectedIds.value = selectedIds.value.includes(id) ? selectedIds.value.filter(value => value !== id) : [...selectedIds.value, id] }
function batchSaved(count: number) { notice.value = '已更新 ' + count + ' 份资料'; selectedIds.value = []; void load() }
const stats = ref<CatalogStats | null>(null)
const categories = ref<{ label: string; value: string }[]>([])
const q = ref('')
const status = ref('all')
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const error = ref('')
const notice = ref('')
let sequence = 0
const labels: Record<PublicationStatus, string> = { draft: '草稿', published: '已发布', withdrawn: '已下架' }
const statuses = [{ label: '全部状态', value: 'all' }, ...Object.entries(labels).map(([value, label]) => ({ label, value }))]
const dialog = ref(false)
const target = ref<CatalogPaper | null>(null)
const busy = ref(false)
const dialogError = ref('')
const form = ref<PublicationEdit>({ revision: 1, title: '', description: '', category_id: '', status: 'draft', featured: false, confirm_publication: false, view_access: 'inherit', download_access: 'inherit' })
const accessOptions = [{ label: '继承题型权限', value: 'inherit' }, { label: '普通用户与 VIP', value: 'free' }, { label: '仅 VIP 会员', value: 'vip' }]
watch(() => form.value.view_access, value => { if (value === 'vip') form.value.download_access = 'vip' })
const sourceQuery = ref('')
const sources = ref<CatalogSource[]>([])
const sourceId = ref('')
const sourceMore = ref(false)
const sourceLoading = ref(false)
let sourceSequence = 0
const sourceItems = computed(() => sources.value.map(item => ({ value: item.id, label: `${item.title} · ${item.grade} · v${item.version}${item.file_status !== 'ready' ? ' · 文件未完成' : ''}` })))
const publishing = computed(() => !!target.value && form.value.status === 'published' && target.value.status !== 'published')
const valid = computed(() => !!form.value.title.trim() && !!form.value.category_id && (!!target.value || !!sourceId.value) && (!publishing.value || form.value.confirm_publication))
const categoryNames = computed(() => new Map(categories.value.map(item => [item.value, item.label])))
const preview = ref<CatalogDetail | null>(null)
const previewTarget = ref<CatalogPaper | null>(null)
const previewRole = ref('admin')
const previewOpen = ref(false)
const previewLoading = ref(false)
const previewError = ref('')
const previewPages = ref(4)
const removeTarget = ref<CatalogPaper | null>(null)
const removeOpen = ref(false)
const removeError = ref('')
const message = (cause: unknown) => cause instanceof Error ? cause.message : '操作失败，请重试'
const date = (stamp: number) => new Date(stamp * 1000).toLocaleString('zh-CN', { hour12: false })
const categoryText = (item: CatalogPaper) => categoryNames.value.get(item.category_id || '') || item.category || '未分类'

async function loadCategories() {
  try { categories.value = (await siteCategories()).items.filter(item => item.is_visible).map(item => ({ label: item.name, value: item.id })) }
  catch { categories.value = [] }
}

async function load() {
  const current = ++sequence
  loading.value = true; error.value = ''; selectedIds.value = []
  try {
    const result = await catalogList(q.value.trim(), status.value === 'all' ? '' : status.value, (page.value - 1) * 20)
    if (current !== sequence) return
    items.value = result.items; total.value = result.total
    if (!items.value.length && page.value > 1) { page.value--; return }
    const resultStats = await catalogStats()
    if (current === sequence) stats.value = resultStats
  } catch (cause) { if (current === sequence) error.value = message(cause) }
  finally { if (current === sequence) loading.value = false }
}
function search() { if (page.value !== 1) page.value = 1; else void load() }
watch(page, load)
watch(status, search)
onActivated(() => { void loadCategories(); void load() })
onDeactivated(() => { sequence++; sourceSequence++; loading.value = false; previewOpen.value = false; dialog.value = false; batchOpen.value = false; revisionOpen.value = false; metadataOpen.value = false })

async function loadSources(more = false) {
  const current = ++sourceSequence
  sourceLoading.value = true; dialogError.value = ''
  try {
    const result = await catalogSources(sourceQuery.value.trim(), more ? sources.value.length : 0)
    if (current !== sourceSequence) return
    sources.value = more ? [...sources.value, ...result.items] : result.items
    sourceMore.value = result.has_more
  } catch (cause) { if (current === sourceSequence) dialogError.value = message(cause) }
  finally { if (current === sourceSequence) sourceLoading.value = false }
}
function create() {
  target.value = null; sourceId.value = ''; sourceQuery.value = ''; sources.value = []; dialogError.value = ''
  form.value = { revision: 1, title: '', description: '', category_id: categories.value[0]?.value || '', status: 'draft', featured: false, confirm_publication: false, view_access: 'inherit', download_access: 'inherit' }
  dialog.value = true; void loadSources()
}
function edit(item: CatalogPaper) {
  target.value = item; dialogError.value = ''
  form.value = { revision: item.revision, title: item.title, description: item.description, category_id: item.category_id || '',
    status: item.status, featured: item.featured, confirm_publication: false, view_access: item.view_access, download_access: item.download_access }
  dialog.value = true
}
watch(sourceId, id => { const item = sources.value.find(source => source.id === id); if (item) form.value.title = item.title })
async function save() {
  if (busy.value || !valid.value) return
  busy.value = true; dialogError.value = ''
  try {
    if (target.value) await updatePublication(props.user.id, target.value.id, { ...form.value, title: form.value.title.trim() })
    else await createPublication(props.user.id, { paper_id: sourceId.value, title: form.value.title.trim(), description: form.value.description, category_id: form.value.category_id, view_access: form.value.view_access, download_access: form.value.download_access })
    notice.value = target.value ? '公共习题已更新' : '已创建草稿，预览并确认后可发布'
    dialog.value = false; await load()
  } catch (cause) { dialogError.value = message(cause) }
  finally { busy.value = false }
}
async function showPreview(item: CatalogPaper, role = 'admin') {
  previewRole.value = role; previewTarget.value = item
  preview.value = null; previewPages.value = 4; previewError.value = ''; previewOpen.value = true; previewLoading.value = true
  const current = ++sourceSequence
  try { const value = await (role === 'admin' ? catalogDetail(item.id) : previewCatalog(item.id, role)); if (current === sourceSequence) preview.value = value }
  catch (cause) { if (current === sourceSequence) previewError.value = message(cause) }
  finally { if (current === sourceSequence) previewLoading.value = false }
}
function askRemove(item: CatalogPaper) { removeTarget.value = item; removeError.value = ''; removeOpen.value = true }
async function remove() {
  if (busy.value || !removeTarget.value) return
  busy.value = true; removeError.value = ''
  try { await deletePublication(props.user.id, removeTarget.value); removeOpen.value = false; notice.value = '公共条目已删除，原始习题仍保留'; await load() }
  catch (cause) { removeError.value = message(cause) }
  finally { busy.value = false }
}
</script>

<template>
  <section class="admin-section" aria-label="公共习题管理">
    <dl v-if="stats" class="catalog-metrics"><div><dt>已发布</dt><dd>{{ stats.published }}</dd></div><div><dt>草稿</dt><dd>{{ stats.draft }}</dd></div><div><dt>已下架</dt><dd>{{ stats.withdrawn }}</dd></div><div><dt>收藏记录</dt><dd>{{ stats.favorites }}</dd></div><div><dt>下载记录</dt><dd>{{ stats.downloads }}</dd></div></dl>
    <div class="section-toolbar catalog-toolbar">
      <form class="table-search" @submit.prevent="search"><UInput v-model="q" icon="i-lucide-search" placeholder="搜索习题、知识点或分类" aria-label="搜索公共习题" /><UButton type="submit" icon="i-lucide-arrow-right" color="neutral" variant="outline" aria-label="搜索公共习题" :loading="loading" /></form>
      <div class="actions-row"><USelect v-model="status" :items="statuses" aria-label="发布状态筛选" class="status-filter" /><UTooltip text="刷新"><UButton icon="i-lucide-refresh-cw" color="neutral" variant="ghost" aria-label="刷新公共习题" :loading="loading" @click="load" /></UTooltip><UButton icon="i-lucide-plus" label="添加习题" @click="create" /></div>
    </div>
    <UAlert v-if="error" :title="error" color="error" variant="soft" class="notice" />
    <UAlert v-if="notice" :title="notice" color="success" variant="soft" close class="notice" @update:open="notice = ''" />
    <div class="actions-row mb-3"><UButton :label="'批量管理（' + selectedItems.length + '）'" :disabled="!selectedItems.length" variant="outline" @click="batchOpen = true" /><span class="text-sm text-muted">勾选资料后可批量分类、上下架或调整权限</span></div><div class="data-scroll" :aria-busy="loading"><table class="data-table catalog-table"><thead><tr><th><UCheckbox aria-label="选择当前页" :model-value="!!items.length && selectedItems.length === items.length" :disabled="loading" @update:model-value="selectedIds = $event ? items.map(item => item.id) : []" /></th><th>习题</th><th>分类</th><th>发布状态</th><th>收藏</th><th>下载用户</th><th>更新于</th><th><span class="sr-only">操作</span></th></tr></thead><tbody>
      <tr v-for="item in items" :key="item.id"><td><UCheckbox :aria-label="'选择 ' + item.title" :model-value="selectedIds.includes(item.id)" :disabled="loading" @update:model-value="toggleSelection(item.id)" /></td><td><div class="catalog-paper"><img v-if="item.thumbnail_url" :src="item.thumbnail_url" alt="" class="catalog-thumb" loading="lazy" /><UIcon v-else name="i-lucide-file-text" class="size-9 text-dimmed" /><div><div class="catalog-name"><span>{{ item.title }}</span><UIcon v-if="item.featured" name="i-lucide-pin" class="catalog-featured size-3 text-primary" title="优先展示" /></div><div class="catalog-meta">{{ item.grade }} · {{ item.subject }} · {{ item.question_count }} 题 · 第 {{ item.release_number || 1 }} 版 · 原稿 v{{ item.version }}</div><div v-if="item.file_status !== 'ready'" class="text-warning text-xs">文件未完成</div></div></div></td>
        <td>{{ categoryText(item) }}<div v-if="!item.category_id" class="missing-category">未关联分类</div><div class="access-caption">{{ item.required_view === 'vip' ? 'VIP 专享' : item.required_download === 'vip' ? '免费预览 · VIP 下载' : '普通用户可用' }}</div></td><td><UBadge :color="item.status === 'published' ? 'success' : item.status === 'draft' ? 'warning' : 'neutral'" variant="soft">{{ labels[item.status] }}</UBadge></td><td>{{ item.favorite_count || 0 }}</td><td>{{ item.download_users || 0 }}</td><td class="date-cell">{{ date(item.updated_at) }}</td>
        <td><div class="actions-row"><UTooltip text="预览习题"><UButton icon="i-lucide-eye" color="neutral" variant="ghost" :aria-label="'预览 ' + item.title" @click="showPreview(item)" /></UTooltip><UTooltip text="编辑与发布"><UButton icon="i-lucide-square-pen" color="neutral" variant="ghost" :aria-label="'编辑 ' + item.title" @click="edit(item)" /></UTooltip><UTooltip text="标签与打印"><UButton icon="i-lucide-tags" color="neutral" variant="ghost" :aria-label="'标签与打印 ' + item.title" @click="metadataTarget = item; metadataOpen = true" /></UTooltip><UTooltip text="更新修订稿"><UButton icon="i-lucide-file-clock" color="neutral" variant="ghost" :aria-label="'修订 ' + item.title" @click="revisionTarget = item; revisionOpen = true" /></UTooltip><UTooltip text="删除公共条目"><UButton icon="i-lucide-trash-2" color="error" variant="ghost" :aria-label="'删除公共条目 ' + item.title" @click="askRemove(item)" /></UTooltip></div></td></tr>
      <tr v-if="!items.length"><td colspan="8"><div class="empty-state"><UIcon :name="loading ? 'i-lucide-loader-circle' : 'i-lucide-library'" class="size-7" :class="{ 'animate-spin': loading }" /><h3>{{ loading ? '正在加载' : error ? '习题列表暂不可用' : '暂无公共习题' }}</h3></div></td></tr>
    </tbody></table></div>
    <div class="table-footer"><span>共 {{ total }} 份习题</span><UPagination v-if="total > 20" v-model:page="page" :total="total" :items-per-page="20" :sibling-count="1" size="sm" /></div>

    <UModal v-model:open="dialog" :title="target ? '编辑公共习题' : '添加习题草稿'" :dismissible="!busy" :close="!busy"><template #body>
      <form id="publication-form" class="field-stack" @submit.prevent="save">
        <template v-if="!target"><UFormField label="工作台已保存的习题" required><div class="source-search"><UInput v-model="sourceQuery" placeholder="搜索自己的习题" :disabled="busy" @keydown.enter.prevent="loadSources()" /><UButton icon="i-lucide-search" aria-label="查找源习题" color="neutral" variant="outline" :loading="sourceLoading" @click="loadSources()" /></div><USelect v-model="sourceId" :items="sourceItems" placeholder="选择习题" :disabled="busy || sourceLoading" class="w-full mt-2" /><UButton v-if="sourceMore" label="加载更多" icon="i-lucide-chevron-down" variant="link" :loading="sourceLoading" @click="loadSources(true)" /><UButton v-if="!sourceLoading && !sources.length" href="/" label="前往出题工作台" icon="i-lucide-arrow-up-right" variant="link" /></UFormField></template>
        <UFormField label="公开标题" required><UInput v-model="form.title" maxlength="240" :disabled="busy" required /></UFormField>
        <UFormField label="分类" required hint="分类决定小程序首页专题入口与筛选器，可在「小程序管理 › 分类管理」里维护"><USelect v-model="form.category_id" :items="categories" placeholder="选择分类" :disabled="busy" required class="w-full" /></UFormField>
        <UAlert v-if="!categories.length" color="warning" variant="soft" title="还没有可用的分类" description="请先到「小程序管理 › 分类管理」新建分类，再回来发布习题。" />
        <UFormField label="习题简介"><UTextarea v-model="form.description" maxlength="2000" :rows="3" :disabled="busy" /></UFormField>
        <template v-if="target"><UFormField label="发布状态"><USelect v-model="form.status" :items="statuses.slice(1)" :disabled="busy" /></UFormField><USwitch v-model="form.featured" label="优先展示" :disabled="busy" /></template>
        <UFormField label="完整原稿观看"><USelect v-model="form.view_access" :items="accessOptions" :disabled="busy" class="w-full" /></UFormField>
        <UFormField label="PDF 下载"><USelect v-model="form.download_access" :items="accessOptions" :disabled="busy || form.view_access === 'vip'" class="w-full" /></UFormField>
        <UAlert v-if="publishing" color="warning" variant="soft" title="发布后，习题、答案和文件按所设权限提供给小程序用户。请确认拥有发布权限且不含学生隐私。" />
        <UCheckbox v-if="publishing" v-model="form.confirm_publication" label="已核对内容，确认公开发布" :disabled="busy" />
        <UAlert v-if="dialogError" :title="dialogError" color="error" variant="soft" />
      </form></template><template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="busy" @click="dialog = false" /><UButton type="submit" form="publication-form" :label="publishing ? '确认发布' : target ? '保存更改' : '创建草稿'" :loading="busy" :disabled="busy || !valid" /></template></UModal>

    <UModal v-model:open="previewOpen" :title="preview?.title || '习题预览'" :ui="{ content: 'sm:max-w-3xl' }"><template #body><div v-if="previewLoading" class="empty-state"><UIcon name="i-lucide-loader-circle" class="size-6 animate-spin" /></div><UAlert v-if="previewError" :title="previewError" color="error" variant="soft" /><div v-if="previewTarget" class="actions-row mb-4"><UButton v-for="role in [{ value: 'admin', label: '管理员' }, { value: 'regular', label: '普通用户' }, { value: 'vip', label: 'VIP' }]" :key="role.value" :label="role.label" :variant="previewRole === role.value ? 'solid' : 'outline'" :disabled="previewLoading" @click="showPreview(previewTarget, role.value)" /></div><template v-if="preview"><UAlert v-if="previewRole !== 'admin'" :title="(preview.can_view ? '可查看原稿' : '原稿受限') + ' · ' + (preview.can_download ? '可下载 PDF' : 'PDF 受限')" color="info" class="mb-4" /><UAlert v-if="previewRole !== 'admin' && !preview.can_view" title="普通用户查看这份资料需要 VIP，可切换 VIP 预览检查会员可见内容。" color="info" variant="soft" /><UAlert v-else-if="!preview.assets.length" title="原卷文件尚未完成，请先在工作台重试文件。" color="warning" variant="soft" /><div class="catalog-preview"><img v-for="asset in preview.assets.filter(asset => asset.kind === 'page').slice(0, previewPages)" :key="asset.id" :src="asset.url" :alt="'第 ' + asset.page_number + ' 页'" /></div><UButton v-if="preview.can_view && preview.page_count > previewPages" label="更多页面" icon="i-lucide-chevron-down" variant="outline" @click="previewPages += 4" /></template></template><template #footer><UButton v-if="preview?.assets.some(asset => asset.kind === 'pdf')" :href="preview.assets.find(asset => asset.kind === 'pdf')?.url" label="下载 PDF" icon="i-lucide-download" color="neutral" variant="outline" /><UButton label="关闭" @click="previewOpen = false" /></template></UModal>

    <UModal v-model:open="removeOpen" title="删除公共条目" :dismissible="!busy" :close="!busy"><template #body><UAlert color="warning" variant="soft" :title="'确认删除「' + removeTarget?.title + '」的公共条目？'" description="该条目的收藏和下载记录会被删除，工作台中的原始习题与文件仍保留。" /><UAlert v-if="removeError" :title="removeError" color="error" variant="soft" class="mt-3" /></template><template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="busy" @click="removeOpen = false" /><UButton label="删除条目" icon="i-lucide-trash-2" color="error" :loading="busy" @click="remove" /></template></UModal>
    <CatalogBatchDialog :open="batchOpen" :admin-id="user.id" :items="selectedItems" :categories="categories" @close="batchOpen = false" @saved="batchSaved" /><CatalogRevisionDialog :open="revisionOpen" :target="revisionTarget" :admin-id="user.id" @close="revisionOpen = false" @saved="load" />
    <PaperMetadataDialog :open="metadataOpen" :target="metadataTarget" :admin-id="user.id" @close="metadataOpen = false" @saved="load" />
  </section>
</template>

<style scoped>
.catalog-metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); border-bottom: 1px solid var(--ui-border); margin: 0 0 24px; padding-bottom: 20px; gap: 16px; }
.catalog-metrics dt { color: var(--ui-text-muted); font-size: 12px; }
.catalog-metrics dd { margin: 8px 0 0; font-size: 24px; font-weight: 600; font-variant-numeric: tabular-nums; }
.catalog-toolbar { flex-wrap: wrap; gap: 12px; }
.catalog-toolbar > .actions-row { flex-wrap: nowrap; }
.status-filter { width: 136px; min-width: 116px; flex: none; }
.catalog-table { min-width: 940px; }
.catalog-table th { position: relative; }
.catalog-paper { display: flex; align-items: center; gap: 12px; min-width: 240px; }
.catalog-thumb { width: 40px; height: 56px; object-fit: cover; border: 1px solid var(--ui-border); flex: none; }
.catalog-name { display: flex; align-items: flex-start; gap: 6px; font-size: 13px; font-weight: 600; max-width: 300px; white-space: normal; overflow-wrap: anywhere; }
.catalog-name > span:first-child { min-width: 0; }
.catalog-featured { flex: none; margin-top: 3px; }
.catalog-meta { margin-top: 5px; color: var(--ui-text-muted); font-size: 11px; }
.access-caption { margin-top: 6px; color: var(--ui-text-muted); font-size: 11px; white-space: normal; }
.missing-category { margin-top: 5px; color: var(--ui-warning); font-size: 11px; }
.source-search { display: flex; gap: 8px; }
.source-search > :first-child { flex: 1; min-width: 0; }
.catalog-preview { display: grid; gap: 20px; }
.catalog-preview img { display: block; width: 100%; height: auto; border: 1px solid var(--ui-border); }
@media (max-width: 600px) { .catalog-metrics { grid-template-columns: repeat(3, minmax(0, 1fr)); } .catalog-toolbar .actions-row { flex-wrap: wrap; } }
</style>
