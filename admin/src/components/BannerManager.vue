<script setup lang="ts">
import { computed, onActivated, onDeactivated, ref } from 'vue'
import type { UserInfo } from '../api'
import {
  bannerImageUrl, clearBannerImage, createBanner, deleteBanner, siteBanners, siteCategories, siteDictionary,
  updateBanner, uploadBannerImage, type Banner, type BannerTarget, type Category, type DictionaryItem,
} from '../site'

const props = defineProps<{ user: UserInfo }>()
const items = ref<Banner[]>([])
const categories = ref<Category[]>([])
const subjects = ref<DictionaryItem[]>([])
const loading = ref(false)
const error = ref('')
const notice = ref('')
const busy = ref(false)
const uploading = ref(false)
const dialog = ref(false)
const target = ref<Banner | null>(null)
const formError = ref('')
const removing = ref<Banner | null>(null)
const removeOpen = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const previewKey = ref('')
let sequence = 0

const targetOptions = [
  { label: '不跳转（纯展示）', value: 'none' },
  { label: '按关键词搜索习题', value: 'keyword' },
  { label: '跳到指定分类', value: 'category' },
  { label: '跳到指定科目', value: 'subject' },
  { label: '跳到指定习题', value: 'paper' },
]
const targetLabels: Record<BannerTarget, string> = {
  none: '不跳转', keyword: '关键词', category: '分类', subject: '科目', paper: '习题',
}
const form = ref({
  kicker: '', title: '', subtitle: '', action_label: '', target_type: 'none' as BannerTarget,
  target_value: '', sort_order: 0, is_visible: true,
})
const categoryOptions = computed(() => categories.value.map(item => ({ label: item.name, value: item.id })))
const subjectOptions = computed(() => subjects.value.map(item => ({ label: item.value, value: item.value })))
const canSave = computed(() => !!form.value.title.trim() && (form.value.target_type === 'none' || !!form.value.target_value.trim()))
const message = (cause: unknown) => (cause instanceof Error ? cause.message : '操作失败，请重试')
const fileSize = (bytes: number) => (bytes ? (bytes < 1024 ? bytes + ' B' : (bytes / 1024).toFixed(0) + ' KB') : '未设置')
const date = (stamp: number) => new Date(stamp * 1000).toLocaleString('zh-CN', { hour12: false })

function targetText(item: Banner) {
  if (item.target_type === 'none') return '不跳转'
  if (item.target_type === 'category') return '分类 · ' + (categories.value.find(entry => entry.id === item.target_value)?.name || item.target_value)
  if (item.target_type === 'subject') return '科目 · ' + item.target_value
  if (item.target_type === 'keyword') return '搜索 ' + item.target_value
  return '习题 · ' + item.target_value.slice(0, 8)
}

async function load() {
  const current = ++sequence
  loading.value = true; error.value = ''
  try {
    const [banners, cats, dict] = await Promise.all([siteBanners(), siteCategories(), siteDictionary('subject')])
    if (current !== sequence) return
    items.value = banners.items; categories.value = cats.items; subjects.value = dict.items
  } catch (cause) { if (current === sequence) error.value = message(cause) }
  finally { if (current === sequence) loading.value = false }
}

function create() {
  target.value = null
  form.value = { kicker: '', title: '', subtitle: '', action_label: '去看看', target_type: 'none', target_value: '', sort_order: (items.value.length + 1) * 10, is_visible: true }
  formError.value = ''; previewKey.value = ''; dialog.value = true
}
function edit(item: Banner) {
  target.value = item
  form.value = {
    kicker: item.kicker, title: item.title, subtitle: item.subtitle, action_label: item.action_label,
    target_type: item.target_type, target_value: item.target_value, sort_order: item.sort_order, is_visible: item.is_visible,
  }
  formError.value = ''; previewKey.value = ''; dialog.value = true
}
async function save() {
  if (busy.value || !canSave.value) return
  busy.value = true; formError.value = ''
  try {
    if (target.value) {
      await updateBanner(props.user.id, target.value.id, { revision: target.value.revision, ...form.value })
      notice.value = 'Banner 已更新'
    } else {
      const created = await createBanner(props.user.id, form.value)
      target.value = created
      notice.value = 'Banner 已创建，接着可以上传配图'
      previewKey.value = ''
      await load()
      return
    }
    dialog.value = false; await load()
  } catch (cause) { formError.value = message(cause) }
  finally { busy.value = false }
}
function pickFile() { fileInput.value?.click() }
async function onFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !target.value) return
  if (file.size > 2 * 1024 * 1024) { formError.value = '图片不能超过 2 MB'; return }
  uploading.value = true; formError.value = ''
  try {
    const saved = await uploadBannerImage(props.user.id, target.value.id, file)
    target.value = saved
    previewKey.value = String(saved.revision)
    notice.value = '配图已更新'
    await load()
  } catch (cause) { formError.value = message(cause) }
  finally { uploading.value = false }
}
async function removeImage() {
  if (!target.value || uploading.value) return
  uploading.value = true; formError.value = ''
  try {
    const saved = await clearBannerImage(props.user.id, target.value.id, target.value.revision)
    target.value = saved; previewKey.value = ''; notice.value = '配图已移除'; await load()
  } catch (cause) { formError.value = message(cause) }
  finally { uploading.value = false }
}
async function toggleVisible(item: Banner) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    await updateBanner(props.user.id, item.id, { revision: item.revision, kicker: item.kicker, title: item.title, subtitle: item.subtitle, action_label: item.action_label, target_type: item.target_type, target_value: item.target_value, sort_order: item.sort_order, is_visible: !item.is_visible })
    await load()
  } catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}
function askRemove(item: Banner) { removing.value = item; removeOpen.value = true }
async function confirmRemove() {
  if (!removing.value || busy.value) return
  busy.value = true
  try {
    await deleteBanner(props.user.id, removing.value.id, removing.value.revision)
    removeOpen.value = false; notice.value = 'Banner 已删除'; await load()
  } catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}

onActivated(load)
onDeactivated(() => { sequence++; loading.value = false; dialog.value = false; removeOpen.value = false })
</script>

<template>
  <section class="admin-section" aria-label="首页 Banner 管理">
    <div class="section-toolbar">
      <p class="section-hint">小程序首页顶部的轮播位。留空配图时会自动回退到内置插画，不会出现坏图。</p>
      <div class="actions-row"><UTooltip text="刷新"><UButton icon="i-lucide-refresh-cw" color="neutral" variant="ghost" aria-label="刷新 Banner" :loading="loading" @click="load" /></UTooltip><UButton icon="i-lucide-plus" label="新建 Banner" @click="create" /></div>
    </div>
    <UAlert v-if="error" :title="error" color="error" variant="soft" class="notice" />
    <UAlert v-if="notice" :title="notice" color="success" variant="soft" close class="notice" @update:open="notice = ''" />
    <div class="data-scroll" :aria-busy="loading"><table class="data-table banner-table"><thead><tr><th class="thumb-col">配图</th><th>文案</th><th>跳转</th><th class="num-col">顺序</th><th>状态</th><th>更新时间</th><th><span class="sr-only">操作</span></th></tr></thead><tbody>
      <tr v-for="item in items" :key="item.id">
        <td class="thumb-col"><div class="thumb"><img v-if="item.image_url" :src="bannerImageUrl(item.id)" :alt="item.title + ' 配图'" /><UIcon v-else name="i-lucide-image" class="size-5 text-muted" /></div></td>
        <td class="copy-cell"><strong>{{ item.title }}</strong><span v-if="item.kicker" class="copy-kicker">{{ item.kicker }}</span><span v-if="item.subtitle" class="copy-sub">{{ item.subtitle }}</span></td>
        <td><UBadge color="neutral" variant="soft">{{ targetLabels[item.target_type] }}</UBadge><div class="target-detail">{{ targetText(item) }}</div></td>
        <td class="num-col">{{ item.sort_order }}</td>
        <td><UBadge :color="item.is_visible ? 'success' : 'neutral'" variant="soft">{{ item.is_visible ? '展示中' : '已下线' }}</UBadge></td>
        <td class="date-cell">{{ date(item.updated_at) }}</td>
        <td><div class="row-actions"><UTooltip text="编辑与配图"><UButton icon="i-lucide-pencil" color="neutral" variant="ghost" :aria-label="'编辑 ' + item.title" @click="edit(item)" /></UTooltip><UTooltip :text="item.is_visible ? '下线' : '上线'"><UButton :icon="item.is_visible ? 'i-lucide-eye-off' : 'i-lucide-eye'" color="neutral" variant="ghost" :aria-label="(item.is_visible ? '下线 ' : '上线 ') + item.title" @click="toggleVisible(item)" /></UTooltip><UTooltip text="删除"><UButton icon="i-lucide-trash-2" color="error" variant="ghost" :aria-label="'删除 ' + item.title" @click="askRemove(item)" /></UTooltip></div></td>
      </tr>
      <tr v-if="!items.length"><td colspan="7"><div class="empty-state"><UIcon :name="loading ? 'i-lucide-loader-circle' : 'i-lucide-gallery-horizontal-end'" class="size-7" :class="{ 'animate-spin': loading }" /><h3>{{ loading ? '正在加载' : '还没有 Banner' }}</h3><p v-if="!loading">没有配置时，小程序首页显示内置的两条默认轮播。</p></div></td></tr>
    </tbody></table></div>
    <div class="table-footer"><span>共 {{ items.length }} 条 Banner</span></div>

    <UModal v-model:open="dialog" :title="target ? '编辑 Banner' : '新建 Banner'" :dismissible="!busy && !uploading" :close="!busy && !uploading"><template #body><form id="banner-form" class="field-stack" @submit.prevent="save">
      <UFormField label="标题" required><UInput v-model="form.title" maxlength="40" :disabled="busy" required class="w-full" /></UFormField>
      <div class="grid-two"><UFormField label="上方小字"><UInput v-model="form.kicker" maxlength="40" :disabled="busy" class="w-full" /></UFormField><UFormField label="按钮文案"><UInput v-model="form.action_label" maxlength="20" :disabled="busy" class="w-full" /></UFormField></div>
      <UFormField label="副标题"><UInput v-model="form.subtitle" maxlength="60" :disabled="busy" class="w-full" /></UFormField>
      <div class="grid-two"><UFormField label="跳转方式"><USelect v-model="form.target_type" :items="targetOptions" :disabled="busy" class="w-full" /></UFormField>
        <UFormField v-if="form.target_type === 'category'" label="目标分类" required><USelect v-model="form.target_value" :items="categoryOptions" :disabled="busy" class="w-full" /></UFormField>
        <UFormField v-else-if="form.target_type === 'subject'" label="目标科目" required><USelect v-model="form.target_value" :items="subjectOptions" :disabled="busy" class="w-full" /></UFormField>
        <UFormField v-else-if="form.target_type === 'keyword'" label="搜索关键词" required><UInput v-model="form.target_value" maxlength="64" placeholder="例如：阅读" :disabled="busy" class="w-full" /></UFormField>
        <UFormField v-else-if="form.target_type === 'paper'" label="习题 ID" required hint="从「公共习题」列表复制条目 ID"><UInput v-model="form.target_value" maxlength="64" :disabled="busy" class="w-full" /></UFormField>
      </div>
      <UFormField label="展示顺序" hint="数值小的排前面"><UInput v-model.number="form.sort_order" type="number" min="0" :disabled="busy" class="w-full" /></UFormField>
      <USwitch v-model="form.is_visible" label="在小程序展示" :disabled="busy" />
      <div v-if="target" class="image-block">
        <span class="block-label">配图（JPG / PNG / WebP，≤2 MB，宽高上限 2400×1600）</span>
        <div class="image-row">
          <div class="thumb large"><img v-if="target.image_url" :key="previewKey || target.revision" :src="bannerImageUrl(target.id)" :alt="target.title + ' 配图预览'" /><UIcon v-else name="i-lucide-image" class="size-6 text-muted" /></div>
          <div class="image-actions">
            <UButton icon="i-lucide-upload" label="上传配图" color="neutral" variant="outline" :loading="uploading" :disabled="busy || uploading" @click="pickFile" />
            <UButton v-if="target.image_url" icon="i-lucide-x" label="移除配图" color="error" variant="ghost" :disabled="busy || uploading" @click="removeImage" />
            <span class="image-meta">{{ fileSize(target.image_bytes) }}<template v-if="target.image_mime"> · {{ target.image_mime }}</template></span>
          </div>
        </div>
        <input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp" class="sr-only" @change="onFile" />
      </div>
      <UAlert v-else color="info" variant="soft" title="保存后即可上传配图。" />
      <UAlert v-if="formError" :title="formError" color="error" variant="soft" />
    </form></template><template #footer><UButton label="关闭" color="neutral" variant="outline" :disabled="busy || uploading" @click="dialog = false" /><UButton type="submit" form="banner-form" :label="target ? '保存' : '创建'" icon="i-lucide-check" :loading="busy" :disabled="busy || uploading || !canSave" /></template></UModal>

    <UModal v-model:open="removeOpen" title="删除 Banner" :dismissible="!busy" :close="!busy"><template #body><div class="field-stack"><p>确认删除「{{ removing?.title }}」？配图会一并从存储中清理。</p></div></template><template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="busy" @click="removeOpen = false" /><UButton label="确认删除" color="error" icon="i-lucide-trash-2" :loading="busy" :disabled="busy" @click="confirmRemove" /></template></UModal>
  </section>
</template>

<style scoped>
.section-hint { margin: 0; max-width: 620px; color: var(--ui-text-muted); font-size: 12px; line-height: 1.7; }
.banner-table { min-width: 940px; }
.thumb-col { width: 96px; }
.num-col { width: 76px; font-variant-numeric: tabular-nums; }
.thumb { width: 72px; height: 46px; display: flex; align-items: center; justify-content: center; border: 1px solid var(--ui-border-muted); border-radius: 5px; background: #f8fafb; overflow: hidden; }
.thumb.large { width: 132px; height: 84px; }
.thumb img { width: 100%; height: 100%; object-fit: cover; }
.copy-cell { display: flex; flex-direction: column; gap: 3px; white-space: normal; max-width: 300px; }
.copy-kicker, .copy-sub { color: var(--ui-text-muted); font-size: 11px; }
.target-detail { margin-top: 5px; color: var(--ui-text-muted); font-size: 11px; }
.row-actions { display: flex; gap: 2px; }
.grid-two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.block-label { display: block; margin-bottom: 10px; font-size: 12px; color: var(--ui-text-toned); }
.image-row { display: flex; align-items: center; gap: 16px; }
.image-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.image-meta { color: var(--ui-text-muted); font-size: 11px; }
.empty-state p { margin: 8px 0 0; font-size: 12px; }
@media (max-width: 767px) { .grid-two { grid-template-columns: minmax(0, 1fr); } }
</style>
