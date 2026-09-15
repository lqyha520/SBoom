<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { errorMessage } from '../services/api'
import { savePassword, session } from '../services/session'
import { useTabBarOverlay } from '../services/tabbar-overlay'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const current = ref('')
const next = ref('')
const confirm = ref('')
const busy = ref(false)
const error = ref('')
// 刚打开时不要先甩一条红字，等用户动过输入框再提示
const touched = ref(false)
let revision = 0
useTabBarOverlay(() => props.open)

// 微信一键登录建出来的账号还没有密码，这里是「首次设置密码」，不要问当前密码
const hasPassword = computed(() => !!session.user?.has_password)
const localError = computed(() => {
  if (hasPassword.value && !current.value) return '请输入当前密码'
  if (next.value && next.value.length < 6) return '新密码至少需要 6 位'
  if (confirm.value && confirm.value !== next.value) return '两次输入的新密码不一致'
  return ''
})
const canSave = computed(() => !busy.value && next.value.length >= 6 && confirm.value === next.value &&
  (!hasPassword.value || current.value.length > 0))

function reset() {
  current.value = ''
  next.value = ''
  confirm.value = ''
  error.value = ''
  touched.value = false
  busy.value = false
}
watch(() => props.open, () => { revision++; reset() })

function input() { touched.value = true; error.value = '' }

async function save() {
  if (busy.value || !canSave.value || !session.user) return
  if (localError.value) { touched.value = true; error.value = localError.value; return }
  const submitting = ++revision
  busy.value = true; error.value = ''
  try {
    await savePassword(current.value, next.value)
    if (submitting !== revision) return
    reset()
    emit('saved')
  } catch (cause) {
    if (submitting === revision) {
      error.value = errorMessage(cause)
      // 当前密码错时清掉它，别让用户对着旧值反复重试
      if (/当前密码/.test(error.value)) current.value = ''
    }
  } finally { if (submitting === revision) busy.value = false }
}
</script>

<template>
  <wd-popup :model-value="open" position="bottom" :z-index="1250" :close-on-click-modal="!busy" root-portal safe-area-inset-bottom custom-style="border-radius:8px 8px 0 0" @update:model-value="!$event && emit('close')">
    <view class="sheet password-sheet" role="dialog" aria-modal="true" :aria-label="hasPassword ? '修改密码' : '设置密码'">
      <view class="sheet-handle" />
      <view class="sheet-head"><text class="sheet-title">{{ hasPassword ? '修改密码' : '设置密码' }}</text><button class="bare-icon" role="button" aria-label="关闭密码设置" :disabled="busy" @click="emit('close')"><wd-icon name="close" size="20px" /></button></view>
      <text class="password-intro">{{ hasPassword ? '修改后，其它设备上的登录会失效，这台设备保持登录状态。' : '设置密码后，这串昵称也能用来登录习题库。' }}</text>
      <text v-if="hasPassword" class="field-label">当前密码</text>
      <wd-input v-if="hasPassword" v-model="current" prefix-icon="lock" show-password custom-class="field-input" placeholder="请输入当前密码" aria-label="当前密码" :maxlength="128" :disabled="busy" @input="input" />
      <text class="field-label">新密码</text>
      <wd-input v-model="next" prefix-icon="lock" show-password custom-class="field-input" placeholder="至少 6 位" aria-label="新密码" :maxlength="128" :disabled="busy" @input="input" />
      <text class="field-label">确认新密码</text>
      <wd-input v-model="confirm" prefix-icon="lock" show-password custom-class="field-input" placeholder="再输入一次" aria-label="确认新密码" :maxlength="128" confirm-type="done" :disabled="busy" @input="input" @confirm="save" />
      <text v-if="touched && localError" class="field-hint error-text">{{ localError }}</text>
      <text v-else class="field-hint">{{ hasPassword ? '密码至少 6 位，建议字母与数字混合；修改后其它设备会退出登录。' : '密码至少 6 位，建议字母与数字混合；设置后可用昵称加密码登录。' }}</text>
      <view v-if="error" class="error-strip" role="alert">{{ error }}</view>
      <view class="sheet-actions"><wd-button role="button" block :loading="busy" :disabled="!canSave" @click="save">{{ hasPassword ? '保存新密码' : '设置密码' }}</wd-button></view>
    </view>
  </wd-popup>
</template>

<style scoped>
.password-sheet { max-height: 88vh; overflow-y: auto; }
.password-intro { display: block; margin-top: 2px; color: var(--lc-secondary); font-size: 12px; line-height: 1.8; }
.field-input :deep(.wd-input) { background: var(--lc-background); border-radius: 8px; --wot-input-padding: 14px; --wot-input-inner-height: 24px; --wot-input-bg: transparent; }
.field-hint { display: block; margin-top: 10px; color: var(--lc-muted); font-size: 11px; line-height: 1.7; }
.field-hint.error-text { color: #a34040; }
</style>
