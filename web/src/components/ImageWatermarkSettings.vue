<script setup lang="ts">
import {
  MAX_WATERMARK_LINE_LENGTH,
  MAX_WATERMARK_LINES,
  MAX_WATERMARK_TEXT_LENGTH,
  WATERMARK_LAYOUTS,
  WATERMARK_POSITIONS,
  type WatermarkLayout,
  type WatermarkPosition
} from '../image-watermark'
defineProps<{
  disabled: boolean
  watermarkIssue: string
  watermarkPreviewError: string
  watermarkPreviewBusy: boolean
  watermarkPreview: string
}>()
const watermarkEnabled = defineModel<boolean>('enabled', { required: true })
const watermarkLabel = defineModel<string>('text', { required: true })
const watermarkPosition = defineModel<WatermarkPosition>('position', { required: true })
const watermarkLayout = defineModel<WatermarkLayout>('layout', { required: true })
const watermarkTransparency = defineModel<number>('transparency', { required: true })
</script>

<template>
  <fieldset class="image-watermark-settings" :disabled="disabled" aria-label="下载水印设置">
    <USwitch v-model="watermarkEnabled" label="下载时添加文字水印" :disabled="disabled" />
    <template v-if="watermarkEnabled">
      <label for="image-watermark-text">水印文字</label>
      <UTextarea
        id="image-watermark-text"
        v-model="watermarkLabel"
        placeholder="例如：王老师的数学课堂&#10;仅供学习使用"
        :rows="3"
        :maxlength="MAX_WATERMARK_TEXT_LENGTH"
        :aria-invalid="!!watermarkIssue"
        aria-describedby="image-watermark-hint"
        class="w-full"
      />
      <label class="image-watermark-position"
        >水印布局
        <select v-model="watermarkLayout" aria-label="水印布局">
          <option v-for="layout in WATERMARK_LAYOUTS" :key="layout.value" :value="layout.value">
            {{ layout.label }}
          </option>
        </select>
      </label>
      <label v-if="watermarkLayout === 'single'" class="image-watermark-position"
        >水印位置
        <select v-model="watermarkPosition" aria-label="水印位置">
          <option v-for="position in WATERMARK_POSITIONS" :key="position.value" :value="position.value">
            {{ position.label }}
          </option>
        </select>
      </label>
      <label for="image-watermark-transparency" class="image-watermark-opacity-label"
        >水印透明度 <span>{{ watermarkTransparency }}%</span></label
      >
      <input
        id="image-watermark-transparency"
        v-model.number="watermarkTransparency"
        type="range"
        min="0"
        max="100"
        step="1"
        :aria-valuetext="`${watermarkTransparency}%，${watermarkTransparency === 100 ? '完全透明' : '数值越大水印越淡'}`"
        aria-describedby="image-watermark-opacity-hint"
        class="image-watermark-opacity"
      />
      <p id="image-watermark-opacity-hint" class="image-field-hint">
        0% 最清晰，100% 完全透明。{{ watermarkTransparency === 100 ? '当前下载不显示水印。' : '' }}
      </p>
      <p id="image-watermark-hint" class="image-field-hint">
        支持换行，最多 {{ MAX_WATERMARK_LINES }} 行，每行 {{ MAX_WATERMARK_LINE_LENGTH }} 个字符。适用于单张、批量图片和
        PDF 下载；云端保存与后台草稿保留原图。
      </p>
      <p v-if="watermarkIssue" role="alert" class="text-error">{{ watermarkIssue }}</p>
      <p v-else-if="watermarkPreviewError" role="alert" class="text-error">{{ watermarkPreviewError }}</p>
      <p v-else-if="watermarkPreviewBusy" role="status" class="image-field-hint">正在更新水印预览…</p>
      <p v-else-if="watermarkPreview" role="status" class="image-field-hint">下方为水印效果预览，可放大查看。</p>
    </template>
  </fieldset>
</template>
