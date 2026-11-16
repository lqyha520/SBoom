<script setup lang="ts">
import { onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import { assetThumbnail, type Asset } from '../xhs-workspace'
const props = defineProps<{ asset: Asset }>()
const root = ref<HTMLElement | null>(null), url = ref(''), loading = ref(false), failed = ref(false)
let observer: IntersectionObserver | undefined, sequence = 0, active = true
function clear() { if (url.value) URL.revokeObjectURL(url.value); url.value = '' }
async function load() {
  if (!active || loading.value || url.value || !props.asset.media_type.startsWith('image/')) return
  const seq = ++sequence; loading.value = true; failed.value = false
  try { const blob = await assetThumbnail(props.asset); if (seq === sequence && active) url.value = URL.createObjectURL(blob) }
  catch { if (seq === sequence && active) failed.value = true }
  finally { if (seq === sequence) loading.value = false }
}
function observe() { if (!root.value) return; observer?.disconnect(); if (typeof IntersectionObserver === 'undefined') { void load(); return }; observer = new IntersectionObserver(entries => { if (entries.some(entry => entry.isIntersecting)) { observer?.disconnect(); void load() } }, { rootMargin: '100px' }); observer.observe(root.value) }
onMounted(observe); onActivated(() => { active = true; observe() }); onDeactivated(() => { active = false; ++sequence; loading.value = false; observer?.disconnect() })
watch(() => [props.asset.id, props.asset.revision], () => { ++sequence; loading.value = false; failed.value = false; clear(); observe() }, { flush: 'post' })
onBeforeUnmount(() => { active = false; ++sequence; observer?.disconnect(); clear() })
</script>
<template><div ref="root" class="asset-thumbnail" :class="asset.template?.theme">
  <img v-if="url" :src="url" :alt="asset.data.title+' 缩略图'" />
  <div v-else-if="asset.template" class="template-thumbnail"><strong>{{ asset.template.cover_title || '封面模板' }}</strong><small>{{ asset.template.cover_subtitle }}</small></div>
  <div v-else class="thumbnail-placeholder"><UIcon :name="asset.media_type.startsWith('video/')?'i-lucide-video':'i-lucide-image'" class="size-8" /><span>{{ loading?'加载缩略图…':failed?'缩略图未加载，可点击预览':asset.media_type.startsWith('video/')?'MP4 · 点击预览播放':'图片' }}</span></div>
</div></template>
<style scoped>.asset-thumbnail{aspect-ratio:4/3;display:grid;place-items:center;border-radius:10px;background:var(--ui-bg-muted);overflow:hidden}.asset-thumbnail img{width:100%;height:100%;object-fit:contain}.template-thumbnail,.thumbnail-placeholder{display:grid;gap:12px;padding:18px;text-align:center;justify-items:center;font-size:12px}.template-thumbnail strong{font-size:20px}.asset-thumbnail.green{background:#e6f5ec;color:#176346}.asset-thumbnail.orange{background:#fff0df;color:#89531d}.asset-thumbnail.blue{background:#e5effc;color:#275185}</style>
