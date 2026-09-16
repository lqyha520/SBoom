<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { UserInfo } from '../api'
import { useAdminPage } from '../admin-page'
import { getTags, saveTag, removeTag, tagKinds, type CatalogTag, type TagKind } from '../growth'
const props = defineProps<{ user: UserInfo }>()
const items = ref<CatalogTag[]>([]), kind = ref('all'), q = ref(''), pageNumber = ref(1), dialog = ref(false), deleting = ref(false), target = ref<CatalogTag | null>(null)
const form = ref({ kind: 'textbook' as TagKind, name: '', is_visible: true, sort_order: 0, revision: 0 })
const filtered = computed(() => items.value.filter(item => (kind.value === 'all' || item.kind === kind.value) && item.name.toLowerCase().includes(q.value.trim().toLowerCase())))
const visible = computed(() => filtered.value.slice((pageNumber.value - 1) * 20, pageNumber.value * 20))
const page = useAdminPage(async valid => { const result = await getTags(); if (valid()) items.value = result.items }, () => { dialog.value = false; deleting.value = false })
const { error, notice, loading, busy } = page
watch([kind, q], () => { pageNumber.value = 1 })
function edit(item: CatalogTag | null = null) { error.value = ''; target.value = item; form.value = { kind: item?.kind || (kind.value === 'all' ? 'textbook' : kind.value as TagKind), name: item?.name || '', is_visible: item?.is_visible ?? true, sort_order: item?.sort_order || 0, revision: item?.revision || 0 }; dialog.value = true }
function save() { void page.act(async valid => { await saveTag(props.user.id, { ...form.value, name: form.value.name.trim(), sort_order: Number(form.value.sort_order) }, target.value?.id); if (valid()) { dialog.value = false; notice.value = '标签已保存'; await page.load() } }) }
function remove() { if (!target.value) return; void page.act(async valid => { await removeTag(props.user.id, target.value!); if (valid()) { deleting.value = false; notice.value = '标签已删除'; await page.load() } }) }
</script>
<template>
  <section class="admin-section"><div class="section-toolbar"><p class="text-sm text-muted">管理教材、学期、单元与知识点。在公共习题的「标签与打印」中关联资料。</p><UButton label="新增标签" icon="i-lucide-plus" @click="edit()" /></div>
    <UAlert v-if="error" :title="error" color="error" class="notice" /><UAlert v-if="notice" :title="notice" color="success" class="notice" />
    <div class="section-toolbar"><div class="actions-row"><USelect v-model="kind" :items="[{ value: 'all', label: '全部类型' }, ...tagKinds]" aria-label="标签类型" /><UInput v-model="q" placeholder="搜索标签" aria-label="搜索标签" /></div><UButton label="刷新" variant="outline" :loading="loading" @click="page.load" /></div>
    <div class="data-scroll"><table class="data-table"><thead><tr><th>标签</th><th>类型</th><th>已发布资料数</th><th>顺序</th><th>小程序展示</th><th>操作</th></tr></thead><tbody><tr v-for="item in visible" :key="item.id"><td class="name-cell">{{ item.name }}</td><td>{{ tagKinds.find(kind => kind.value === item.kind)?.label }}</td><td>{{ item.paper_count }}</td><td>{{ item.sort_order }}</td><td>{{ item.is_visible ? '显示' : '隐藏' }}</td><td><div class="actions-row"><UButton label="编辑标签" variant="soft" @click="edit(item)" /><UButton label="删除" color="error" variant="ghost" @click="target = item; deleting = true; error = ''" /></div></td></tr><tr v-if="!visible.length"><td colspan="6">{{ loading ? '正在加载' : '暂无匹配标签' }}</td></tr></tbody></table></div><div class="table-footer"><span>共 {{ filtered.length }} 个标签</span><UPagination v-if="filtered.length > 20" v-model:page="pageNumber" :total="filtered.length" :items-per-page="20" /></div>
    <UModal v-model:open="dialog" :title="target ? '编辑标签' : '新增标签'" :dismissible="!busy" :close="!busy"><template #body><form id="tag-editor" class="field-stack" @submit.prevent="save"><UFormField label="类型"><USelect v-model="form.kind" :items="tagKinds" :disabled="!!target || busy" class="w-full" /></UFormField><UFormField label="标签名称" required><UInput v-model="form.name" :disabled="busy" maxlength="80" required class="w-full" /></UFormField><UFormField label="顺序（越小越靠前）"><UInput v-model="form.sort_order" :disabled="busy" type="number" min="0" max="10000" required /></UFormField><USwitch v-model="form.is_visible" :disabled="busy" label="在小程序显示" /><p class="text-sm text-muted">隐藏后不会显示在小程序筛选项和资料标签中，原有资料关联会保留。</p><UAlert v-if="error" :title="error" color="error" /></form></template><template #footer><UButton label="取消" variant="outline" color="neutral" :disabled="busy" @click="dialog = false" /><UButton form="tag-editor" type="submit" label="保存标签" :loading="busy" :disabled="busy || !form.name.trim()" /></template></UModal>
    <UModal v-model:open="deleting" title="删除标签" :dismissible="!busy" :close="!busy"><template #body><p>确认删除「{{ target?.name }}」？已关联资料的标签需先解除关联，或改为隐藏。</p><UAlert v-if="error" :title="error" color="error" class="mt-4" /></template><template #footer><UButton label="取消" color="neutral" :disabled="busy" @click="deleting = false" /><UButton label="确认删除" color="error" :loading="busy" @click="remove" /></template></UModal>
  </section>
</template>
