<script setup lang="ts">
import { showPrivacyError } from '../services/privacy'
import { computed, ref, watch } from 'vue'
import { errorMessage } from '../services/api'
import { saveAvatar, saveProfile, session } from '../services/session'
import { useTabBarOverlay } from '../services/tabbar-overlay'
import { prepareProfilePhoto, type ProfilePhoto } from '../services/profile-photo'
import { DEFAULT_AVATAR_CHOICES } from '../presentation'
import { nicknameError as validateNickname } from '../../../shared/mini-profile'
import ProfileAvatar from './ProfileAvatar.vue'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const nickname = ref('')
const avatar = ref('')
const photo = ref<ProfilePhoto | null>(null)
const busy = ref(false)
const processing = ref(false)
const error = ref('')
let revision = 0
useTabBarOverlay(() => props.open)

// 微信端用 nickname 输入类型，键盘上方会出现「使用微信昵称」的快捷入口；
// 其余平台用普通文本输入（同一个变量赋值，避免条件编译在两端各声明一次而无法通过类型检查）
let nicknameType: 'text' | 'nickname' = 'text'
// #ifdef MP-WEIXIN
nicknameType = 'nickname'
// #endif

const previewUser = computed(() => session.user ? {
  ...session.user, nickname: nickname.value, avatar: avatar.value,
  avatar_url: avatar.value === session.user.avatar ? session.user.avatar_url : null,
} : null)
const nicknameError = computed(() => validateNickname(nickname.value))
const dirty = computed(() => !!session.user &&
  (nickname.value.trim() !== (session.user.nickname || session.user.username) || avatar.value !== (session.user.avatar || '') || !!photo.value))
const canSave = computed(() => !busy.value && dirty.value && !nicknameError.value)

watch(() => props.open, value => {
  revision++
  error.value = ''
  busy.value = false
  processing.value = false
  photo.value = null
  if (value) {
    nickname.value = session.user?.nickname || session.user?.username || ''
    avatar.value = session.user?.avatar || ''
  }
})

function editNickname(event: Event | { detail: { value: string } }) {
  const value = 'detail' in event && typeof event.detail === 'object'
    ? event.detail.value : (('target' in event ? event.target : null) as HTMLInputElement | null)?.value
  if (typeof value === 'string') { nickname.value = value; error.value = '' }
}
function choosePreset(key: string) {
  if (busy.value) return
  avatar.value = key; photo.value = null; error.value = ''
}
async function selectPhoto(path: string) {
  if (!props.open || busy.value || !path) return
  const current = ++revision
  busy.value = true; processing.value = true; error.value = ''
  try {
    const selected = await prepareProfilePhoto(path)
    if (current === revision) photo.value = selected
  } catch (cause) { if (current === revision) error.value = errorMessage(cause) }
  finally { if (current === revision) { busy.value = false; processing.value = false } }
}
function chooseWechatAvatar(event: { detail: { avatarUrl?: string } }) {
  if (event.detail.avatarUrl) void selectPhoto(event.detail.avatarUrl)
  else error.value = '未能获取头像，请重新选择'
}
function choosePhoto() {
  if (busy.value) return
  uni.chooseImage({
    count: 1, sizeType: ['compressed'], sourceType: ['album'],
    success: result => { if (result.tempFilePaths[0]) void selectPhoto(result.tempFilePaths[0]) },
    fail: cause => { if (!cause.errMsg?.includes('cancel')) error.value = '图片选择失败，请重试' },
  })
}

async function save() {
  if (busy.value || !canSave.value || !session.user) return
  if (nicknameError.value) { error.value = nicknameError.value; return }
  const current = ++revision
  busy.value = true; error.value = ''
  try {
    const name = nickname.value.trim()
    // 只提交真正改过的字段，免得白写一次库、白涨一次 revision
    const payload: { nickname?: string; avatar?: string } = {}
    if (name !== (session.user.nickname || session.user.username)) payload.nickname = name
    if (photo.value) await saveAvatar({ image: photo.value.image, ...(payload.nickname !== undefined ? { nickname: payload.nickname } : {}) })
    else {
      if (avatar.value !== (session.user.avatar || '')) payload.avatar = avatar.value
      await saveProfile(payload)
    }
    if (current !== revision) return
    emit('saved')
  } catch (cause) { if (current === revision) error.value = errorMessage(cause) }
  finally { if (current === revision) busy.value = false }
}
</script>

<template>
  <wd-popup :model-value="open" position="bottom" :z-index="1250" :close-on-click-modal="!busy" root-portal safe-area-inset-bottom custom-style="border-radius:22px 22px 0 0" @update:model-value="!$event && emit('close')">
    <view class="sheet profile-sheet" role="dialog" aria-modal="true" aria-label="编辑资料">
      <view class="sheet-handle" />
      <view class="sheet-head"><view><text class="sheet-title">编辑资料</text><text class="profile-intro">换个喜欢的头像，认识一下新的自己</text></view><button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="bare-icon" role="button" aria-label="关闭编辑资料" :disabled="busy" @click="emit('close')"><wd-icon name="close" size="20px" /></button></view>
      <view class="profile-preview">
        <view class="preview-avatar"><ProfileAvatar :user="previewUser" :preview-src="photo?.path" /></view>
        <text class="preview-name">{{ processing ? '正在处理图片…' : nickname.trim() || '我的昵称' }}</text>
      </view>
      <view class="avatar-actions">
        <!-- #ifdef MP-WEIXIN -->
        <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="choose-avatar" role="button" aria-label="使用微信头像" open-type="chooseAvatar" :disabled="busy" @chooseavatar="chooseWechatAvatar" @error="showPrivacyError"><wd-icon name="camera" size="18px" /><text>使用微信头像</text></button>
        <!-- #endif -->
        <!-- #ifdef H5 -->
        <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" class="choose-avatar" role="button" aria-label="选择头像图片" :disabled="busy" @click="choosePhoto"><wd-icon name="camera" size="18px" /><text>选择头像图片</text></button>
        <!-- #endif -->
      </view>
      <view class="avatar-label"><text class="field-label">默认头像</text><text>选一个你喜欢的</text></view>
      <view class="preset-grid" role="radiogroup" aria-label="选择默认头像">
        <button hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" v-for="choice in DEFAULT_AVATAR_CHOICES" :key="choice.key" class="preset-option" :class="{ selected: !photo && avatar === choice.key }" role="radio" :aria-label="choice.label" :aria-checked="!photo && avatar === choice.key" :disabled="busy" @click="choosePreset(choice.key)">
          <view class="preset-picture" :style="{ background: choice.background }"><image :src="choice.image" mode="aspectFill" /><view v-if="!photo && avatar === choice.key" class="preset-check"><wd-icon name="check" size="11px" /></view></view>
          <text>{{ choice.label }}</text>
        </button>
      </view>
      <view class="nickname-label"><text class="field-label">昵称</text><text>{{ Array.from(nickname.trim()).length }}/32</text></view>
      <view class="nickname-field"><wd-icon name="user" size="18px" /><input :value="nickname" :type="nicknameType" :maxlength="64" placeholder="请输入昵称" aria-label="昵称" :disabled="busy" @input="editNickname" @blur="editNickname" /></view>
      <text v-if="nickname && nicknameError" class="field-hint error-text">{{ nicknameError }}</text>
      <text v-else class="field-hint">支持中文和表情，简短一点更好记。</text>
      <!-- #ifdef MP-WEIXIN -->
      <text class="field-hint">点击输入框可使用微信昵称，头像和昵称会在保存后更新。</text>
      <!-- #endif -->
      <!-- #ifdef H5 -->
      <text class="field-hint">支持 JPG、PNG、WebP，图片会自动压缩。</text>
      <!-- #endif -->
      <view v-if="error" class="error-strip" role="alert">{{ error }}</view>
      <view class="sheet-actions"><wd-button role="button" block :loading="busy" :disabled="!canSave" @click="save">{{ processing ? '正在处理图片' : '保存资料' }}</wd-button></view>
    </view>
  </wd-popup>
</template>

<style scoped>
.profile-sheet { max-height:90vh;overflow-y:auto; }
.profile-intro { display:block;margin-top:4px;color:var(--lc-muted);font-size:12px; }
.profile-preview { display:flex;flex-direction:column;align-items:center;gap:8px;padding:4px 0; }
.preview-avatar { width:78px;height:78px;overflow:hidden;border:3px solid #fff;border-radius:50%;box-shadow:0 0 0 1px var(--lc-card-line),0 8px 18px #23392d14;font-size:32px; }
.preview-name { font-size:15px;font-weight:600;color:var(--lc-text);overflow-wrap:anywhere; }
.avatar-actions { display:flex;align-items:center;justify-content:center;margin:10px 0 20px; }
.choose-avatar { display:flex;align-items:center;justify-content:center;gap:8px;min-height:42px;padding:8px 18px;margin:0;border-radius:999px;color:var(--lc-primary);background:var(--lc-primary-soft);font-size:13px;line-height:1.5; }
.choose-avatar::after { border:0; }
.avatar-label,.nickname-label { display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px; }
.avatar-label .field-label,.nickname-label .field-label { margin:0; }
.avatar-label > text:last-child,.nickname-label > text:last-child { color:var(--lc-muted);font-size: 12px; }
.preset-grid { display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin-bottom:24px; }
.preset-option { display:flex;flex-direction:column;align-items:center;gap:7px;margin:0;padding:5px 0;background:transparent;color:var(--lc-secondary);font-size: 12px;line-height:1.4; }
.preset-picture { position:relative;width:48px;height:48px;border:2px solid transparent;border-radius:50%; }
.preset-picture image { width:100%;height:100%;border-radius:50%; }
.preset-option.selected { color:var(--lc-primary);font-weight:600; }.preset-option.selected .preset-picture { border-color:var(--lc-primary);box-shadow:0 0 0 3px var(--lc-primary-soft); }
.preset-check { position:absolute;right:-3px;bottom:-2px;display:flex;align-items:center;justify-content:center;width:17px;height:17px;border:2px solid #fff;border-radius:50%;color:#fff;background:var(--lc-primary); }
.nickname-field { display:flex;align-items:center;gap:10px;padding:12px 14px;border:1px solid var(--lc-card-line);border-radius:12px;color:var(--lc-muted);background:var(--lc-background); }
.nickname-field:focus-within { border-color:var(--lc-primary); }
.nickname-field input { flex:1;min-width:0;height:26px;font-size:15px;color:var(--lc-text); }
.field-hint { display:block;margin-top:8px;color:var(--lc-muted);font-size: 12px;line-height:1.7; }
.field-hint.error-text { color:#a34040; }
</style>
