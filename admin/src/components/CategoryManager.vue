<script setup lang="ts">
import { computed, onActivated, onDeactivated, ref } from 'vue'
import type { UserInfo } from '../api'
import { createCategory, deleteCategory, reorderCategories, siteCategories, updateCategory, type Category } from '../site'

const props = defineProps<{ user: UserInfo }>()
const items = ref<Category[]>([])
const loading = ref(false)
const error = ref('')
const notice = ref('')
const busy = ref(false)
const dialog = ref(false)
const target = ref<Category | null>(null)
const formError = ref('')
const removing = ref<Category | null>(null)
const removeOpen = ref(false)
const removeError = ref('')
let sequence = 0

// 取值必须是 wot-design-uni 图标名（小程序端用 wd-icon 渲染），改这里前先确认图标字体里有该名字
const iconOptions = [
  { label: '无图标', value: 'none' },
  { label: 'book · 书本', value: 'book' },
  { label: 'formula · 公式', value: 'formula' },
  { label: 'translate · 翻译', value: 'translate' },
  { label: 'edit · 编辑', value: 'edit' },
  { label: 'copy · 复制', value: 'copy' },
  { label: 'file · 文件', value: 'file' },
  { label: 'list · 列表', value: 'list' },
  { label: 'ordered-list · 有序列表', value: 'ordered-list' },
  { label: 'mind-mapping · 思维导图', value: 'mind-mapping' },
  { label: 'star · 星星', value: 'star' },
  { label: 'trophy · 奖杯', value: 'trophy' },
  { label: 'experiment · 实验', value: 'experiment' },
  { label: 'bulb · 灯泡', value: 'bulb' },
  { label: 'calendar-line · 日历', value: 'calendar-line' },
  { label: 'clock-circle · 时钟', value: 'clock-circle' },
  { label: 'folder · 文件夹', value: 'folder' },
  { label: 'tag · 标签', value: 'tag' },
  { label: 'heart · 爱心', value: 'heart' },
  { label: 'archive · 归档', value: 'archive' },
]
const form = ref({ name: '', description: '', icon: '', sort_order: 0, is_visible: true })
const selectedIcon = computed({
  get: () => form.value.icon || 'none',
  set: (value: string) => { form.value.icon = value === 'none' ? '' : value },
})
const message = (cause: unknown) => (cause instanceof Error ? cause.message : '操作失败，请重试')

async function load() {
  const current = ++sequence
  loading.value = true; error.value = ''
  try {
    const result = await siteCategories()
    if (current === sequence) items.value = result.items
  } catch (cause) { if (current === sequence) error.value = message(cause) }
  finally { if (current === sequence) loading.value = false }
}

function create() {
  target.value = null
  form.value = { name: '', description: '', icon: '', sort_order: (items.value.length + 1) * 10, is_visible: true }
  formError.value = ''; dialog.value = true
}
function edit(item: Category) {
  target.value = item
  form.value = { name: item.name, description: item.description, icon: item.icon, sort_order: item.sort_order, is_visible: item.is_visible }
  formError.value = ''; dialog.value = true
}
async function save() {
  if (busy.value || !form.value.name.trim()) return
  busy.value = true; formError.value = ''
  try {
    if (target.value) {
      await updateCategory(props.user.id, target.value.id, { revision: target.value.revision, ...form.value })
      notice.value = '分类已更新，小程序端同步生效'
    } else {
      await createCategory(props.user.id, form.value)
      notice.value = '分类已创建'
    }
    dialog.value = false; await load()
  } catch (cause) { formError.value = message(cause) }
  finally { busy.value = false }
}

/** 上下移动：本地重排后整体提交顺序，避免逐条改 sort_order 产生中间态 */
async function move(index: number, delta: number) {
  const next = index + delta
  if (busy.value || next < 0 || next >= items.value.length) return
  const ordered = [...items.value]
  const [moved] = ordered.splice(index, 1)
  ordered.splice(next, 0, moved!)
  busy.value = true; error.value = ''
  try {
    const result = await reorderCategories(props.user.id, ordered.map(item => item.id))
    items.value = result.items
    notice.value = '展示顺序已保存'
  } catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}

async function toggleVisible(item: Category) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    await updateCategory(props.user.id, item.id, {
      revision: item.revision, name: item.name, description: item.description,
      icon: item.icon, sort_order: item.sort_order, is_visible: !item.is_visible,
    })
    await load()
  } catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}

function askRemove(item: Category) { removing.value = item; removeError.value = ''; removeOpen.value = true }
async function confirmRemove() {
  if (!removing.value || busy.value) return
  busy.value = true; removeError.value = ''
  try {
    await deleteCategory(props.user.id, removing.value.id, removing.value.revision)
    removeOpen.value = false; notice.value = '分类已删除'; await load()
  } catch (cause) { removeError.value = message(cause) }
  finally { busy.value = false }
}

onActivated(load)
onDeactivated(() => { sequence++; loading.value = false; dialog.value = false; removeOpen.value = false })
</script>

<template>
  <section class="admin-section" aria-label="习题分类管理">
    <div class="section-toolbar">
      <p class="section-hint">分类决定小程序首页专题入口与筛选器里的选项；顺序即小程序里的展示顺序。</p>
      <div class="actions-row"><UTooltip text="刷新"><UButton icon="i-lucide-refresh-cw" color="neutral" variant="ghost" aria-label="刷新分类" :loading="loading" @click="load" /></UTooltip><UButton icon="i-lucide-plus" label="新建分类" @click="create" /></div>
    </div>
    <UAlert v-if="error" :title="error" color="error" variant="soft" class="notice" />
    <UAlert v-if="notice" :title="notice" color="success" variant="soft" close class="notice" @update:open="notice = ''" />
    <div class="data-scroll" :aria-busy="loading"><table class="data-table category-table"><thead><tr><th class="order-col">顺序</th><th>分类名</th><th>简介</th><th>图标</th><th>关联习题</th><th>小程序展示</th><th><span class="sr-only">操作</span></th></tr></thead><tbody>
      <tr v-for="(item, index) in items" :key="item.id">
        <td class="order-col"><div class="order-buttons"><UButton icon="i-lucide-chevron-up" size="xs" color="neutral" variant="ghost" :disabled="index === 0 || busy" :aria-label="'上移 ' + item.name" @click="move(index, -1)" /><UButton icon="i-lucide-chevron-down" size="xs" color="neutral" variant="ghost" :disabled="index === items.length - 1 || busy" :aria-label="'下移 ' + item.name" @click="move(index, 1)" /></div></td>
        <td class="name-cell">{{ item.name }}</td>
        <td class="desc-cell">{{ item.description || '—' }}</td>
        <td class="date-cell">{{ item.icon || '—' }}</td>
        <td>{{ item.paper_count }} 份</td>
        <td><UBadge :color="item.is_visible ? 'success' : 'neutral'" variant="soft">{{ item.is_visible ? '展示中' : '已隐藏' }}</UBadge></td>
        <td><div class="row-actions"><UTooltip text="编辑分类"><UButton icon="i-lucide-pencil" color="neutral" variant="ghost" :aria-label="'编辑 ' + item.name" @click="edit(item)" /></UTooltip><UTooltip :text="item.is_visible ? '隐藏' : '展示'"><UButton :icon="item.is_visible ? 'i-lucide-eye-off' : 'i-lucide-eye'" color="neutral" variant="ghost" :aria-label="(item.is_visible ? '隐藏 ' : '展示 ') + item.name" @click="toggleVisible(item)" /></UTooltip><UTooltip text="删除分类"><UButton icon="i-lucide-trash-2" color="error" variant="ghost" :aria-label="'删除 ' + item.name" @click="askRemove(item)" /></UTooltip></div></td>
      </tr>
      <tr v-if="!items.length"><td colspan="7"><div class="empty-state"><UIcon :name="loading ? 'i-lucide-loader-circle' : 'i-lucide-folder-tree'" class="size-7" :class="{ 'animate-spin': loading }" /><h3>{{ loading ? '正在加载' : '还没有分类' }}</h3><p v-if="!loading">点击「新建分类」创建分类，再到「公共习题」分配资料。历史分类会在服务启动时自动收编。</p></div></td></tr>
    </tbody></table></div>
    <div class="table-footer"><span>共 {{ items.length }} 个分类</span></div>

    <UModal v-model:open="dialog" :title="target ? '编辑分类' : '新建分类'" :dismissible="!busy" :close="!busy"><template #body><form id="category-form" class="field-stack" @submit.prevent="save">
      <UFormField label="分类名" required hint="展示在小程序筛选器与首页专题入口"><UInput v-model="form.name" maxlength="60" :disabled="busy" required class="w-full" /></UFormField>
      <UFormField label="一句话简介" hint="显示在首页专题卡片的副标题"><UInput v-model="form.description" maxlength="300" :disabled="busy" class="w-full" /></UFormField>
      <UFormField label="图标"><USelect v-model="selectedIcon" :items="iconOptions" :disabled="busy" class="w-full" /></UFormField>
      <UFormField label="展示顺序" hint="数值小的排前面，也可以用列表里的上下箭头调整"><UInput v-model.number="form.sort_order" type="number" min="0" :disabled="busy" class="w-full" /></UFormField>
      <USwitch v-model="form.is_visible" label="在小程序展示" :disabled="busy" />
      <UAlert v-if="formError" :title="formError" color="error" variant="soft" />
    </form></template><template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="busy" @click="dialog = false" /><UButton type="submit" form="category-form" :label="target ? '保存' : '创建'" icon="i-lucide-check" :loading="busy" :disabled="busy || !form.name.trim()" /></template></UModal>

    <UModal v-model:open="removeOpen" title="删除分类" :dismissible="!busy" :close="!busy"><template #body><div class="field-stack"><p>确认删除分类「{{ removing?.name }}」？该操作不可撤销。</p><UAlert v-if="removing?.paper_count" color="warning" variant="soft" :title="'当前还有 ' + removing.paper_count + ' 份习题属于该分类，需要先把这些习题改到其他分类。'" /><UAlert v-if="removeError" :title="removeError" color="error" variant="soft" /></div></template><template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="busy" @click="removeOpen = false" /><UButton label="确认删除" color="error" icon="i-lucide-trash-2" :loading="busy" :disabled="busy" @click="confirmRemove" /></template></UModal>
  </section>
</template>

<style scoped>
.section-hint { margin: 0; max-width: 620px; color: var(--ui-text-muted); font-size: 12px; line-height: 1.7; }
.category-table { min-width: 900px; }
.order-col { width: 76px; }
.order-buttons { display: flex; gap: 2px; }
.desc-cell { max-width: 320px; white-space: normal; overflow-wrap: anywhere; color: var(--ui-text-muted); }
.row-actions { display: flex; gap: 2px; }
.empty-state p { margin: 8px 0 0; color: var(--ui-text-muted); font-size: 12px; }
</style>
