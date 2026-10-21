<script setup lang="ts">
import { getCurrentInstance, onMounted, onUnmounted, ref, watch } from 'vue'
import { acquireAsset } from '../services/assets'
import type { FileHandle } from '../services/file-pool'
const props = withDefaults(defineProps<{ src: string | null; preview?: boolean; label?: string; lazy?: boolean; fit?: boolean; crop?: boolean; active?: boolean; priority?: number }>(), { active: true, priority: 1 })
const instance = getCurrentInstance()
const visible = ref(!props.lazy)
let observer: UniApp.IntersectionObserver | undefined
const source = ref('')
const loaded = ref(false)
const failed = ref(false)
let sequence = 0
let disposed = false
let handle: FileHandle | null = null
let startedAt = 0
async function load() {
  if (disposed) return
  const run = ++sequence
  handle?.release()
  handle = null
  failed.value = false
  loaded.value = false
  source.value = ''
  if (!props.src || !visible.value || props.active === false) return
  startedAt = Date.now()
  handle = acquireAsset(props.src, props.priority)
  try { const value = await handle.ready; if (run === sequence) source.value = value }
  catch { if (run === sequence) failed.value = true }
}
watch([() => props.src, () => props.active], load, { immediate: true })
watch(() => props.priority, priority => handle?.prioritize?.(priority))
function imageLoaded() {
  loaded.value = true
  if (props.priority >= 2) uni.$emit?.('lc-performance', { kind: 'reader_image', value: Date.now() - startedAt })
}
onMounted(() => {
  if (visible.value) return
  const reveal = () => { if (disposed || visible.value) return; visible.value = true; void load() }
  try {
    observer = uni.createIntersectionObserver(instance?.proxy, { thresholds: [0] })
    observer.relativeToViewport({ top: 400, bottom: 400 }).observe('.private-image', result => {
      if (disposed) return
      if (result.intersectionRatio > 0) reveal()
      else if (visible.value) { visible.value = false; sequence++; handle?.release(); handle = null; source.value = ''; loaded.value = false; failed.value = false }
    })
  } catch { reveal() }
})
onUnmounted(() => { disposed = true; observer?.disconnect(); sequence++; handle?.release() })
function imageFailed() {
  handle?.invalidate()
  handle?.release()
  handle = null
  loaded.value = false
  failed.value = true
  source.value = ''
}
function tap() {
  if (failed.value) { void load(); return }
  if (props.preview && source.value) uni.previewImage({ urls: [source.value], current: source.value })
}
</script>

<template>
  <view class="private-image" :class="{ fit }" :role="preview || failed ? 'button' : 'img'" :tabindex="preview || failed ? 0 : -1" :aria-label="failed ? '重试加载预览图' : label || (preview ? '放大习题预览' : '习题封面')" @click="tap" @keydown.enter="tap">
    <image v-if="source" :src="source" :mode="crop ? 'aspectFill' : 'aspectFit'" class="image" :class="{ 'is-loaded': loaded }" @error="imageFailed" @load="imageLoaded" />
    <view v-else class="placeholder"><text v-if="failed" class="retry-mark">↻</text><view v-else class="placeholder-paper" /></view>
    <view v-if="preview && source" class="zoom-badge" aria-hidden="true"><wd-icon name="fullscreen" size="17px" /></view>
  </view>
</template>

<style scoped>
.private-image { position: relative; width: 100%; height: 0; padding-bottom: 141.43%; background: #fff; overflow: hidden; }
.private-image.fit { height:100%;padding-bottom:0; }
.image, .placeholder { position: absolute; inset: 0; width: 100%; height: 100%; }
.image { opacity: 0; transition: opacity .24s ease; }
.image.is-loaded { opacity: 1; }
.placeholder { display: flex; align-items: center; justify-content: center; background: #f7faf8; }
.placeholder-paper { width:21px;height:28px;border:2px solid #acb9af;border-radius:2px;background:repeating-linear-gradient(to bottom,transparent 0,transparent 5px,#dbe3de 5px,#dbe3de 7px); }.retry-mark { color:#acb9af;font-size:26px; }
.zoom-badge { position: absolute; top: 10px; right: 10px; width: 31px; height: 31px; display: flex; align-items: center; justify-content: center; color: #74849f; background: #fff; border: 1px solid #e6ebf2; border-radius: 4px; pointer-events: none; }
</style>
