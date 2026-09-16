<script setup lang="ts">
import { computed, ref, reactive, watch } from 'vue'
import { exerciseText } from '../presentation'
import { useTabBarOverlay } from '../services/tabbar-overlay'
import type { SiteCategory } from '../types'
import { emptyTags, tagKinds, type CatalogTag, type TagFilters } from '../services/growth'

const props = defineProps<{ open: boolean; grade: string; category: string; grades: string[]; categories: SiteCategory[]; tags: CatalogTag[]; tagFilters: TagFilters }>()
const emit = defineEmits<{ close: []; apply: [filters: { grade: string; category: string; tags: TagFilters }] }>()
const gradeDraft = ref('')
const categoryDraft = ref('')
const tagDraft = reactive(emptyTags())
const tagPicker = ref(false)
const activeTag = ref<CatalogTag['kind']>('textbook')
const tagValue = ref<(string | number)[]>([''])
const tagColumns = computed(() => tagOptions(activeTag.value).map(tag => ({ value: tag.id, label: tag.name })))
const tagTitle = computed(() => `选择${tagKinds.find(item => item.kind === activeTag.value)?.label || '标签'}`)
useTabBarOverlay(() => props.open)
watch(() => props.open, open => { tagPicker.value = false; if (open) { gradeDraft.value = props.grade; categoryDraft.value = props.category; Object.assign(tagDraft, props.tagFilters) } })
function reset() { gradeDraft.value = ''; categoryDraft.value = ''; Object.assign(tagDraft, emptyTags()) }
function apply() { emit('apply', { grade: gradeDraft.value, category: categoryDraft.value, tags: { ...tagDraft } }); emit('close') }
function tagOptions(kind: CatalogTag['kind']) { return [{ id: '', name: '不限' }, ...props.tags.filter(item => item.kind === kind)] }
function openTag(kind: CatalogTag['kind']) { activeTag.value = kind; tagValue.value = [tagDraft[kind]]; tagPicker.value = true }
function selectTag(event: { value: (string | number)[] }) { tagDraft[activeTag.value] = String(event.value[0] || '') }
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
        <view v-for="item in tagKinds" :key="item.kind"><text class="filter-label">{{ item.label }}</text><button class="tag-picker" role="button" :aria-label="`选择${item.label}`" @click="openTag(item.kind)">{{ tagOptions(item.kind).find(tag => tag.id === tagDraft[item.kind])?.name || '不限' }}<wd-icon name="down" /></button></view>
      </scroll-view>
      <view class="filter-sheet-actions"><wd-button type="info" variant="plain" block role="button" @click="reset">重置</wd-button><wd-button block role="button" @click="apply">查看习题</wd-button></view>
    </view>
  </wd-popup>
  <wd-picker v-model="tagValue" v-model:visible="tagPicker" :title="tagTitle" :columns="tagColumns" :z-index="1400" root-portal @confirm="selectTag" />
</template>

<style scoped>
.catalog-sheet { max-width: 520px; margin: 0 auto; padding: 12px 22px 24px; }
.catalog-sheet-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.catalog-sheet-head .sheet-title { margin: 0; }
.filter-options { max-height: 54vh; }
.tag-picker { display:flex;justify-content:space-between;align-items:center;gap:12px;width:100%;min-height:44px;margin:0;padding:10px 14px;border:0;border-radius:10px;background:var(--lc-background);font-size:13px;line-height:1.5;text-align:left;color:var(--lc-text); }
.tag-picker::after { border:0; }
.filter-label { display: block; margin: 18px 0 12px; font-size: 13px; font-weight: 600; color: var(--lc-secondary); }
.filter-sheet-actions { display: grid; grid-template-columns: 1fr 2fr; gap: 12px; padding-top: 24px; }
.catalog-sheet :deep(.filter-radio-group) { display: flex; flex-wrap: wrap; gap: 9px; }
.catalog-sheet :deep(.filter-radio) { margin: 0 !important; min-width: 76px; max-width: 100%; --wot-radio-button-border-radius: 999px; --wot-radio-button-font-size: 12px; --wot-radio-button-padding: 10px 14px; }
.catalog-sheet :deep(.wd-radio__label) { white-space: normal; overflow-wrap: anywhere; }
</style>
