<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, nextTick } from 'vue'

interface VirtualScrollProps {
  items: any[]
  itemHeight: number
  visibleCount: number
}

const props = withDefaults(defineProps<VirtualScrollProps>(), {
  itemHeight: 100,
  visibleCount: 10
})

const scrollTop = ref(0)
const containerRef = ref<HTMLElement>()
const visibleRange = computed(() => {
  const start = Math.floor(scrollTop.value / props.itemHeight)
  const end = Math.min(start + props.visibleCount + 2, props.items.length)
  return { start: Math.max(0, start - 2), end }
})

const visibleItems = computed(() => {
  const { start, end } = visibleRange.value
  return props.items.slice(start, end).map((item, index) => ({
    item,
    index: start + index
  }))
})

const totalHeight = computed(() => props.items.length * props.itemHeight)
const offsetY = computed(() => visibleRange.value.start * props.itemHeight)

function handleScroll(e: any) {
  scrollTop.value = e.detail.scrollTop
}

onMounted(() => {
  if (containerRef.value) {
    containerRef.value.scrollTop = 0
  }
})
</script>

<template>
  <scroll-view
    :scroll-y="true"
    :style="{ height: visibleCount * itemHeight + 'px' }"
    :scroll-top="scrollTop"
    @scroll="handleScroll"
    ref="containerRef"
  >
    <view :style="{ height: totalHeight + 'px', position: 'relative' }">
      <view
        :style="{ 
          position: 'absolute',
          top: offsetY + 'px',
          width: '100%'
        }"
      >
        <slot :items="visibleItems" />
      </view>
    </view>
  </scroll-view>
</template>
