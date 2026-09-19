<script setup lang="ts">
import { ref, watch } from 'vue'
import PrivateImage from './PrivateImage.vue'
import type { Asset } from '../types'
import { session } from '../services/session'
import { readPosition, rememberPosition } from '../services/reading-position'

const props = defineProps<{ pages: Asset[]; paperId: string; release: number }>()
const emit = defineEmits<{ close: [] }>()
const owner = session.user?.id || ''
const current = ref(readPosition(owner, props.paperId, props.release, props.pages.length))
const scale = ref(1)
const resetKeys = ref<Record<number, number>>({})
const zoomed = new Set<number>()
const jumpOpen = ref(false)
const navigationTop = ref(0)
const navigationHeight = ref(52)
// Keep the back action on the left, clear of WeChat's native right capsule.
// #ifdef MP-WEIXIN
const windowInfo = uni.getWindowInfo()
const capsule = uni.getMenuButtonBoundingClientRect()
navigationTop.value = windowInfo.statusBarHeight || 20
navigationHeight.value = Math.max(44, (capsule.top - navigationTop.value) * 2 + capsule.height)
// #endif
function close() { jumpOpen.value = false; emit('close') }
function select(index: number) {
  if (!Number.isInteger(index) || index < 0 || index >= props.pages.length) return
  // Native movable-view retains internal pan/zoom state. Reset only a page
  // that was zoomed, keeping ordinary adjacent images mounted during turns.
  if (zoomed.delete(current.value)) resetKeys.value[current.value] = (resetKeys.value[current.value] || 0) + 1
  current.value = index; scale.value = 1; jumpOpen.value = false
  rememberPosition(owner, props.paperId, props.release, index)
}
function change(event: { detail: { current: number } }) { select(event.detail.current) }
function resize(event: { detail: { scale: number } }, index: number) {
  if (index === current.value) {
    scale.value = event.detail.scale
    if (scale.value > 1.01) zoomed.add(index)
  }
}
watch(() => props.pages.length, count => { if (current.value >= count) select(Math.max(0, count - 1)) })
</script>

<template>
  <view class="paper-reader" role="dialog" aria-modal="true" aria-label="习题原稿预览">
    <view class="reader-header" :style="{ paddingTop: navigationTop + 'px', height: navigationTop + navigationHeight + 'px' }"><button class="reader-back" role="button" hover-class="control-pressed" aria-label="返回习题详情" @click.stop="close"><wd-icon name="arrow-left" size="20px" /><text>返回详情</text></button><text class="reader-title">原稿预览</text><view aria-hidden="true" /></view>
    <swiper class="reader-pages" :current="current" :disable-touch="scale > 1.01" @change="change">
      <swiper-item v-for="(page, index) in pages" :key="page.id">
        <movable-area class="reader-area" scale-area>
          <movable-view v-if="Math.abs(index - current) <= 1" :key="page.id + ':' + (resetKeys[index] || 0)" class="reader-image" :direction="index === current && scale > 1.01 ? 'all' : 'none'" scale :scale-min="1" :scale-max="4" :scale-value="1" @scale="resize($event, index)">
            <PrivateImage :src="page.url" :label="'第 ' + page.page_number + ' 页原稿'" fit />
          </movable-view>
        </movable-area>
      </swiper-item>
    </swiper>
    <view class="reader-footer"><text class="reader-hint">{{ scale > 1.01 ? '拖动查看细节，缩小后可横滑翻页' : '左右滑动翻页 · 双指缩放查看细节' }}</text><view class="reader-controls"><wd-button role="button" variant="text" :disabled="current === 0" @click="select(current - 1)">上一页</wd-button><button class="reader-jump" role="button" hover-class="control-pressed" aria-label="选择预览页码" @click="jumpOpen = true">{{ current + 1 }} / {{ pages.length }} 页 <wd-icon name="down" size="12px" /></button><wd-button role="button" variant="text" :disabled="current >= pages.length - 1" @click="select(current + 1)">下一页</wd-button></view></view>
    <wd-popup v-model="jumpOpen" position="bottom" :z-index="1300" root-portal safe-area-inset-bottom custom-style="border-radius:22px 22px 0 0">
      <view class="sheet"><view class="sheet-handle" /><view class="sheet-head"><text class="sheet-title">跳转到指定页</text><button class="reader-close" role="button" aria-label="关闭页码选择" @click="jumpOpen = false"><wd-icon name="close" size="20px" /></button></view><scroll-view scroll-y class="reader-page-options" :scroll-into-view="'reader-page-' + current"><button v-for="(page, index) in pages" :id="'reader-page-' + index" :key="page.id" class="reader-page-option" :class="{ selected: index === current }" role="button" hover-class="control-pressed" :aria-pressed="index === current" @click="select(index)">第 {{ page.page_number }} 页</button></scroll-view></view>
    </wd-popup>
  </view>
</template>

<style scoped>
.paper-reader { height:100vh;height:100dvh;display:flex;flex-direction:column;background:var(--lc-background);padding-bottom:env(safe-area-inset-bottom);box-sizing:border-box; }
.reader-header { position:relative;z-index:2;display:grid;grid-template-columns:92px minmax(0,1fr) 92px;align-items:center;padding:0 12px;flex:none;box-sizing:border-box;background:var(--lc-card); }.reader-title { text-align:center;font-size:18px;font-weight:600;white-space:nowrap; }.reader-back { display:flex;align-items:center;justify-content:flex-start;gap:4px;min-height:44px;width:92px;margin:0;padding:0;background:transparent;color:var(--lc-text);font-size:14px;line-height:1.5; }.reader-close { display:flex;align-items:center;justify-content:center;width:44px;height:44px;margin:0;padding:0;background:transparent;color:var(--lc-text); }
.reader-pages { position:relative;z-index:0;overflow:hidden;flex:1;min-height:0;width:100%; }.reader-area,.reader-image { width:100%;height:100%; }.reader-image { display:block; }
.reader-footer { position:relative;z-index:2;padding:12px 12px 16px;flex:none;background:var(--lc-card); }.reader-hint { display:block;text-align:center;font-size:12px;line-height:1.7;color:var(--lc-secondary); }.reader-controls { display:flex;align-items:center;justify-content:space-between;gap:8px; }.reader-jump { display:flex;align-items:center;justify-content:center;gap:8px;min-height:44px;margin:0;padding:0 8px;background:transparent;font-size:14px;font-variant-numeric:tabular-nums;color:var(--lc-text); }
.reader-page-options { height:40vh; }.reader-page-option { width:100%;margin:0;padding:12px;background:transparent;color:var(--lc-text);font-size:14px;text-align:left;line-height:1.6; }.reader-page-option.selected { background:var(--lc-primary-soft);color:var(--lc-primary); }
</style>
