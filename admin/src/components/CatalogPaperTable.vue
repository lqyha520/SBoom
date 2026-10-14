<script setup lang="ts">
import { computed } from 'vue'
import type { CatalogPaper } from '../catalog'
import { publicationLabels as labels } from '../publication-editor'

const props = defineProps<{
  items: CatalogPaper[]
  selectedIds: string[]
  categories: { label: string; value: string }[]
  loading: boolean
  error: string
  highlighted: string
}>()
const emit = defineEmits<{
  select: [id: string]
  selectPage: [checked: boolean | 'indeterminate']
  preview: [item: CatalogPaper]
  edit: [item: CatalogPaper]
  metadata: [item: CatalogPaper]
  edition: [item: CatalogPaper]
  revision: [item: CatalogPaper]
  remove: [item: CatalogPaper]
}>()
const categoryNames = computed(
  () => new Map(props.categories.map((item) => [item.value, item.label])),
)
const categoryText = (item: CatalogPaper) =>
  categoryNames.value.get(item.category_id || '') || item.category || '未分类'
const date = (stamp: number) =>
  new Date(stamp * 1000).toLocaleString('zh-CN', { hour12: false })
const moreActions = (item: CatalogPaper) => [
  [
    {
      label: '教学标签',
      icon: 'i-lucide-tags',
      onSelect: () => emit('metadata', item),
    },
    {
      label: '打印版本',
      icon: 'i-lucide-file-stack',
      onSelect: () => emit('edition', item),
    },
    {
      label: '更新修订稿',
      icon: 'i-lucide-file-clock',
      onSelect: () => emit('revision', item),
    },
  ],
  [
    {
      label: '删除公共条目',
      icon: 'i-lucide-trash-2',
      color: 'error' as const,
      onSelect: () => emit('remove', item),
    },
  ],
]
</script>

<template>
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
              @update:model-value="emit('selectPage', $event)"
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
          <td class="catalog-selection">
            <UCheckbox
              :aria-label="'选择 ' + item.title"
              :model-value="selectedIds.includes(item.id)"
              :disabled="loading"
              @update:model-value="emit('select', item.id)"
            />
          </td>
          <td class="catalog-main">
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
                    item.download_mode === 'external'
                      ? '网盘资料'
                      : item.question_count + ' 题'
                  }}
                  · 第 {{ item.release_number || 1 }} 版
                </div>
                <div class="catalog-mobile-meta">
                  {{ categoryText(item) }} · 收藏
                  {{ item.favorite_count || 0 }} · 下载
                  {{ item.download_users || 0 }}
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
          <td class="catalog-extra">
            {{ categoryText(item) }}
            <div v-if="!item.category_id" class="missing-category">
              未关联分类
            </div>
            <div class="access-caption">
              {{
                item.required_view === 'vip'
                  ? 'VIP 专享'
                  : item.required_download === 'vip'
                    ? '免费预览 · VIP 下载'
                    : '普通用户可用'
              }}
            </div>
          </td>
          <td class="catalog-status">
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
          <td class="catalog-extra">{{ item.favorite_count || 0 }}</td>
          <td class="catalog-extra">{{ item.download_users || 0 }}</td>
          <td class="date-cell catalog-extra">{{ date(item.updated_at) }}</td>
          <td class="catalog-actions">
            <div class="actions-row catalog-row-actions">
              <UTooltip text="预览"><UButton
                icon="i-lucide-eye"
                color="neutral"
                variant="ghost"
                :aria-label="'预览 ' + item.title"
                @click="emit('preview', item)"
              /></UTooltip>
              <UTooltip text="编辑"><UButton
                icon="i-lucide-square-pen"
                color="neutral"
                variant="ghost"
                :aria-label="'编辑 ' + item.title"
                @click="emit('edit', item)"
              /></UTooltip>
              <UDropdownMenu :items="moreActions(item)"
                ><UButton
                  icon="i-lucide-ellipsis"
                  color="neutral"
                  variant="ghost"
                  :aria-label="'更多操作 ' + item.title"
              /></UDropdownMenu>
            </div>
          </td>
        </tr>
        <tr v-if="!items.length">
          <td colspan="8">
            <div class="empty-state">
              <UIcon
                :name="loading ? 'i-lucide-loader-circle' : 'i-lucide-library'"
                class="size-7"
                :class="{ 'animate-spin': loading }"
              />
              <h3>
                {{
                  loading
                    ? '正在加载'
                    : error
                      ? '习题列表暂不可用'
                      : '暂无公共习题'
                }}
              </h3>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.created-highlight {
  background: var(--ui-bg-accented);
}
.catalog-table {
  min-width: 820px;
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
  border-radius: 5px;
  box-shadow: 0 3px 8px #183e3212;
  transition: transform .2s, box-shadow .2s;
  flex: none;
}
.catalog-paper:hover .catalog-thumb { transform:translateY(-2px) rotate(-2deg);box-shadow:0 5px 12px #183e3220; }
.catalog-name {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 14px;
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
  font-size: 12px;
}
.access-caption {
  margin-top: 6px;
  color: var(--ui-text-muted);
  font-size: 12px;
  white-space: normal;
}
.missing-category {
  margin-top: 5px;
  color: var(--ui-warning);
  font-size: 12px;
}
.catalog-mobile-meta,
.catalog-mobile-actions {
  display: none;
}
@media (max-width: 767px) {
  .catalog-table {
    display: block;
    min-width: 0;
  }
  .catalog-table thead,
  .catalog-table tbody {
    display: block;
  }
  .catalog-table thead tr {
    display: block;
    padding: 12px 8px;
  }
  .catalog-table thead th {
    display: none;
    padding: 0;
  }
  .catalog-table thead th:first-child {
    display: block;
  }
  .catalog-table tbody tr {
    display: grid;
    grid-template-columns: 28px minmax(0, 1fr);
    gap: 10px 8px;
    padding: 16px 8px;
    border-top: 1px solid var(--ui-border);
  }
  .catalog-table td {
    min-width: 0;
    padding: 0;
    border: 0;
    white-space: normal;
  }
  .catalog-table .catalog-extra,
  .catalog-desktop-actions {
    display: none;
  }
  .catalog-selection {
    grid-column: 1;
    grid-row: 1;
    padding-top: 2px !important;
  }
  .catalog-main {
    grid-column: 2;
    grid-row: 1;
  }
  .catalog-status,
  .catalog-actions {
    grid-column: 2;
  }
  .catalog-paper {
    min-width: 0;
    align-items: flex-start;
    gap: 8px;
  }
  .catalog-paper > div {
    min-width: 0;
  }
  .catalog-name {
    max-width: none;
  }
  .catalog-meta {
    line-height: 1.6;
  }
  .catalog-mobile-meta {
    display: block;
    margin-top: 4px;
    color: var(--ui-text-muted);
    font-size: 12px;
    overflow-wrap: anywhere;
  }
  .catalog-mobile-actions {
    display: flex;
    flex-wrap: wrap;
  }
  .catalog-mobile-actions button {
    min-height: 44px;
    min-width: 44px;
  }
  .catalog-table td[colspan] {
    grid-column: 1 / -1;
  }
}
</style>
