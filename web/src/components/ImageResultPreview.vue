<script setup lang="ts">
import ImageQualityReview from './ImageQualityReview.vue'
import type { GeneratedPage } from '../image-batch'
import type { WorksheetImage } from '../image-generation'
defineProps<{
  pages: GeneratedPage[]
  selectedPage: number
  busy: boolean
  checking: boolean
  exportBusy: boolean
  singleBusy: boolean
  active: boolean
  followLatest: boolean
  imageUrl: string
  previewImageUrl: string
  watermarkPreview: string
  watermarkIssue: string
  result: WorksheetImage | null | undefined
}>()
const emit = defineEmits<{ select: [index: number]; zoom: []; regenerate: []; download: []; follow: [] }>()
const pageLabels = {
  queued: '待生成',
  running: '生成中',
  unknown: '待查询',
  failed: '未完成',
  ready: '已完成',
  expired: '已过期'
}
</script>

<template>
  <div v-if="pages.length > 1" class="image-pages" aria-label="图片列表">
    <button
      v-for="(page, index) in pages"
      :key="page.id"
      type="button"
      :aria-label="`第 ${index + 1} 张 · ${pageLabels[page.state]}`"
      :aria-pressed="selectedPage === index"
      :class="{ selected: selectedPage === index }"
      @click="emit('select', index)"
    >
      <img v-if="page.url" :src="page.url" alt="" loading="lazy" decoding="async" /><UIcon
        v-else
        :name="
          page.state === 'running'
            ? 'i-lucide-loader-circle'
            : page.state === 'failed' || page.state === 'unknown'
              ? 'i-lucide-circle-alert'
              : 'i-lucide-image'
        "
        class="size-5"
        :class="{ 'animate-spin': page.state === 'running' }"
      />
      <span
        >第 {{ index + 1 }} 张<small>{{ pageLabels[page.state] }}</small></span
      >
    </button>
  </div>
  <div class="image-result-tools">
    <div class="image-page-navigation">
      <UButton
        icon="i-lucide-chevron-left"
        aria-label="上一张图片"
        color="neutral"
        variant="ghost"
        :disabled="selectedPage === 0"
        @click="emit('select', selectedPage - 1)"
      /><span>{{ selectedPage + 1 }} / {{ pages.length }}</span
      ><UButton
        icon="i-lucide-chevron-right"
        aria-label="下一张图片"
        color="neutral"
        variant="ghost"
        :disabled="selectedPage >= pages.length - 1"
        @click="emit('select', selectedPage + 1)"
      />
    </div>
    <div class="image-result-actions">
      <UButton
        label="放大"
        icon="i-lucide-maximize"
        color="neutral"
        variant="ghost"
        :disabled="!imageUrl"
        @click="emit('zoom')"
      /><UButton
        label="重新生成本张"
        icon="i-lucide-refresh-cw"
        color="neutral"
        variant="outline"
        :loading="busy && pages[selectedPage]?.state === 'running'"
        :disabled="!imageUrl || busy || checking || exportBusy || !active"
        @click="emit('regenerate')"
      /><UButton
        label="下载本张"
        icon="i-lucide-image-down"
        color="neutral"
        variant="outline"
        :loading="singleBusy"
        :disabled="!imageUrl || !active || exportBusy || !!watermarkIssue"
        @click="emit('download')"
      />
    </div>
  </div>
  <UButton v-if="busy && !followLatest" label="跟随最新图片" color="neutral" variant="ghost" @click="emit('follow')" />
  <template v-if="imageUrl">
    <button class="image-zoom-target" type="button" aria-label="放大查看本张图片" @click="emit('zoom')">
      <img
        :src="previewImageUrl"
        :alt="`AI 生成的习题图片，第 ${selectedPage + 1} 张${watermarkPreview ? '，含水印预览' : ''}`"
        class="worksheet-image"
      />
    </button>
    <div class="image-result-caption">
      <span>{{ result?.width }} × {{ result?.height }} · PNG</span><span>使用前请核对文字、题目与答案准确性</span>
    </div>
    <ImageQualityReview :review="result?.quality_review" />
    <details class="image-result-prompt">
      <summary>查看本张生成说明</summary>
      <pre>{{ result?.prompt }}</pre>
    </details>
  </template>
  <div v-else class="image-empty">
    <UIcon
      :name="checking || pages[selectedPage]?.state === 'running' ? 'i-lucide-loader-circle' : 'i-lucide-image'"
      class="size-9"
      :class="{ 'animate-spin': checking || pages[selectedPage]?.state === 'running' }"
    />
    <h3>
      第 {{ selectedPage + 1 }} 张 · {{ checking ? '正在查询' : pageLabels[pages[selectedPage]?.state || 'queued'] }}
    </h3>
    <p>
      {{
        pages[selectedPage]?.state === 'queued'
          ? '按顺序生成，完成后会显示在这里。'
          : pages[selectedPage]?.state === 'running'
            ? '图片正在生成，请稍候。'
            : '在上方确认生成状态后，即可继续。'
      }}
    </p>
    <p v-if="pages[selectedPage]?.error" role="alert" class="image-batch-error">{{ pages[selectedPage]?.error }}</p>
  </div>
</template>
