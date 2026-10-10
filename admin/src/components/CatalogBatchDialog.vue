<script setup lang="ts">
import { useDialogDraft } from "../dialog-draft";
import { computed, ref, watch } from "vue";
import { catalogDetail, type CatalogPaper } from "../catalog";
import { ApiError } from "../api";
import { batchCatalog } from "../experience";
import { getTags, tagKinds, type CatalogTag, type TagKind } from "../growth";
const props = defineProps<{
  open: boolean;
  adminId: number;
  items: CatalogPaper[];
  categories: { value: string; label: string }[];
}>();
const emit = defineEmits<{ close: []; saved: [count: number] }>();
const action = ref("category");
const category = ref("");
const viewAccess = ref("inherit");
const downloadAccess = ref("inherit");
const confirmed = ref(false);
const busy = ref(false);
const error = ref("");
const policies = [
  { label: "继承题型权限", value: "inherit" },
  { label: "普通用户与 VIP", value: "free" },
  { label: "仅 VIP", value: "vip" },
];
const tags = ref<CatalogTag[]>([]);
const tagsLoading = ref(false),
  tagsError = ref(""),
  conflict = ref(false);
const refreshed = ref<CatalogPaper[] | null>(null);
let tagSequence = 0;
async function loadTags() {
  const current = ++tagSequence;
  tagsLoading.value = true;
  tagsError.value = "";
  try {
    const result = await getTags();
    if (current !== tagSequence) return;
    tags.value = result.items;
    knowledge.value = result.items.filter((item) => item.kind === "knowledge");
  } catch (cause) {
    if (current === tagSequence)
      tagsError.value = cause instanceof Error ? cause.message : "标签加载失败";
  } finally {
    if (current === tagSequence) tagsLoading.value = false;
  }
}
async function reloadSelected() {
  busy.value = true;
  try {
    const latest: CatalogPaper[] = [];
    for (const item of props.items) latest.push(await catalogDetail(item.id));
    refreshed.value = latest;
    conflict.value = false;
    error.value = "已载入最新版本，所选操作已保留，请核对后应用";
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : "加载失败";
  } finally {
    busy.value = false;
  }
}
type SingleTagKind = Exclude<TagKind, "knowledge">;
const singleKinds = tagKinds.filter(
  (item): item is { value: SingleTagKind; label: string } =>
    item.value !== "knowledge",
);
const singles = ref<Record<SingleTagKind, string>>({
  textbook: "",
  term: "",
  unit: "",
});
const knowledgePicked = ref<string[]>([]);
const knowledgeQuery = ref("");
const knowledge = ref<CatalogTag[]>([]);
watch(
  () => props.open,
  () => {
    tagSequence++;
    tagsLoading.value = false;
    refreshed.value = null;
    conflict.value = false;
    action.value = "category";
    category.value = "";
    viewAccess.value = "inherit";
    downloadAccess.value = "inherit";
    confirmed.value = false;
    error.value = "";
    singles.value = { textbook: "", term: "", unit: "" };
    knowledgePicked.value = [];
    knowledgeQuery.value = "";
    draft.markSaved();
  },
);
watch(action, (value) => {
  confirmed.value = false;
  if (value === "tags") void loadTags();
});
watch(knowledgeQuery, (value) => {
  const query = value.trim().toLowerCase();
  knowledge.value = tags.value.filter(
    (item) =>
      item.kind === "knowledge" && item.name.toLowerCase().includes(query),
  );
});
watch(viewAccess, (value) => {
  if (value === "vip") downloadAccess.value = "vip";
});
function tagOptions(kind: TagKind) {
  return [
    { value: "", label: "不修改" },
    ...tags.value
      .filter((item) => item.kind === kind)
      .map((item) => ({
        value: item.id,
        label: item.name + (item.is_visible ? "" : "（隐藏）"),
      })),
  ];
}
function toggleKnowledge(id: string, checked: boolean | "indeterminate") {
  if (checked === true && knowledgePicked.value.length >= 20) {
    error.value = "每份资料最多选择 20 个知识点";
    return;
  }
  knowledgePicked.value =
    checked === true
      ? [...knowledgePicked.value, id]
      : knowledgePicked.value.filter((value) => value !== id);
}
function tagIds(): string[] {
  const ids: string[] = [];
  for (const { value: kind } of singleKinds)
    if (singles.value[kind]) ids.push(singles.value[kind]);
  return [...ids, ...knowledgePicked.value];
}
async function save() {
  if (busy.value || !props.items.length) return;
  if (props.items.length > 50) {
    error.value = "每批最多 50 份资料";
    return;
  }
  if (action.value === "tags" && (tagsLoading.value || tagsError.value)) return;
  if (
    action.value === "tags" &&
    (refreshed.value || props.items).some(
      (item) =>
        new Set([
          ...(item.tags || [])
            .filter((tag) => tag.kind === "knowledge")
            .map((tag) => tag.id),
          ...knowledgePicked.value,
        ]).size > 20,
    )
  ) {
    error.value = "部分资料合并后超过 20 个知识点，请减少选择";
    return;
  }
  if (action.value === "published" && !confirmed.value) {
    error.value = "请先确认发布";
    return;
  }
  if (action.value === "category" && !category.value) {
    error.value = "请选择目标分类";
    return;
  }
  if (action.value === "tags" && !tagIds().length) {
    error.value = "请至少选择一个要设置的标签";
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    const result = await batchCatalog(
      props.adminId,
      refreshed.value || props.items,
      {
        action: action.value,
        category_id: category.value,
        view_access: viewAccess.value,
        download_access: downloadAccess.value,
        confirm_publication: confirmed.value,
        tag_ids: tagIds(),
      },
    );
    emit("saved", result.updated);
    emit("close");
  } catch (cause) {
    conflict.value = cause instanceof ApiError && cause.status === 409;
    error.value = cause instanceof Error ? cause.message : "批量操作失败";
  } finally {
    busy.value = false;
  }
}
const draft = useDialogDraft(computed({ get: () => props.open, set: value => { if (!value) emit('close') } }), () => [action.value, category.value, viewAccess.value, downloadAccess.value, confirmed.value, singles.value, knowledgePicked.value], busy, '批量操作');
</script>
<template>
  <UModal
    :open="open"
    title="批量管理资料"
    :dismissible="!busy"
    :close="!busy"
    :ui="{ content: 'max-w-3xl' }"
    @update:open="draft.setOpen($event)"
    ><template #body
      ><form id="batch-catalog" class="field-stack" @submit.prevent="save">
        <p>已选择 {{ items.length }} 份资料</p>
        <USelect
          v-model="action"
          aria-label="批量操作类型"
          :items="[
            { label: '修改分类', value: 'category' },
            { label: '批量打标签', value: 'tags' },
            { label: '发布', value: 'published' },
            { label: '下架', value: 'withdrawn' },
            { label: '修改访问权限', value: 'access' },
          ]"
        /><UFormField v-if="action === 'category'" label="目标分类"
          ><USelect
            v-model="category"
            :items="categories"
            :disabled="!categories.length"
            placeholder="选择分类"
          />
          <p v-if="!categories.length" class="text-sm text-muted mt-2">
            暂无可用分类，请先到「分类管理」创建并展示一个分类。
          </p></UFormField
        ><template v-if="action === 'tags'"
          ><p v-if="tagsLoading" role="status">正在加载标签</p>
          <UAlert v-if="tagsError" :title="tagsError" color="error" /><UButton
            v-if="tagsError"
            label="重试加载标签"
            @click="loadTags"
          />
          <div class="tag-single-grid">
            <UFormField
              v-for="kind in singleKinds"
              :key="kind.value"
              :label="kind.label + '（不选则保留原值）'"
              ><USelect
                v-model="singles[kind.value]"
                :items="tagOptions(kind.value)"
                class="w-full"
            /></UFormField>
          </div>
          <UFormField label="知识点（追加到所选资料，合并后每份最多 20 个）"
            ><UInput
              v-model="knowledgeQuery"
              placeholder="搜索知识点"
              class="w-full mb-3"
            />
            <div class="knowledge-options">
              <UCheckbox
                v-for="tag in knowledge"
                :key="tag.id"
                :label="tag.name + (tag.is_visible ? '' : '（隐藏）')"
                :model-value="knowledgePicked.includes(tag.id)"
                :disabled="busy"
                @update:model-value="toggleKnowledge(tag.id, $event)"
              />
              <p
                v-if="!tagsLoading && !tagsError && !knowledge.length"
                class="text-sm text-muted"
              >
                暂无匹配知识点，请先在「教材与知识点」中添加。
              </p>
            </div></UFormField
          >
          <p class="text-sm text-muted">
            单选类标签会覆盖所选资料的原有同类标签；知识点在原有基础上追加。任一资料合并后超限，整批取消。
          </p></template
        ><template v-if="action === 'access'"
          ><UFormField label="原稿观看"
            ><USelect v-model="viewAccess" :items="policies" /></UFormField
          ><UFormField label="下载 / 获取链接权限"
            ><USelect
              v-model="downloadAccess"
              :items="policies"
              :disabled="viewAccess === 'vip'" /></UFormField></template
        ><UCheckbox
          v-if="action === 'published'"
          v-model="confirmed"
          label="已核对所选资料原稿与普通用户/VIP 权限，确认发布"
        />
        <p class="text-sm text-muted">
          若有资料被其他管理员修改，本批操作会整体取消；发布操作还会检查 PDF
          或网盘链接是否就绪。
        </p>
        <UButton
          v-if="conflict"
          label="载入最新并保留我的修改"
          @click="reloadSelected"
        /><UAlert v-if="error" :title="error" color="error" /></form></template
    ><template #footer
      ><UButton
        label="取消"
        color="neutral"
        variant="outline"
        :disabled="busy"
        @click="draft.setOpen(false)" /><UButton
        label="应用到所选资料"
        type="submit"
        form="batch-catalog"
        :loading="busy"
        :disabled="
          (action === 'tags' && (tagsLoading || !!tagsError)) ||
          !items.length ||
          (action === 'published' && !confirmed) ||
          (action === 'category' && !category)
        " /></template
  ></UModal>
</template>
<style scoped>
.tag-single-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.knowledge-options {
  display: grid;
  gap: 12px;
  max-height: 180px;
  overflow: auto;
}
@media (max-width: 600px) {
  .tag-single-grid {
    grid-template-columns: 1fr;
  }
}
</style>
