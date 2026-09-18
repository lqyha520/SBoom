<script setup lang="ts">
import { ref, computed } from 'vue'

interface SwipeAction {
  key: string
  label: string
  icon: string
  color?: string
}

const props = defineProps<{
  actions: SwipeAction[]
}>()

const emit = defineEmits<{
  action: [key: string]
}>()

const startX = ref(0)
const currentX = ref(0)
const isSwiping = ref(false)
const actionWidth = 80
const swipeThreshold = 40

const containerStyle = computed(() => ({
  transform: `translateX(${currentX.value}px)`,
  transition: isSwiping.value ? 'none' : 'transform 0.3s ease'
}))

const activeAction = computed(() => {
  if (Math.abs(currentX.value) < swipeThreshold) return null
  const index = Math.floor(Math.abs(currentX.value) / actionWidth)
  const direction = currentX.value > 0 ? 'right' : 'left'
  if (direction === 'left' && index < props.actions.length) {
    return props.actions[index]
  }
  return null
})

function handleTouchStart(e: any) {
  startX.value = e.touches[0].clientX
  isSwiping.value = true
}

function handleTouchMove(e: any) {
  if (!isSwiping.value) return
  const diff = e.touches[0].clientX - startX.value
  const maxSwipe = -props.actions.length * actionWidth
  
  if (diff < 0) {
    currentX.value = Math.max(maxSwipe, diff)
  } else {
    currentX.value = Math.min(0, diff)
  }
}

function handleTouchEnd() {
  isSwiping.value = false
  
  if (activeAction.value) {
    emit('action', activeAction.value.key)
    currentX.value = 0
  } else {
    currentX.value = 0
  }
}

function reset() {
  currentX.value = 0
  isSwiping.value = false
}
</script>

<template>
  <view 
    class="swipe-container"
    @touchstart="handleTouchStart"
    @touchmove="handleTouchMove"
    @touchend="handleTouchEnd"
    @touchcancel="reset"
  >
    <view class="swipe-actions">
      <view 
        v-for="(action, index) in actions" 
        :key="action.key"
        class="swipe-action"
        :class="`action-${action.key}`"
        :style="{ 
          width: actionWidth + 'px',
          backgroundColor: action.color || '#f0f0f0'
        }"
        @click.stop="emit('action', action.key)"
      >
        <wd-icon :name="action.icon" size="20px" />
        <text>{{ action.label }}</text>
      </view>
    </view>
    <view class="swipe-content" :style="containerStyle">
      <slot />
    </view>
  </view>
</template>

<style scoped>
.swipe-container {
  position: relative;
  overflow: hidden;
}

.swipe-actions {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  display: flex;
  height: 100%;
}

.swipe-action {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  color: white;
  font-size: 12px;
}

.swipe-content {
  position: relative;
  z-index: 1;
  background: white;
  min-height: 100%;
}
</style>
