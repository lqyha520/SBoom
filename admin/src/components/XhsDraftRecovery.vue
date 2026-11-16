<script setup lang="ts">
import { permissionDirective as vPermission } from '../permissions'
import { adminRoute } from '../navigation'
import type { DraftBackupController } from '../xhs-draft-backup'
defineProps<{ backup: DraftBackupController }>()
</script>
<template>
  <div class="draft-recovery">
    <UAlert v-if="backup.storageError.value" :title="backup.storageError.value" color="warning" />
    <div v-if="backup.recovery.value" class="workflow-step" role="status">
      <p><strong>发现本机未保存草稿</strong> · {{ new Date(backup.recovery.value.updatedAt).toLocaleString('zh-CN') }}</p>
      <p v-if="backup.stale.value">后台版本已变化，不能直接覆盖。请下载备份，与最新内容核对后手动合并。</p>
      <p v-else>恢复后仍需点击保存；备份只保存在当前浏览器和管理员账号下。</p>
      <div class="workflow-actions"><UButton label="恢复本机草稿" :disabled="backup.stale.value" @click="backup.restore" /><UButton v-permission="adminRoute.tab + ':export'" label="下载草稿备份" variant="outline" @click="backup.download" /><UButton label="丢弃本机备份" variant="ghost" @click="backup.discard" /></div>
    </div>
    <p v-else-if="backup.savedAt.value" class="workflow-hint" role="status">编辑已备份到本机 · {{ new Date(backup.savedAt.value).toLocaleTimeString('zh-CN') }}。点击保存后才会写入后台。</p>
  </div>
</template>
<style scoped>.draft-recovery{display:grid;gap:10px;margin-bottom:14px}.draft-recovery p{font-size:13px;line-height:1.8;margin-bottom:10px}</style>
