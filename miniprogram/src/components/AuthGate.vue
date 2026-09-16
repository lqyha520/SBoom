<script setup lang="ts">
import { requireLogin, session } from '../services/session'
function login() { requireLogin() }
</script>

<template>
  <view class="state-block">
    <wd-loading v-if="!session.ready" color="#307e61" />
    <wd-empty v-else icon="lock" :icon-size="64" tip="登录习题库"><template #bottom><view class="empty-actions"><wd-button icon="user" role="button" @click="login">去登录</wd-button></view></template></wd-empty>
  </view>
</template>
