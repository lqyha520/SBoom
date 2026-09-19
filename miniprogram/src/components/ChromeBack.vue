<script setup lang="ts">
// 全站统一的左上角返回按钮：只负责外观与点击，跳转/关闭由使用方决定。
// 页面用 PageChrome、原稿预览等自绘导航栏都必须复用它，避免出现两套返回样式。
withDefaults(defineProps<{ label?: string; top?: number; left?: number }>(), {
  label: '返回上一页', top: 0, left: 15,
})
defineEmits<{ tap: [] }>()
</script>

<template>
  <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="bare-icon chrome-back" :style="{ top: top + 'px', left: left + 'px' }" role="button" :aria-label="label" :title="label" @click="$emit('tap')"><wd-icon name="arrow-left" size="20px" /></button>
</template>

<style scoped>
.chrome-back { position: absolute; background: #ffffffb8; color: var(--lc-text); z-index: 1; }
</style>
