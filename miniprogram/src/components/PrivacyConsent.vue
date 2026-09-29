<script setup lang="ts">
import { privacyState, openPrivacy, resolvePrivacy } from '../services/privacy'
import { ref } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
const visible = ref(true)
onShow(() => { visible.value = true })
onHide(() => { visible.value = false })
</script>
<template>
  <view v-if="visible && privacyState.open" class="privacy-mask" role="dialog" aria-label="隐私授权">
    <view class="privacy-dialog">
      <text>使用头像、昵称或剪贴板前，请阅读并同意微信隐私保护指引。</text>
      <button @click="openPrivacy">{{ privacyState.name }}</button>
      <button id="privacy-agree" open-type="agreePrivacyAuthorization" @agreeprivacyauthorization="resolvePrivacy(true)">同意并继续</button>
      <button @click="resolvePrivacy(false)">暂不同意</button>
    </view>
  </view>
</template>
<style scoped>
.privacy-mask{position:fixed;inset:0;z-index:10000;display:flex;align-items:center;justify-content:center;background:#0008}
.privacy-dialog{width:80%;max-width:360px;padding:24px;background:#fff;border-radius:16px;color:#263c32;line-height:1.7}
.privacy-dialog button{margin-top:12px;font-size:14px}
</style>
