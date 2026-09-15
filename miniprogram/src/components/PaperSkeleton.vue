<script setup lang="ts">
withDefaults(defineProps<{ cards?: boolean; count?: number }>(), { count: 3 })
const coverRows = [{ height: '162px', borderRadius: '8px' }, { height: '18px', width: '88%' }, { height: '18px', width: '64%' }, { height: '12px', width: '48%' }]
const textRows = [{ height: '18px', width: '90%' }, { height: '14px', width: '58%' }, { height: '12px', width: '70%' }]
</script>

<template>
  <view :class="cards ? 'loading-cards' : 'loading-papers'" aria-label="正在加载习题" aria-busy="true">
    <view v-for="index in count" :key="index" class="loading-paper" :class="{ 'loading-card': cards }">
      <wd-skeleton v-if="cards" :row-col="coverRows" />
      <template v-else><view class="loading-thumb"><wd-skeleton :row-col="[{ height: '100px', borderRadius: '4px' }]" /></view><view class="grow"><wd-skeleton :row-col="textRows" /></view></template>
    </view>
  </view>
</template>

<style scoped>
.loading-cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 19px; overflow: hidden; }
.loading-papers { display: flex; flex-direction: column; gap: 12px; }
.loading-paper { display: flex; align-items: center; gap: 13px; padding: 14px 0; min-width: 0; }
.loading-card { display: block; padding: 0; }
.loading-thumb { width: 66px; flex: none; }
</style>
