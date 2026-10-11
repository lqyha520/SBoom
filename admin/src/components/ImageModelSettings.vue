<script setup lang="ts">
import { useAdminLeaveGuard } from "../navigation"
import { useAdminRefresh } from '../admin-page'
import { useBeforeUnload } from '../unsaved'
import { computed, onActivated, onDeactivated, ref } from 'vue'
import { fetchImageConfig, saveImageConfig, clearImageConfig, type ImageModelConfig } from '../image-api'

const empty = () => ({ baseUrl: '', model: '', apiKey: '', timeout: 300, size: '1024x1536', responseFormat: 'auto' as ImageModelConfig['responseFormat'] })
const config = ref(empty())
const hasKey = ref(false), loading = ref(true), busy = ref(false), clearOpen = ref(false)
const loadError = ref(''), error = ref(''), message = ref('')
const formats = [{ label: '自动（使用接口默认）', value: 'auto' }, { label: 'Base64 图片', value: 'b64_json' }, { label: '图片 URL', value: 'url' }]
const baseline = ref('')
const dirty = computed(() => !!baseline.value && baseline.value !== JSON.stringify(config.value))
const pageActive = ref(true)
onActivated(() => { pageActive.value = true })
onDeactivated(() => { pageActive.value = false })
useBeforeUnload(computed(() => pageActive.value && dirty.value))
useAdminLeaveGuard(() => !pageActive.value || (!busy.value && (!dirty.value || window.confirm('有未保存的生图配置，确认离开？'))))
let loadSequence = 0
async function load() {
  if (dirty.value) return
  const sequence = ++loadSequence
  loading.value = true; loadError.value = ''
  try { const value = await fetchImageConfig(); const { hasKey: saved, ...fields } = value; if (sequence !== loadSequence || dirty.value) return; config.value = { ...fields, apiKey: '' }; hasKey.value = saved; baseline.value = JSON.stringify(config.value) }
  catch (e) { if (sequence === loadSequence) loadError.value = e instanceof Error ? e.message : '生图配置加载失败' }
  finally { if (sequence === loadSequence) loading.value = false }
}
async function save() {
  if (busy.value || loading.value || loadError.value) return
  busy.value = true; error.value = ''; message.value = ''
  try {
    const result = await saveImageConfig({ ...config.value, baseUrl: config.value.baseUrl.trim(), model: config.value.model.trim(), apiKey: config.value.apiKey.trim() })
    hasKey.value = result.hasKey; config.value.apiKey = ''; baseline.value = JSON.stringify(config.value); message.value = '生图配置已保存，可在出题工作台「图片出题」中使用'
  } catch (e) { error.value = e instanceof Error ? e.message : '保存失败' }
  finally { busy.value = false }
}
async function clear() {
  if (busy.value || loading.value || loadError.value) return
  busy.value = true; error.value = ''; message.value = ''
  try { await clearImageConfig(); config.value = empty(); baseline.value = JSON.stringify(config.value); hasKey.value = false; clearOpen.value = false; message.value = '生图配置已清除' }
  catch (e) { error.value = e instanceof Error ? e.message : '清除失败' }
  finally { busy.value = false }
}
useAdminRefresh(load, () => { loadSequence++; loading.value = false })
</script>

<template>
  <section class="admin-section image-model-settings" aria-label="图片生成服务">
    <div class="section-toolbar"><h2>图片生成服务</h2><UBadge :color="hasKey ? 'success' : 'warning'" variant="subtle">{{ hasKey ? '密钥已保存' : '未配置密钥' }}</UBadge></div>
    <UAlert v-if="loadError" :title="loadError" color="error" :actions="[{ label: '重试', onClick: load }]" />
    <div v-if="loading" role="status"><USkeleton v-for="n in 4" :key="n" class="h-14 mb-3" /></div>
    <form v-else-if="!loadError" class="settings-form settings-section" @submit.prevent="save">
      <UFormField label="生图接口地址" description="支持 API 基础地址，或以 /images/generations 结尾的完整地址" required><UInput v-model="config.baseUrl" type="url" placeholder="https://你的接口域名/v1" :disabled="busy" required maxlength="500" /></UFormField>
      <div class="field-grid">
        <UFormField label="生图模型名称" required><UInput v-model="config.model" placeholder="填写接口支持的图片模型 ID" :disabled="busy" required maxlength="120" /></UFormField>
        <UFormField label="生图超时（秒）"><UInputNumber v-model="config.timeout" :min="30" :max="600" :step="30" :disabled="busy" /></UFormField>
      </div>
      <div class="field-grid">
        <UFormField label="图片尺寸" description="按模型支持的尺寸填写，如 1024x1536、1024x1792 或 auto"><UInput v-model="config.size" :disabled="busy" required maxlength="30" /></UFormField>
        <UFormField label="图片返回格式"><USelect v-model="config.responseFormat" :items="formats" :disabled="busy" /></UFormField>
      </div>
      <UFormField label="生图 API 密钥"><UInput v-model="config.apiKey" type="password" autocomplete="new-password" :placeholder="hasKey ? '留空保留已保存密钥' : '输入生图接口密钥'" :required="!hasKey" :disabled="busy" maxlength="4000" /></UFormField>
      <UAlert v-if="error && !clearOpen" :title="error" color="error" role="alert" />
      <UAlert v-if="message" :title="message" color="success" role="status" />
      <div class="actions-row"><UButton type="submit" label="保存生图配置" icon="i-lucide-save" :loading="busy" :disabled="busy" /><UButton type="button" label="清除生图配置" color="error" variant="outline" :disabled="busy || !hasKey" @click="clearOpen = true; error = ''" /></div>
    </form>
    <UModal v-model:open="clearOpen" title="清除生图配置" :dismissible="!busy" :close="!busy">
      <template #body><p>清除后将停用图片出题，需要重新配置接口和密钥才能使用。</p><UAlert v-if="error" :title="error" color="error" class="mt-3" /></template>
      <template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="busy" @click="clearOpen = false" /><UButton label="确认清除" color="error" :loading="busy" :disabled="busy" @click="clear" /></template>
    </UModal>
  </section>
</template>

<style scoped>
.image-model-settings { margin-top:0;max-width:800px; }
</style>
