<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import BannerArtwork from './BannerArtwork.vue'
import { acquireAsset } from '../services/assets'
import { createBannerImages } from '../services/banner-images'
import { openCatalog, openCatalogPaper } from '../services/navigation'
import type { SiteBanner, PaperSummary } from '../types'

const props = withDefaults(defineProps<{ banners: SiteBanner[]; mode?: 'welcome' | 'operations'; grade?: string; loading?: boolean; recent?: PaperSummary | null; active?: boolean }>(), { mode: 'welcome', grade: '', loading: false, active: true })
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
}, { immediate: true })
watch([() => props.banners, () => props.active, () => props.mode], () => {
  if (props.active === false || props.mode !== 'operations') images.clear()
  else images.sync(props.banners)
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
    <view v-if="loading && !banners.length" class="banner-skeleton" :class="{ 'welcome-skeleton': mode === 'welcome' }" role="status" aria-label="正在加载首页推荐"><view /><view /><view /></view>
    <view v-else-if="mode !== 'operations' || !banners.length" class="home-welcome">
      <view class="welcome-copy"><text class="welcome-kicker">{{ recent ? '最近浏览' : grade || '今日练习' }}</text><text class="welcome-title">{{ recent ? recent.title : '每天一份好练习' }}</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="welcome-link" role="button" @click="recent ? openCatalogPaper(recent.id) : openCatalog({ grade })">{{ recent ? '继续查看' : '挑选习题' }}<wd-icon name="arrow-right" size="14px" /></button></view>
      <view class="welcome-art"><BannerArtwork /></view>
    </view>
    <view v-else class="banner-wrap">
      <swiper class="banner-swiper" :current="current" :autoplay="active" :interval="5000" :circular="banners.length > 1" :duration="360" @change="change">
        <swiper-item v-for="slide in banners" :key="slide.id">
          <view v-if="slide.image_url" class="banner-slide image-banner">
            <view class="banner-media">
              <image v-if="art[slide.id]" :key="slide.image_url" class="banner-photo" :src="art[slide.id]" :mode="slide.image_fit === 'cover' ? 'aspectFill' : 'aspectFit'" aria-hidden="true" @error="images.fail(slide.id, art[slide.id] || '')" />
              <view v-else class="banner-media-fallback banner-image-placeholder" aria-hidden="true"><wd-icon name="book" size="30px" /></view>
            </view>
            <view class="banner-body"><view class="banner-copy"><text v-if="slide.kicker" class="banner-kicker">{{ slide.kicker }}</text><text class="banner-title">{{ slide.title }}</text><text v-if="slide.subtitle" class="banner-subtitle">{{ slide.subtitle }}</text></view><view v-if="actionable(slide)" class="banner-cta"><text>{{ slide.action_label || '去看看' }}</text><wd-icon name="arrow-right" size="16px" /></view></view>
            <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-if="actionable(slide)" class="banner-hit" role="button" :aria-label="slide.title + '，' + (slide.action_label || '去看看')" @click="go(slide)" />
          </view>
          <view v-else class="banner-slide text-banner">
            <view class="banner-art" aria-hidden="true"><BannerArtwork /></view>
            <view class="banner-copy banner-body">
              <text v-if="slide.kicker" class="banner-kicker">{{ slide.kicker }}</text>
              <text class="banner-title">{{ slide.title }}</text>
              <text v-if="slide.subtitle" class="banner-subtitle">{{ slide.subtitle }}</text>
            </view>
            <view v-if="actionable(slide)" class="banner-go" aria-hidden="true"><wd-icon name="arrow-right" size="16px" /></view>
            <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-if="actionable(slide)" class="banner-hit" role="button" :aria-label="slide.title + '，' + (slide.action_label || '去看看')" @click="go(slide)" />
          </view>
        </swiper-item>
      </swiper>
      <view v-if="banners.length > 1" class="banner-dots">
        <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-for="(slide, index) in banners" :key="slide.id" class="banner-dot" :aria-label="'查看第' + (index + 1) + '张：' + slide.title" :aria-pressed="current === index" role="button" @click="current = index"><view :class="{ active: current === index }" /></button>
      </view>
      <button v-if="banners.length > 1" class="banner-next" role="button" aria-label="下一张 Banner" @click="current = (current + 1) % banners.length"><wd-icon name="arrow-right" size="16px" /></button>
    </view>
  </view>
</template>

<style scoped>
.home-banner { padding: 0 var(--lc-page-gutter); }
.banner-wrap { position: relative; }
.banner-swiper, .banner-skeleton { height: 246px; }

/* 运营图片与文案分行，保持海报完整和文字对比度。 */
.banner-slide { position: relative; height: 100%; overflow: hidden; border-radius: 8px; background: #f3f7f4; }
.banner-media { height: 150px; width: 100%; }
.banner-body { display: flex; align-items: center; gap: 12px; height: 96px; padding: 8px 14px; box-sizing: border-box; background: #fff; }
.banner-body .banner-kicker { margin: 0; font-size: 10px; letter-spacing: 0; }
.banner-body .banner-title { font-size: 16px; -webkit-line-clamp: 1; }
.banner-body .banner-subtitle { font-size: 11px; margin-top: 2px; -webkit-line-clamp: 1; }
.banner-cta { display: flex; align-items: center; gap: 5px; max-width: 65px; flex: none; font-size: 11px; color: #307e61; }
.banner-cta text { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.banner-next { position: absolute; right: 8px; top: 104px; width: 40px; height: 40px; padding: 0; background: #fff; color: #307e61; border-radius: 50%; z-index: 4; display: flex; align-items: center; justify-content: center; }
.text-banner .banner-body { background: transparent; display: block; height: auto; padding: 0; max-width: 80%; }
.image-banner { background: #f3f7f4; }
.banner-photo { display: block; width: 100%; height: 100%; }
.banner-media-fallback { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; height: 100%; background: #e7efe9; color: #86a791; font-size: 12px; }

/* —— 无图运营卡：文字卡 —— */
.text-banner { display: flex; align-items: center; gap: 12px; padding: 18px 16px; background: var(--lc-hero, #e4f0e6); }
.banner-copy { position: relative; z-index: 1; flex: 1; min-width: 0; }
.banner-kicker { display: block; margin-bottom: 5px; color: #2f6a52; font-size: 11px; line-height: 1.4; letter-spacing: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.banner-title { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; color: #24473a; font-size: 18px; line-height: 1.4; font-weight: 700; overflow-wrap: anywhere; }
.banner-subtitle { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; margin-top: 5px; color: #5e7a6b; font-size: 12px; line-height: 1.5; overflow-wrap: anywhere; }
.banner-go { display: flex; align-items: center; justify-content: center; flex: none; position: relative; z-index: 1; width: 32px; height: 32px; border-radius: 50%; background: var(--lc-primary, #307e61); color: #fff; box-sizing: border-box; }
.banner-art { position: absolute; right: 0; top: 50%; transform: translateY(-50%) scale(0.64); transform-origin: right center; pointer-events: none; }

/* —— 轮播点：卡外右上，不受点击层影响 —— */
.banner-dots { position: absolute; z-index: 4; right: 12px; top: 11px; display: flex; align-items: center; gap: 2px; padding: 3px 6px; border-radius: 999px; background: rgba(20, 40, 28, 0.26); }
.banner-dot { display: flex; align-items: center; justify-content: center; flex: none; width: 32px; height: 36px; margin: 0; padding: 0; background: transparent; }
.banner-dot > view { width: 5px; height: 5px; border-radius: 99px; background: rgba(255, 255, 255, 0.55); transition: width .2s; }
.banner-dot > view.active { width: 13px; background: #fff; }

.banner-hit { position: absolute; z-index: 3; inset: 0; width: 100%; height: 100%; margin: 0; padding: 0; border-radius: var(--lc-radius-card, 16px); background: transparent; }
.banner-hit:active { background: rgba(35, 80, 55, 0.06); }
.banner-hit:focus-visible { outline-offset: -3px; }

/* —— 加载骨架 —— */
.banner-skeleton { padding: 18px; border-radius: var(--lc-radius-card, 16px); background: #eef3ef; box-sizing: border-box; }
.banner-skeleton > view { width: 55%; height: 11px; border-radius: 8px; margin-bottom: 9px; background: #dde7de; }
.banner-skeleton > view:last-child { width: 38%; margin-bottom: 0; }

.home-welcome { position:relative;min-height:128px;padding:12px 16px;border:1px solid #dbe7dc;border-radius:8px;background:#edf4ed;overflow:hidden; }
.welcome-copy { position:relative;z-index:2;width:65%; }
.welcome-kicker { display:inline-flex;align-items:center;color:#66806a;font-size:10px;line-height:18px;letter-spacing:0; }
.welcome-title { display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;white-space:pre-line;margin-top:4px;color:#294f3a;font-size:18px;font-weight:700;line-height:1.35;letter-spacing:0; }
.welcome-link { display:inline-flex;align-items:center;gap:11px;min-height:44px;margin:4px 0 0;padding:0 13px;border-radius:6px;background:#38664d;color:#fffdf1;font-size:12px;font-weight:550;line-height:1.5;box-shadow:0 3px 0 #254b3814; }
.welcome-art { position:absolute;right:0;top:-18px;transform:scale(.48);transform-origin:right center;pointer-events:none; }
.welcome-skeleton { height:128px; }

@media (max-width: 359px) {
  .home-banner { padding-left: 16px; padding-right: 16px; }
  .text-banner { padding: 15px 14px; }
  .banner-title { font-size: 16px; }
  .welcome-title { font-size:17px; }
  .welcome-art { right:-6px;transform:scale(.42); }
  .home-welcome { padding-left:15px; }
  .welcome-copy { width:64%; }
}
</style>
