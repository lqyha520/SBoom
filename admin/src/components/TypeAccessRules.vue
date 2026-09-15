<script setup lang="ts">
import { computed, onActivated, onDeactivated, ref, watch } from 'vue'
import type { UserInfo } from '../api'
import { typeRules, updateTypeRule, type TypeRule } from '../mini'

const props = defineProps<{ user: UserInfo }>()
const items = ref<TypeRule[]>([])
const q = ref('')
const error = ref('')
const notice = ref('')
const loading = ref(false)
const busy = ref(false)
const dialog = ref(false)
const edit = ref<TypeRule | null>(null)
const formError = ref('')
let sequence = 0
const options = [{ label: '普通用户与 VIP', value: 'free' }, { label: '仅 VIP 会员', value: 'vip' }]
const filtered = computed(() => items.value.filter(item => (item.label + item.question_type).toLowerCase().includes(q.value.trim().toLowerCase())))
const message = (cause: unknown) => cause instanceof Error ? cause.message : '操作失败，请重试'
watch(() => edit.value?.view_access, value => { if (value === 'vip' && edit.value) edit.value.download_access = 'vip' })
async function load() {
  const current = ++sequence
  loading.value = true; error.value = ''
  try { const result = await typeRules(); if (current === sequence) items.value = result.items }
  catch (cause) { if (current === sequence) error.value = message(cause) }
  finally { if (current === sequence) loading.value = false }
}
function open(item: TypeRule) { edit.value = { ...item }; formError.value = ''; dialog.value = true }
async function save() {
  if (!edit.value || busy.value) return
  busy.value = true; formError.value = ''
  try { await updateTypeRule(props.user.id, edit.value); dialog.value = false; notice.value = '题型权限已更新'; await load() }
  catch (cause) { formError.value = message(cause) }
  finally { busy.value = false }
}
onActivated(load)
onDeactivated(() => { sequence++; loading.value = false; dialog.value = false })
</script>

<template>
  <section class="admin-section" aria-label="题型权限">
    <div class="section-toolbar"><UInput v-model="q" icon="i-lucide-search" placeholder="搜索题型" aria-label="搜索题型" /><UTooltip text="刷新"><UButton icon="i-lucide-refresh-cw" color="neutral" variant="ghost" aria-label="刷新题型权限" :loading="loading" @click="load" /></UTooltip></div>
    <UAlert v-if="error" :title="error" color="error" variant="soft" class="notice" />
    <UAlert v-if="notice" :title="notice" color="success" variant="soft" close class="notice" @update:open="notice = ''" />
    <div class="data-scroll" :aria-busy="loading"><table class="data-table rules-table"><thead><tr><th>题型</th><th>关联习题</th><th>完整原稿观看</th><th>PDF 下载</th><th><span class="sr-only">操作</span></th></tr></thead><tbody><tr v-for="item in filtered" :key="item.question_type"><td><strong>{{ item.label }}</strong><div class="type-code">{{ item.question_type }}</div></td><td>{{ item.paper_count }} 份</td><td><UBadge :color="item.view_access === 'vip' ? 'warning' : 'neutral'" variant="soft">{{ item.view_access === 'vip' ? '仅 VIP' : '所有登录用户' }}</UBadge></td><td><UBadge :color="item.download_access === 'vip' ? 'warning' : 'neutral'" variant="soft">{{ item.download_access === 'vip' ? '仅 VIP' : '所有登录用户' }}</UBadge></td><td><UTooltip text="配置权限"><UButton icon="i-lucide-shield-check" color="neutral" variant="ghost" :aria-label="'配置权限 ' + item.label" @click="open(item)" /></UTooltip></td></tr><tr v-if="!filtered.length"><td colspan="5"><div class="empty-state"><UIcon :name="loading ? 'i-lucide-loader-circle' : 'i-lucide-list-filter'" class="size-7" :class="{ 'animate-spin': loading }" /><h3>{{ loading ? '正在加载' : '没有匹配的题型' }}</h3></div></td></tr></tbody></table></div>
    <div class="table-footer"><span>共 {{ filtered.length }} 种题型</span></div>
    <UModal v-model:open="dialog" :title="'题型权限 · ' + (edit?.label || '')" :dismissible="!busy" :close="!busy"><template #body><form v-if="edit" id="type-access-form" class="field-stack" @submit.prevent="save"><UFormField label="完整原稿观看"><USelect v-model="edit.view_access" :items="options" :disabled="busy" class="w-full" /></UFormField><UFormField label="PDF 下载"><USelect v-model="edit.download_access" :items="options" :disabled="busy || edit.view_access === 'vip'" class="w-full" /></UFormField><UAlert color="warning" variant="soft" :title="'保存后将影响含该题型且使用继承权限的习题。当前关联 ' + edit.paper_count + ' 份。'" /><UAlert v-if="formError" :title="formError" color="error" variant="soft" /></form></template><template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="busy" @click="dialog = false" /><UButton type="submit" form="type-access-form" label="保存权限" icon="i-lucide-check" :loading="busy" /></template></UModal>
  </section>
</template>

<style scoped>
.rules-table { min-width: 650px; }
.type-code { color: var(--ui-text-muted); font-size: 11px; margin-top: 5px; }
</style>
