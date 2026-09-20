<script setup lang="ts">
import { ref, watch } from 'vue'
import ChromeBack from './ChromeBack.vue'
import PrivateImage from './PrivateImage.vue'
import type { Asset } from '../types'
import { session } from '../services/session'
import { chromeBar } from '../services/chrome'
import { readPosition, rememberPosition } from '../services/reading-position'

const props = defineProps<{ pages: Asset[]; paperId: string; release: number }>()
const emit = defineEmits<{ close: [] }>()
const owner = session.user?.id || ''
const current = ref(readPosition(owner, props.paperId, props.release, props.pages.length))
const scale = ref(1)
/** 当前页是否处于放大态：给 swiper 的 disable-touch 与提示文案用，跨阈值才变，避免每帧 setData。 */
const zoomedCurrent = ref(false)
const resetKeys = ref<Record<number, number>>({})
const zoomed = new Set<number>()
const jumpOpen = ref(false)
// 顶部栏几何与 PageChrome 共用同一处计算，保证各页返回按钮位置一致。
// 注意 chromeBar().height 是**含状态栏的总高**（PageChrome 直接拿它当占位高度）；
// 这里 header 用 paddingTop 顶出状态栏 + border-box，所以 height 直接取总高，
// 不能再加 navigationTop，否则状态栏会被算两遍、标题栏偏高。
const bar = chromeBar()
const navigationTop = ref(bar.inset)
const navigationHeight = ref(bar.height)
function close() { jumpOpen.value = false; emit('close') }
function select(index: number) {
  if (!Number.isInteger(index) || index < 0 || index >= props.pages.length) return
  // Native movable-view retains internal pan/zoom state. Reset only a page
  // that was zoomed, keeping ordinary adjacent images mounted during turns.
  if (zoomed.delete(current.value)) resetKeys.value[current.value] = (resetKeys.value[current.value] || 0) + 1
  current.value = index; scale.value = 1; zoomedCurrent.value = false; jumpOpen.value = false
  rememberPosition(owner, props.paperId, props.release, index)
}
function change(event: { detail: { current: number } }) { select(event.detail.current) }
// 缩放期间绝不给 movable-view 改属性（direction 固定为 all）：每帧 setData 会打断它的
// 手势状态机，表现为"放大后拖不动"。这里只记录结果，并把倍数量化到 0.05 减少重渲染。
function resize(event: { detail: { scale: number } }, index: number) {
  if (index !== current.value) return
  const next = event.detail.scale
  const rounded = Math.round(next * 20) / 20
  if (rounded !== scale.value) scale.value = rounded
  const zoomedNow = next > 1.01
  if (zoomedNow) zoomed.add(index)
  if (zoomedNow !== zoomedCurrent.value) zoomedCurrent.value = zoomedNow
}
watch(() => props.pages.length, count => { if (current.value >= count) select(Math.max(0, count - 1)) })
</script>

<template>
  <view class="paper-reader" role="dialog" aria-modal="true" aria-label="习题原稿预览">
    <view class="reader-header" :style="{ paddingTop: navigationTop + 'px', height: navigationHeight + 'px' }"><ChromeBack :top="navigationTop + 5" label="返回习题详情" @press="close" /><text class="reader-title">原稿预览</text></view>
    <swiper class="reader-pages" :current="current" :disable-touch="zoomedCurrent" @change="change">
      <swiper-item v-for="(page, index) in pages" :key="page.id">
        <movable-area class="reader-area" scale-area>
          <!-- direction 固定为 all：只有放大后才有可移动空间；动态改它会在手势中途打断 movable-view，表现为放大后拖不动 -->
          <movable-view v-if="Math.abs(index - current) <= 1" :key="page.id + ':' + (resetKeys[index] || 0)" class="reader-image" direction="all" scale :scale-min="1" :scale-max="4" :scale-value="1" @scale="resize($event, index)">
            <PrivateImage :src="page.url" :label="'第 ' + page.page_number + ' 页原稿'" fit />
          </movable-view>
        </movable-area>
      </swiper-item>
    </swiper>
    <view class="reader-footer"><text class="reader-hint">{{ zoomedCurrent ? '拖动查看细节，缩小后可横滑翻页' : '左右滑动翻页 · 双指缩放查看细节' }}</text><view class="reader-controls"><wd-button role="button" variant="text" :disabled="current === 0" @click="select(current - 1)">上一页</wd-button><button class="reader-jump" role="button" hover-class="control-pressed" aria-label="选择预览页码" @click="jumpOpen = true">{{ current + 1 }} / {{ pages.length }} 页 <wd-icon name="down" size="12px" /></button><wd-button role="button" variant="text" :disabled="current >= pages.length - 1" @click="select(current + 1)">下一页</wd-button></view></view>
    <wd-popup v-model="jumpOpen" position="bottom" :z-index="1300" root-portal safe-area-inset-bottom custom-style="border-radius:22px 22px 0 0">
      <view class="sheet"><view class="sheet-handle" /><view class="sheet-head"><text class="sheet-title">跳转到指定页</text><button class="reader-close" role="button" aria-label="关闭页码选择" @click="jumpOpen = false"><wd-icon name="close" size="20px" /></button></view><scroll-view scroll-y class="reader-page-options" :scroll-into-view="'reader-page-' + current"><button v-for="(page, index) in pages" :id="'reader-page-' + index" :key="page.id" class="reader-page-option" :class="{ selected: index === current }" role="button" hover-class="control-pressed" :aria-pressed="index === current" @click="select(index)">第 {{ page.page_number }} 页</button></scroll-view></view>
    </wd-popup>
  </view>
</template>

<style scoped>
.paper-reader { height:100vh;height:100dvh;display:flex;flex-direction:column;background:var(--lc-background);padding-bottom:env(safe-area-inset-bottom);box-sizing:border-box; }
.reader-header { position:relative;z-index:2;display:flex;align-items:center;justify-content:center;padding:0 12px;flex:none;box-sizing:border-box;background:var(--lc-card); }.reader-title { text-align:center;font-size:18px;font-weight:600;white-space:nowrap; }.reader-close { display:flex;align-items:center;justify-content:center;width:44px;height:44px;margin:0;padding:0;background:transparent;color:var(--lc-text); }
.reader-pages { position:relative;z-index:0;overflow:hidden;flex:1;min-height:0;width:100%; }.reader-area,.reader-image { width:100%;height:100%; }.reader-image { display:block; }
.reader-footer { position:relative;z-index:2;padding:12px 12px 16px;flex:none;background:var(--lc-card); }.reader-hint { display:block;text-align:center;font-size:12px;line-height:1.7;color:var(--lc-secondary); }.reader-controls { display:flex;align-items:center;justify-content:space-between;gap:8px; }.reader-jump { display:flex;align-items:center;justify-content:center;gap:8px;min-height:44px;margin:0;padding:0 8px;background:transparent;font-size:14px;font-variant-numeric:tabular-nums;color:var(--lc-text); }
.reader-page-options { height:40vh; }.reader-page-option { width:100%;margin:0;padding:12px;background:transparent;color:var(--lc-text);font-size:14px;text-align:left;line-height:1.6; }.reader-page-option.selected { background:var(--lc-primary-soft);color:var(--lc-primary); }
</style>
