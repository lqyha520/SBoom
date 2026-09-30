<script setup lang="ts">
import { ref, watch } from 'vue'
const props = defineProps<{
  content: { kicker: string; title: string; subtitle: string; action_label: string; target_type: string; image_fit: 'contain' | 'cover' }
  imageUrl: string
}>()
const failed = ref(false)
watch(() => props.imageUrl, () => { failed.value = false })
</script>

<template>
  <div class="banner-preview" :class="{ 'copy-preview': !imageUrl }">
    <div v-if="imageUrl" class="preview-media"><img v-if="!failed" :src="imageUrl" :alt="content.title || 'Banner 图片预览'" :style="{ objectFit: content.image_fit }" @error="failed = true" /><div v-else class="preview-unavailable"><UIcon name="i-lucide-image-off" /><span>图片暂不可用</span></div></div>
    <div v-else class="preview-book" aria-hidden="true"><UIcon name="i-lucide-book-open" /></div>
    <div class="preview-body"><div class="preview-copy"><span v-if="content.kicker" class="preview-kicker">{{ content.kicker }}</span><strong class="preview-title">{{ content.title || '填写一个简洁的标题' }}</strong><span v-if="content.subtitle" class="preview-subtitle">{{ content.subtitle }}</span></div><div v-if="content.target_type !== 'none'" class="preview-cta"><span>{{ content.action_label || '去看看' }}</span><span class="preview-arrow"><UIcon name="i-lucide-arrow-right" /></span></div></div>
  </div>
</template>

<style scoped>
.banner-preview { position: relative; overflow: hidden; border: 1px solid #e6ede8; border-radius: 18px; background: #fff; color: #28372f; font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif; }
.preview-media { width: 100%; height: 150px; background: #f0f3f1; overflow: hidden; }
.preview-media img { display: block; width: 100%; height: 100%; }
.preview-unavailable { display: flex; align-items: center; justify-content: center; flex-direction: column; gap: 8px; height: 100%; color: #719781; font-size: 12px; }
.preview-body { display: flex; align-items: center; gap: 12px; height: 96px; padding: 12px 15px; }
.preview-copy { flex: 1; min-width: 0; }
.preview-kicker { display: block; color: #527461; font-size: 10px; line-height: 1.6; margin-bottom: 2px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.preview-title { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; font-size: 17px; line-height: 1.4; font-weight: 650; overflow-wrap: anywhere; }
.banner-preview:not(.copy-preview) .preview-title { -webkit-line-clamp: 1; }
.preview-subtitle { display: block; color: #637168; font-size: 11px; line-height: 1.6; margin-top: 3px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.preview-cta { display: flex; flex-direction: column-reverse; align-items: center; gap: 5px; flex: none; max-width: 72px; font-size: 10px; color: #307e61; line-height: 1.3; }
.preview-cta > span:first-child { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.preview-arrow { display: flex; align-items: center; justify-content: center; width: 30px; height: 30px; border-radius: 50%; background: #307e61; color: #fff; font-size: 17px; }
.copy-preview { min-height: 230px; background: #eaf3ed; }
.copy-preview .preview-body { position: relative; flex-direction: column; align-items: flex-start; justify-content: center; min-height: 230px; height: auto; max-width: 83%; padding: 24px; }
.copy-preview .preview-copy { flex: none; }
.copy-preview .preview-title { font-size: 23px; }
.copy-preview .preview-kicker { margin-bottom: 9px; font-size: 11px; }
.copy-preview .preview-subtitle { margin-top: 8px; white-space: normal; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.copy-preview .preview-cta { flex-direction: row; max-width: 100%; font-size: 12px; gap: 9px; }
.preview-book { position: absolute; right: -14px; bottom: 22px; display: flex; align-items: center; justify-content: center; width: 112px; height: 112px; border-radius: 34px; background: #dcebdd; color: #92b49f; transform: rotate(-15deg); opacity: .65; font-size: 50px; }
</style>
