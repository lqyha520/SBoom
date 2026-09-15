<script setup lang="ts">
import { computed, onActivated, onDeactivated, ref } from 'vue'
import type { UserInfo } from '../api'
import {
  adoptDictionary, createDictionary, deleteDictionary, siteDictionary, unlistedDictionary, updateDictionary,
  type DictionaryItem,
} from '../site'

const props = defineProps<{ user: UserInfo }>()
const items = ref<DictionaryItem[]>([])
const unlisted = ref<{ grade: string[]; subject: string[] }>({ grade: [], subject: [] })
const kind = ref<'grade' | 'subject'>('grade')
const loading = ref(false)
const error = ref('')
const notice = ref('')
const busy = ref(false)
const dialog = ref(false)
const target = ref<DictionaryItem | null>(null)
const formError = ref('')
const removing = ref<DictionaryItem | null>(null)
const removeOpen = ref(false)
let sequence = 0

const tabs = [{ label: '年级', value: 'grade' }, { label: '科目', value: 'subject' }]
const kindLabel = computed(() => (kind.value === 'grade' ? '年级' : '科目'))
const visible = computed(() => items.value.filter(item => item.kind === kind.value))
const pending = computed(() => unlisted.value[kind.value] || [])
// 字段名用 entry 而不是 value：模板里 ref 会被自动解包，form.value 已经指向对象本身，
// 再写 form.value.value 既难读也容易被类型检查判错。
const form = ref({ entry: '', label: '', sort_order: 0, is_visible: true })
const message = (cause: unknown) => (cause instanceof Error ? cause.message : '操作失败，请重试')

async function load() {
  const current = ++sequence
  loading.value = true; error.value = ''
  try {
    const [dictionary, missing] = await Promise.all([siteDictionary(), unlistedDictionary()])
    if (current !== sequence) return
    items.value = dictionary.items; unlisted.value = missing
  } catch (cause) { if (current === sequence) error.value = message(cause) }
  finally { if (current === sequence) loading.value = false }
}

function create() {
  target.value = null
  form.value = { entry: '', label: '', sort_order: (visible.value.length + 1) * 10, is_visible: true }
  formError.value = ''; dialog.value = true
}
function edit(item: DictionaryItem) {
  target.value = item
  form.value = { entry: item.value, label: item.label, sort_order: item.sort_order, is_visible: item.is_visible }
  formError.value = ''; dialog.value = true
}
async function save() {
  if (busy.value || !form.value.entry.trim()) return
  busy.value = true; formError.value = ''
  const payload = { value: form.value.entry.trim(), label: form.value.label, sort_order: form.value.sort_order, is_visible: form.value.is_visible }
  try {
    if (target.value) await updateDictionary(props.user.id, target.value.id, { revision: target.value.revision, ...payload })
    else await createDictionary(props.user.id, { kind: kind.value, ...payload })
    notice.value = kindLabel.value + '字典已更新'
    dialog.value = false; await load()
  } catch (cause) { formError.value = message(cause) }
  finally { busy.value = false }
}
async function move(index: number, delta: number) {
  const next = index + delta
  const list = visible.value
  if (busy.value || next < 0 || next >= list.length) return
  const reordered = [...list]
  const [moved] = reordered.splice(index, 1)
  reordered.splice(next, 0, moved!)
  busy.value = true; error.value = ''
  try {
    await Promise.all(reordered.map((item, position) => updateDictionary(props.user.id, item.id, {
      revision: item.revision, value: item.value, label: item.label, sort_order: (position + 1) * 10, is_visible: item.is_visible,
    })))
    notice.value = '顺序已保存'
    await load()
  } catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}
async function toggleVisible(item: DictionaryItem) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    await updateDictionary(props.user.id, item.id, { revision: item.revision, value: item.value, label: item.label, sort_order: item.sort_order, is_visible: !item.is_visible })
    await load()
  } catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}
async function adopt() {
  if (busy.value || !pending.value.length) return
  busy.value = true; error.value = ''
  try {
    const result = await adoptDictionary(props.user.id, kind.value, pending.value)
    notice.value = result.added ? `已收录 ${result.added} 个${kindLabel.value}` : '没有新增条目'
    await load()
  } catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}
function askRemove(item: DictionaryItem) { removing.value = item; removeOpen.value = true }
async function confirmRemove() {
  if (!removing.value || busy.value) return
  busy.value = true
  try {
    await deleteDictionary(props.user.id, removing.value.id, removing.value.revision)
    removeOpen.value = false; notice.value = '条目已删除'; await load()
  } catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}

onActivated(load)
onDeactivated(() => { sequence++; loading.value = false; dialog.value = false; removeOpen.value = false })
</script>

<template>
  <section class="admin-section" aria-label="年级科目字典">
    <div class="section-toolbar">
      <p class="section-hint">字典决定小程序筛选器里的选项和顺序；隐藏的取值不会出现在小程序，但已有习题不受影响。</p>
      <div class="actions-row"><UTooltip text="刷新"><UButton icon="i-lucide-refresh-cw" color="neutral" variant="ghost" aria-label="刷新字典" :loading="loading" @click="load" /></UTooltip><UButton icon="i-lucide-plus" :label="'新建' + kindLabel" @click="create" /></div>
    </div>
    <UTabs v-model="kind" :items="tabs" :content="false" class="dict-tabs" />
    <UAlert v-if="error" :title="error" color="error" variant="soft" class="notice" />
    <UAlert v-if="notice" :title="notice" color="success" variant="soft" close class="notice" @update:open="notice = ''" />

    <div v-if="pending.length" class="unlisted">
      <div class="unlisted-head"><UIcon name="i-lucide-triangle-alert" class="size-4" /><strong>发现 {{ pending.length }} 个未收录的{{ kindLabel }}</strong><span>来自历史试卷的自由文本，建议收编进字典以便统一管理。</span></div>
      <div class="unlisted-values"><UBadge v-for="value in pending" :key="value" color="warning" variant="soft">{{ value }}</UBadge></div>
      <UButton icon="i-lucide-plus" :label="'全部收录进' + kindLabel + '字典'" color="warning" variant="soft" size="sm" :loading="busy" :disabled="busy" @click="adopt" />
    </div>

    <div class="data-scroll" :aria-busy="loading"><table class="data-table dict-table"><thead><tr><th class="order-col">顺序</th><th>{{ kindLabel }}</th><th>显示名</th><th>小程序展示</th><th><span class="sr-only">操作</span></th></tr></thead><tbody>
      <tr v-for="(item, index) in visible" :key="item.id">
        <td class="order-col"><div class="order-buttons"><UButton icon="i-lucide-chevron-up" size="xs" color="neutral" variant="ghost" :disabled="index === 0 || busy" :aria-label="'上移 ' + item.value" @click="move(index, -1)" /><UButton icon="i-lucide-chevron-down" size="xs" color="neutral" variant="ghost" :disabled="index === visible.length - 1 || busy" :aria-label="'下移 ' + item.value" @click="move(index, 1)" /></div></td>
        <td class="name-cell">{{ item.value }}</td>
        <td class="desc-cell">{{ item.label || '—' }}</td>
        <td><UBadge :color="item.is_visible ? 'success' : 'neutral'" variant="soft">{{ item.is_visible ? '展示中' : '已隐藏' }}</UBadge></td>
        <td><div class="row-actions"><UTooltip text="编辑"><UButton icon="i-lucide-pencil" color="neutral" variant="ghost" :aria-label="'编辑 ' + item.value" @click="edit(item)" /></UTooltip><UTooltip :text="item.is_visible ? '隐藏' : '展示'"><UButton :icon="item.is_visible ? 'i-lucide-eye-off' : 'i-lucide-eye'" color="neutral" variant="ghost" :aria-label="(item.is_visible ? '隐藏 ' : '展示 ') + item.value" @click="toggleVisible(item)" /></UTooltip><UTooltip text="删除"><UButton icon="i-lucide-trash-2" color="error" variant="ghost" :aria-label="'删除 ' + item.value" @click="askRemove(item)" /></UTooltip></div></td>
      </tr>
      <tr v-if="!visible.length"><td colspan="5"><div class="empty-state"><UIcon :name="loading ? 'i-lucide-loader-circle' : 'i-lucide-list-tree'" class="size-7" :class="{ 'animate-spin': loading }" /><h3>{{ loading ? '正在加载' : '该字典为空' }}</h3></div></td></tr>
    </tbody></table></div>
    <div class="table-footer"><span>共 {{ visible.length }} 个{{ kindLabel }}</span></div>

    <UModal v-model:open="dialog" :title="(target ? '编辑' : '新建') + kindLabel" :dismissible="!busy" :close="!busy"><template #body><form id="dict-form" class="field-stack" @submit.prevent="save">
      <UFormField :label="kindLabel + '取值'" required :hint="kind === 'grade' ? '需与试卷里保存的年级写法完全一致' : '需与试卷里保存的科目写法完全一致'"><UInput v-model="form.entry" maxlength="80" :disabled="busy" required class="w-full" /></UFormField>
      <UFormField label="显示名" hint="留空则直接显示取值本身"><UInput v-model="form.label" maxlength="80" :disabled="busy" class="w-full" /></UFormField>
      <UFormField label="展示顺序" hint="数值小的排前面"><UInput v-model.number="form.sort_order" type="number" min="0" :disabled="busy" class="w-full" /></UFormField>
      <USwitch v-model="form.is_visible" label="在小程序展示" :disabled="busy" />
      <UAlert v-if="formError" :title="formError" color="error" variant="soft" />
    </form></template><template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="busy" @click="dialog = false" /><UButton type="submit" form="dict-form" :label="target ? '保存' : '创建'" icon="i-lucide-check" :loading="busy" :disabled="busy || !form.entry.trim()" /></template></UModal>

    <UModal v-model:open="removeOpen" title="删除字典条目" :dismissible="!busy" :close="!busy"><template #body><div class="field-stack"><p>确认删除「{{ removing?.value }}」？已有习题本身不会被改动。</p></div></template><template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="busy" @click="removeOpen = false" /><UButton label="确认删除" color="error" icon="i-lucide-trash-2" :loading="busy" :disabled="busy" @click="confirmRemove" /></template></UModal>
  </section>
</template>

<style scoped>
.section-hint { margin: 0; max-width: 640px; color: var(--ui-text-muted); font-size: 12px; line-height: 1.7; }
.dict-tabs { margin-bottom: 20px; max-width: 260px; }
.dict-table { min-width: 760px; }
.order-col { width: 76px; }
.order-buttons { display: flex; gap: 2px; }
.desc-cell { color: var(--ui-text-muted); }
.row-actions { display: flex; gap: 2px; }
.unlisted { display: flex; flex-direction: column; gap: 12px; align-items: flex-start; margin-bottom: 24px; padding: 18px; border: 1px solid var(--ui-warning); border-radius: 8px; background: var(--ui-warning-soft, #fff9ec); }
.unlisted-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; color: var(--ui-text-highlighted); }
.unlisted-head span { color: var(--ui-text-muted); font-size: 12px; }
.unlisted-values { display: flex; flex-wrap: wrap; gap: 8px; }
</style>
