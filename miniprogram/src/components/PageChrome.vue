<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(defineProps<{ back?: boolean; fallback?: string }>(), { fallback: '/pages/home/index' })
const inset = ref(0)
const height = ref(props.back ? 54 : 0)
// Leave WeChat's system capsule and status bar unobstructed in custom navigation.
// #ifdef MP-WEIXIN
const windowInfo = uni.getWindowInfo()
const capsule = uni.getMenuButtonBoundingClientRect()
inset.value = windowInfo.statusBarHeight || 20
height.value = Math.max(inset.value + 44, capsule.bottom + 8)
// #endif
function goBack() {
  const fallback = () => uni.switchTab({ url: props.fallback })
  if (getCurrentPages().length > 1) uni.navigateBack({ fail: fallback })
  else fallback()
}
</script>

<template>
  <view class="page-chrome" :style="{ height: height + 'px' }">
    <button v-if="back" class="bare-icon chrome-back" :style="{ top: inset + 5 + 'px' }" role="button" aria-label="返回上一页" title="返回上一页" @click="goBack"><wd-icon name="arrow-left" size="20px" /></button>
  </view>
</template>

<style scoped>
.page-chrome { position: relative; width: 100%; flex: none; }
.chrome-back { position: absolute; left: 15px; background: #ffffffb8; color: var(--lc-text); z-index: 1; }
</style>
