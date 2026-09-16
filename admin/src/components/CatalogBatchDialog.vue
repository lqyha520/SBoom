<script setup lang="ts">
import { ref, watch } from 'vue'
import type { CatalogPaper } from '../catalog'
import { batchCatalog } from '../experience'
const props = defineProps<{ open: boolean; adminId: number; items: CatalogPaper[]; categories: { value: string; label: string }[] }>()
const emit = defineEmits<{ close: []; saved: [count: number] }>()
const action = ref('category')
const category = ref('')
const viewAccess = ref('inherit')
const downloadAccess = ref('inherit')
const confirmed = ref(false)
const busy = ref(false)
const error = ref('')
const policies = [{ label: '继承题型权限', value: 'inherit' }, { label: '普通用户与 VIP', value: 'free' }, { label: '仅 VIP', value: 'vip' }]
watch(() => props.open, () => { action.value = 'category'; category.value = ''; viewAccess.value = 'inherit'; downloadAccess.value = 'inherit'; confirmed.value = false; error.value = '' })
watch(action, () => { confirmed.value = false })
watch(viewAccess, value => { if (value === 'vip') downloadAccess.value = 'vip' })
async function save() {
  if (busy.value || !props.items.length) return
  busy.value = true; error.value = ''
  try { const result = await batchCatalog(props.adminId, props.items, { action: action.value, category_id: category.value, view_access: viewAccess.value, download_access: downloadAccess.value, confirm_publication: confirmed.value }); emit('saved', result.updated); emit('close') }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '批量操作失败' }
  finally { busy.value = false }
}
</script>
<template><UModal :open="open" title="批量管理资料" :dismissible="!busy" :close="!busy" @update:open="!$event && emit('close')"><template #body><form id="batch-catalog" class="field-stack" @submit.prevent="save"><p>已选择 {{ items.length }} 份资料</p><USelect v-model="action" aria-label="批量操作类型" :items="[{ label: '修改分类', value: 'category' }, { label: '发布', value: 'published' }, { label: '下架', value: 'withdrawn' }, { label: '修改访问权限', value: 'access' }]" /><UFormField v-if="action === 'category'" label="目标分类"><USelect v-model="category" :items="categories" :disabled="!categories.length" placeholder="选择分类" /><p v-if="!categories.length" class="text-sm text-muted mt-2">暂无可用分类，请先到「分类管理」创建并展示一个分类。</p></UFormField><template v-if="action === 'access'"><UFormField label="原稿观看"><USelect v-model="viewAccess" :items="policies" /></UFormField><UFormField label="PDF 下载"><USelect v-model="downloadAccess" :items="policies" :disabled="viewAccess === 'vip'" /></UFormField></template><UCheckbox v-if="action === 'published'" v-model="confirmed" label="已核对所选资料原稿与普通用户/VIP 权限，确认发布" /><p class="text-sm text-muted">若有资料被其他管理员修改，本批操作会整体取消；发布操作还会检查文件是否就绪。</p><UAlert v-if="error" :title="error" color="error" /></form></template><template #footer><UButton label="取消" color="neutral" :disabled="busy" @click="emit('close')" /><UButton label="应用到所选资料" type="submit" form="batch-catalog" :loading="busy" :disabled="!items.length || (action === 'published' && !confirmed) || (action === 'category' && !category)" /></template></UModal></template>
