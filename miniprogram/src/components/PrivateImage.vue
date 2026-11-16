<script setup lang="ts">
import { getCurrentInstance, onMounted, onUnmounted, ref, watch } from 'vue'
import { acquireAsset } from '../services/assets'
import type { FileHandle } from '../services/file-pool'
const props = withDefaults(defineProps<{ src: string | null; placeholderSrc?: string | null; preview?: boolean; label?: string; lazy?: boolean; fit?: boolean; crop?: boolean; active?: boolean; priority?: number }>(), { active: true, priority: 1 })
const emit = defineEmits<{ load: [] }>()
const instance = getCurrentInstance()
const visible = ref(!props.lazy)
let observer: UniApp.IntersectionObserver | undefined
const source = ref('')
const loaded = ref(false)
const failed = ref(false)
const progress = ref(0)
const waiting = ref(false)
let waitTimer: ReturnType<typeof setTimeout> | undefined
let retryOnReconnect = false
let sequence = 0
let disposed = false
let handle: FileHandle | null = null
let placeholderHandle: FileHandle | null = null
let placeholderSequence = 0
const placeholder = ref('')
let startedAt = 0
function clearWait() { clearTimeout(waitTimer); waitTimer = undefined; waiting.value = false }
function waitForImage() {
  clearWait()
  if ((props.priority ?? 1) < 2 || loaded.value || !props.src || !visible.value || props.active === false) return
  waitTimer = setTimeout(() => { if (!disposed && !loaded.value) waiting.value = true }, 800)
  ;(waitTimer as unknown as { unref?: () => void }).unref?.()
}
function clearPlaceholder() {
  placeholderSequence++
  placeholderHandle?.release(); placeholderHandle = null
  placeholder.value = ''
}
async function loadPlaceholder() {
  clearPlaceholder()
  if (disposed || loaded.value || !visible.value || props.active === false || !props.src || !props.placeholderSrc || props.placeholderSrc === props.src) return
  const run = placeholderSequence
  placeholderHandle = acquireAsset(props.placeholderSrc, props.priority)
  try { const value = await placeholderHandle.ready; if (run === placeholderSequence) placeholder.value = value }
  catch { /* 缩略图失败不影响原图及重试。 */ }
}
async function load() {
  if (disposed) return
  const run = ++sequence
  handle?.release()
  handle = null
  failed.value = false
  retryOnReconnect = false; progress.value = 0
  clearWait()
  loaded.value = false
  source.value = ''
  clearPlaceholder()
  if (!props.src || !visible.value || props.active === false) return
  startedAt = Date.now()
  handle = acquireAsset(props.src, props.priority, percent => {
    if (run !== sequence || disposed) return
    // 百分比按 5% 更新，避免原生下载进度逐帧回传。
    progress.value = Math.floor(percent / 5) * 5
  })
  waitForImage()
  void loadPlaceholder()
  try { const value = await handle.ready; if (run === sequence) source.value = value }
  catch (cause) {
    if (run === sequence) {
      failed.value = true; clearWait()
      const status = Number((cause as { status?: number } | null)?.status) || 0
      retryOnReconnect = status === 0 || status >= 500
    }
  }
}
watch([() => props.src, () => props.active], load, { immediate: true })
watch(() => props.placeholderSrc, loadPlaceholder)
watch(() => props.priority, priority => {
  handle?.prioritize?.(priority)
  placeholderHandle?.prioritize?.(priority)
  // 相邻页已解码时，成为当前页无需等待第二次原生 load 事件。
  if (priority >= 2 && loaded.value) emit('load')
  else waitForImage()
})
function imageLoaded() {
  loaded.value = true
  clearWait(); retryOnReconnect = false
  clearPlaceholder()
  emit('load')
  if (props.priority >= 2) uni.$emit?.('lc-performance', { kind: 'reader_image', value: Date.now() - startedAt })
}
onMounted(() => {
  uni.$on?.('lc-network-restored', reconnect)
  if (visible.value) return
  const reveal = () => { if (disposed || visible.value) return; visible.value = true; void load() }
  try {
    observer = uni.createIntersectionObserver(instance?.proxy, { thresholds: [0] })
    observer.relativeToViewport({ top: 400, bottom: 400 }).observe('.private-image', result => {
      if (disposed) return
      if (result.intersectionRatio > 0) reveal()
      else if (visible.value) { visible.value = false; sequence++; handle?.release(); handle = null; clearWait(); clearPlaceholder(); source.value = ''; loaded.value = false; failed.value = false }
    })
  } catch { reveal() }
})
onUnmounted(() => { disposed = true; observer?.disconnect(); sequence++; handle?.release(); clearWait(); clearPlaceholder(); if (typeof uni !== 'undefined') uni.$off?.('lc-network-restored', reconnect) })
function reconnect() {
  if (!disposed && props.active !== false && visible.value && props.priority >= 2 && failed.value && retryOnReconnect) void load()
}
function imageFailed() {
  handle?.invalidate()
  handle?.release()
  handle = null
  loaded.value = false
  failed.value = true
  clearWait(); retryOnReconnect = false
  source.value = ''
}
function tap() {
  if (failed.value) { void load(); return }
  if (props.preview && source.value) uni.previewImage({ urls: [source.value], current: source.value })
}
</script>

<template>
  <view class="private-image" :class="{ fit }" :role="preview || failed ? 'button' : 'img'" :tabindex="preview || failed ? 0 : -1" :aria-label="failed ? '重试加载预览图' : label || (preview ? '放大习题预览' : '习题封面')" @click="tap" @keydown.enter="tap">
    <view v-if="!loaded" class="placeholder"><image v-if="placeholder" :src="placeholder" :mode="crop ? 'aspectFill' : 'aspectFit'" class="placeholder-image" /><text v-if="failed" class="retry-mark">↻</text><view v-else-if="!placeholder" class="placeholder-paper" /></view>
    <image v-if="source" :src="source" :mode="crop ? 'aspectFill' : 'aspectFit'" class="image" :class="{ 'is-loaded': loaded }" @error="imageFailed" @load="imageLoaded" />
    <view v-if="!loaded && (placeholder || (priority >= 2 && (waiting || failed)))" class="image-status" role="status">{{ failed ? '图片加载失败，点击重试' : progress >= 100 ? '正在显示清晰原图…' : progress > 0 ? '正在加载清晰原图 ' + progress + '%' : '正在加载清晰原图…' }}</view>
    <view v-if="preview && source" class="zoom-badge" aria-hidden="true"><wd-icon name="fullscreen" size="17px" /></view>
  </view>
</template>

<style scoped>
.private-image { position: relative; width: 100%; height: 0; padding-bottom: 141.43%; background: #fff; overflow: hidden; }
.private-image.fit { height:100%;padding-bottom:0; }
.image, .placeholder { position: absolute; inset: 0; width: 100%; height: 100%; }
.placeholder-image { width:100%;height:100%; }
.image-status { position:absolute;bottom:12px;left:50%;transform:translateX(-50%);padding:5px 10px;border-radius:6px;background:#ffffffe8;color:#74849f;font-size:12px;white-space:nowrap;pointer-events:none; }
.image { opacity: 0; transition: opacity .24s ease; }
.image.is-loaded { opacity: 1; }
.placeholder { display: flex; align-items: center; justify-content: center; background: #f7faf8; }
.placeholder-paper { width:21px;height:28px;border:2px solid #acb9af;border-radius:2px;background:repeating-linear-gradient(to bottom,transparent 0,transparent 5px,#dbe3de 5px,#dbe3de 7px); }.retry-mark { color:#acb9af;font-size:26px; }
.zoom-badge { position: absolute; top: 10px; right: 10px; width: 31px; height: 31px; display: flex; align-items: center; justify-content: center; color: #74849f; background: #fff; border: 1px solid #e6ebf2; border-radius: 4px; pointer-events: none; }
</style>
