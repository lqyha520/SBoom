<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { errorMessage } from '../services/api'
import { saveProfile, session } from '../services/session'
import { useTabBarOverlay } from '../services/tabbar-overlay'
import { avatarChoice, profileAvatar, AVATAR_CHOICES } from '../presentation'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const nickname = ref('')
const avatar = ref('')
const busy = ref(false)
const error = ref('')
let revision = 0
useTabBarOverlay(() => props.open)

// 微信端用 nickname 输入类型，键盘上方会出现「使用微信昵称」的快捷入口；
// 其余平台用普通文本输入（同一个变量赋值，避免条件编译在两端各声明一次而无法通过类型检查）
let nicknameType: 'text' | 'nickname' = 'text'
// #ifdef MP-WEIXIN
nicknameType = 'nickname'
// #endif

const look = computed(() => profileAvatar(session.user))
// 没选头像时的「默认形象」预览：首字 + 由账号 id 派生的配色
const fallback = computed(() => profileAvatar({ id: session.user?.id || '', username: session.user?.username || '', avatar: '' }))
const chosen = computed(() => avatarChoice(avatar.value))
const shown = computed(() => chosen.value || fallback.value)
const nicknameError = computed(() => {
  const value = nickname.value.trim()
  if (!value) return '昵称不能为空'
  if (value.length < 2 || value.length > 32) return '昵称需为 2-32 位'
  if (!/^[\w\u4e00-\u9fa5-]{2,32}$/.test(value)) return '昵称只能用中文、字母、数字、下划线或短横线'
  return ''
})
const dirty = computed(() => !!session.user &&
  (nickname.value.trim() !== session.user.username || avatar.value !== (session.user.avatar || '')))
const canSave = computed(() => !busy.value && dirty.value && !nicknameError.value)

watch(() => props.open, value => {
  revision++
  error.value = ''
  busy.value = false
  if (value) {
    nickname.value = session.user?.username || ''
    avatar.value = session.user?.avatar || ''
  }
})

async function save() {
  if (busy.value || !canSave.value || !session.user) return
  if (nicknameError.value) { error.value = nicknameError.value; return }
  const current = ++revision
  busy.value = true; error.value = ''
  try {
    const name = nickname.value.trim()
    // 只提交真正改过的字段，免得白写一次库、白涨一次 revision
    const payload: { username?: string; avatar?: string } = {}
    if (name !== session.user.username) payload.username = name
    if (avatar.value !== (session.user.avatar || '')) payload.avatar = avatar.value
    await saveProfile(payload)
    if (current !== revision) return
    emit('saved')
  } catch (cause) { if (current === revision) error.value = errorMessage(cause) }
  finally { if (current === revision) busy.value = false }
}
</script>

<template>
  <wd-popup :model-value="open" position="bottom" :z-index="1250" :close-on-click-modal="!busy" root-portal safe-area-inset-bottom custom-style="border-radius:8px 8px 0 0" @update:model-value="!$event && emit('close')">
    <view class="sheet profile-sheet" role="dialog" aria-modal="true" aria-label="编辑资料">
      <view class="sheet-handle" />
      <view class="sheet-head"><text class="sheet-title">编辑资料</text><button class="bare-icon" role="button" aria-label="关闭编辑资料" :disabled="busy" @click="emit('close')"><wd-icon name="close" size="20px" /></button></view>
      <view class="profile-preview">
        <view class="preview-avatar" :style="{ background: shown.background, color: shown.color }">
          <text v-if="chosen" class="preview-glyph">{{ chosen.glyph }}</text>
          <text v-else class="preview-initial">{{ fallback.initial || '学' }}</text>
        </view>
        <text class="preview-name">{{ nickname.trim() || look.initial || '我的昵称' }}</text>
      </view>
      <text class="field-label">选择头像</text>
      <view class="avatar-grid" role="radiogroup" aria-label="选择头像">
        <button v-for="choice in AVATAR_CHOICES" :key="choice.key" class="avatar-option" :class="{ selected: avatar === choice.key }" role="radio" :aria-checked="avatar === choice.key" :aria-label="choice.label" :disabled="busy" @click="avatar = choice.key; error = ''">
          <text class="avatar-glyph" :style="{ background: choice.background, color: choice.color }">{{ choice.glyph }}</text>
          <wd-icon v-if="avatar === choice.key" name="check-circle-fill" size="15px" class="avatar-tick" />
        </button>
      </view>
      <button v-if="session.user?.avatar" class="text-link reset-avatar" role="button" :disabled="busy" @click="avatar = ''; error = ''">恢复默认形象</button>
      <text class="field-label">昵称</text>
      <wd-input v-model="nickname" :type="nicknameType" :maxlength="32" :show-word-limit="true" clearable prefix-icon="user" custom-class="field-input" placeholder="请输入昵称" aria-label="昵称" :disabled="busy" @input="error = ''" />
      <text v-if="nickname && nicknameError" class="field-hint error-text">{{ nicknameError }}</text>
      <text v-else class="field-hint">2-32 位，支持中文、字母、数字、下划线；昵称会显示在「我的」页面，也是账号密码登录时用的账号名。</text>
      <view v-if="error" class="error-strip" role="alert">{{ error }}</view>
      <view class="sheet-actions"><wd-button role="button" block :loading="busy" :disabled="!canSave" @click="save">保存</wd-button></view>
    </view>
  </wd-popup>
</template>

<style scoped>
.profile-sheet { max-height: 88vh; overflow-y: auto; }
.profile-preview { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 6px 0 4px; }
.preview-avatar { display: flex; align-items: center; justify-content: center; width: 76px; height: 76px; border: 2px solid #ffffff; border-radius: 50%; box-shadow: 0 8px 18px #23392d14; }
.preview-glyph { font-size: 40px; line-height: 1; }
.preview-initial { font-size: 30px; font-weight: 650; line-height: 1; }
.preview-name { font-size: 15px; font-weight: 600; color: var(--lc-text); overflow-wrap: anywhere; }
.avatar-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.avatar-option { position: relative; display: flex; align-items: center; justify-content: center; width: 100%; min-height: 66px; padding: 0; margin: 0; background: transparent; border: 0; border-radius: 0; line-height: 1.5; }
.avatar-option::after { border: 0; }
.avatar-glyph { display: flex; align-items: center; justify-content: center; width: 54px; height: 54px; border: 2px solid transparent; border-radius: 50%; font-size: 27px; line-height: 1; }
.avatar-option.selected .avatar-glyph { border-color: var(--lc-primary); box-shadow: 0 4px 12px #307e611f; }
.avatar-option:active .avatar-glyph { transform: scale(.94); }
.avatar-tick { position: absolute; right: 12px; bottom: 4px; color: var(--lc-primary); background: #fff; border-radius: 50%; }
.reset-avatar { display: flex; align-items: center; justify-content: center; margin: 6px auto 0; }
.field-input :deep(.wd-input) { background: var(--lc-background); border-radius: 8px; --wot-input-padding: 14px; --wot-input-inner-height: 24px; --wot-input-bg: transparent; }
.field-hint { display: block; margin-top: 8px; color: var(--lc-muted); font-size: 11px; line-height: 1.7; }
.field-hint.error-text { color: #a34040; }
@media (max-width: 359px) { .avatar-grid { gap: 8px; } .avatar-glyph { width: 48px; height: 48px; font-size: 24px; } }
</style>
