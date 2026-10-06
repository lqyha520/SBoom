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
import CatalogRevisionDialog from './CatalogRevisionDialog.vue'
import PaperMetadataDialog from './PaperMetadataDialog.vue'
import PaperEditionDialog from './PaperEditionDialog.vue'

const props = defineProps<{ user: UserInfo }>()
const items = ref<CatalogPaper[]>([])
const selection = useCatalogSelection()
const selectedIds = selection.ids
const selectedItems = selection.selected
const batchOpen = ref(false),
  revisionOpen = ref(false),
  metadataOpen = ref(false),
  editionOpen = ref(false)
const metadataTarget = ref<CatalogPaper | null>(null),
  editionTarget = ref<CatalogPaper | null>(null),
  revisionTarget = ref<CatalogPaper | null>(null)
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
    await load()
    if (revealCreated) {
      await nextTick()
      createdPanel.value?.scrollIntoView?.({ block: 'nearest' })
    }
  },
)
const { categories, statuses } = toRefs(editor)
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
}
async function load() {
  const current = ++sequence
  loading.value = true
  error.value = ''
  try {
    const result = await catalogList(
      q.value.trim(),
      status.value === 'all' ? '' : status.value,
      (page.value - 1) * 20,
    )
    if (current !== sequence) return
    items.value = result.items
    total.value = result.total
    if (!items.value.length && page.value > 1) {
      page.value--
      return
    }
    const resultStats = await catalogStats()
    if (current === sequence) stats.value = resultStats
  } catch (cause) {
    if (current === sequence) error.value = message(cause)
  } finally {
    if (current === sequence) loading.value = false
  }
}
const routeState = useAdminListRoute('papers', { q, status, page }, () => {
  void load()
})
function search() {
  if (routeState.restoring) return
  if (page.value !== 1) page.value = 1
  else void load()
}
watch(page, load)
watch(status, search)
onActivated(() => {
  void load()
})
onDeactivated(() => {
  sequence++
  loading.value = false
  previewOpen.value = false
  batchOpen.value = false
  revisionOpen.value = false
  metadataOpen.value = false
  editionOpen.value = false
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
  metadataTarget.value = item
  metadataOpen.value = true
}
async function locateCreated(item: CatalogPaper) {
  highlighted.value = item.id
  q.value = item.title.slice(0, 120)
  status.value = 'all'
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
    await load()
  } catch (cause) {
    removeError.value = message(cause)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="admin-section" aria-label="公共习题管理">
    <dl v-if="stats" class="catalog-metrics">
      <div>
        <dt>已发布</dt>
        <dd>{{ stats.published }}</dd>
      </div>
      <div>
        <dt>草稿</dt>
        <dd>{{ stats.draft }}</dd>
      </div>
      <div>
        <dt>已下架</dt>
        <dd>{{ stats.withdrawn }}</dd>
      </div>
      <div>
        <dt>收藏记录</dt>
        <dd>{{ stats.favorites }}</dd>
      </div>
      <div>
        <dt>下载记录</dt>
        <dd>{{ stats.downloads }}</dd>
      </div>
    </dl>
    <div class="section-toolbar catalog-toolbar">
      <form class="table-search" @submit.prevent="search">
        <UInput
          v-model="q"
          icon="i-lucide-search"
          placeholder="搜索习题、知识点或分类"
          aria-label="搜索公共习题"
        /><UButton
          type="submit"
          icon="i-lucide-arrow-right"
          color="neutral"
          variant="outline"
          aria-label="搜索公共习题"
          :loading="loading"
        />
      </form>
      <div class="actions-row">
        <USelect
          v-model="status"
          :items="statuses"
          aria-label="发布状态筛选"
          class="status-filter"
        /><UTooltip text="刷新"
          ><UButton
            icon="i-lucide-refresh-cw"
            color="neutral"
            variant="ghost"
            aria-label="刷新公共习题"
            :loading="loading"
            @click="load" /></UTooltip
        ><UButton icon="i-lucide-plus" label="添加习题" @click="create" />
      </div>
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
        <h2>本次新建 {{ createdItems.length }} 份习题</h2>
        <UButton
          label="继续添加"
          size="sm"
          variant="outline"
          :disabled="busy"
          @click="create"
        />
      </div>
      <p class="text-sm text-muted">草稿不会自动公开；请预览核对后再发布。</p>
      <ul>
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
    <div class="actions-row mb-3">
      <UButton
        :label="'批量管理（' + selectedItems.length + '）'"
        :disabled="!selectedItems.length"
        variant="outline"
        @click="batchOpen = true"
      /><span class="text-sm text-muted"
        >勾选资料后可批量分类、上下架或调整权限</span
      >
    </div>
    <CatalogPaperTable
      :items="items"
      :selected-ids="selectedIds"
      :categories="categories"
      :loading="loading"
      :error="error"
      :highlighted="highlighted"
      @select="toggleSelection"
      @select-page="selectPage"
      @preview="showPreview"
      @edit="edit"
      @remove="askRemove"
      @metadata="
        metadataTarget = $event;
        metadataOpen = true
      "
      @edition="
        editionTarget = $event;
        editionOpen = true
      "
      @revision="
        revisionTarget = $event;
        revisionOpen = true
      "
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
    /><CatalogRevisionDialog
      :open="revisionOpen"
      :target="revisionTarget"
      :admin-id="user.id"
      @close="revisionOpen = false"
      @saved="load"
    />
    <PaperMetadataDialog
      :open="metadataOpen"
      :target="metadataTarget"
      :admin-id="user.id"
      @close="metadataOpen = false"
      @saved="load"
    />
    <PaperEditionDialog
      :open="editionOpen"
      :target="editionTarget"
      :admin-id="user.id"
      @close="editionOpen = false"
      @saved="load"
    />
  </section>
</template>

<style scoped>
.created-results {
  padding: 16px;
  margin-bottom: 20px;
  border: 1px solid var(--ui-border);
  border-radius: 10px;
  background: var(--ui-bg-muted);
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
.catalog-metrics {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  border-bottom: 1px solid var(--ui-border);
  margin: 0 0 24px;
  padding-bottom: 20px;
  gap: 16px;
}
.catalog-metrics dt {
  color: var(--ui-text-muted);
  font-size: 12px;
}
.catalog-metrics dd {
  margin: 8px 0 0;
  font-size: 24px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.catalog-toolbar {
  flex-wrap: wrap;
  gap: 12px;
}
.catalog-toolbar > .actions-row {
  flex-wrap: nowrap;
}
.status-filter {
  width: 136px;
  min-width: 116px;
  flex: none;
}
@media (max-width: 600px) {
  .catalog-metrics {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .catalog-toolbar .actions-row {
    flex-wrap: wrap;
  }
}
</style>
