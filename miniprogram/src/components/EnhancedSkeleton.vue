<script setup lang="ts">
interface SkeletonProps {
  count?: number
  /**
   * card = 首页精选横向卡（贴合 PaperCard 封面 + 文案几何）
   * row  = 习题库列表行（贴合 PaperRow 几何）
   * list / text = 通用块
   */
  type?: 'card' | 'row' | 'list' | 'text'
  /** 读屏文案，随所在列表变化 */
  label?: string
}

withDefaults(defineProps<SkeletonProps>(), {
  count: 3,
  type: 'card',
  label: '正在加载习题'
})
</script>

<template>
  <view class="skeleton-container" :class="'is-' + type" :aria-label="label" aria-busy="true">
    <template v-if="type === 'card'">
      <view v-for="index in count" :key="index" class="skeleton-card">
        <view class="skeleton skeleton-cover"><view class="skeleton-shimmer" /></view>
        <view class="skeleton-card-lines">
          <view class="skeleton skeleton-title"><view class="skeleton-shimmer" /></view>
          <view class="skeleton skeleton-title skeleton-title-short"><view class="skeleton-shimmer" /></view>
          <view class="skeleton skeleton-card-meta"><view class="skeleton-shimmer" /></view>
        </view>
      </view>
    </template>
    <template v-else-if="type === 'row'">
      <view v-for="index in count" :key="index" class="skeleton-row">
        <view class="skeleton skeleton-thumb"><view class="skeleton-shimmer" /></view>
        <view class="skeleton-row-lines">
          <view class="skeleton skeleton-labels"><view class="skeleton-shimmer" /></view>
          <view class="skeleton skeleton-name"><view class="skeleton-shimmer" /></view>
          <view class="skeleton skeleton-meta"><view class="skeleton-shimmer" /></view>
        </view>
      </view>
    </template>
    <template v-else>
      <view v-for="index in count" :key="index" class="skeleton" :class="'skeleton-' + type"><view class="skeleton-shimmer" /></view>
    </template>
  </view>
</template>

<style scoped>
.skeleton-container { display: flex; flex-direction: column; gap: 12px; }
.skeleton-container.is-card { gap: 10px; }
.skeleton-container.is-row { gap:0;padding:0 12px;border:1px solid var(--lc-card-line);border-radius:var(--lc-radius-card);background:var(--lc-card); }

.skeleton { position: relative; overflow: hidden; background: var(--lc-card-line, #e7eee8); border-radius: 8px; }
.skeleton-list { height: 80px; border-radius: 10px; }
.skeleton-text { height: 20px; width: 80%; border-radius: 4px; }

.skeleton-card { display: flex; align-items: center; gap: 12px; padding: 10px 12px 10px 10px; border: 1px solid var(--lc-card-line); border-radius: 16px; background: var(--lc-card, #ffffff); box-shadow: var(--lc-card-shadow-soft); }
.skeleton-cover { flex: none; width: 68px; height: 92px; border-radius: 10px; }
.skeleton-card-lines { flex: 1; min-width: 0; align-self: stretch; padding: 4px 0; display: flex; flex-direction: column; justify-content: center; gap: 8px; }
.skeleton-title { height: 17px; border-radius: 6px; }
.skeleton-title-short { width: 68%; }
.skeleton-card-meta { height: 14px; width: 46%; margin-top: 3px; border-radius: 6px; }

.skeleton-row { display: flex; align-items: center; gap: 12px; min-height: 120px; padding: 16px 0; }
.skeleton-thumb { flex: none; width: 56px; height: 78px; }
.skeleton-row-lines { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 9px; }
.skeleton-labels { height: 12px; width: 38%; border-radius: 6px; }
.skeleton-name { height: 18px; width: 88%; border-radius: 6px; }
.skeleton-meta { height: 12px; width: 52%; border-radius: 6px; }

.skeleton-shimmer { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.55), transparent); animation: shimmer 1.5s infinite; }

@keyframes shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}
@media (max-width:359px) { .skeleton-container.is-row { padding:0 10px; }.skeleton-row { gap:10px; }.skeleton-thumb { width:52px;height:74px; }.skeleton-card { gap:10px;padding:9px 10px 9px 9px; }.skeleton-cover { width:64px;height:86px; } }
</style>
