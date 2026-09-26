<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { zh_cn } from '@nuxt/ui/locale'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const LoginView = defineAsyncComponent(() => import('./components/LoginView.vue'))
const Workspace = defineAsyncComponent(() => import('./Workspace.vue'))
</script>

<template>
  <UApp :locale="zh_cn" :toaster="{ position: 'top-right' }">
    <div v-if="!auth.ready" class="loading-screen" role="status">
      <UIcon name="i-lucide-loader-circle" class="size-6 animate-spin text-primary" />
      <p>正在加载工作台</p>
    </div>
    <div v-else-if="auth.bootError" class="loading-screen p-6">
      <UAlert title="暂时无法连接工作台" :description="auth.bootError" color="error" role="alert" class="max-w-md" />
      <UButton label="重新连接" icon="i-lucide-refresh-cw" @click="auth.init()" />
    </div>
    <Suspense v-else>
      <Workspace v-if="auth.user" :key="auth.user.id" />
      <LoginView v-else />
      <template #fallback>
        <div class="loading-screen" role="status">
          <UIcon name="i-lucide-loader-circle" class="size-6 animate-spin text-primary" />
          <p>正在加载工作台</p>
        </div>
      </template>
    </Suspense>
  </UApp>
</template>
