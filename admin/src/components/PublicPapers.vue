<script setup lang="ts">
import {
  computed,
  nextTick,
  onActivated,
  onDeactivated,
  reactive,
  ref,
  toRefs,
  watch,
} from 'vue'
import type { UserInfo } from '../api'
import {
  catalogDetail,
  catalogList,
  catalogStats,
  deletePublication,
  type CatalogDetail,
  type CatalogPaper,
  type CatalogStats,
} from '../catalog'
import { useCatalogSelection } from '../catalog-selection'
import { useCatalogPreview } from '../catalog-preview'
import { usePublicationEditor, publicationLabels as labels } from '../publication-editor'
import { adminRoute, useAdminListRoute } from '../navigation'
import CatalogPaperTable from './CatalogPaperTable.vue'
import PublicationEditorDialog from './PublicationEditorDialog.vue'
import CatalogPreviewDialog from './CatalogPreviewDialog.vue'
import CatalogBatchDialog from './CatalogBatchDialog.vue'


const props = defineProps<{ user: UserInfo }>()
const items = ref<CatalogPaper[]>([])
const selection = useCatalogSelection()
const selectedIds = selection.ids
const selectedItems = selection.selected
const batchOpen = ref(false)
const grade = ref('all'), subject = ref('all'), category = ref('all'), access = ref('all')
const createdExpanded = ref(false)
const statsLoading = ref(false), statsError = ref('')
let statsLoadedAt = 0
let statsPending = false
const stats = ref<CatalogStats | null>(null)
const q = ref(''),
  status = ref('all'),
  page = ref(1),
  total = ref(0)
const loading = ref(false),
  error = ref(''),
  notice = ref('')
const createdItems = ref<CatalogDetail[]>([]),
  createdPanel = ref<HTMLElement | null>(null),
  highlighted = ref('')
const saving = ref(false),
  removeOpen = ref(false),
  removeError = ref('')
const removeTarget = ref<CatalogPaper | null>(null)
let sequence = 0
function rememberCreated(paper: CatalogDetail, existingOnly = false) {
  const index = createdItems.value.findIndex((item) => item.id === paper.id)
  if (index >= 0) createdItems.value[index] = paper
  else if (!existingOnly) createdItems.value.unshift(paper)
}
const editor = usePublicationEditor(
  props.user.id,
  rememberCreated,
  async (message, revealCreated = false) => {
    notice.value = message
    void loadStats(true)
    await load()
    if (revealCreated) {
      await nextTick()
      createdPanel.value?.scrollIntoView?.({ block: 'nearest' })
    }
  },
)
const { categories, filterCategories, statuses, gradeOptions, subjectOptions } = toRefs(editor)
const statusTabs = computed(() => statuses.value.map(item => {
  const count = !stats.value ? null : item.value === 'all'
    ? stats.value.published + stats.value.draft + stats.value.withdrawn
    : stats.value[item.value as 'published' | 'draft' | 'withdrawn']
  return { ...item, label: (item.value === 'all' ? '全部习题' : item.label) + (Number.isFinite(count) ? ` ${count}` : '') }
}))
const busy = computed(() => saving.value || editor.busy)
const previewState = reactive(useCatalogPreview())
const { preview, previewOpen } = toRefs(previewState)
const showPreview = previewState.showPreview
const message = (cause: unknown) =>
  cause instanceof Error ? cause.message : '操作失败，请重试'
function create() {
  if (!saving.value) editor.create()
}
function edit(item: CatalogPaper) {
  if (!saving.value) editor.edit(item)
}
function toggleSelection(id: string) {
  const item = items.value.find((value) => value.id === id)
  if (item && !selection.toggle(item)) error.value = '每批最多选择 50 份资料'
}
function selectPage(checked: boolean | 'indeterminate') {
  if (!selection.page(items.value, checked === true))
    error.value = '每批最多选择 50 份资料，请减少选择'
}
function batchSaved(count: number) {
  notice.value = '已更新 ' + count + ' 份资料'
  selection.clear()
  void load()
  void loadStats(true)
}
async function loadStats(force = false) {
  if (statsLoading.value) { if (force) statsPending = true; return }
  if (!force && Date.now() - statsLoadedAt < 60000) return
  statsLoading.value = true; statsError.value = ''
  try { stats.value = await catalogStats(); statsLoadedAt = Date.now() }
  catch (cause) { statsError.value = message(cause) }
  finally {
    statsLoading.value = false
    if (statsPending) { statsPending = false; void loadStats(true) }
  }
}
function refresh() { void load(); void loadStats(true) }
async function load() {
  const current = ++sequence
  loading.value = true
  error.value = ''
  try {
    const result = await catalogList(
      q.value.trim(),
      status.value === 'all' ? '' : status.value,
      (page.value - 1) * 20,
      Object.fromEntries(Object.entries({ grade: grade.value, subject: subject.value, category: category.value, access: access.value }).filter(([, value]) => value !== 'all')),
    )
    if (current !== sequence) return
    items.value = result.items
    total.value = result.total
    if (!items.value.length && page.value > 1) {
      page.value--
      return
    }
  } catch (cause) {
    if (current === sequence) error.value = message(cause)
  } finally {
    if (current === sequence) loading.value = false
  }
}
const routeState = useAdminListRoute('papers', { q, status, grade, subject, category, access, page }, () => {
  void load()
})
function search() {
  if (routeState.restoring) return
  if (page.value !== 1) page.value = 1
  else void load()
}
watch(page, () => { if (!routeState.restoring) void load() })
watch([status, grade, subject, category, access], search)
onActivated(() => {
  void load()
  void loadStats()
})
onDeactivated(() => {
  sequence++
  loading.value = false
  previewOpen.value = false
  batchOpen.value = false
})
async function openLinkedPaper() {
  const id = new URLSearchParams(adminRoute.query).get('paper')
  if (adminRoute.tab !== 'papers' || !id) return
  try {
    const item = await catalogDetail(id)
    if (
      adminRoute.tab === 'papers' &&
      new URLSearchParams(adminRoute.query).get('paper') === id
    )
      await showPreview(item)
  } catch (cause) {
    if (
      adminRoute.tab === 'papers' &&
      new URLSearchParams(adminRoute.query).get('paper') === id
    )
      error.value = message(cause)
  }
}
onActivated(openLinkedPaper)
watch(() => new URLSearchParams(adminRoute.query).get('paper'), openLinkedPaper)

function previewCreated(item: CatalogPaper) {
  if (!editor.setDialogOpen(false)) return
  void showPreview(item)
}
function tagCreated(item: CatalogPaper) {
  if (!editor.setDialogOpen(false)) return
  editor.edit(item, 'metadata')
}
async function locateCreated(item: CatalogPaper) {
  highlighted.value = item.id
  q.value = item.title.slice(0, 120)
  status.value = 'all'
  grade.value = subject.value = category.value = access.value = 'all'
  page.value = 1
  await load()
}
function publishPreview() {
  if (preview.value) {
    previewOpen.value = false
    edit(preview.value)
    editor.form.status = 'published'
  }
}
function askRemove(item: CatalogPaper) {
  removeTarget.value = item
  removeError.value = ''
  removeOpen.value = true
}
async function remove() {
  if (busy.value || !removeTarget.value) return
  saving.value = true
  removeError.value = ''
  try {
    await deletePublication(props.user.id, removeTarget.value)
    removeOpen.value = false
    notice.value = '公共条目已删除，原始习题仍保留'
    void loadStats(true)
    await load()
  } catch (cause) {
    removeError.value = message(cause)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="admin-section catalog-page" aria-label="公共习题管理">
    <div class="catalog-library-heading"><span class="catalog-library-icon"><UIcon name="i-lucide-folders" class="size-5" /></span><div><h2>教学资料库</h2><p>整理、核对与发布，在一个地方完成。</p></div><span class="catalog-library-badge"><UIcon name="i-lucide-globe" class="size-3.5" />公共内容</span></div>
    <div v-if="statsError" class="actions-row mb-3"><span class="text-sm text-muted">统计暂不可用，仍可管理资料</span><UButton label="重试统计" size="xs" variant="outline" :loading="statsLoading" @click="loadStats(true)" /></div>
    <div class="section-toolbar catalog-toolbar">
      <UTabs v-model="status" :items="statusTabs" :content="false" variant="link" aria-label="发布状态筛选" class="max-w-full overflow-x-auto" :ui="{ list: 'w-max p-0 gap-4', trigger: 'flex-none px-0 pb-3 text-sm' }" />
      <div class="actions-row"><UTooltip text="刷新"><UButton icon="i-lucide-refresh-cw" color="neutral" variant="ghost" aria-label="刷新公共习题" :loading="loading" @click="refresh" /></UTooltip><UButton icon="i-lucide-plus" label="添加习题" @click="create" /></div>
    </div>
    <div class="catalog-filters" aria-label="资料筛选">
      <form class="table-search" @submit.prevent="search">
        <UInput
          v-model="q"
          icon="i-lucide-search"
          placeholder="搜索习题、知识点或分类"
          aria-label="搜索公共习题"
        /><UButton
          type="submit"
          icon="i-lucide-search"
          color="neutral"
          variant="outline"
          aria-label="搜索公共习题"
          :loading="loading"
        />
      </form>
      <USelect v-model="grade" :items="[{value:'all',label:'全部年级'}, ...gradeOptions]" aria-label="年级筛选" />
      <USelect v-model="subject" :items="[{value:'all',label:'全部学科'}, ...subjectOptions]" aria-label="学科筛选" />
      <USelect v-model="category" :items="[{value:'all',label:'全部分类'}, ...filterCategories]" aria-label="分类筛选" />
      <USelect v-model="access" :items="[{value:'all',label:'全部权限'},{value:'free',label:'普通用户可用'},{value:'vip_download',label:'免费预览 · VIP 下载'},{value:'vip_view',label:'VIP 专享'}]" aria-label="权限筛选" />
      <UButton v-if="[grade,subject,category,access].some(value => value !== 'all')" label="清除条件" variant="ghost" @click="grade = subject = category = access = 'all'" />
      <UButton v-if="editor.dictionaryError" label="重试年级与学科" variant="outline" @click="editor.loadDictionaryOptions" />
    </div>
    <UAlert
      v-if="error"
      :title="error"
      color="error"
      variant="soft"
      class="notice"
    />
    <UAlert
      v-if="notice"
      :title="notice"
      color="success"
      variant="soft"
      close
      class="notice"
      @update:open="notice = ''"
    />
    <section
      v-if="createdItems.length"
      ref="createdPanel"
      class="created-results"
      aria-label="本次新建习题"
    >
      <div class="actions-row">
        <button type="button" :aria-expanded="createdExpanded" @click="createdExpanded = !createdExpanded">本次新建 {{ createdItems.length }} 份习题 · {{ createdExpanded ? '收起' : '展开' }}</button>
        <UButton
          label="继续添加"
          size="sm"
          variant="outline"
          :disabled="busy"
          @click="create"
        />
      </div>
      <p v-if="createdExpanded" class="text-sm text-muted">草稿不会自动公开；请预览核对后再发布。</p>
      <ul v-if="createdExpanded">
        <li v-for="item in createdItems" :key="item.id">
          <div class="actions-row"><strong>{{ item.title }}</strong><UBadge :color="item.status === 'published' ? 'success' : item.status === 'draft' ? 'warning' : 'neutral'" variant="soft">{{ labels[item.status] }}</UBadge></div>
          <div class="actions-row">
            <UButton
              :label="item.status === 'draft' ? '预览并发布' : '查看资料'"
              size="sm"
              variant="outline"
              :disabled="busy"
              @click="previewCreated(item)"
            /><UButton
              label="补充教学标签"
              size="sm"
              variant="outline"
              :disabled="busy"
              @click="tagCreated(item)"
            /><UButton
              label="在列表中定位"
              size="sm"
              variant="ghost"
              :disabled="busy"
              @click="locateCreated(item)"
            />
          </div>
        </li>
      </ul>
    </section>
    <div class="catalog-selection-bar" :class="{ 'has-selection': selectedItems.length }">
      <span>{{ selectedItems.length ? '已选择 ' + selectedItems.length + ' 份' : '共 ' + total + ' 份习题' }}</span>
      <div class="actions-row" v-if="selectedItems.length">
      <UButton
        :label="'批量管理（' + selectedItems.length + '）'"
        icon="i-lucide-list-checks" size="sm" variant="soft"
        @click="batchOpen = true"
      /><UButton label="取消选择" variant="ghost" color="neutral" size="sm" @click="selection.clear()" />
      </div>
      <span v-else-if="stats" class="catalog-engagement">收藏 {{ stats.favorites }}<span>·</span>下载 {{ stats.downloads }}</span>
    </div>
    <CatalogPaperTable
      :items="items"
      :selected-ids="selectedIds"
      :categories="filterCategories"
      :loading="loading"
      :error="error"
      :highlighted="highlighted"
      @select="toggleSelection"
      @select-page="selectPage"
      @preview="showPreview"
      @edit="edit"
      @remove="askRemove"
      @metadata="editor.edit($event, 'metadata')"
      @edition="editor.edit($event, 'editions')"
      @revision="editor.edit($event, 'revision')"
    />
    <div class="table-footer">
      <span>共 {{ total }} 份习题</span
      ><UPagination
        v-if="total > 20"
        v-model:page="page"
        :total="total"
        :items-per-page="20"
        :sibling-count="1"
        size="sm"
      />
    </div>

    <PublicationEditorDialog
      :editor="editor"
      @preview="previewCreated"
      @metadata="tagCreated"
    />
    <CatalogPreviewDialog
      :state="previewState"
      :busy="busy"
      @publish="publishPreview"
    />

    <UModal
      v-model:open="removeOpen"
      title="删除公共条目"
      :dismissible="!busy"
      :close="!busy"
      ><template #body
        ><UAlert
          color="warning"
          variant="soft"
          :title="'确认删除「' + removeTarget?.title + '」的公共条目？'"
          description="该条目的收藏和下载记录会被删除，工作台中的原始习题与文件仍保留。" /><UAlert
          v-if="removeError"
          :title="removeError"
          color="error"
          variant="soft"
          class="mt-3" /></template
      ><template #footer
        ><UButton
          label="取消"
          color="neutral"
          variant="outline"
          :disabled="busy"
          @click="removeOpen = false" /><UButton
          label="删除条目"
          icon="i-lucide-trash-2"
          color="error"
          :loading="busy"
          @click="remove" /></template
    ></UModal>
    <CatalogBatchDialog
      :open="batchOpen"
      :admin-id="user.id"
      :items="selectedItems"
      :categories="categories"
      @close="batchOpen = false"
      @saved="batchSaved"
    />
  </section>
</template>

<style scoped>
.catalog-library-heading { display:flex;align-items:center;gap:12px;padding-bottom:24px; }
.catalog-library-icon { display:grid;place-items:center;width:42px;height:42px;flex:none;border-radius:12px;background:#eaf4ee;color:#3f8161; }
.catalog-library-heading h2 { font-size:15px;font-weight:650;margin:0 0 4px; }
.catalog-library-heading p { font-size:11px;color:var(--ui-text-muted);margin:0; }
.catalog-library-badge { display:flex;align-items:center;gap:6px;margin-left:auto;color:#6c8075;background:#f2f6f3;font-size:11px;padding:6px 10px;border-radius:6px;white-space:nowrap; }
.catalog-filters { display:flex;flex-wrap:wrap;gap:10px;padding:16px;background:#f7f9f8;border:1px solid #e8eeea;border-radius:10px;margin-top:12px; }
.catalog-filters > :deep([role='combobox']) { min-width:0;flex:1 1 140px;width:auto; }
.catalog-filters .table-search { flex:1 1 280px; }
.catalog-selection-bar { display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:58px;font-size:12px;color:var(--ui-text-muted);transition:background .2s,padding .2s; }
.catalog-selection-bar.has-selection { padding:10px 14px;margin:12px 0;background:#edf7f1;border-radius:10px;color:#286b4d; }
.catalog-engagement { display:flex;gap:12px; }
.catalog-toolbar { margin-bottom:0;gap:12px; }
.catalog-toolbar > .actions-row { margin-left:auto;flex-wrap:nowrap; }
@media(max-width:600px) { .catalog-filters { display:grid;grid-template-columns:repeat(2,minmax(0,1fr)); }.catalog-filters > :not([role='combobox']) { grid-column:1 / -1; }.catalog-filters .table-search { width:100%; }.catalog-toolbar > :first-child { order:2;width:100%; }.catalog-selection-bar { flex-wrap:wrap;padding:10px 0; } }
@media(max-width:600px) { .catalog-library-badge { display:none; }.catalog-filters { padding:12px; }.catalog-library-heading { padding-bottom:20px; } }
.created-results {
  padding: 16px;
  margin-bottom: 20px;
  border-left: 3px solid var(--ui-primary);
  background: #f2f8f5;
}
.created-results ul {
  list-style: none;
  padding: 0;
  max-height: 240px;
  overflow: auto;
}
.created-results li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 0;
}
.created-results strong {
  overflow-wrap: anywhere;
}
</style>
