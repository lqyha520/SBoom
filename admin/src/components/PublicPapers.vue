<script setup lang="ts">
import {
  computed,
  nextTick,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  reactive,
  ref,
  watch,
} from "vue";
import CatalogImportQueue from "./CatalogImportQueue.vue";
import { useCatalogImportQueue } from "../catalog-import-queue";
import ImagePdfComposer from "./ImagePdfComposer.vue";
import { useImagePdfComposer } from "../image-pdf";
import DownloadSettings from "./DownloadSettings.vue";
import {
  defaultDownloadSettings,
  downloadPayload,
  downloadSettingsIssue,
} from "../download-settings";
import CatalogBatchDialog from "./CatalogBatchDialog.vue";
import CatalogRevisionDialog from "./CatalogRevisionDialog.vue";
import PaperMetadataDialog from "./PaperMetadataDialog.vue";
import PaperEditionDialog from "./PaperEditionDialog.vue";
import { useCatalogPreview } from "../catalog-preview";
import { ApiError, type UserInfo } from "../api";
import { useCatalogSelection } from "../catalog-selection";
import { useBeforeUnload } from "../unsaved";
import {
  catalogDetail,
  catalogList,
  catalogSources,
  catalogStats,
  createPublication,
  deletePublication,
  updatePublication,
  type CatalogDetail,
  type CatalogImportMeta,
  type CatalogPaper,
  type CatalogSource,
  type CatalogStats,
  type PublicationEdit,
  type PublicationStatus,
} from "../catalog";
import { siteCategories, siteDictionary } from "../site";
import {
  adminRoute,
  useAdminLeaveGuard,
  useAdminListRoute,
} from "../navigation";

const props = defineProps<{ user: UserInfo }>();
const items = ref<CatalogPaper[]>([]);
const selection = useCatalogSelection();
const selectedIds = selection.ids;
const selectedItems = selection.selected;
const batchOpen = ref(false);
const revisionOpen = ref(false);
const metadataOpen = ref(false);
const metadataTarget = ref<CatalogPaper | null>(null);
const editionOpen = ref(false);
const editionTarget = ref<CatalogPaper | null>(null);
const revisionTarget = ref<CatalogPaper | null>(null);
function toggleSelection(id: string) {
  const item = items.value.find((value) => value.id === id);
  if (item && !selection.toggle(item)) error.value = "每批最多选择 50 份资料";
}
function selectPage(checked: boolean | "indeterminate") {
  if (!selection.page(items.value, checked === true))
    error.value = "每批最多选择 50 份资料，请减少选择";
}
function batchSaved(count: number) {
  notice.value = "已更新 " + count + " 份资料";
  selection.clear();
  void load();
}
const stats = ref<CatalogStats | null>(null);
const categories = ref<{ label: string; value: string }[]>([]);
const q = ref("");
const status = ref("all");
const page = ref(1);
const total = ref(0);
const loading = ref(false);
const error = ref("");
const notice = ref("");
let sequence = 0;
const answerReadiness: Record<string, string> = {
  included: "原稿包含答案",
  separate: "已关联答案版",
  missing: "未配套",
  unknown: "待核对",
};
const labels: Record<PublicationStatus, string> = {
  draft: "草稿",
  published: "已发布",
  withdrawn: "已下架",
};
const statuses = [
  { label: "全部状态", value: "all" },
  ...Object.entries(labels).map(([value, label]) => ({ label, value })),
];
const dialog = ref(false);
const target = ref<CatalogPaper | null>(null);
const saving = ref(false);
const imageComposer = useImagePdfComposer();
const imageFields = reactive({
  grade: "",
  subject: "",
  category_id: "",
  mode: "student" as CatalogImportMeta["mode"],
});
let active = true;
const createdItems = ref<CatalogDetail[]>([]);
const createdPanel = ref<HTMLElement | null>(null);
const highlighted = ref("");
const dialogNotice = ref("");
const importQueue = useCatalogImportQueue(props.user.id, (paper) => {
  const index = createdItems.value.findIndex((item) => item.id === paper.id);
  if (index < 0) createdItems.value.unshift(paper);
  else createdItems.value[index] = paper;
});
const busy = computed(
  () => saving.value || importQueue.busy || imageComposer.busy,
);
const dialogError = ref("");
const editConflict = ref(false);
const pendingImport = computed(
  () =>
    busy.value ||
    importQueue.rows.some((item) => !item.created) ||
    imageComposer.pages.length > 0,
);
useBeforeUnload(pendingImport);
useAdminLeaveGuard(
  () =>
    !active ||
    !pendingImport.value ||
    window.confirm("导入尚未完成，离开会停止当前队列。确认离开？"),
);
const form = ref<PublicationEdit>({
  ...defaultDownloadSettings(),
  revision: 1,
  title: "",
  description: "",
  category_id: "",
  status: "draft",
  featured: false,
  confirm_publication: false,
  view_access: "inherit",
  download_access: "inherit",
});
const accessOptions = [
  { label: "继承题型权限", value: "inherit" },
  { label: "普通用户与 VIP", value: "free" },
  { label: "仅 VIP 会员", value: "vip" },
];
watch(
  () => form.value.view_access,
  (value) => {
    if (value === "vip") form.value.download_access = "vip";
  },
);
const sourceQuery = ref("");
const sources = ref<CatalogSource[]>([]);
const sourceId = ref("");
const sourceMore = ref(false);
const sourceLoading = ref(false);
let sourceSequence = 0;
const sourceItems = computed(() =>
  sources.value.map((item) => ({
    value: item.id,
    label: `${item.title} · ${item.grade} · v${item.version}${item.file_status !== "ready" ? " · 文件未完成" : ""}`,
  })),
);
const mode = ref<"source" | "import" | "images" | "link">("source");
const gradeOptions = ref<{ label: string; value: string }[]>([]);
const subjectOptions = ref<{ label: string; value: string }[]>([]);
const dictionaryError = ref("");
const categoryError = ref("");
const dictionaryLoading = ref(false);
const categoryLoading = ref(false);
async function loadDictionaryOptions() {
  if (dictionaryLoading.value) return;
  dictionaryLoading.value = true;
  dictionaryError.value = "";
  try {
    const [grades, subjects] = await Promise.all([
      siteDictionary("grade"),
      siteDictionary("subject"),
    ]);
    gradeOptions.value = grades.items.map((item) => ({
      label: item.label || item.value,
      value: item.value,
    }));
    subjectOptions.value = subjects.items.map((item) => ({
      label: item.label || item.value,
      value: item.value,
    }));
  } catch {
    dictionaryError.value = "年级与科目加载失败，请重试后继续填写";
  } finally {
    dictionaryLoading.value = false;
  }
}
const publishing = computed(
  () =>
    !!target.value &&
    form.value.status === "published" &&
    target.value.status !== "published",
);
const importing = computed(
  () => !target.value && ["import", "images"].includes(mode.value),
);
const valid = computed(
  () =>
    !categoryLoading.value &&
    !categoryError.value &&
    (importing.value
      ? !dictionaryLoading.value &&
        !dictionaryError.value &&
        (mode.value === "images"
          ? imageComposer.ready &&
            !!imageFields.grade &&
            !!imageFields.subject &&
            !!imageFields.category_id &&
            !downloadSettingsIssue(form.value)
          : importQueue.pending.length > 0)
      : !!form.value.title.trim() &&
        !!form.value.category_id &&
        !downloadSettingsIssue(form.value) &&
        (!!target.value ||
          (mode.value === "link"
            ? !dictionaryLoading.value &&
              !dictionaryError.value &&
              !!imageFields.grade &&
              !!imageFields.subject
            : !!sourceId.value))) &&
    (!publishing.value || form.value.confirm_publication),
);
const categoryNames = computed(
  () => new Map(categories.value.map((item) => [item.value, item.label])),
);
const {
  preview,
  previewTarget,
  previewRole,
  previewOpen,
  previewLoading,
  previewError,
  previewPages,
  showPreview,
} = useCatalogPreview();
const removeTarget = ref<CatalogPaper | null>(null);
const removeOpen = ref(false);
const removeError = ref("");
const message = (cause: unknown) =>
  cause instanceof Error ? cause.message : "操作失败，请重试";
const date = (stamp: number) =>
  new Date(stamp * 1000).toLocaleString("zh-CN", { hour12: false });
const categoryText = (item: CatalogPaper) =>
  categoryNames.value.get(item.category_id || "") || item.category || "未分类";

async function loadCategories() {
  if (categoryLoading.value) return;
  categoryLoading.value = true;
  categoryError.value = "";
  try {
    categories.value = (await siteCategories()).items
      .filter((item) => item.is_visible)
      .map((item) => ({ label: item.name, value: item.id }));
  } catch {
    categoryError.value = "分类加载失败，请重试后继续填写";
  } finally {
    categoryLoading.value = false;
  }
}

async function load() {
  const current = ++sequence;
  loading.value = true;
  error.value = "";
  try {
    const result = await catalogList(
      q.value.trim(),
      status.value === "all" ? "" : status.value,
      (page.value - 1) * 20,
    );
    if (current !== sequence) return;
    items.value = result.items;
    total.value = result.total;
    if (!items.value.length && page.value > 1) {
      page.value--;
      return;
    }
    const resultStats = await catalogStats();
    if (current === sequence) stats.value = resultStats;
  } catch (cause) {
    if (current === sequence) error.value = message(cause);
  } finally {
    if (current === sequence) loading.value = false;
  }
}
const routeState = useAdminListRoute("papers", { q, status, page }, () => {
  void load();
});
function search() {
  if (routeState.restoring) return;
  if (page.value !== 1) page.value = 1;
  else void load();
}
watch(page, load);
watch(status, search);
onActivated(() => {
  active = true;
  void loadCategories();
  void load();
});
onDeactivated(() => {
  active = false;
  imageComposer.cancel();
  importQueue.stop();
  sequence++;
  sourceSequence++;
  loading.value = false;
  previewOpen.value = false;
  dialog.value = false;
  batchOpen.value = false;
  revisionOpen.value = false;
  metadataOpen.value = false;
  editionOpen.value = false;
});
onBeforeUnmount(() => {
  active = false;
  imageComposer.dispose();
  importQueue.stop();
});
async function openLinkedPaper() {
  const id = new URLSearchParams(adminRoute.query).get("paper");
  if (adminRoute.tab !== "papers" || !id) return;
  try {
    const item = await catalogDetail(id);
    if (
      adminRoute.tab === "papers" &&
      new URLSearchParams(adminRoute.query).get("paper") === id
    )
      await showPreview(item);
  } catch (cause) {
    if (
      adminRoute.tab === "papers" &&
      new URLSearchParams(adminRoute.query).get("paper") === id
    )
      error.value = message(cause);
  }
}
onActivated(openLinkedPaper);
watch(
  () => new URLSearchParams(adminRoute.query).get("paper"),
  openLinkedPaper,
);

async function loadSources(more = false) {
  const current = ++sourceSequence;
  sourceLoading.value = true;
  dialogError.value = "";
  try {
    const result = await catalogSources(
      sourceQuery.value.trim(),
      more ? sources.value.length : 0,
    );
    if (current !== sourceSequence) return;
    sources.value = more ? [...sources.value, ...result.items] : result.items;
    sourceMore.value = result.has_more;
  } catch (cause) {
    if (current === sourceSequence) dialogError.value = message(cause);
  } finally {
    if (current === sourceSequence) sourceLoading.value = false;
  }
}
function create() {
  if (busy.value) return;
  if (importQueue.rows.length && !target.value && mode.value === "import") {
    dialog.value = true;
    return;
  }
  if (imageComposer.pages.length && !target.value && mode.value === "images") {
    dialog.value = true;
    return;
  }
  target.value = null;
  mode.value = "source";
  sourceId.value = "";
  sourceQuery.value = "";
  sources.value = [];
  dialogError.value = "";
  dialogNotice.value = "";
  form.value = {
    ...defaultDownloadSettings(),
    revision: 1,
    title: "",
    description: "",
    category_id: categories.value[0]?.value || "",
    status: "draft",
    featured: false,
    confirm_publication: false,
    view_access: "inherit",
    download_access: "inherit",
  };
  dialog.value = true;
  void loadSources();
  void loadDictionaryOptions();
}
function edit(item: CatalogPaper) {
  if (busy.value) return;
  target.value = item;
  dialogError.value = "";
  dialogNotice.value = "";
  editConflict.value = false;
  form.value = {
    ...downloadPayload(item),
    revision: item.revision,
    title: item.title,
    description: item.description,
    category_id: item.category_id || "",
    status: item.status,
    featured: item.featured,
    confirm_publication: false,
    view_access: item.view_access,
    download_access: item.download_access,
  };
  dialog.value = true;
}
watch(sourceId, (id) => {
  const item = sources.value.find((source) => source.id === id);
  if (item) form.value.title = item.title;
});
async function save() {
  if (busy.value || !valid.value) return;
  if (!target.value && mode.value === "images") {
    await saveImages();
    return;
  }
  if (importing.value) {
    await runImport();
    return;
  }
  saving.value = true;
  dialogError.value = "";
  dialogNotice.value = "";
  try {
    if (target.value) {
      const result = await updatePublication(props.user.id, target.value.id, {
        ...form.value,
        ...downloadPayload(form.value),
        title: form.value.title.trim(),
      });
      target.value = result;
      form.value.revision = result.revision;
      form.value.title = result.title;
      form.value.confirm_publication = false;
      createdItems.value = createdItems.value.map((item) =>
        item.id === result.id ? result : item,
      );
      notice.value = dialogNotice.value = "公共习题已更新";
      await load();
    } else {
      const result = await createPublication(props.user.id, {
        ...downloadPayload(form.value),
        paper_id: mode.value === "link" ? "" : sourceId.value,
        ...(mode.value === "link"
          ? { grade: imageFields.grade, subject: imageFields.subject }
          : {}),
        title: form.value.title.trim(),
        description: form.value.description,
        category_id: form.value.category_id,
        view_access: form.value.view_access,
        download_access: form.value.download_access,
      });
      createdItems.value.unshift(result);
      notice.value = "已创建草稿，预览并确认后可发布";
      dialog.value = false;
      await load();
      await nextTick();
      createdPanel.value?.scrollIntoView?.({ block: "nearest" });
    }
  } catch (cause) {
    editConflict.value = cause instanceof ApiError && cause.status === 409;
    dialogError.value = message(cause);
  } finally {
    saving.value = false;
  }
}
async function reloadEdited() {
  if (!target.value) return;
  try {
    const latest = await catalogDetail(target.value.id);
    target.value = latest;
    form.value.revision = latest.revision;
    form.value.confirm_publication = false;
    editConflict.value = false;
    dialogNotice.value = "已载入最新版本，您的修改已保留，请核对后保存";
  } catch (cause) {
    dialogError.value = message(cause);
  }
}
async function runImport(retry = false) {
  if (
    busy.value ||
    categoryError.value ||
    dictionaryError.value ||
    categoryLoading.value ||
    dictionaryLoading.value
  )
    return;
  await importQueue.run(
    {
      description: form.value.description,
      view_access: form.value.view_access,
      download_access: form.value.download_access,
    },
    retry,
  );
  notice.value = `已创建 ${importQueue.succeeded} 份草稿，可预览并发布`;
  await load();
}
async function saveImages() {
  const title = imageComposer.title.trim();
  const file = await imageComposer.build();
  if (!file || !active) return;
  saving.value = true;
  dialogError.value = "";
  try {
    await importQueue.add([file], {
      ...imageFields,
      ...downloadPayload(form.value),
    });
    const row = importQueue.rows.find((item) => item.file === file);
    if (!row || row.fileError) {
      dialogError.value = row?.fileError || "PDF 未能加入导入清单，请重试";
      return;
    }
    row.meta.title = title;
    imageComposer.clear();
    mode.value = "import";
    if (!active) return;
    await importQueue.run(
      {
        description: form.value.description,
        view_access: form.value.view_access,
        download_access: form.value.download_access,
      },
      false,
      row.id,
    );
    notice.value = row.created
      ? "图片已合并成一份 PDF 并创建草稿，可预览并发布"
      : "PDF 已合并，请在导入清单中重试上传";
    await load();
  } catch (cause) {
    dialogError.value = message(cause);
  } finally {
    saving.value = false;
  }
}
function previewCreated(item: CatalogPaper) {
  dialog.value = false;
  void showPreview(item);
}
function tagCreated(item: CatalogPaper) {
  dialog.value = false;
  metadataTarget.value = item;
  metadataOpen.value = true;
}
async function locateCreated(item: CatalogPaper) {
  highlighted.value = item.id;
  q.value = item.title.slice(0, 120);
  status.value = "all";
  page.value = 1;
  await load();
}
function publishPreview() {
  if (preview.value) {
    previewOpen.value = false;
    edit(preview.value);
    form.value.status = "published";
  }
}
function askRemove(item: CatalogPaper) {
  removeTarget.value = item;
  removeError.value = "";
  removeOpen.value = true;
}
async function remove() {
  if (busy.value || !removeTarget.value) return;
  saving.value = true;
  removeError.value = "";
  try {
    await deletePublication(props.user.id, removeTarget.value);
    removeOpen.value = false;
    notice.value = "公共条目已删除，原始习题仍保留";
    await load();
  } catch (cause) {
    removeError.value = message(cause);
  } finally {
    saving.value = false;
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
          <strong>{{ item.title }}</strong>
          <div class="actions-row">
            <UButton
              label="预览并发布"
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
    <div class="data-scroll" :aria-busy="loading">
      <table class="data-table catalog-table">
        <thead>
          <tr>
            <th>
              <UCheckbox
                aria-label="选择当前页"
                :model-value="
                  !!items.length &&
                  items.every((item) => selectedIds.includes(item.id))
                "
                :disabled="loading"
                @update:model-value="selectPage"
              />
            </th>
            <th>习题</th>
            <th>分类</th>
            <th>发布状态</th>
            <th>收藏</th>
            <th>下载用户</th>
            <th>更新于</th>
            <th><span class="sr-only">操作</span></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in items"
            :key="item.id"
            :class="{ 'created-highlight': item.id === highlighted }"
          >
            <td>
              <UCheckbox
                :aria-label="'选择 ' + item.title"
                :model-value="selectedIds.includes(item.id)"
                :disabled="loading"
                @update:model-value="toggleSelection(item.id)"
              />
            </td>
            <td>
              <div class="catalog-paper">
                <img
                  v-if="item.thumbnail_url"
                  :src="item.thumbnail_url"
                  alt=""
                  class="catalog-thumb"
                  loading="lazy"
                /><UIcon
                  v-else
                  name="i-lucide-file-text"
                  class="size-9 text-dimmed"
                />
                <div>
                  <div class="catalog-name">
                    <span>{{ item.title }}</span
                    ><UIcon
                      v-if="item.featured"
                      name="i-lucide-pin"
                      class="catalog-featured size-3 text-primary"
                      title="优先展示"
                    />
                  </div>
                  <div class="catalog-meta">
                    {{ item.grade }} · {{ item.subject }} ·
                    {{
                      item.download_mode === "external"
                        ? "网盘资料"
                        : item.question_count + " 题"
                    }}
                    · 第 {{ item.release_number || 1 }} 版 · 原稿 v{{
                      item.version
                    }}
                  </div>
                  <div
                    v-if="
                      item.download_mode !== 'external' &&
                      item.file_status !== 'ready'
                    "
                    class="text-warning text-xs"
                  >
                    文件未完成
                  </div>
                </div>
              </div>
            </td>
            <td>
              {{ categoryText(item) }}
              <div v-if="!item.category_id" class="missing-category">
                未关联分类
              </div>
              <div class="access-caption">
                {{
                  item.required_view === "vip"
                    ? "VIP 专享"
                    : item.required_download === "vip"
                      ? "免费预览 · VIP 下载"
                      : "普通用户可用"
                }}
              </div>
            </td>
            <td>
              <UBadge
                :color="
                  item.status === 'published'
                    ? 'success'
                    : item.status === 'draft'
                      ? 'warning'
                      : 'neutral'
                "
                variant="soft"
                >{{ labels[item.status] }}</UBadge
              >
            </td>
            <td>{{ item.favorite_count || 0 }}</td>
            <td>{{ item.download_users || 0 }}</td>
            <td class="date-cell">{{ date(item.updated_at) }}</td>
            <td>
              <div class="actions-row">
                <UTooltip text="预览习题"
                  ><UButton
                    icon="i-lucide-eye"
                    color="neutral"
                    variant="ghost"
                    :aria-label="'预览 ' + item.title"
                    @click="showPreview(item)" /></UTooltip
                ><UTooltip text="编辑与发布"
                  ><UButton
                    icon="i-lucide-square-pen"
                    color="neutral"
                    variant="ghost"
                    :aria-label="'编辑 ' + item.title"
                    @click="edit(item)" /></UTooltip
                ><UTooltip text="教学标签"
                  ><UButton
                    icon="i-lucide-tags"
                    color="neutral"
                    variant="ghost"
                    :aria-label="'教学标签 ' + item.title"
                    @click="
                      metadataTarget = item;
                      metadataOpen = true;
                    " /></UTooltip
                ><UTooltip text="打印版本"
                  ><UButton
                    icon="i-lucide-file-stack"
                    color="neutral"
                    variant="ghost"
                    :aria-label="'打印版本 ' + item.title"
                    @click="
                      editionTarget = item;
                      editionOpen = true;
                    " /></UTooltip
                ><UTooltip text="更新修订稿"
                  ><UButton
                    icon="i-lucide-file-clock"
                    color="neutral"
                    variant="ghost"
                    :aria-label="'修订 ' + item.title"
                    @click="
                      revisionTarget = item;
                      revisionOpen = true;
                    " /></UTooltip
                ><UTooltip text="删除公共条目"
                  ><UButton
                    icon="i-lucide-trash-2"
                    color="error"
                    variant="ghost"
                    :aria-label="'删除公共条目 ' + item.title"
                    @click="askRemove(item)"
                /></UTooltip>
              </div>
            </td>
          </tr>
          <tr v-if="!items.length">
            <td colspan="8">
              <div class="empty-state">
                <UIcon
                  :name="
                    loading ? 'i-lucide-loader-circle' : 'i-lucide-library'
                  "
                  class="size-7"
                  :class="{ 'animate-spin': loading }"
                />
                <h3>
                  {{
                    loading
                      ? "正在加载"
                      : error
                        ? "习题列表暂不可用"
                        : "暂无公共习题"
                  }}
                </h3>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
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

    <UModal
      v-model:open="dialog"
      :title="
        target
          ? '编辑公共习题'
          : mode === 'images'
            ? '图片合成 PDF 习题'
            : mode === 'import'
              ? '导入 PDF 习题'
              : '添加习题草稿'
      "
      :ui="{ content: importing ? 'sm:max-w-5xl' : 'sm:max-w-xl' }"
      :dismissible="!busy"
      :close="!busy"
      ><template #body>
        <form id="publication-form" class="field-stack" @submit.prevent="save">
          <UAlert v-if="categoryError" :title="categoryError" color="error"
            ><template #actions
              ><UButton
                label="重试加载分类"
                :loading="categoryLoading"
                @click="loadCategories" /></template
          ></UAlert>
          <UAlert
            v-if="!target && mode !== 'source' && dictionaryError"
            :title="dictionaryError"
            color="error"
            ><template #actions
              ><UButton
                label="重试加载年级与科目"
                :loading="dictionaryLoading"
                @click="loadDictionaryOptions" /></template
          ></UAlert>
          <template v-if="!target">
            <div class="actions-row">
              <UButton
                label="选择工作台习题"
                size="sm"
                :variant="mode === 'source' ? 'solid' : 'outline'"
                :disabled="busy"
                @click="mode = 'source'"
              /><UButton
                label="手动导入 PDF"
                size="sm"
                :variant="mode === 'import' ? 'solid' : 'outline'"
                :disabled="busy"
                @click="mode = 'import'"
              /><UButton
                label="上传图片生成 PDF"
                size="sm"
                :variant="mode === 'images' ? 'solid' : 'outline'"
                :disabled="busy"
                @click="mode = 'images'"
              /><UButton
                label="仅添加网盘链接"
                size="sm"
                :variant="mode === 'link' ? 'solid' : 'outline'"
                :disabled="busy"
                @click="
                  mode = 'link';
                  form.download_mode = 'external';
                "
              />
            </div>
            <UFormField
              v-if="mode === 'source'"
              label="工作台已保存的习题"
              required
              ><div class="source-search">
                <UInput
                  v-model="sourceQuery"
                  placeholder="搜索自己的习题"
                  :disabled="busy"
                  @keydown.enter.prevent="loadSources()"
                /><UButton
                  icon="i-lucide-search"
                  aria-label="查找源习题"
                  color="neutral"
                  variant="outline"
                  :loading="sourceLoading"
                  @click="loadSources()"
                />
              </div>
              <USelect
                v-model="sourceId"
                :items="sourceItems"
                placeholder="选择习题"
                :disabled="busy || sourceLoading"
                class="w-full mt-2" /><UButton
                v-if="sourceMore"
                label="加载更多"
                icon="i-lucide-chevron-down"
                variant="link"
                :loading="sourceLoading"
                @click="loadSources(true)" /><UButton
                v-if="!sourceLoading && !sources.length"
                href="/"
                label="前往出题工作台"
                icon="i-lucide-arrow-up-right"
                variant="link"
            /></UFormField>
            <CatalogImportQueue
              v-else-if="mode === 'import'"
              :queue="importQueue"
              :grades="gradeOptions"
              :subjects="subjectOptions"
              :categories="categories"
              :options-loading="dictionaryLoading || categoryLoading"
              @preview="previewCreated"
              @metadata="tagCreated"
            />
            <template v-else-if="mode === 'images'">
              <ImagePdfComposer
                :composer="imageComposer"
                :disabled="saving || importQueue.busy"
              />
              <div class="image-metadata">
                <UFormField label="年级" required
                  ><USelect
                    v-model="imageFields.grade"
                    :items="gradeOptions"
                    aria-label="图片习题年级"
                    placeholder="选择年级"
                    :disabled="busy || dictionaryLoading"
                    class="w-full"
                /></UFormField>
                <UFormField label="科目" required
                  ><USelect
                    v-model="imageFields.subject"
                    :items="subjectOptions"
                    aria-label="图片习题科目"
                    placeholder="选择科目"
                    :disabled="busy || dictionaryLoading"
                    class="w-full"
                /></UFormField>
                <UFormField label="分类" required
                  ><USelect
                    v-model="imageFields.category_id"
                    :items="categories"
                    aria-label="图片习题分类"
                    placeholder="选择分类"
                    :disabled="busy || categoryLoading"
                    class="w-full"
                /></UFormField>
              </div>
              <UFormField label="图片内容类型"
                ><USelect
                  v-model="imageFields.mode"
                  :items="[
                    { value: 'student', label: '仅习题（练习版）' },
                    { value: 'withAnswers', label: '习题与答案' },
                    { value: 'answersOnly', label: '仅答案（答案解析版）' },
                  ]"
                  aria-label="图片内容类型"
                  :disabled="busy"
                  class="w-full"
              /></UFormField>
              <p class="text-xs text-muted">
                合并后上传一份 PDF，最大 32
                MB。上传失败可在导入清单重试，无需重新选择图片。
              </p>
            </template>
            <div v-else-if="mode === 'link'" class="image-metadata">
              <UFormField label="年级" required
                ><USelect
                  v-model="imageFields.grade"
                  :items="gradeOptions"
                  aria-label="网盘习题年级"
                  placeholder="选择年级"
                  :disabled="busy || dictionaryLoading"
                  class="w-full"
              /></UFormField>
              <UFormField label="科目" required
                ><USelect
                  v-model="imageFields.subject"
                  :items="subjectOptions"
                  aria-label="网盘习题科目"
                  placeholder="选择科目"
                  :disabled="busy || dictionaryLoading"
                  class="w-full"
              /></UFormField>
            </div>
          </template>
          <UFormField v-if="!importing" label="公开标题" required
            ><UInput
              v-model="form.title"
              maxlength="240"
              :disabled="busy"
              required
          /></UFormField>
          <UFormField
            v-if="!importing"
            label="分类"
            required
            hint="分类决定小程序首页专题入口与筛选器，可在「小程序管理 › 分类管理」里维护"
            ><USelect
              v-model="form.category_id"
              :items="categories"
              placeholder="选择分类"
              :disabled="busy"
              required
              class="w-full"
          /></UFormField>
          <DownloadSettings
            v-if="target || mode !== 'import'"
            :fields="form"
            :disabled="busy"
            :link-only="!target && mode === 'link'"
          />
          <p
            v-if="
              target?.download_mode === 'external' &&
              target.file_status !== 'ready'
            "
            class="text-xs text-muted"
          >
            这份资料尚无 PDF。若要改为 PDF
            下载，请先通过列表中的“修订”关联已就绪的原稿。
          </p>
          <UAlert
            v-if="!categoryLoading && !categoryError && !categories.length"
            color="warning"
            variant="soft"
            title="还没有可用的分类"
            description="请先到「小程序管理 › 分类管理」新建分类，再回来发布习题。"
          />
          <UFormField
            :label="importing ? '统一习题简介（应用到本次导入）' : '习题简介'"
            ><UTextarea
              v-model="form.description"
              maxlength="2000"
              :rows="3"
              :disabled="busy"
          /></UFormField>
          <template v-if="target"
            ><UFormField label="发布状态"
              ><USelect
                v-model="form.status"
                :items="statuses.slice(1)"
                :disabled="busy" /></UFormField
            ><USwitch v-model="form.featured" label="优先展示" :disabled="busy"
          /></template>
          <UFormField label="完整原稿观看"
            ><USelect
              v-model="form.view_access"
              :items="accessOptions"
              :disabled="busy"
              class="w-full"
          /></UFormField>
          <UFormField label="下载 / 获取链接权限"
            ><USelect
              v-model="form.download_access"
              :items="accessOptions"
              :disabled="busy || form.view_access === 'vip'"
              class="w-full"
          /></UFormField>
          <UAlert
            v-if="publishing"
            color="warning"
            variant="soft"
            title="发布后，习题、答案和文件按所设权限提供给小程序用户。请确认拥有发布权限且不含学生隐私。"
          />
          <p v-if="target" class="text-sm text-muted">
            当前已保存权限：{{
              target.required_view === "vip" ? "仅 VIP 可看" : "所有人可看"
            }}
            ·
            {{
              target.required_download === "vip"
                ? "仅 VIP 可下载"
                : "登录后可下载"
            }}。{{
              target.question_types?.length
                ? ""
                : "此资料无可继承题型；请选择明确的观看和下载权限。"
            }}
          </p>
          <p v-if="target" class="text-sm text-muted">
            内容复核：{{ target.reviewed_at ? "已记录人工确认" : "尚未记录" }} ·
            答案文件：{{
              answerReadiness[target.answer_readiness || "unknown"]
            }}。导入题量为申报值，请与文件逐页核对。
          </p>
          <UCheckbox
            v-if="target"
            v-model="form.confirm_publication"
            label="已核对内容，确认公开发布"
            :disabled="busy"
          />
          <UAlert
            v-if="dialogNotice"
            :title="dialogNotice"
            color="success"
            variant="soft"
          /><UButton
            v-if="editConflict"
            label="载入最新并保留我的修改"
            @click="reloadEdited"
          /><UAlert
            v-if="dialogError"
            :title="dialogError"
            color="error"
            variant="soft"
          /></form></template
      ><template #footer
        ><UButton
          :label="importing ? '完成并返回列表' : '关闭'"
          color="neutral"
          variant="outline"
          :disabled="busy"
          @click="dialog = false" /><UButton
          v-if="!target && mode === 'import' && importQueue.failed.length"
          :label="'仅重试失败项（' + importQueue.failed.length + '）'"
          color="warning"
          variant="outline"
          :disabled="
            busy ||
            !!categoryError ||
            !!dictionaryError ||
            categoryLoading ||
            dictionaryLoading
          "
          @click="runImport(true)" /><UButton
          type="submit"
          form="publication-form"
          :label="
            publishing
              ? '确认发布'
              : target
                ? '保存更改'
                : mode === 'images'
                  ? '合并图片并创建草稿'
                  : mode === 'import'
                    ? '导入待处理文件（' + importQueue.pending.length + '）'
                    : '创建草稿'
          "
          :loading="busy"
          :disabled="busy || !valid" /></template
    ></UModal>

    <UModal
      v-model:open="previewOpen"
      :title="preview?.title || '习题预览'"
      :ui="{ content: 'sm:max-w-3xl' }"
      ><template #body
        ><div v-if="previewLoading" class="empty-state">
          <UIcon name="i-lucide-loader-circle" class="size-6 animate-spin" />
        </div>
        <UAlert
          v-if="previewError"
          :title="previewError"
          color="error"
          variant="soft" />
        <div v-if="previewTarget" class="actions-row mb-4">
          <UButton
            v-for="role in [
              { value: 'admin', label: '管理员' },
              { value: 'regular', label: '普通用户' },
              { value: 'vip', label: 'VIP' },
            ]"
            :key="role.value"
            :label="role.label"
            :variant="previewRole === role.value ? 'solid' : 'outline'"
            :disabled="previewLoading"
            @click="showPreview(previewTarget, role.value)"
          />
        </div>
        <template v-if="preview"
          ><UAlert
            v-if="previewRole !== 'admin'"
            :title="
              (preview.can_view ? '可查看原稿' : '原稿受限') +
              ' · ' +
              (preview.can_download
                ? preview.download_mode === 'external'
                  ? '可获取网盘链接'
                  : '可下载 PDF'
                : '下载受限')
            "
            color="info"
            class="mb-4" /><UAlert
            v-if="previewRole !== 'admin' && !preview.can_view"
            title="普通用户查看这份资料需要 VIP，可切换 VIP 预览检查会员可见内容。"
            color="info"
            variant="soft" /><UAlert
            v-else-if="preview.download_mode === 'external'"
            title="网盘资料：小程序显示“获取网盘链接”，用户可复制链接与提取码。"
            color="info"
            variant="soft" /><UAlert
            v-else-if="!preview.assets.length"
            title="原卷文件尚未完成，请先在工作台重试文件。"
            color="warning"
            variant="soft" />
          <p
            v-if="
              previewRole === 'admin' &&
              preview.download_mode === 'external' &&
              preview.external_code
            "
            class="my-3 text-sm"
          >
            提取码：{{ preview.external_code }}
          </p>
          <div class="catalog-preview">
            <img
              v-for="asset in preview.assets
                .filter((asset) => asset.kind === 'page')
                .slice(0, previewPages)"
              :key="asset.id"
              :src="asset.url"
              :alt="'第 ' + asset.page_number + ' 页'"
            />
          </div>
          <UButton
            v-if="preview.can_view && preview.page_count > previewPages"
            label="更多页面"
            icon="i-lucide-chevron-down"
            variant="outline"
            @click="previewPages += 4" /></template></template
      ><template #footer
        ><UButton
          v-if="
            previewRole === 'admin' &&
            preview?.download_mode === 'external' &&
            preview.external_url
          "
          :href="preview.external_url"
          target="_blank"
          rel="noopener noreferrer"
          label="打开网盘链接"
          icon="i-lucide-external-link"
          color="neutral"
          variant="outline" /><UButton
          v-if="
            preview?.download_mode !== 'external' &&
            preview?.assets.some((asset) => asset.kind === 'pdf')
          "
          :href="preview.assets.find((asset) => asset.kind === 'pdf')?.url"
          label="下载 PDF"
          icon="i-lucide-download"
          color="neutral"
          variant="outline" /><UButton
          v-if="
            preview && previewRole === 'admin' && preview.status !== 'published'
          "
          label="核对后设置发布"
          :disabled="previewLoading || busy"
          @click="publishPreview" /><UButton
          label="关闭"
          @click="previewOpen = false" /></template
    ></UModal>

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
.image-metadata {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 600px) {
  .image-metadata {
    grid-template-columns: 1fr;
  }
}
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
.created-highlight {
  background: var(--ui-bg-accented);
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
.catalog-table {
  min-width: 940px;
}
.catalog-table th {
  position: relative;
}
.catalog-paper {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 240px;
}
.catalog-thumb {
  width: 40px;
  height: 56px;
  object-fit: cover;
  border: 1px solid var(--ui-border);
  flex: none;
}
.catalog-name {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  max-width: 300px;
  white-space: normal;
  overflow-wrap: anywhere;
}
.catalog-name > span:first-child {
  min-width: 0;
}
.catalog-featured {
  flex: none;
  margin-top: 3px;
}
.catalog-meta {
  margin-top: 5px;
  color: var(--ui-text-muted);
  font-size: 11px;
}
.access-caption {
  margin-top: 6px;
  color: var(--ui-text-muted);
  font-size: 11px;
  white-space: normal;
}
.missing-category {
  margin-top: 5px;
  color: var(--ui-warning);
  font-size: 11px;
}
.source-search {
  display: flex;
  gap: 8px;
}
.source-search > :first-child {
  flex: 1;
  min-width: 0;
}
.catalog-preview {
  display: grid;
  gap: 20px;
}
.catalog-preview img {
  display: block;
  width: 100%;
  height: auto;
  border: 1px solid var(--ui-border);
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
