<script setup lang="ts">
import { computed, ref, watch } from 'vue'

interface Action { key: string; label: string; icon: string; color?: string; openType?: 'share' }
interface SwipeTouchEvent { touches: ArrayLike<{ clientX: number; clientY: number }>; preventDefault?: () => void }
const props = withDefaults(defineProps<{ actions: Action[]; open?: boolean; disabled?: boolean; shareId?: string; shareTitle?: string }>(), { open: false, disabled: false })
const emit = defineEmits<{ action: [key: string]; 'update:open': [value: boolean] }>()
const currentX = ref(0)
const direction = ref<'pending' | 'horizontal' | 'vertical'>('pending')
const dragging = ref(false)
const actionWidth = 70
const width = computed(() => props.actions.length * actionWidth)
let startX = 0, startY = 0, origin = 0, ignoreClickUntil = 0
const containerStyle = computed(() => ({ transform: `translateX(${currentX.value}px)`, transition: dragging.value ? 'none' : 'transform .2s ease' }))
watch(() => props.open, open => { currentX.value = open ? -width.value : 0 })
watch(() => props.disabled, disabled => { if (disabled) close() })
function close() { dragging.value = false; currentX.value = 0; emit('update:open', false) }
function handleTouchStart(event: SwipeTouchEvent) {
  if (props.disabled || !event.touches[0]) return
  startX = event.touches[0].clientX; startY = event.touches[0].clientY
  origin = props.open ? -width.value : 0; direction.value = 'pending'; dragging.value = true
}
function handleTouchMove(event: SwipeTouchEvent) {
  if (!dragging.value || !event.touches[0]) return
  const dx = event.touches[0].clientX - startX, dy = event.touches[0].clientY - startY
  if (direction.value === 'pending') {
    if (Math.max(Math.abs(dx), Math.abs(dy)) < 10) return
    direction.value = Math.abs(dx) > Math.abs(dy) * 1.2 ? 'horizontal' : 'vertical'
  }
  if (direction.value !== 'horizontal') return
  event.preventDefault?.()
  currentX.value = Math.max(-width.value, Math.min(0, origin + dx))
}
function handleTouchEnd() {
  if (!dragging.value) return
  dragging.value = false
  if (direction.value !== 'horizontal') return
  ignoreClickUntil = Date.now() + 350
  const open = origin === 0 ? currentX.value < -36 : currentX.value < origin + 36
  currentX.value = open ? -width.value : 0
  emit('update:open', open)
}
function cancel() { dragging.value = false; currentX.value = props.open ? -width.value : 0; ignoreClickUntil = Date.now() + 350 }
function blocksClick(allowWhileBusy = false) {
  if (Date.now() < ignoreClickUntil) return true
  if (props.open) { close(); return true }
  return props.disabled && !allowWhileBusy
}
function perform(key: string) { if (!props.disabled && props.open) { emit('action', key); close() } }
defineExpose({ blocksClick })
</script>

<template>
  <view class="swipe-container">
    <view v-if="open || dragging" class="swipe-actions" :aria-hidden="!open">
      <button role="button" v-for="action in actions" :key="action.key" class="swipe-action" hover-class="control-pressed"
        :style="{ width: actionWidth + 'px', backgroundColor: action.color }" :disabled="disabled || !open" :tabindex="open ? 0 : -1"
        :open-type="action.openType" :data-paper-id="shareId" :data-paper-title="shareTitle" :aria-label="action.label"
        @click.stop="perform(action.key)"><wd-icon :name="action.icon" size="20px" /><text>{{ action.label }}</text></button>
    </view>
    <view class="swipe-content" :style="containerStyle" @touchstart="handleTouchStart" @touchmove="handleTouchMove" @touchend="handleTouchEnd" @touchcancel="cancel"><slot /></view>
  </view>
</template>

<style scoped>
.swipe-container { position:relative;overflow:hidden;border-radius:10px; }
.swipe-actions { position:absolute;right:0;top:0;bottom:0;display:flex; }
.swipe-action { display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;min-height:44px;margin:0;padding:0;border-radius:0;color:#fff;font-size:12px;line-height:1.5; }
.swipe-content { position:relative;z-index:1;background:var(--lc-card);min-height:100%; }
</style>
