<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import BannerArtwork from './BannerArtwork.vue'
import { acquireAsset } from '../services/assets'
import { createBannerImages } from '../services/banner-images'
import { openCatalog, openCatalogPaper } from '../services/navigation'
import type { SiteBanner, PaperSummary } from '../types'

const props = withDefaults(defineProps<{ banners: SiteBanner[]; mode?: 'welcome' | 'operations'; grade?: string; loading?: boolean; recent?: PaperSummary | null; active?: boolean }>(), { mode: 'welcome', grade: '', loading: false, active: true })
const emit = defineEmits<{ 'select-grade': [] }>()
const current = ref(0)
const art = ref<Record<string, string>>({})
const images = createBannerImages(url => acquireAsset(url, 0), (id, path) => {
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
watch([() => props.banners, () => props.active, () => props.mode, current], () => {
  if (props.active === false || props.mode !== 'operations') images.clear()
  else images.sync(props.banners, current.value)
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
function welcomeAction() {
  if (props.recent) openCatalogPaper(props.recent.id)
  else if (props.grade) openCatalog({ grade: props.grade })
  else emit('select-grade')
}
</script>

<template>
  <view class="home-banner">
    <view v-if="loading && !banners.length" class="banner-skeleton" :class="{ 'welcome-skeleton': mode === 'welcome' }" role="status" aria-label="正在加载首页推荐"><view><view class="skeleton-glow" /></view><view><view class="skeleton-glow" /></view><view><view class="skeleton-glow" /></view></view>
    <view v-else-if="mode !== 'operations' || !banners.length" class="home-welcome">
      <view class="welcome-copy">
        <view class="welcome-kicker"><view class="welcome-dot" aria-hidden="true" /><text>{{ recent ? '最近浏览' : grade || '今日练习' }}</text></view>
        <text class="welcome-title">{{ recent ? recent.title : '每天一份好练习' }}</text>
        <button hover-class="welcome-pressed" :hover-start-time="0" :hover-stay-time="80" class="welcome-link" role="button" @click="welcomeAction"><text>{{ recent ? '继续阅读' : grade ? '查看' + grade.replace(/^小学/, '') + '练习' : '选择适合的年级' }}</text><wd-icon name="arrow-right" size="13px" /></button>
      </view>
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
.banner-slide { position: relative; height: 100%; overflow: hidden; border-radius: 16px; background: #f3f7f4; }
.banner-media { height: 150px; width: 100%; }
.banner-body { display: flex; align-items: center; gap: 12px; height: 96px; padding: 8px 16px; box-sizing: border-box; background: #fff; }
.banner-body .banner-kicker { margin: 0; font-size: 11.5px; letter-spacing: 0; }
.banner-body .banner-title { font-size: 16.5px; -webkit-line-clamp: 1; }
.banner-body .banner-subtitle { font-size: 12px; margin-top: 2px; -webkit-line-clamp: 1; }
.banner-cta { display: flex; align-items: center; gap: 4px; max-width: 86px; flex: none; padding: 6px 10px; border-radius: 999px; background: var(--lc-primary-soft, #e9f4eb); font-size: 12px; font-weight: 600; color: var(--lc-primary, #307e61); }
.banner-cta text { display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.banner-next { position: absolute; right: 4px; top: 100px; width: 44px; height: 44px; padding: 0; background: rgba(255, 255, 255, .92); color: #307e61; border-radius: 50%; box-shadow: 0 2px 8px #1d3a2a1f; z-index: 4; display: flex; align-items: center; justify-content: center; }
.text-banner .banner-body { background: transparent; display: block; height: auto; padding: 0; max-width: 80%; }
.image-banner { background: #f3f7f4; }
.banner-photo { display: block; width: 100%; height: 100%; }
.banner-media-fallback { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; height: 100%; background: #e7efe9; color: #86a791; font-size: 12px; }

/* —— 无图运营卡：文字卡 —— */
.text-banner { display: flex; align-items: center; gap: 12px; padding: 20px 18px; background: linear-gradient(118deg, #eef7ef 0%, #e4f0e6 58%, #dcebdd 100%); }
.banner-copy { position: relative; z-index: 1; flex: 1; min-width: 0; }
.banner-kicker { display: block; margin-bottom: 6px; color: #356a51; font-size: 11.5px; font-weight: 600; line-height: 1.4; letter-spacing: .2px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.banner-title { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; color: #234936; font-size: 19px; line-height: 1.4; font-weight: 700; overflow-wrap: anywhere; }
.banner-subtitle { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; margin-top: 6px; color: #587565; font-size: 12px; line-height: 1.5; overflow-wrap: anywhere; }
.banner-go { display: flex; align-items: center; justify-content: center; flex: none; position: relative; z-index: 1; width: 34px; height: 34px; border-radius: 50%; background: var(--lc-primary, #307e61); color: #fff; box-sizing: border-box; box-shadow: 0 3px 8px #2f6b5026; }
.banner-art { position: absolute; right: 0; top: 50%; transform: translateY(-50%) scale(0.64); transform-origin: right center; pointer-events: none; }

/* —— 轮播点：卡外右上，不受点击层影响 —— */
.banner-dots { position: absolute; z-index: 4; right: 12px; top: 11px; display: flex; align-items: center; gap: 1px; padding: 2px 5px; border-radius: 999px; background: rgba(20, 40, 28, 0.22); }
.banner-dot { position: relative; display: flex; align-items: center; justify-content: center; flex: none; width: 30px; height: 30px; margin: 0; padding: 0; background: transparent; }
/* 视觉圆点保持紧凑，纵向点击热区补到 44px。 */
.banner-dot::after { content: ''; position: absolute; top: -7px; right: 0; bottom: -7px; left: 0; }
.banner-dot > view { width: 5px; height: 5px; border-radius: 99px; background: rgba(255, 255, 255, 0.6); transition: width .2s; }
.banner-dot > view.active { width: 13px; background: #fff; }

.banner-hit { position: absolute; z-index: 3; inset: 0; width: 100%; height: 100%; margin: 0; padding: 0; border-radius: var(--lc-radius-card, 16px); background: transparent; }
.banner-hit:active { background: rgba(35, 80, 55, 0.06); }
.banner-hit:focus-visible { outline-offset: -3px; }

/* —— 加载骨架 —— */
.banner-skeleton { position: relative; display: flex; flex-direction: column; justify-content: center; gap: 10px; padding: 0 18px; border: 1px solid #e2ece4; border-radius: 16px; background: linear-gradient(115deg, #f3f8f3 0%, #e9f3ea 60%, #e2eee3 100%); box-sizing: border-box; overflow: hidden; }
.banner-skeleton > view { position: relative; z-index: 1; width: 55%; height: 11px; margin: 0; border-radius: 6px; background: #dce8dd; overflow: hidden; }
.banner-skeleton > view:first-child { width: 30%; height: 9px; }
.banner-skeleton > view:nth-child(2) { width: 58%; height: 17px; }
.banner-skeleton > view:last-child { width: 42%; height: 30px; margin-top: 4px; border-radius: 999px; background: #cfe0d1; }
.skeleton-glow { position: absolute; inset: 0; background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .6), transparent); animation: banner-shimmer 1.7s ease-in-out infinite; }
@keyframes banner-shimmer { 0% { transform: translateX(-100%); } 100% { transform: translateX(100%); } }
.welcome-skeleton::after { content: ''; position: absolute; right: 24px; top: 50%; width: 78px; height: 78px; margin-top: -39px; border-radius: 26px; background: #dce9dc; transform: rotate(-9deg); }

.home-welcome { position:relative;min-height:136px;padding:16px;border:1px solid #dbe8dd;border-radius:16px;overflow:hidden;background:radial-gradient(130px 120px at 88% 14%, #d7e9d9 0%, rgba(215,233,217,0) 72%),linear-gradient(115deg,#f3f9f3 0%,#e8f3e9 54%,#e0eee2 100%); }
.welcome-copy { position:relative;z-index:2;width:66%; }
.welcome-kicker { display:flex;align-items:center;gap:6px;color:#48705a;font-size:12px;font-weight:600;line-height:18px;letter-spacing:.2px; }
.welcome-dot { width:5px;height:5px;flex:none;border-radius:50%;background:#5f9675;box-shadow:0 0 0 3px #5f96751f; }
.welcome-title { display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;white-space:pre-line;margin-top:6px;color:#234936;font-size:20px;font-weight:700;line-height:1.38;letter-spacing:.1px; }
.welcome-link { display:inline-flex;align-items:center;gap:6px;min-height:40px;margin:12px 0 0;padding:0 14px 0 17px;border-radius:999px;background:#2f6b50;color:#fff;font-size:13.5px;font-weight:600;line-height:1.4;box-shadow:0 4px 10px #2f6b5026;transition:transform .16s ease, opacity .16s ease; }
.welcome-link text { max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap; }
.welcome-pressed { transform:scale(.97);opacity:.9; }
.welcome-art { position:absolute;right:-4px;top:50%;transform:translateY(-50%) scale(.52);transform-origin:right center;pointer-events:none; }
.welcome-skeleton { height:136px; }
@media (max-height:680px) { .home-welcome { min-height:108px;padding:12px 15px; }.welcome-kicker { display:none; }.welcome-title { margin-top:0;-webkit-line-clamp:1;font-size:19px; }.welcome-link { min-height:34px;margin-top:9px;font-size:12px; }.welcome-skeleton { height:108px; } }

@media (max-width: 359px) {
  .home-banner { padding-left: 16px; padding-right: 16px; }
  .text-banner { padding: 17px 15px; }
  .banner-title { font-size: 17px; }
  .welcome-title { font-size:18px; }
  .welcome-art { right:-12px;transform:translateY(-50%) scale(.46); }
  .home-welcome { padding:14px 15px; }
  .welcome-copy { width:68%; }
}
@media (prefers-reduced-motion: reduce) { .welcome-link { transition: none; } .skeleton-glow { animation: none; } }
</style>
