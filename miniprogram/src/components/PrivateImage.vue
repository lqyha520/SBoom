<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { acquireAsset } from '../services/assets'
import type { FileHandle } from '../services/file-pool'
const props = defineProps<{ src: string | null; preview?: boolean; label?: string }>()
const source = ref('')
const failed = ref(false)
let sequence = 0
let handle: FileHandle | null = null
async function load() {
  const run = ++sequence
  handle?.release()
  handle = null
  failed.value = false
  source.value = ''
  if (!props.src) return
  handle = acquireAsset(props.src)
  try { const value = await handle.ready; if (run === sequence) source.value = value }
  catch { if (run === sequence) failed.value = true }
}
watch(() => props.src, load, { immediate: true })
onUnmounted(() => { sequence++; handle?.release() })
function imageFailed() {
  handle?.invalidate()
  handle?.release()
  handle = null
  failed.value = true
  source.value = ''
}
function tap() {
  if (failed.value) { void load(); return }
  if (props.preview && source.value) uni.previewImage({ urls: [source.value], current: source.value })
}
</script>

<template>
  <view class="private-image" :role="preview || failed ? 'button' : 'img'" :tabindex="preview || failed ? 0 : -1" :aria-label="failed ? '重试加载预览图' : label || (preview ? '放大习题预览' : '习题封面')" @click="tap" @keydown.enter="tap">
    <image v-if="source" :src="source" mode="aspectFit" class="image" @error="imageFailed" />
    <view v-else class="placeholder"><wd-icon :name="failed ? 'refresh' : src ? 'image' : 'file'" size="22px" color="#acb9af" /></view>
    <view v-if="preview && source" class="zoom-badge" aria-hidden="true"><wd-icon name="fullscreen" size="17px" /></view>
  </view>
</template>

<style scoped>
.private-image { position: relative; width: 100%; height: 0; padding-bottom: 141.43%; background: #fff; overflow: hidden; }
.image, .placeholder { position: absolute; inset: 0; width: 100%; height: 100%; }
.placeholder { display: flex; align-items: center; justify-content: center; background: #f7faf8; }
.zoom-badge { position: absolute; top: 10px; right: 10px; width: 31px; height: 31px; display: flex; align-items: center; justify-content: center; color: #74849f; background: #fff; border: 1px solid #e6ebf2; border-radius: 4px; pointer-events: none; }
</style>
