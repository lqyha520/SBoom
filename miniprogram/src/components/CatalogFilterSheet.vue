<script setup lang="ts">
import { computed, getCurrentInstance, nextTick, onBeforeUnmount, ref, reactive, watch } from 'vue'
import { exerciseText } from '../presentation'
import { useTabBarOverlay } from '../services/tabbar-overlay'
import type { SiteCategory } from '../types'
import { emptyTags, tagKinds, type CatalogTag, type TagFilters } from '../services/growth'

const props = defineProps<{ open: boolean; grade: string; subject?: string; category: string; grades: string[]; categories: SiteCategory[]; tags: CatalogTag[]; tagFilters: TagFilters }>()
const emit = defineEmits<{ close: []; resetAll: []; apply: [filters: { grade: string; category: string; tags: TagFilters }] }>()
const gradeDraft = ref('')
const categoryDraft = ref('')
const tagDraft = reactive(emptyTags())
const tagPicker = ref(false)
const activeTag = ref<CatalogTag['kind']>('textbook')
const tagValue = ref<(string | number)[]>([''])
const availableKinds = computed(() => tagKinds.filter(item => props.tags.some(tag => tag.kind === item.kind)))
const tagColumns = computed(() => tagOptions(activeTag.value).map(tag => ({ value: tag.id, label: tag.name })))
const tagTitle = computed(() => `选择${tagKinds.find(item => item.kind === activeTag.value)?.label || '标签'}`)
const instance = getCurrentInstance()
const optionsId = 'catalog-filter-options-' + instance?.uid
const optionsHeight = ref(240)
let measurement = 0
uni.onWindowResize(measureOptions)
onBeforeUnmount(() => { measurement++; uni.offWindowResize(measureOptions) })
async function measureOptions() {
  const current = ++measurement
  if (!props.open) return
  await nextTick()
  if (!props.open || current !== measurement) return
  const info = uni.getWindowInfo()
  const limit = Math.min(460, info.windowHeight * .48, Math.max(100, info.windowHeight - 280))
  optionsHeight.value = limit
  const applyHeight = (height?: number) => {
    if (props.open && current === measurement && height) optionsHeight.value = Math.min(limit, Math.ceil(height))
  }
  // H5 的 teleport 在 body 下，uni 的页面查询无法覆盖它。
  // #ifdef H5
  applyHeight(document.getElementById(optionsId)?.getBoundingClientRect().height)
  // #endif
  // 微信 root-portal 保留组件归属，查询必须限定到当前组件。
  // #ifndef H5
  if (instance?.proxy) uni.createSelectorQuery().in(instance.proxy).select('#' + optionsId).boundingClientRect(result => {
    applyHeight((result as UniApp.NodeInfo | null)?.height)
  }).exec()
  // #endif
}
watch(() => [props.open, props.categories, props.tags, ...Object.values(tagDraft)], measureOptions)
useTabBarOverlay(() => props.open)
watch(() => props.open, open => { tagPicker.value = false; if (open) { gradeDraft.value = props.grade; categoryDraft.value = props.category; Object.assign(tagDraft, props.tagFilters) } })
function reset() { gradeDraft.value = props.grade; categoryDraft.value = ''; Object.assign(tagDraft, emptyTags()) }
function apply() { emit('apply', { grade: gradeDraft.value, category: categoryDraft.value, tags: { ...tagDraft } }); emit('close') }
function tagOptions(kind: CatalogTag['kind']) { return [{ id: '', name: '不限' }, ...props.tags.filter(item => item.kind === kind)] }
function openTag(kind: CatalogTag['kind']) { activeTag.value = kind; tagValue.value = [tagDraft[kind]]; tagPicker.value = true }
function selectTag(event: { value: (string | number)[] }) { tagDraft[activeTag.value] = String(event.value[0] || '') }
</script>

<template>
  <wd-popup :model-value="open" position="bottom" :z-index="1200" root-portal safe-area-inset-bottom custom-style="border-radius:22px 22px 0 0" @after-enter="measureOptions" @update:model-value="!$event && emit('close')">
    <view class="catalog-sheet" role="dialog" aria-modal="true" aria-label="更多筛选">
      <view class="sheet-handle" /><view class="catalog-sheet-head"><text class="sheet-title">更多筛选</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="bare-icon" role="button" aria-label="关闭筛选" title="关闭筛选" @click="emit('close')"><wd-icon name="close" size="20px" /></button></view>
      <text class="filter-context">{{ grade || '全部年级' }} · {{ subject || '全部学科' }}</text>
      <scroll-view scroll-y class="filter-options" :style="{ height: optionsHeight + 'px' }">
        <view :id="optionsId" class="filter-options-content">
        <text class="filter-label">习题分类</text>
        <wd-radio-group v-model="categoryDraft" type="button" direction="horizontal" custom-class="filter-radio-group" role="radiogroup" aria-label="习题分类">
          <wd-radio value="" custom-class="filter-radio" role="radio" :aria-checked="!categoryDraft">全部分类</wd-radio>
          <wd-radio v-for="item in categories" :key="item.id" :value="item.id" custom-class="filter-radio" role="radio" :aria-checked="categoryDraft === item.id">{{ exerciseText(item.name) }}</wd-radio>
        </wd-radio-group>
        <view v-for="item in availableKinds" :key="item.kind"><text class="filter-label">{{ item.label }}</text><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="tag-picker" role="button" :aria-label="`选择${item.label}`" @click="openTag(item.kind)">{{ tagOptions(item.kind).find(tag => tag.id === tagDraft[item.kind])?.name || '不限' }}<wd-icon name="down" /></button></view>
        </view>
      </scroll-view>
      <view class="filter-sheet-actions"><wd-button type="info" variant="plain" block role="button" @click="reset">清空本面板</wd-button><wd-button block role="button" @click="apply">查看习题</wd-button></view>
      <button class="reset-all-filters" hover-class="control-pressed" role="button" @click="emit('resetAll'); emit('close')">重置全部条件<text>包含年级、学科和搜索词</text></button>
    </view>
  </wd-popup>
  <wd-picker v-model="tagValue" v-model:visible="tagPicker" :title="tagTitle" :columns="tagColumns" :z-index="1400" root-portal @confirm="selectTag" />
</template>

<style scoped>
.catalog-sheet { display:flex;flex-direction:column;max-width:520px;max-height:90vh;margin:0 auto;padding:12px 22px 24px; }
.catalog-sheet-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.catalog-sheet-head .sheet-title { margin: 0; }
.filter-options { min-height:0;flex-shrink:1;max-height:48vh; }.filter-options-content { display:flex;flex-direction:column;padding-bottom:2px; }
.filter-context { display:block;color:var(--lc-secondary);font-size:13px;line-height:1.7; }
.tag-picker { display:flex;justify-content:space-between;align-items:center;gap:12px;width:100%;min-height:44px;margin:0;padding:10px 14px;border:0;border-radius:10px;background:var(--lc-background);font-size:13px;line-height:1.5;text-align:left;color:var(--lc-text); }
.tag-picker::after { border:0; }
.filter-label { display: block; margin: 18px 0 12px; font-size: 13px; font-weight: 600; color: var(--lc-secondary); }
.filter-sheet-actions { display: grid; grid-template-columns: 1fr 1.5fr; gap: 12px; padding-top: 20px; }
.reset-all-filters { display:flex;align-items:center;justify-content:center;gap:8px;flex-wrap:wrap;min-height:44px;margin:10px auto 0;padding:4px 0;background:transparent;color:var(--lc-secondary);font-size:13px;line-height:1.5; }.reset-all-filters text { font-size:12px;color:var(--lc-muted); }
.catalog-sheet :deep(.filter-radio-group) { display: flex; flex-wrap: wrap; gap: 9px; }
.catalog-sheet :deep(.filter-radio) { margin: 0 !important; min-width: 76px; max-width: 100%; --wot-radio-button-border-radius: 999px; --wot-radio-button-font-size: 12px; --wot-radio-button-padding: 10px 14px; }
.catalog-sheet :deep(.wd-radio__label) { white-space: normal; overflow-wrap: anywhere; }
</style>
