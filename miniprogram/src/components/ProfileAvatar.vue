<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import type { User } from '../types'
import type { FileHandle } from '../services/file-pool'
import { acquireAsset } from '../services/assets'
import { avatarChoice, profileAvatar } from '../presentation'

// Keep the avatar root directly inside its sized container on WeChat as on H5.
// An extra native component host breaks percentage sizing in this layout.
defineOptions({ options: { virtualHost: true } })

const props = defineProps<{ user: Pick<User, 'id' | 'username' | 'nickname' | 'avatar' | 'avatar_url'> | null; previewSrc?: string }>()
const look = computed(() => profileAvatar(props.user))
const presetImage = computed(() => avatarChoice(props.user?.avatar)?.image)
const source = ref('')
let handle: FileHandle | null = null
let sequence = 0
watch(() => [props.user?.avatar_url, props.previewSrc], async () => {
  const current = ++sequence
  handle?.release(); handle = null; source.value = props.previewSrc || ''
  if (props.previewSrc || !props.user?.avatar_url) return
  handle = acquireAsset(props.user.avatar_url)
  try { const path = await handle.ready; if (current === sequence) source.value = path }
  catch { /* The default avatar remains available when the image cannot be loaded. */ }
}, { immediate: true })
function failed() { handle?.invalidate(); source.value = '' }
onUnmounted(() => { sequence++; handle?.release() })
</script>

<template>
  <view class="profile-avatar" :style="{ background: look.background, color: look.color }" role="img" aria-label="头像">
    <image v-if="source" :src="source" mode="aspectFill" class="photo" @error="failed" />
    <image v-else-if="presetImage" :src="presetImage" mode="aspectFill" class="photo" />
    <text v-else-if="look.glyph" class="glyph">{{ look.glyph }}</text>
    <text v-else>{{ look.initial || '学' }}</text>
  </view>
</template>

<style scoped>
.profile-avatar { display:flex;flex-shrink:0;align-items:center;justify-content:center;width:100%;height:100%;border-radius:50%;overflow:hidden;font-size:inherit;font-weight:600;line-height:1; }
.photo { display:block;width:100%;height:100%; }.glyph { font-size:1.2em;font-weight:400; }
</style>
