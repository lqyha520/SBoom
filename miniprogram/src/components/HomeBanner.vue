<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import BannerArtwork from './BannerArtwork.vue'
import { acquireAsset } from '../services/assets'
import { createBannerImages } from '../services/banner-images'
import { openCatalog, openCatalogPaper } from '../services/navigation'
import type { SiteBanner, PaperSummary } from '../types'

const props = withDefaults(defineProps<{ banners: SiteBanner[]; grade?: string; loading?: boolean; recent?: PaperSummary | null; active?: boolean }>(), { grade: '', loading: false, active: true })
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
watch([() => props.banners, () => props.active], () => {
  if (props.active === false) images.clear()
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
    <view v-if="loading && !banners.length" class="banner-skeleton" role="status" aria-label="正在加载首页推荐"><view /><view /><view /></view>
    <view v-else-if="!banners.length" class="home-welcome">
      <view class="welcome-copy"><view class="welcome-kicker"><view class="kicker-dot" /><text>{{ recent ? '接着上次的发现' : '今天，也有新收获' }}</text></view><text class="welcome-title">{{ recent ? recent.title : '把好奇心，\n变成小进步。' }}</text><text class="welcome-subtitle">{{ recent ? '喜欢的练习，值得再看一遍' : '选一份好练习，让知识慢慢发芽' }}</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="welcome-link" role="button" @click="recent ? openCatalogPaper(recent.id) : openCatalog({ grade })">{{ recent ? '继续查看' : '去发现习题' }}<wd-icon name="arrow-right" size="14px" /></button></view>
      <view class="welcome-art"><BannerArtwork /></view>
      <view class="welcome-footer"><text>{{ grade || '跟着自己的节奏学' }}</text><view class="welcome-subjects"><text>语文</text><view /><text>数学</text><view /><text>英语</text></view></view>
    </view>
    <template v-else>
      <swiper class="banner-swiper" :current="current" :autoplay="false" :circular="banners.length > 1" :duration="240" @change="change">
        <swiper-item v-for="slide in banners" :key="slide.id">
          <view class="banner-slide modern-banner" :class="{ 'text-banner': !slide.image_url }">
            <view v-if="slide.image_url" class="banner-media">
              <image v-if="art[slide.id]" :key="slide.image_url" class="banner-photo" :src="art[slide.id]" :mode="slide.image_fit === 'cover' ? 'aspectFill' : 'aspectFit'" aria-hidden="true" @error="images.fail(slide.id, art[slide.id] || '')" />
              <view v-else class="banner-image-placeholder" aria-hidden="true"><wd-icon name="book" size="32px" /><text>每天一点进步</text></view>
            </view>
            <view v-else class="text-banner-art" aria-hidden="true"><BannerArtwork /></view>
            <view class="banner-body">
              <view class="banner-copy"><text v-if="slide.kicker" class="banner-kicker">{{ slide.kicker }}</text><text class="banner-title">{{ slide.title }}</text><text v-if="slide.subtitle" class="banner-subtitle">{{ slide.subtitle }}</text></view>
              <view v-if="actionable(slide)" class="banner-cta"><text>{{ slide.action_label || '去看看' }}</text><view class="banner-arrow"><wd-icon name="arrow-right" size="17px" /></view></view>
            </view>
            <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-if="actionable(slide)" class="banner-hit" role="button" :aria-label="slide.title + '，' + (slide.action_label || '去看看')" @click="go(slide)" />
          </view>
        </swiper-item>
      </swiper>
      <view v-if="banners.length > 1" class="banner-controls">
        <view class="banner-dots"><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-for="(slide, index) in banners" :key="slide.id" class="banner-dot" :aria-label="'查看第' + (index + 1) + '张：' + slide.title" :aria-pressed="current === index" role="button" @click="current = index"><view :class="{ active: current === index }" /></button></view>
        <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="banner-next" role="button" aria-label="下一张 Banner" @click="current = (current + 1) % banners.length"><text>{{ current + 1 }} / {{ banners.length }}</text><wd-icon name="arrow-right" size="14px" /></button>
      </view>
    </template>
  </view>
</template>

<style scoped>
.home-banner { padding: 0 var(--lc-page-gutter); }
.banner-swiper,.banner-skeleton { height: calc(41.6667vw + 75.333px); max-height: 292px; }
.banner-slide { position: relative; height: 100%; overflow: hidden; border: 1px solid #e6ede8; border-radius: 18px; background: #fff; }
.banner-media { position: relative; width: 100%; height: calc(100% - 92px); background: #f0f3f1; overflow: hidden; }
.banner-photo { display: block; width: 100%; height: 100%; }
.banner-image-placeholder { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 9px; height: 100%; background: #eaf3ed; color: #719781; font-size: 12px; }
.banner-body { display: flex; align-items: center; gap: 12px; height: 92px; padding: 12px 15px; }
.banner-copy { flex: 1; min-width: 0; }
.banner-kicker { display: block; color: #527461; font-size: 12px; line-height: 1.6; margin-bottom: 2px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.banner-title { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; color: var(--lc-text); font-size: 17px; line-height: 1.4; font-weight: 650; overflow-wrap: anywhere; }
.banner-slide:not(.text-banner) .banner-title { -webkit-line-clamp: 1; }
.banner-subtitle { display: block; color: var(--lc-muted); font-size: 12px; line-height: 1.6; margin-top: 3px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.banner-cta { display: flex; flex-direction: column-reverse; align-items: center; gap: 5px; flex: none; max-width: 72px; font-size: 12px; color: var(--lc-primary); line-height: 1.3; }
.banner-cta > text { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.banner-arrow { display: flex; align-items: center; justify-content: center; width: 30px; height: 30px; border-radius: 50%; background: var(--lc-primary); color: #fff; }
.banner-hit { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; padding: 0; border-radius: 18px; background: transparent; }
.banner-hit:active { background: #163c2006; }
.banner-hit:focus-visible { outline-offset: -3px; }
.text-banner { background: #eaf3ed; }
.text-banner .banner-body { position: relative; align-items: flex-start; flex-direction: column; justify-content: center; height: 100%; padding: 24px; max-width: 83%; }
.text-banner .banner-copy { flex: none; }
.text-banner .banner-title { font-size: 23px; }
.text-banner .banner-kicker { margin-bottom: 9px; font-size: 12px; }
.text-banner .banner-subtitle { margin-top: 8px; white-space: normal; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.text-banner .banner-cta { flex-direction: row; max-width: 100%; font-size: 12px; gap: 9px; }
.text-banner-symbol { position: absolute; right: -14px; bottom: 22px; width: 112px; height: 112px; display: flex; align-items: center; justify-content: center; border-radius: 34px; background: #dcebdd; color: #92b49f; transform: rotate(-15deg); opacity: .65; }
.banner-controls { display: flex; align-items: center; justify-content: space-between; min-height: 36px; margin-top: -2px; }
.banner-dots { display: flex; max-width: calc(100% - 65px); overflow-x: auto; }
.banner-dot { display: flex; align-items: center; justify-content: center; flex: none; width: 30px; height: 44px; margin: 0; padding: 0; background: transparent; }
.banner-dot > view { width: 5px; height: 5px; border-radius: 99px; background: #c3d1c8; transition: width .2s; }
.banner-dot > view.active { width: 17px; background: var(--lc-primary); }
.banner-next { display: flex; align-items: center; justify-content: flex-end; gap: 9px; min-width: 65px; height: 44px; margin: 0; padding: 0; background: transparent; font-size: 12px; color: var(--lc-muted); }
.home-welcome { position:relative;min-height:242px;padding:21px 18px 49px;border:1px solid #e8e4ce;border-radius:22px;background:linear-gradient(115deg,#fff8e9 0%,#f7f1d9 57%,#e5eedc 100%);overflow:hidden;box-shadow:0 5px 16px #6a79500a; }
.welcome-copy { position:relative;z-index:2;width:65%; }
.welcome-kicker { display:inline-flex;align-items:center;gap:6px;color:#66806a;font-size:10px;line-height:18px;letter-spacing:1px; }.kicker-dot { width:5px;height:5px;border-radius:50%;background:#78975d; }
.welcome-title { display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;white-space:pre-line;margin-top:10px;color:#294f3a;font-size:25px;font-weight:700;line-height:1.35;letter-spacing:1px; }
.welcome-subtitle { display:block;max-width:155px;margin-top:10px;color:#78816a;font-size:11px;line-height:1.7; }
.welcome-link { display:inline-flex;align-items:center;gap:11px;min-height:38px;margin:15px 0 0;padding:0 13px;border-radius:10px;background:#38664d;color:#fffdf1;font-size:12px;font-weight:550;line-height:1.5;box-shadow:0 3px 0 #254b3814; }
.welcome-art { position:absolute;right:-6px;top:25px;transform:rotate(3deg) scale(.88);transform-origin:right center;pointer-events:none; }
.welcome-footer { position:absolute;bottom:0;left:18px;right:18px;height:35px;display:flex;align-items:center;justify-content:space-between;border-top:1px solid #70815924;color:#819078;font-size:10px;letter-spacing:.3px; }.welcome-subjects { display:flex;align-items:center;gap:7px; }.welcome-subjects view { width:2px;height:2px;border-radius:50%;background:#abb497; }
.text-banner { background:linear-gradient(115deg,#fff8e9 0%,#f7f1d9 57%,#e5eedc 100%);border-color:#e8e4ce; }
.text-banner .banner-body { width:65%;max-width:65%;padding:20px 17px;z-index:1; }.text-banner .banner-title { font-size:24px;color:#294f3a; }.text-banner .banner-subtitle { color:#78816a;font-size:11px; }.text-banner .banner-kicker { color:#66806a;letter-spacing:1px;font-size:10px; }.text-banner .banner-cta { padding:7px 10px;border-radius:9px;background:#38664d;color:#fffdf1; }.text-banner .banner-arrow { width:18px;height:18px;background:transparent; }
.text-banner-art { position:absolute;right:-8px;top:22px;transform:scale(.88);transform-origin:right center;pointer-events:none; }
.banner-skeleton { padding: 135px 18px 10px; border-radius: 18px; background: #eaf0eb; }
.banner-skeleton > view { width: 65%; height: 9px; border-radius: 8px; margin-bottom: 8px; background: #dce7df; }
.banner-skeleton > view:last-child { width: 40%; }
.modern-banner { border-color:#e8e4ce; background:linear-gradient(115deg,#fff8e9 0%,#f7f1d9 58%,#e5eedc 100%); }
.modern-banner .banner-media { position:absolute;right:0;top:0;width:43%;height:100%;background:#e5eedc;clip-path:polygon(18% 0,100% 0,100% 100%,0 100%); }
.modern-banner .banner-photo { opacity:.92; }
.modern-banner .banner-body { position:relative;z-index:1;align-items:flex-start;flex-direction:column;justify-content:center;width:62%;max-width:62%;height:100%;box-sizing:border-box;padding:20px 8px 20px 18px; }
.modern-banner .banner-copy { flex:none;width:100%; }
.modern-banner .banner-kicker { color:#66806a;letter-spacing:1px;font-size:10px;margin-bottom:7px; }
.modern-banner .banner-title { color:#294f3a;font-size:21px;line-height:1.35;-webkit-line-clamp:2; }
.modern-banner .banner-subtitle { color:#78816a;font-size:11px;white-space:normal;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;margin-top:7px; }
.modern-banner .banner-cta { flex-direction:row;align-items:center;max-width:100%;margin-top:12px;padding:7px 10px;border-radius:9px;background:#38664d;color:#fffdf1;font-size:11px;gap:7px; }
.modern-banner .banner-arrow { width:18px;height:18px;background:transparent; }
.modern-banner.text-banner .banner-media { display:none; }
@media (max-width: 359px) { .modern-banner .banner-body { padding-left:15px; }.modern-banner .banner-title { font-size:19px; }.modern-banner .banner-subtitle { max-width:120px; }.modern-banner .banner-cta { margin-top:9px; } }
@media (max-width: 359px) { .home-banner { padding-left: 16px; padding-right: 16px; } .banner-swiper,.banner-skeleton { height: calc(41.6667vw + 78.666px); } .banner-title { font-size: 16px; } .banner-body { padding-left: 13px; padding-right: 13px; } .welcome-title { font-size:22px; }.welcome-art,.text-banner-art { right:-16px;transform:scale(.73); }.welcome-subtitle { max-width:132px; }.home-welcome { padding-left:15px; }.welcome-copy { width:64%; } }
</style>
