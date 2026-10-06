<script setup lang="ts">
import { computed } from 'vue'
import { useExamStore } from '../stores/exam'
import { TYPE_NAME } from '../constants'
import type { PaperStyle } from '../types'
defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()
const store = useExamStore()
const preset = computed(() => store.style.frame !== 'none' || store.style.reward ? 'fun' : store.style.banner || store.style.secColor ? 'colorful' : 'standard')
const presets = [{ value: 'standard' as const, label: '标准', icon: 'i-lucide-file-text' }, { value: 'colorful' as const, label: '彩色', icon: 'i-lucide-palette' }, { value: 'fun' as const, label: '童趣', icon: 'i-lucide-sparkles' }]
const backgrounds = [{ value: 'none', label: '无' }, { value: 'dots', label: '彩色圆点' }, { value: 'grid', label: '浅格线' }, { value: 'stars', label: '小星星' }, { value: 'clouds', label: '云朵' }, { value: 'rainbow', label: '彩虹' }]
const frames = [{ value: 'none', label: '无边框' }, { value: 'rainbow', label: '彩虹花边' }, { value: 'stars', label: '星星边框' }, { value: 'crayon', label: '蜡笔粉边' }, { value: 'dots', label: '蓝色圆点' }]
</script>

<template>
  <USlideover :open="open" title="卷面设置" @update:open="value => { if (!value) emit('close') }">
    <template #body>
      <div class="field-stack">
        <h3 class="text-sm font-semibold">整体风格</h3>
        <UFormField label="卷面风格">
          <div class="grid grid-cols-3 gap-2">
            <UButton v-for="item in presets" :key="item.value" :icon="item.icon" :label="item.label" :color="preset === item.value ? 'primary' : 'neutral'" :variant="preset === item.value ? 'soft' : 'outline'" class="justify-center" :aria-pressed="preset === item.value" @click="store.applyStylePreset(item.value)" />
          </div>
        </UFormField>
        <UFormField label="背景图案"><USelect :model-value="store.style.bg" :items="backgrounds" @update:model-value="store.setStyle({ bg: $event as PaperStyle['bg'] })" /></UFormField>
        <UFormField v-if="store.style.bg !== 'none'" label="背景不透明度" :hint="store.style.bgOpacity + '%'"><USlider :model-value="store.style.bgOpacity" :min="10" :max="100" aria-label="背景不透明度" @update:model-value="store.setStyle({ bgOpacity: Number($event) })" /></UFormField>
        <USwitch :model-value="store.style.banner" label="标题横幅" @update:model-value="store.setStyle({ banner: $event })" />
        <USwitch :model-value="store.style.secColor" label="彩色大题标题" @update:model-value="store.setStyle({ secColor: $event })" />
        <USeparator />
        <h3 class="text-sm font-semibold">卷面元素</h3>
        <UFormField label="装饰边框"><USelect :model-value="store.style.frame" :items="frames" @update:model-value="store.setStyle({ frame: $event as PaperStyle['frame'] })" /></UFormField>
        <USwitch :model-value="store.style.encourage" label="大题鼓励语" @update:model-value="store.setStyle({ encourage: $event })" />
        <USwitch :model-value="store.style.reward" label="卷尾奖励区" @update:model-value="store.setStyle({ reward: $event })" />
        <UFormField label="大字号"><USelect :model-value="store.style.kidFont" :items="[{ label: '关闭', value: 'off' }, { label: '开启', value: 'on' }, { label: '一、二年级自动开启', value: 'auto' }]" @update:model-value="store.setStyle({ kidFont: $event as PaperStyle['kidFont'] })" /></UFormField>
        <USeparator />
        <h3 class="text-sm font-semibold">导出设置</h3>
        <USwitch :model-value="store.style.exportBg" label="导出保留彩色背景" @update:model-value="store.setStyle({ exportBg: $event })" />
        <template v-if="store.customTypes.length">
          <USeparator /><h3 class="text-sm font-medium">自定义题型</h3>
          <div v-for="type in store.customTypes" :key="type.id" class="row-between">
            <div><p class="text-sm">{{ type.name }}</p><p class="text-xs text-muted">{{ TYPE_NAME[type.baseType] || type.baseType }} / {{ type.defaultCount }} 题</p></div>
            <UTooltip :text="'删除' + type.name"><UButton icon="i-lucide-trash-2" color="error" variant="ghost" :aria-label="'删除' + type.name" @click="store.removeCustomType(type.id)" /></UTooltip>
          </div>
        </template>
      </div>
    </template>
    <template #footer><UButton label="完成" @click="emit('close')" /></template>
  </USlideover>
</template>
