<script setup lang="ts">
import { onMounted, ref } from 'vue'
import * as api from '../api'

const config = ref({ baseUrl: '', model: '', apiKey: '', timeout: 60 })
const hasKey = ref(false)
const loading = ref(true)
const loadError = ref('')
const busy = ref<'save' | 'test' | 'clear' | ''>('')
const message = ref('')
const ok = ref(true)
const clearOpen = ref(false)
async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const value = await api.fetchLlmConfig()
    config.value = { baseUrl: value.baseUrl, model: value.model, apiKey: '', timeout: value.timeout || 60 }
    hasKey.value = value.hasKey
  } catch (e: unknown) { loadError.value = e instanceof Error ? e.message : '配置加载失败' }
  finally { loading.value = false }
}
async function execute(action: 'save' | 'test' | 'clear') {
  if (busy.value || loading.value || loadError.value) return
  busy.value = action
  message.value = ''
  try {
    const value = { ...config.value, baseUrl: config.value.baseUrl.trim(), model: config.value.model.trim(), apiKey: config.value.apiKey.trim(), timeout: Number(config.value.timeout) || 60 }
    if (action === 'save') {
      const result = await api.saveLlmConfig(value)
      hasKey.value = result.hasKey
      config.value.apiKey = ''
      message.value = result.message || '模型配置已保存'
    } else if (action === 'test') {
      const result = await api.testLlm(value)
      message.value = '连接成功：' + result.reply
    } else {
      await api.clearLlmConfig()
      config.value = { baseUrl: '', model: '', apiKey: '', timeout: 60 }
      hasKey.value = false
      clearOpen.value = false
      message.value = '模型配置与已保存密钥已清除'
    }
    ok.value = true
  } catch (e: unknown) {
    ok.value = false
    message.value = e instanceof Error ? e.message : '操作失败，请重试'
  } finally { busy.value = '' }
}
onMounted(load)
</script>

<template>
  <section class="admin-section" aria-label="全局模型配置">
    <div class="section-toolbar"><h2>全局模型服务</h2><UBadge :color="hasKey ? 'success' : 'warning'" variant="subtle" :icon="hasKey ? 'i-lucide-key-round' : 'i-lucide-circle-alert'">{{ hasKey ? '密钥已保存' : '未配置密钥' }}</UBadge></div>
    <UAlert v-if="loadError" :title="loadError" color="error" variant="soft" :actions="[{ label: '重试', onClick: load }]" class="notice" />
    <div v-if="loading" class="field-stack max-w-xl" role="status" aria-label="正在加载模型配置"><USkeleton v-for="n in 4" :key="n" class="h-14" /></div>
    <template v-else-if="!loadError">
      <form class="settings-form settings-section" @submit.prevent="execute('save')">
        <UFormField label="接口地址" required><UInput v-model="config.baseUrl" type="url" placeholder="https://api.openai.com/v1" :disabled="!!busy" required icon="i-lucide-globe" /></UFormField>
        <div class="field-grid">
          <UFormField label="模型名称" required><UInput v-model="config.model" placeholder="模型 ID" :disabled="!!busy" required /></UFormField>
          <UFormField label="超时时间（秒）"><UInputNumber :model-value="config.timeout" :min="10" :max="600" :step="10" :disabled="!!busy" @update:model-value="config.timeout = $event ?? 60" /></UFormField>
        </div>
        <UFormField label="API 密钥"><UInput v-model="config.apiKey" type="password" autocomplete="new-password" :placeholder="hasKey ? '留空保留已保存的密钥' : 'sk-...'" :disabled="!!busy" icon="i-lucide-key-round" /></UFormField>
        <UAlert v-if="message && !clearOpen" :color="ok ? 'success' : 'error'" variant="soft" :title="message" role="status" />
        <div class="actions-row"><UButton type="submit" icon="i-lucide-save" label="保存配置" :loading="busy === 'save'" :disabled="!!busy" /><UButton icon="i-lucide-plug" label="测试连接" color="neutral" variant="outline" :loading="busy === 'test'" :disabled="!!busy" @click="execute('test')" /></div>
      </form>
      <div class="danger-zone"><UButton icon="i-lucide-trash-2" color="error" variant="outline" label="清除全局配置" :disabled="!!busy || (!hasKey && !config.baseUrl && !config.model)" @click="clearOpen = true; message = ''" /></div>
    </template>
    <UModal v-model:open="clearOpen" title="清除全局模型配置" :dismissible="!busy" :close="!busy">
      <template #body><div class="field-stack"><UAlert color="warning" variant="soft" title="已保存密钥将被删除，所有用户将无法生成题目，直到重新配置模型服务。" icon="i-lucide-triangle-alert" /><UAlert v-if="message && !ok" :title="message" color="error" variant="soft" /></div></template>
      <template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="!!busy" @click="clearOpen = false" /><UButton label="确认清除" color="error" :loading="busy === 'clear'" :disabled="!!busy" @click="execute('clear')" /></template>
    </UModal>
  </section>
</template>
