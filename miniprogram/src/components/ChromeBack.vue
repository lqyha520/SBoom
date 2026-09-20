<script setup lang="ts">
// 全站统一的左上角返回按钮：只负责外观与点击，跳转/关闭由使用方决定。
// 页面用 PageChrome、原稿预览等自绘导航栏都必须复用它，避免出现两套返回样式。
//
// ⚠️ 事件名必须避开原生事件名（tap/click/touch* 等），这里用 press。
// 之前叫 tap 时，`$emit('tap')` 和内部 <button> 冒泡到组件节点上的原生 tap 会命中
// 同一个 bindtap 绑定，一次点击触发两次 navigateBack —— 表现为「返回一次退了两级」
// （反馈页返回直接落到列表页，详情页被一起弹掉）。改事件名后只剩自定义事件一条路径。
withDefaults(defineProps<{ label?: string; top?: number; left?: number }>(), {
  label: '返回上一页', top: 0, left: 15,
})
defineEmits<{ press: [] }>()
</script>

<template>
  <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="bare-icon chrome-back" :style="{ top: top + 'px', left: left + 'px' }" role="button" :aria-label="label" :title="label" @click="$emit('press')"><wd-icon name="arrow-left" size="20px" /></button>
</template>

<style scoped>
.chrome-back { position: absolute; background: #ffffffb8; color: var(--lc-text); z-index: 1; }
</style>
