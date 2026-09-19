<script setup lang="ts">
import { ref } from 'vue'
import ChromeBack from './ChromeBack.vue'
import { chromeBar } from '../services/chrome'

const props = withDefaults(defineProps<{ back?: boolean; fallback?: string }>(), { fallback: '/pages/home/index' })
// 状态栏内边距与栏高由 services/chrome.ts 统一计算（对齐微信胶囊）。
const { inset, height: barHeight } = chromeBar()
const height = ref(props.back ? barHeight : 0)
function goBack() {
  const fallback = () => uni.switchTab({ url: props.fallback })
  if (getCurrentPages().length > 1) uni.navigateBack({ fail: fallback })
  else fallback()
}
</script>

<template>
  <view class="page-chrome" :style="{ height: height + 'px' }">
    <ChromeBack v-if="back" :top="inset + 5" label="返回上一页" @tap="goBack" />
  </view>
</template>

<style scoped>
.page-chrome { position: relative; width: 100%; flex: none; }
</style>
