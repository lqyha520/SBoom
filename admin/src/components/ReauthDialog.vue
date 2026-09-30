<script setup lang="ts">
import type { UserInfo } from '../api'
import LoginForm from './LoginForm.vue'
defineProps<{ user: UserInfo }>()
const emit = defineEmits<{ logined: [user: UserInfo] }>()
</script>
<template>
  <UModal :open="true" :dismissible="false" :close="false" title="重新验证管理员身份" description="当前编辑内容已保留。使用同一账号登录后，可继续保存。" :ui="{ overlay: 'z-[10000]', content: 'z-[10001] max-w-xl' }">
    <template #body><LoginForm :expected-user="user" @logined="emit('logined', $event)" /></template>
  </UModal>
</template>
