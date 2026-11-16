<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
const props = defineProps<{ modelValue: string; id: string; label: string; items: { value: string; label: string; badge?: number }[]; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const icons: Record<string, string> = { overview: 'i-lucide-chart-no-axes-combined', campaigns: 'i-lucide-megaphone', records: 'i-lucide-users-round', rules: 'i-lucide-book-open', workspace: 'i-lucide-wallet', bills: 'i-lucide-receipt-text', payee: 'i-lucide-credit-card', notices: 'i-lucide-bell', monthly: 'i-lucide-calendar-days', batches: 'i-lucide-list-checks', disputes: 'i-lucide-messages-square', finance: 'i-lucide-users-round' }
const navigation = ref<HTMLElement>()
let observer: ResizeObserver | undefined
async function reveal() {
  await nextTick()
  const tab = document.getElementById(`${props.id}-tab-${props.modelValue}`), strip = navigation.value
  if (!tab || !strip) return
  const target = tab.getBoundingClientRect(), frame = strip.getBoundingClientRect()
  if (target.right > frame.right) strip.scrollLeft += target.right - frame.right + 6
  else if (target.left < frame.left) strip.scrollLeft -= frame.left - target.left + 6
}
watch(() => props.modelValue, reveal)
onMounted(() => { observer = new ResizeObserver(() => { void reveal() }); if (navigation.value) observer.observe(navigation.value); void reveal() })
onBeforeUnmount(() => observer?.disconnect())
async function move(event: KeyboardEvent, index: number) {
  if (props.disabled || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? props.items.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + props.items.length) % props.items.length
  const item = props.items[next]
  if (!item) return
  emit('update:modelValue', item.value)
  await nextTick()
  document.getElementById(`${props.id}-tab-${item.value}`)?.focus()
}
</script>
<template>
  <div ref="navigation" class="promotion-tabs" role="tablist" :aria-label="label">
    <button v-for="(item, index) in items" :id="`${id}-tab-${item.value}`" :key="item.value" type="button" role="tab"
      :aria-selected="modelValue === item.value" :aria-controls="`${id}-panel-${item.value}`" :tabindex="modelValue === item.value ? 0 : -1"
      :disabled="disabled" @click="emit('update:modelValue', item.value)" @keydown="move($event, index)"><UIcon v-if="icons[item.value]" :name="icons[item.value]!" aria-hidden="true" class="promotion-tab-icon" />{{ item.label }}<span v-if="item.badge" class="promotion-tab-badge">{{ item.badge }}<span class="sr-only"> 条未读</span></span></button>
  </div>
</template>
