<script setup lang="ts">
import { computed, onActivated, onDeactivated, ref } from 'vue'
import type { UserInfo } from '../api'
import { catalogList, type CatalogPaper } from '../catalog'
import { getTopics, saveTopic, removeTopic, type Topic } from '../experience'
const props = defineProps<{ user: UserInfo }>()
const topics = ref<Topic[]>([])
const target = ref<Topic | null>(null)
const dialog = ref(false)
const deleting = ref<Topic | null>(null)
const deleteOpen = ref(false)
const title = ref('')
const description = ref('')
const visible = ref(false)
const order = ref(0)
const selected = ref<{ id: string; title: string }[]>([])
const choices = ref<CatalogPaper[]>([])
const q = ref('')
const more = ref(false)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const formError = ref('')
const notice = ref('')
let sequence = 0
let searchSequence = 0
const selectedIds = computed(() => new Set(selected.value.map(item => item.id)))
const message = (cause: unknown) => cause instanceof Error ? cause.message : '操作失败'
async function load() {
  const current = ++sequence
  try { const result = await getTopics(); if (current === sequence) topics.value = result.items }
  catch (cause) { if (current === sequence) error.value = message(cause) }
}
async function search(append = false) {
  const current = ++searchSequence
  loading.value = true; formError.value = ''
  try { const data = await catalogList(q.value.trim(), 'published', append ? choices.value.length : 0); if (current === searchSequence) { choices.value = append ? [...choices.value, ...data.items] : data.items; more.value = data.has_more } }
  catch (cause) { if (current === searchSequence) formError.value = message(cause) }
  finally { if (current === searchSequence) loading.value = false }
}
function edit(item: Topic | null = null) {
  target.value = item; title.value = item?.title || ''; description.value = item?.description || ''; visible.value = item?.is_visible || false; order.value = item?.sort_order || 0
  selected.value = item?.papers.map(paper => ({ id: paper.catalog_id, title: paper.title })) || []
  q.value = ''; choices.value = []; formError.value = ''; dialog.value = true; void search()
}
function toggle(item: CatalogPaper) {
  if (selectedIds.value.has(item.id)) selected.value = selected.value.filter(row => row.id !== item.id)
  else if (selected.value.length < 100) selected.value.push({ id: item.id, title: item.title })
}
function move(index: number, direction: number) {
  const next = index + direction
  if (next < 0 || next >= selected.value.length) return
  const items = [...selected.value]; [items[index], items[next]] = [items[next]!, items[index]!]; selected.value = items
}
async function save() {
  if (busy.value || !title.value.trim()) return
  busy.value = true; formError.value = ''
  try { await saveTopic(props.user.id, { title: title.value.trim(), description: description.value, is_visible: visible.value, sort_order: Number(order.value), revision: target.value?.revision || 0, paper_ids: selected.value.map(item => item.id) }, target.value?.id); dialog.value = false; notice.value = '专题已保存'; await load() }
  catch (cause) { formError.value = message(cause) }
  finally { busy.value = false }
}
async function remove() {
  if (!deleting.value || busy.value) return
  busy.value = true; error.value = ''
  try { await removeTopic(props.user.id, deleting.value); deleteOpen.value = false; notice.value = '专题已删除，资料仍保留'; await load() }
  catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}
onActivated(load); onDeactivated(() => { sequence++; searchSequence++; dialog.value = false; deleteOpen.value = false })
</script>
<template>
  <section class="admin-section"><div class="section-toolbar"><p>把多份资料编成专题，按教学顺序展示。</p><UButton label="新建专题" icon="i-lucide-plus" @click="edit()" /></div><UAlert v-if="error" :title="error" color="error" class="notice" /><UAlert v-if="notice" :title="notice" color="success" class="notice" /><div class="data-scroll"><table class="data-table"><thead><tr><th>专题</th><th>资料</th><th>首页顺序</th><th>展示</th><th>操作</th></tr></thead><tbody><tr v-for="item in topics" :key="item.id"><td><strong>{{ item.title }}</strong><p>{{ item.description }}</p></td><td>{{ item.paper_count }} 份</td><td>{{ item.sort_order }}</td><td>{{ item.is_visible ? '已展示' : '隐藏' }}</td><td><div class="actions-row"><UButton label="编辑" variant="soft" @click="edit(item)" /><UButton label="删除专题" color="error" variant="ghost" @click="deleting = item; deleteOpen = true" /></div></td></tr><tr v-if="!topics.length"><td colspan="5">暂无专题</td></tr></tbody></table></div>
    <UModal v-model:open="dialog" :title="target ? '编辑专题' : '新建专题'" :dismissible="!busy" :close="!busy" :ui="{ content: 'max-w-3xl' }"><template #body><form id="topic-form" class="field-stack" @submit.prevent="save"><UFormField label="专题名称" required><UInput v-model="title" maxlength="80" required class="w-full" /></UFormField><UFormField label="专题介绍"><UTextarea v-model="description" maxlength="500" class="w-full" /></UFormField><div class="actions-row"><UFormField label="首页顺序（越小越靠前）"><UInput v-model="order" type="number" min="0" max="100000" /></UFormField><USwitch v-model="visible" label="在小程序展示" /></div><p class="text-sm text-muted">最多 100 份。未发布或文件未就绪的资料不会显示在小程序中。</p><h3>已选资料 · {{ selected.length }}</h3><div class="selected-papers"><div v-for="(item, index) in selected" :key="item.id" class="selected-paper"><span>{{ index + 1 }}. {{ item.title }}</span><UButton label="上移" size="xs" variant="ghost" :disabled="index === 0" @click="move(index, -1)" /><UButton label="下移" size="xs" variant="ghost" :disabled="index === selected.length - 1" @click="move(index, 1)" /><UButton label="移除" size="xs" color="error" variant="ghost" @click="selected = selected.filter(row => row.id !== item.id)" /></div></div><h3>添加资料</h3><div class="actions-row"><UInput v-model="q" placeholder="搜索已发布资料" @keydown.enter.prevent="search()" /><UButton label="搜索" :loading="loading" @click="search()" /></div><div class="source-choices"><UCheckbox v-for="item in choices" :key="item.id" :label="item.title + ' · ' + item.grade + ' · ' + item.subject" :model-value="selectedIds.has(item.id)" :disabled="busy || (!selectedIds.has(item.id) && selected.length >= 100)" @update:model-value="toggle(item)" /></div><UButton v-if="more" label="更多资料" variant="outline" :loading="loading" @click="search(true)" /><UAlert v-if="formError" :title="formError" color="error" /></form></template><template #footer><UButton label="取消" color="neutral" :disabled="busy" @click="dialog = false" /><UButton label="保存专题" type="submit" form="topic-form" :loading="busy" /></template></UModal>
    <UModal v-model:open="deleteOpen" title="删除专题" :dismissible="!busy"><template #body><p>确认删除「{{ deleting?.title }}」？专题内的资料和用户收藏会保留。</p></template><template #footer><UButton label="取消" color="neutral" :disabled="busy" @click="deleteOpen = false" /><UButton label="删除专题" color="error" :loading="busy" @click="remove" /></template></UModal>
  </section>
</template>
<style scoped>
.selected-paper { display:flex;align-items:center;gap:4px;padding:8px 0;border-bottom:1px solid var(--ui-border); }.selected-paper span { flex:1;min-width:0;font-size:13px;overflow-wrap:anywhere; }.selected-papers { max-height:250px;overflow:auto; }.source-choices { display:grid;gap:12px;max-height:240px;overflow:auto; }.data-table p { max-width:380px;font-size:12px;white-space:normal;color:var(--ui-text-muted); }
</style>
