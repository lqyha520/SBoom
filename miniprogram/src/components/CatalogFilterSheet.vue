<script setup lang="ts">
import { ref, watch } from 'vue'
import { exerciseText } from '../presentation'
import { useTabBarOverlay } from '../services/tabbar-overlay'
import type { SiteCategory } from '../types'

const props = defineProps<{ open: boolean; grade: string; category: string; grades: string[]; categories: SiteCategory[] }>()
const emit = defineEmits<{ close: []; apply: [filters: { grade: string; category: string }] }>()
const gradeDraft = ref('')
const categoryDraft = ref('')
useTabBarOverlay(() => props.open)
watch(() => props.open, open => { if (open) { gradeDraft.value = props.grade; categoryDraft.value = props.category } })
function reset() { gradeDraft.value = ''; categoryDraft.value = '' }
function apply() { emit('apply', { grade: gradeDraft.value, category: categoryDraft.value }); emit('close') }
</script>

<template>
  <wd-popup :model-value="open" position="bottom" :z-index="1200" root-portal safe-area-inset-bottom custom-style="border-radius:8px 8px 0 0" @update:model-value="!$event && emit('close')">
    <view class="catalog-sheet" role="dialog" aria-modal="true" aria-label="筛选习题">
      <view class="sheet-handle" /><view class="catalog-sheet-head"><text class="sheet-title">筛选习题</text><button class="bare-icon" role="button" aria-label="关闭筛选" title="关闭筛选" @click="emit('close')"><wd-icon name="close" size="20px" /></button></view>
      <scroll-view scroll-y class="filter-options">
        <text class="filter-label">年级</text>
        <wd-radio-group v-model="gradeDraft" type="button" direction="horizontal" custom-class="filter-radio-group" role="radiogroup" aria-label="年级">
          <wd-radio value="" custom-class="filter-radio" role="radio" :aria-checked="!gradeDraft">全部年级</wd-radio>
          <wd-radio v-for="value in grades" :key="value" :value="value" custom-class="filter-radio" role="radio" :aria-checked="gradeDraft === value">{{ value }}</wd-radio>
        </wd-radio-group>
        <text class="filter-label">习题分类</text>
        <wd-radio-group v-model="categoryDraft" type="button" direction="horizontal" custom-class="filter-radio-group" role="radiogroup" aria-label="习题分类">
          <wd-radio value="" custom-class="filter-radio" role="radio" :aria-checked="!categoryDraft">全部分类</wd-radio>
          <wd-radio v-for="item in categories" :key="item.id" :value="item.id" custom-class="filter-radio" role="radio" :aria-checked="categoryDraft === item.id">{{ exerciseText(item.name) }}</wd-radio>
        </wd-radio-group>
      </scroll-view>
      <view class="filter-sheet-actions"><wd-button type="info" variant="plain" block role="button" @click="reset">重置</wd-button><wd-button block role="button" @click="apply">查看习题</wd-button></view>
    </view>
  </wd-popup>
</template>

<style scoped>
.catalog-sheet { max-width: 520px; margin: 0 auto; padding: 12px 22px 24px; }
.catalog-sheet-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.catalog-sheet-head .sheet-title { margin: 0; }
.filter-options { max-height: 54vh; }
.filter-label { display: block; margin: 18px 0 12px; font-size: 13px; font-weight: 600; color: var(--lc-secondary); }
.filter-sheet-actions { display: grid; grid-template-columns: 1fr 2fr; gap: 12px; padding-top: 24px; }
.catalog-sheet :deep(.filter-radio-group) { display: flex; flex-wrap: wrap; gap: 9px; }
.catalog-sheet :deep(.filter-radio) { margin: 0 !important; min-width: 76px; max-width: 100%; --wot-radio-button-border-radius: 999px; --wot-radio-button-font-size: 12px; --wot-radio-button-padding: 10px 14px; }
.catalog-sheet :deep(.wd-radio__label) { white-space: normal; overflow-wrap: anywhere; }
</style>
