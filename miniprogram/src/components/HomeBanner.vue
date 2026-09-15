<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { acquireAsset } from '../services/assets'
import type { FileHandle } from '../services/file-pool'
import { openCatalog, openCatalogPaper } from '../services/navigation'
import type { SiteBanner } from '../types'

const props = withDefaults(defineProps<{ banners: SiteBanner[]; grade?: string }>(), { grade: '' })
const current = ref(0)
// 后台没有配置 Banner 时的兜底文案，保证首页永远有内容
const fallback: SiteBanner[] = [
  { id: 'fallback-sync', kicker: '新学期 · 同步巩固', title: '同步练习', subtitle: '每天一点进步', action_label: '去挑一份', target_type: 'none', target_value: '', image_url: null },
  { id: 'fallback-reading', kicker: '精选内容 · 专项提升', title: '阅读积累', subtitle: '从好习题开始', action_label: '看看专题', target_type: 'keyword', target_value: '阅读', image_url: null },
]
const slides = computed(() => (props.banners.length ? props.banners : fallback))

// 配图存放在私有存储，必须带登录态取回本地临时文件后才能渲染
const art = ref<Record<string, string>>({})
const handles = new Map<string, FileHandle>()
let sequence = 0
async function resolveArt() {
  const run = ++sequence
  for (const [id, handle] of handles) {
    if (!slides.value.some(slide => slide.id === id)) { handle.release(); handles.delete(id) }
  }
  await Promise.all(slides.value.map(async slide => {
    if (!slide.image_url || handles.has(slide.id)) return
    const handle = acquireAsset(slide.image_url)
    handles.set(slide.id, handle)
    try {
      const path = await handle.ready
      if (run === sequence) art.value = { ...art.value, [slide.id]: path }
    } catch {
      // 取图失败就回退到内置插画，不把破图暴露给用户
      handles.delete(slide.id)
      handle.release()
    }
  }))
}
watch(slides, resolveArt, { immediate: true })
onUnmounted(() => { sequence++; handles.forEach(handle => handle.release()); handles.clear() })

function go(slide: SiteBanner) {
  if (slide.target_type === 'paper' && slide.target_value) { openCatalogPaper(slide.target_value); return }
  if (slide.target_type === 'category') { openCatalog({ category: slide.target_value, grade: props.grade }); return }
  if (slide.target_type === 'subject') { openCatalog({ subject: slide.target_value, grade: props.grade }); return }
  if (slide.target_type === 'keyword' && slide.target_value) { openCatalog({ q: slide.target_value, grade: props.grade }); return }
  openCatalog({ grade: props.grade })
}
function change(event: { detail: { current: number } }) { current.value = event.detail.current }
</script>

<template>
  <view class="home-banner">
    <swiper class="banner-swiper" :current="current" :autoplay="false" circular :duration="240" @change="change">
      <swiper-item v-for="slide in slides" :key="slide.id">
        <view class="banner-slide" :class="{ illustrated: !art[slide.id] }">
          <image v-if="art[slide.id]" class="banner-photo" :src="art[slide.id]" mode="aspectFill" aria-hidden="true" />
          <image v-else class="banner-art" src="/static/illustrations/notebook.png" mode="aspectFit" aria-hidden="true" />
          <view class="banner-copy">
            <text v-if="slide.kicker" class="banner-kicker">{{ slide.kicker }}</text>
            <text class="banner-title">{{ slide.title }}</text>
            <text v-if="slide.subtitle" class="banner-subtitle">{{ slide.subtitle }}</text>
            <button class="banner-link" role="button" :aria-label="slide.action_label || slide.title" @click="go(slide)">
              <text>{{ slide.action_label || '去看看' }}</text>
              <view class="banner-go"><wd-icon name="arrow-right" size="15px" /></view>
            </button>
          </view>
        </view>
      </swiper-item>
    </swiper>
    <view v-if="slides.length > 1" class="banner-controls">
      <view class="banner-dots"><button v-for="(slide, index) in slides" :key="slide.id" class="banner-dot" :aria-label="slide.title" :aria-pressed="current === index" role="button" @click="current = index"><view :class="{ active: current === index }" /></button></view>
      <button class="bare-icon" role="button" aria-label="下一个专题" title="下一个专题" @click="current = (current + 1) % slides.length"><wd-icon name="arrow-right" size="18px" /></button>
    </view>
  </view>
</template>

<style scoped>
.home-banner { padding: 0 18px 7px; }
.banner-swiper { height: 184px; }
.banner-slide { position: relative; height: 184px; overflow: hidden; border-radius: 10px; }
.banner-slide.illustrated { border-radius: 0; }
.banner-photo { position: absolute; inset: 0; width: 100%; height: 100%; }
/* 配图右半部分渐隐到主题底色，保证左侧文案在任何图上都读得清 */
.banner-slide:not(.illustrated)::after { content: ''; position: absolute; inset: 0; background: linear-gradient(90deg, rgba(228, 240, 230, .97) 34%, rgba(228, 240, 230, .58) 60%, rgba(228, 240, 230, 0) 92%); }
.banner-art { position: absolute; width: 220px; height: 220px; right: -10px; top: -7px; pointer-events: none; }
.banner-copy { position: relative; z-index: 1; width: 55%; padding: 21px 0 4px 6px; }
.banner-kicker { display: block; color: var(--lc-muted); font-size: 11px; line-height: 1.6; }
.banner-title { display: block; font-size: 26px; font-weight: 700; line-height: 1.4; color: var(--lc-text); margin-top: 8px; }
.banner-subtitle { display: block; color: var(--lc-secondary); font-size: 12px; margin-top: 4px; }
.banner-link { display: inline-flex; align-items: center; gap: 8px; min-height: 44px; padding: 0; margin: 7px 0 0; color: var(--lc-primary); background: transparent; font-size: 12px; line-height: 1.5; }
.banner-go { display: flex; align-items: center; justify-content: center; width: 25px; height: 25px; border-radius: 50%; background: var(--lc-primary); color: #fff; }
.banner-controls { display: flex; align-items: center; justify-content: space-between; }
.banner-dots { display: flex; }
.banner-dot { display: flex; align-items: center; justify-content: center; width: 36px; min-height: 44px; margin: 0; padding: 0; background: transparent; }
.banner-dot > view { width: 5px; height: 5px; border-radius: 99px; background: #b2c6b7; transition: width .2s; }
.banner-dot > view.active { width: 18px; background: var(--lc-primary); }
@media (max-width: 359px) { .home-banner { padding-left: 14px; padding-right: 14px; } .banner-art { width: 188px; height: 188px; top: 10px; right: -11px; } .banner-copy { padding-left: 3px; } .banner-title { font-size: 24px; } }
</style>
