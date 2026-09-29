<script setup lang="ts">
import PrivacyConsent from './PrivacyConsent.vue'
import { ref, onMounted, onUnmounted } from 'vue'
import ChromeBack from './ChromeBack.vue'
import { chromeBar } from '../services/chrome'

const props = withDefaults(defineProps<{ back?: boolean; fallback?: string }>(), { fallback: '/pages/home/index' })
const inset = ref(0)
const backTop = ref(5)
const online = ref(true)
let revision = 0
function network(value: boolean) { revision++; online.value = value }
onMounted(() => {
  uni.$on('lc-network', network)
  const current = revision
  uni.getNetworkType({ success: result => { if (current === revision) online.value = result.networkType !== 'none' } })
})
onUnmounted(() => { revision++; uni.$off('lc-network', network) })
// 微信端自绘导航栏要**始终**留出「状态栏 + 胶囊」整条高度，跟是否显示返回按钮无关：
// 首页/我的/资料库(tab 态) 不带返回按钮，但内容也必须从胶囊下方开始，否则会顶到
// 状态栏、被系统区域盖住。h5 没有系统状态栏，只在需要返回按钮时占位。
const height = ref(props.back ? 54 : 0)
// #ifdef MP-WEIXIN
const bar = chromeBar()
inset.value = bar.inset
backTop.value = bar.backTop
height.value = bar.height
// #endif
function goBack() {
  const fallback = () => uni.switchTab({ url: props.fallback })
  if (getCurrentPages().length > 1) uni.navigateBack({ fail: fallback })
  else fallback()
}
</script>

<template>
  <PrivacyConsent />
  <view class="page-chrome" :style="{ height: height + 'px' }">
    <ChromeBack v-if="back" :top="backTop" label="返回上一页" @press="goBack" />
  </view>
  <view v-if="!online" class="offline-notice" role="status">网络已断开，请检查网络连接</view>
</template>

<style scoped>
.page-chrome { position: sticky; top:0; z-index:40; background:var(--lc-background); width: 100%; flex: none; }
.offline-notice { padding:8px 16px;background:#fff3d6;color:#70521b;font-size:12px;text-align:center; }
</style>
