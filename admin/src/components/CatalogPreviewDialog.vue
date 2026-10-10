<script setup lang="ts">
import EditorPanel from './EditorPanel.vue'
import { toRefs, type UnwrapNestedRefs } from 'vue'
import type { useCatalogPreview } from '../catalog-preview'

const props = defineProps<{
  state: UnwrapNestedRefs<ReturnType<typeof useCatalogPreview>>
  busy: boolean
  inline?: boolean
}>()
const emit = defineEmits<{ publish: [] }>()
const {
  preview,
  previewTarget,
  previewRole,
  previewOpen,
  previewLoading,
  previewError,
  previewPages,
  showPreview,
} = toRefs(props.state)
</script>

<template>
  <EditorPanel :inline="inline"
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
        @click="emit('publish')" /><UButton
        v-if="!inline"
        label="关闭"
        @click="previewOpen = false" /></template
  ></EditorPanel>
</template>

<style scoped>
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
</style>
