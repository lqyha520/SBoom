<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { acquireAsset } from '../services/assets'
import { createBannerImages } from '../services/banner-images'
import { openCatalog, openCatalogPaper } from '../services/navigation'
import type { SiteBanner } from '../types'

const props = withDefaults(defineProps<{ banners: SiteBanner[]; grade?: string; loading?: boolean }>(), { grade: '', loading: false })
const current = ref(0)
const art = ref<Record<string, string>>({})
const images = createBannerImages(acquireAsset, (id, path) => {
  const next = { ...art.value }
  if (path) next[id] = path
  else delete next[id]
  art.value = next
})
watch(() => props.banners, (next, previous) => {
  const selected = previous?.[current.value]?.id
  const index = next.findIndex(banner => banner.id === selected)
  current.value = index >= 0 ? index : Math.min(current.value, Math.max(0, next.length - 1))
  images.sync(next)
}, { immediate: true })
onUnmounted(() => images.clear())

function actionable(slide: SiteBanner) { return slide.target_type !== 'none' && !!slide.target_value }
function go(slide: SiteBanner) {
  if (!actionable(slide)) return
  if (slide.target_type === 'paper') { openCatalogPaper(slide.target_value); return }
  if (slide.target_type === 'category') { openCatalog({ category: slide.target_value, grade: props.grade }); return }
  if (slide.target_type === 'subject') { openCatalog({ subject: slide.target_value, grade: props.grade }); return }
  if (slide.target_type === 'keyword') openCatalog({ q: slide.target_value, grade: props.grade })
}
function change(event: { detail: { current: number } }) { current.value = event.detail.current }
</script>

<template>
  <view class="home-banner">
    <view v-if="loading && !banners.length" class="banner-skeleton" role="status" aria-label="正在加载首页推荐"><view /><view /><view /></view>
    <view v-else-if="!banners.length" class="home-welcome">
      <view class="welcome-copy"><text class="welcome-kicker">每天一点进步</text><text class="welcome-title">找到今天想练的那一份</text><text class="welcome-subtitle">从一份合适的练习开始</text><button class="welcome-link" role="button" @click="openCatalog({ grade })">开始选习题<wd-icon name="arrow-right" size="15px" /></button></view>
      <view class="welcome-symbol" aria-hidden="true"><wd-icon name="book" size="40px" /><view class="welcome-spark">+</view></view>
    </view>
    <template v-else>
      <swiper class="banner-swiper" :current="current" :autoplay="false" :circular="banners.length > 1" :duration="240" @change="change">
        <swiper-item v-for="slide in banners" :key="slide.id">
          <view class="banner-slide" :class="{ 'text-banner': !slide.image_url }">
            <view v-if="slide.image_url" class="banner-media">
              <image v-if="art[slide.id]" :key="slide.image_url" class="banner-photo" :src="art[slide.id]" :mode="slide.image_fit === 'cover' ? 'aspectFill' : 'aspectFit'" aria-hidden="true" @error="images.fail(slide.id, art[slide.id] || '')" />
              <view v-else class="banner-image-placeholder" aria-hidden="true"><wd-icon name="book" size="32px" /><text>每天一点进步</text></view>
            </view>
            <view v-else class="text-banner-symbol" aria-hidden="true"><wd-icon name="book" size="50px" /></view>
            <view class="banner-body">
              <view class="banner-copy"><text v-if="slide.kicker" class="banner-kicker">{{ slide.kicker }}</text><text class="banner-title">{{ slide.title }}</text><text v-if="slide.subtitle" class="banner-subtitle">{{ slide.subtitle }}</text></view>
              <view v-if="actionable(slide)" class="banner-cta"><text>{{ slide.action_label || '去看看' }}</text><view class="banner-arrow"><wd-icon name="arrow-right" size="17px" /></view></view>
            </view>
            <button v-if="actionable(slide)" class="banner-hit" role="button" :aria-label="slide.title + '，' + (slide.action_label || '去看看')" @click="go(slide)" />
          </view>
        </swiper-item>
      </swiper>
      <view v-if="banners.length > 1" class="banner-controls">
        <view class="banner-dots"><button v-for="(slide, index) in banners" :key="slide.id" class="banner-dot" :aria-label="'查看第' + (index + 1) + '张：' + slide.title" :aria-pressed="current === index" role="button" @click="current = index"><view :class="{ active: current === index }" /></button></view>
        <button class="banner-next" role="button" aria-label="下一张 Banner" @click="current = (current + 1) % banners.length"><text>{{ current + 1 }} / {{ banners.length }}</text><wd-icon name="arrow-right" size="14px" /></button>
      </view>
    </template>
  </view>
</template>

<style scoped>
.home-banner { padding: 0 20px; }
.banner-swiper { height: calc(41.6667vw + 75.333px); max-height: 292px; }
.banner-slide { position: relative; height: 100%; overflow: hidden; border: 1px solid #e6ede8; border-radius: 18px; background: #fff; }
.banner-media { position: relative; width: 100%; height: calc(100% - 92px); background: #f0f3f1; overflow: hidden; }
.banner-photo { display: block; width: 100%; height: 100%; }
.banner-image-placeholder { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 9px; height: 100%; background: #eaf3ed; color: #719781; font-size: 11px; }
.banner-body { display: flex; align-items: center; gap: 12px; height: 92px; padding: 12px 15px; }
.banner-copy { flex: 1; min-width: 0; }
.banner-kicker { display: block; color: #527461; font-size: 10px; line-height: 1.6; margin-bottom: 2px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.banner-title { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; color: var(--lc-text); font-size: 17px; line-height: 1.4; font-weight: 650; overflow-wrap: anywhere; }
.banner-slide:not(.text-banner) .banner-title { -webkit-line-clamp: 1; }
.banner-subtitle { display: block; color: var(--lc-muted); font-size: 11px; line-height: 1.6; margin-top: 3px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.banner-cta { display: flex; flex-direction: column-reverse; align-items: center; gap: 5px; flex: none; max-width: 72px; font-size: 10px; color: var(--lc-primary); line-height: 1.3; }
.banner-cta > text { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.banner-arrow { display: flex; align-items: center; justify-content: center; width: 30px; height: 30px; border-radius: 50%; background: var(--lc-primary); color: #fff; }
.banner-hit { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; padding: 0; border-radius: 18px; background: transparent; }
.banner-hit:active { background: #163c2006; }
.banner-hit:focus-visible { outline-offset: -3px; }
.text-banner { background: #eaf3ed; }
.text-banner .banner-body { position: relative; align-items: flex-start; flex-direction: column; justify-content: center; height: 100%; padding: 24px; max-width: 83%; }
.text-banner .banner-copy { flex: none; }
.text-banner .banner-title { font-size: 23px; }
.text-banner .banner-kicker { margin-bottom: 9px; font-size: 11px; }
.text-banner .banner-subtitle { margin-top: 8px; white-space: normal; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.text-banner .banner-cta { flex-direction: row; max-width: 100%; font-size: 12px; gap: 9px; }
.text-banner-symbol { position: absolute; right: -14px; bottom: 22px; width: 112px; height: 112px; display: flex; align-items: center; justify-content: center; border-radius: 34px; background: #dcebdd; color: #92b49f; transform: rotate(-15deg); opacity: .65; }
.banner-controls { display: flex; align-items: center; justify-content: space-between; min-height: 36px; margin-top: -2px; }
.banner-dots { display: flex; max-width: calc(100% - 65px); overflow-x: auto; }
.banner-dot { display: flex; align-items: center; justify-content: center; flex: none; width: 30px; height: 44px; margin: 0; padding: 0; background: transparent; }
.banner-dot > view { width: 5px; height: 5px; border-radius: 99px; background: #c3d1c8; transition: width .2s; }
.banner-dot > view.active { width: 17px; background: var(--lc-primary); }
.banner-next { display: flex; align-items: center; justify-content: flex-end; gap: 9px; min-width: 65px; height: 44px; margin: 0; padding: 0; background: transparent; font-size: 11px; color: var(--lc-muted); }
.home-welcome { position: relative; display: flex; align-items: center; min-height: 172px; padding: 21px 20px 13px; border: 1px solid #dcebdd; border-radius: 18px; background: #eaf3ed; overflow: hidden; }
.welcome-copy { position: relative; z-index: 1; max-width: 79%; }
.welcome-kicker { display: block; font-size: 10px; color: #527461; letter-spacing: 2px; }
.welcome-title { display: block; margin-top: 6px; font-size: 22px; font-weight: 650; line-height: 1.4; color: #254b38; }
.welcome-subtitle { display: block; font-size: 11px; margin-top: 7px; color: #64806d; }
.welcome-link { display: inline-flex; align-items: center; gap: 9px; min-height: 44px; margin: 4px 0 0; padding: 0; font-size: 12px; line-height: 1.5; color: var(--lc-primary); background: transparent; }
.welcome-symbol { position: absolute; right: -8px; bottom: 25px; display: flex; align-items: center; justify-content: center; width: 88px; height: 97px; border-radius: 24px; background: #d9e9dd; color: #80a78d; transform: rotate(-13deg); }
.welcome-spark { position: absolute; top: -15px; right: 19px; color: #af8d4e; font-size: 25px; font-weight: 300; }
.banner-skeleton { height: 200px; padding: 135px 18px 10px; border-radius: 18px; background: #eaf0eb; }
.banner-skeleton > view { width: 65%; height: 9px; border-radius: 8px; margin-bottom: 8px; background: #dce7df; }
.banner-skeleton > view:last-child { width: 40%; }
@media (max-width: 359px) { .home-banner { padding-left: 16px; padding-right: 16px; } .banner-swiper { height: calc(41.6667vw + 78.666px); } .banner-title { font-size: 16px; } .banner-body { padding-left: 13px; padding-right: 13px; } .welcome-title { font-size: 21px; } }
</style>
