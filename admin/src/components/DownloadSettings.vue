<script setup lang="ts">
import { downloadSettingsIssue, type DownloadSettings } from '../download-settings'
defineProps<{ fields: DownloadSettings; disabled?: boolean; linkOnly?: boolean; labelPrefix?: string }>()
</script>
<template>
  <div class="delivery-fields">
    <UFormField label="下载方式" :description="linkOnly ? '用户获取链接后前往网盘下载。' : '选择小程序中的获取方式。'">
      <USelect v-model="fields.download_mode" :items="linkOnly ? [{ label: '网盘链接', value: 'external' }] : [{ label: 'PDF 文件', value: 'pdf' }, { label: '网盘链接', value: 'external' }]" :aria-label="(labelPrefix || '') + '下载方式'" :disabled="disabled || linkOnly" class="w-full" />
    </UFormField>
    <template v-if="fields.download_mode === 'external'">
      <UFormField label="网盘链接" required><UInput v-model="fields.external_url" type="url" maxlength="2000" placeholder="https://pan.example.com/s/…" :aria-label="(labelPrefix || '') + '网盘链接'" :disabled="disabled" class="w-full" /></UFormField>
      <UFormField label="提取码（可选）"><UInput v-model="fields.external_code" maxlength="100" placeholder="没有提取码可留空" :aria-label="(labelPrefix || '') + '提取码'" :disabled="disabled" class="w-full" /></UFormField>
      <p class="text-xs text-muted">小程序显示“获取网盘链接”，通过下载权限校验后可复制链接与提取码。</p>
      <p v-if="downloadSettingsIssue(fields)" role="alert" class="text-sm text-error">{{ downloadSettingsIssue(fields) }}</p>
    </template>
  </div>
</template>
<style scoped>.delivery-fields{display:grid;gap:12px}</style>
