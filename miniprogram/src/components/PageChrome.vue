<script setup lang="ts">
import { ref } from 'vue'
import ChromeBack from './ChromeBack.vue'
import { chromeBar } from '../services/chrome'

const props = withDefaults(defineProps<{ back?: boolean; fallback?: string }>(), { fallback: '/pages/home/index' })
const inset = ref(0)
// 微信端自绘导航栏要**始终**留出「状态栏 + 胶囊」整条高度，跟是否显示返回按钮无关：
// 首页/我的/资料库(tab 态) 不带返回按钮，但内容也必须从胶囊下方开始，否则会顶到
// 状态栏、被系统区域盖住。h5 没有系统状态栏，只在需要返回按钮时占位。
const height = ref(props.back ? 54 : 0)
// #ifdef MP-WEIXIN
const bar = chromeBar()
inset.value = bar.inset
height.value = bar.height
// #endif
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
