<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'

interface SkeletonProps {
  count?: number
  type?: 'card' | 'list' | 'text'
}

const props = withDefaults(defineProps<SkeletonProps>(), {
  count: 3,
  type: 'card'
})

const skeletons = ref<number[]>([])
let interval: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  skeletons.value = Array.from({ length: props.count }, (_, i) => i)
  
  // Add shimmer animation effect
  interval = setInterval(() => {
    // Could be used for dynamic shimmer effects
  }, 2000)
})

onBeforeUnmount(() => {
  if (interval) clearInterval(interval)
})
</script>

<template>
  <view class="skeleton-container">
    <view 
      v-for="index in skeletons" 
      :key="index" 
      class="skeleton"
      :class="`skeleton-${type}`"
    >
      <view class="skeleton-shimmer" />
    </view>
  </view>
</template>

<style scoped>
.skeleton-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skeleton {
  position: relative;
  overflow: hidden;
  background: #f5f5f5;
  border-radius: 8px;
}

.skeleton-card {
  height: 180px;
  border-radius: 14px;
}

.skeleton-list {
  height: 80px;
  border-radius: 10px;
}

.skeleton-text {
  height: 20px;
  width: 80%;
  border-radius: 4px;
}

.skeleton-shimmer {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.4),
    transparent
  );
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}
</style>
