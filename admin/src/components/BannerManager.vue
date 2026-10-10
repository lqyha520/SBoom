<script setup lang="ts">
import { useDialogDraft } from '../dialog-draft'
import { useRevisionConflict } from '../revision-conflict'
import { computed, onActivated, onDeactivated, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import type { UserInfo } from '../api'
import BannerPreview from './BannerPreview.vue'
import PublishedPaperPicker from './PublishedPaperPicker.vue'
import {
  getHomeSettings, saveHomeSettings, type HomeSettings,
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
const homeSettings = ref<HomeSettings | null>(null)
async function changeMode(enabled: boolean) {
  if (busy.value || !homeSettings.value) return
  busy.value = true; error.value = ''
  try {
    homeSettings.value = await saveHomeSettings(props.user.id, { ...homeSettings.value, banner_mode: enabled ? 'operations' : 'welcome' })
    notice.value = enabled ? '运营 Banner 已启用' : '首页已切换为欢迎卡'
  } catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}
const busy = ref(false)
const checking = ref(false)
const dialog = ref(false)
const target = ref<Banner | null>(null)
const formError = ref('')
const recovery = useRevisionConflict(target, async id => { const value = (await siteBanners()).items.find(item => item.id === id); if (!value) throw new Error('该条目已删除，请复制修改后新建'); return value }, formError)
const removing = ref<Banner | null>(null)
const removeOpen = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const pendingFile = shallowRef<File | null>(null)
const localPreview = ref('')
const removingImage = ref(false)
const imageSize = ref('')
const paperLabel = ref('')
const saveStage = ref('')
let sequence = 0
let imageSequence = 0

const targetOptions = [
  { label: '不跳转（纯展示）', value: 'none' },
  { label: '按关键词找习题', value: 'keyword' },
  { label: '打开一个分类', value: 'category' },
  { label: '打开一个学科', value: 'subject' },
  { label: '打开指定习题', value: 'paper' },
]
function blankForm() {
  return { kicker: '', title: '', subtitle: '', action_label: '去看看', target_type: 'none' as BannerTarget,
    target_value: '', image_fit: 'contain' as 'contain' | 'cover', sort_order: (items.value.length + 1) * 10, is_visible: true }
}
const form = ref(blankForm())
const categoryOptions = computed(() => categories.value.filter(item => item.is_visible).map(item => ({ label: item.name, value: item.id })))
const subjectOptions = computed(() => subjects.value.filter(item => item.is_visible).map(item => ({ label: item.value, value: item.value })))
const canSave = computed(() => !!form.value.title.trim() && (form.value.target_type === 'none' || !!form.value.target_value.trim()))
const shown = computed(() => items.value.filter(item => item.is_visible).length)
const previewUrl = computed(() => localPreview.value || (!removingImage.value && target.value?.image_url ? bannerImageUrl(target.value.id, target.value.revision) : ''))
const message = (cause: unknown) => cause instanceof Error ? cause.message : '操作失败，请重试'
const fileSize = (bytes: number) => bytes < 1024 ? bytes + ' B' : (bytes / 1024).toFixed(0) + ' KB'
const date = (stamp: number) => new Date(stamp * 1000).toLocaleString('zh-CN', { hour12: false })

function targetText(item: { target_type: BannerTarget; target_value: string }) {
  if (item.target_type === 'none') return '纯展示 · 不跳转'
  if (item.target_type === 'category') return '分类 · ' + (categories.value.find(entry => entry.id === item.target_value)?.name || item.target_value)
  if (item.target_type === 'subject') return '学科 · ' + item.target_value
  if (item.target_type === 'keyword') return '搜索 · ' + item.target_value
  return '指定习题 · ' + item.target_value.slice(0, 8)
}
async function load() {
  const current = ++sequence
  loading.value = true; error.value = ''
  try {
    const [banners, cats, dict, settings] = await Promise.all([siteBanners(), siteCategories(), siteDictionary('subject'), getHomeSettings()])
    if (current !== sequence) return
    items.value = banners.items; categories.value = cats.items; subjects.value = dict.items
    homeSettings.value = settings
  } catch (cause) { if (current === sequence) error.value = message(cause) }
  finally { if (current === sequence) loading.value = false }
}
function resetImage() {
  if (localPreview.value) URL.revokeObjectURL(localPreview.value)
  localPreview.value = ''; pendingFile.value = null; removingImage.value = false; imageSize.value = ''
}
function create() {
  resetImage(); target.value = null; form.value = blankForm()
  formError.value = ''; paperLabel.value = ''; dialog.value = true
}
function edit(item: Banner) {
  resetImage(); target.value = item
  form.value = {
    kicker: item.kicker, title: item.title, subtitle: item.subtitle, action_label: item.action_label,
    target_type: item.target_type, target_value: item.target_value, image_fit: item.image_fit || 'contain',
    sort_order: item.sort_order, is_visible: item.is_visible,
  }
  formError.value = ''; paperLabel.value = ''; dialog.value = true
}
function changeTarget(value: string) {
  if (!targetOptions.some(item => item.value === value)) return
  form.value.target_type = value as BannerTarget; form.value.target_value = ''; paperLabel.value = ''
}
async function save() {
  if (busy.value || checking.value || !canSave.value) return
  busy.value = true; formError.value = ''; saveStage.value = '正在保存文案'
  const body = { ...form.value }
  let savedCopy = false
  try {
    const imageChanged = !!pendingFile.value || removingImage.value
    // A new banner stays hidden until its selected image has uploaded. A failed
    // upload keeps the local draft, so retrying never publishes an unfinished card.
    const isVisible = imageChanged ? !!target.value?.is_visible && body.is_visible : body.is_visible
    target.value = target.value
      ? await updateBanner(props.user.id, target.value.id, { ...body, is_visible: isVisible, revision: target.value.revision })
      : await createBanner(props.user.id, { ...body, is_visible: isVisible })
    savedCopy = true
    if (pendingFile.value) {
      saveStage.value = '正在上传图片'
      target.value = await uploadBannerImage(props.user.id, target.value.id, pendingFile.value, target.value.revision)
      resetImage()
    } else if (removingImage.value && target.value.image_url) {
      saveStage.value = '正在移除图片'
      target.value = await clearBannerImage(props.user.id, target.value.id, target.value.revision)
      resetImage()
    }
    if (target.value.is_visible !== body.is_visible) {
      saveStage.value = '正在更新展示状态'
      target.value = await updateBanner(props.user.id, target.value.id, { ...body, revision: target.value.revision })
    }
    notice.value = body.is_visible ? 'Banner 已保存，小程序重新进入首页或下拉刷新即可看到' : 'Banner 已保存为下线状态'
    dialog.value = false
    await load()
  } catch (cause) {
    recovery.capture(cause)
    formError.value = (savedCopy ? '文案已保存，' + (saveStage.value === '正在上传图片' ? '图片尚未上传成功；选中的图片已保留，可重试。' : '其余更改未完成。') : '') + message(cause)
    if (savedCopy) await load()
  } finally { busy.value = false; saveStage.value = '' }
}
function pickFile() { if (!busy.value && !checking.value) fileInput.value?.click() }
async function onFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || busy.value) return
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) { formError.value = '请选择 JPG、PNG 或 WebP 图片'; return }
  if (!file.size || file.size > 2 * 1024 * 1024) { formError.value = '图片需大于 0 且不超过 2 MB'; return }
  const current = ++imageSequence
  checking.value = true; formError.value = ''
  const url = URL.createObjectURL(file)
  try {
    const dimensions = await new Promise<{ width: number; height: number }>((resolve, reject) => {
      const image = new Image()
      image.onload = () => resolve({ width: image.naturalWidth, height: image.naturalHeight })
      image.onerror = () => reject(new Error('图片无法读取，请换一张'))
      image.src = url
    })
    if (current !== imageSequence) { URL.revokeObjectURL(url); return }
    if (dimensions.width > 2400 || dimensions.height > 1600) throw new Error('图片尺寸不能超过 2400 × 1600，请先缩小图片')
    resetImage(); pendingFile.value = file; localPreview.value = url
    imageSize.value = dimensions.width + ' × ' + dimensions.height + ' · ' + fileSize(file.size)
  } catch (cause) {
    URL.revokeObjectURL(url)
    if (current === imageSequence) formError.value = message(cause)
  } finally { if (current === imageSequence) checking.value = false }
}
function removeImage() { resetImage(); removingImage.value = !!target.value?.image_url }
async function toggleVisible(item: Banner) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    await updateBanner(props.user.id, item.id, { revision: item.revision, kicker: item.kicker, title: item.title, subtitle: item.subtitle, action_label: item.action_label, target_type: item.target_type, target_value: item.target_value, image_fit: item.image_fit, sort_order: item.sort_order, is_visible: !item.is_visible })
    notice.value = item.is_visible ? 'Banner 已下线' : 'Banner 已上线'
    await load()
  } catch (cause) { error.value = message(cause) }
  finally { busy.value = false }
}
function askRemove(item: Banner) { removing.value = item; removeOpen.value = true }
async function confirmRemove() {
  if (!removing.value || busy.value) return
  busy.value = true; error.value = ''
  try {
    await deleteBanner(props.user.id, removing.value.id, removing.value.revision)
    removeOpen.value = false; notice.value = 'Banner 已删除'; await load()
  } catch (cause) { error.value = message(cause); removeOpen.value = false }
  finally { busy.value = false }
}
watch(dialog, open => { if (!open) { imageSequence++; checking.value = false; resetImage() } })
onActivated(load)
onDeactivated(() => { sequence++; imageSequence++; loading.value = false; checking.value = false; dialog.value = false; removeOpen.value = false; resetImage() })
onBeforeUnmount(() => { sequence++; imageSequence++; resetImage() })
const draft = useDialogDraft(dialog, () => [form.value, pendingFile.value?.name, pendingFile.value?.lastModified, removingImage.value], busy, '首页推荐图')
</script>

<template>
  <section class="admin-section" aria-label="首页 Banner 管理">
    <div class="section-toolbar banner-toolbar"><div class="banner-summary"><strong>首页轮播</strong><UBadge :color="homeSettings?.banner_mode === 'operations' ? 'success' : 'neutral'" variant="soft">{{ homeSettings?.banner_mode === 'operations' ? shown + ' 张已启用' : '欢迎卡模式' }}</UBadge></div><div class="actions-row"><USwitch :model-value="homeSettings?.banner_mode === 'operations'" label="启用运营 Banner" :disabled="busy || loading || !homeSettings" @update:model-value="changeMode" /><UButton icon="i-lucide-refresh-cw" color="neutral" variant="ghost" aria-label="刷新 Banner" :loading="loading" :disabled="busy" @click="load" /><UButton icon="i-lucide-image-plus" label="新建 Banner" :disabled="busy" @click="create" /></div></div>
    <div class="banner-guide"><UIcon name="i-lucide-info" class="size-4" /><span>推荐图片 <strong>1200 × 500</strong>（12:5），支持 JPG / PNG / WebP，最大 2 MB。上传前可查看手机效果，选择完整展示或居中裁切。</span></div>
    <UAlert v-if="error" :title="error" color="error" variant="soft" class="notice" />
    <UAlert v-if="notice" :title="notice" color="success" variant="soft" close class="notice" @update:open="notice = ''" />
    <div v-if="items.length" class="banner-gallery" :aria-busy="loading">
      <article v-for="item in items" :key="item.id" class="banner-item" :aria-label="item.title">
        <div class="banner-item-head"><UBadge :color="item.is_visible && homeSettings?.banner_mode === 'operations' ? 'success' : 'neutral'" variant="soft">{{ !item.is_visible ? '已下线' : homeSettings?.banner_mode === 'operations' ? '展示中' : '待启用运营模式' }}</UBadge><span>顺序 {{ item.sort_order }}</span></div>
        <BannerPreview :content="item" :image-url="item.image_url ? bannerImageUrl(item.id, item.revision) : ''" />
        <div class="banner-item-info"><span>{{ targetText(item) }}</span><span>{{ item.image_url ? (item.image_fit === 'cover' ? '居中裁切' : '完整展示') : '文字卡片' }}</span></div>
        <div class="banner-item-actions"><UButton icon="i-lucide-pencil" label="编辑 / 换图" color="neutral" variant="outline" :aria-label="'编辑 ' + item.title" :disabled="busy" @click="edit(item)" /><div class="actions-row"><UButton :icon="item.is_visible ? 'i-lucide-eye-off' : 'i-lucide-eye'" :label="item.is_visible ? '下线' : '上线'" color="neutral" variant="ghost" :aria-label="(item.is_visible ? '下线 ' : '上线 ') + item.title" :disabled="busy" @click="toggleVisible(item)" /><UButton icon="i-lucide-trash-2" color="error" variant="ghost" :aria-label="'删除 ' + item.title" :disabled="busy" @click="askRemove(item)" /></div></div>
        <span class="banner-updated">更新于 {{ date(item.updated_at) }}</span>
      </article>
    </div>
    <div v-else class="empty-state banner-empty"><UIcon :name="loading ? 'i-lucide-loader-circle' : 'i-lucide-image-plus'" class="size-9" :class="{ 'animate-spin': loading }" /><h3>{{ loading ? '正在加载' : '用一张图片，介绍你的好内容' }}</h3><p v-if="!loading">尚未配置 Banner 时，首页展示简洁的选题入口。</p><UButton v-if="!loading" icon="i-lucide-upload" label="上传第一张 Banner" @click="create" /></div>

    <UModal v-model:open="draft.model.value" :title="target ? '编辑 Banner' : '新建 Banner'" description="先选图、看效果，再保存到首页。" :dismissible="!busy && !checking" :close="!busy && !checking" :ui="{ content: 'max-w-5xl' }">
      <template #body>
        <form id="banner-form" class="banner-editor" @submit.prevent="save">
          <div class="banner-fields">
            <div class="editor-section"><h3><span>1</span>选择图片</h3><div class="upload-area">
              <UIcon name="i-lucide-image-up" class="upload-symbol" /><div class="upload-copy"><strong>{{ pendingFile ? pendingFile.name : target?.image_url && !removingImage ? '已设置图片，可直接更换' : '从电脑上传 Banner 图片' }}</strong><span>{{ imageSize || (target?.image_bytes && !removingImage ? fileSize(target.image_bytes) : '推荐 1200 × 500，最大 2 MB') }}</span></div>
              <UButton icon="i-lucide-upload" :label="previewUrl ? '更换图片' : '选择图片'" :loading="checking" :disabled="busy || checking" @click="pickFile" />
            </div><input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp" class="sr-only" aria-label="选择 Banner 图片" @change="onFile" />
              <div class="image-choices"><UButton v-if="previewUrl" label="移除图片" icon="i-lucide-x" color="neutral" variant="ghost" size="xs" :disabled="busy || checking" @click="removeImage" /><UButton v-if="pendingFile || removingImage" :label="removingImage ? '撤销移除' : '撤销换图'" color="neutral" variant="ghost" size="xs" :disabled="busy || checking" @click="resetImage" /><span v-if="pendingFile || removingImage" class="draft-indicator">保存后生效</span><span v-else class="image-note">无图时使用文字卡片</span></div>
              <fieldset class="fit-options" :disabled="busy"><legend>图片如何显示</legend><label :class="{ selected: form.image_fit === 'contain' }"><input v-model="form.image_fit" type="radio" value="contain" name="banner-fit" /><span><strong>完整展示</strong><small>保留整张图，适合有文字的海报</small></span></label><label :class="{ selected: form.image_fit === 'cover' }"><input v-model="form.image_fit" type="radio" value="cover" name="banner-fit" /><span><strong>居中裁切</strong><small>铺满图片框，适合照片和插画</small></span></label></fieldset>
            </div>
            <div class="editor-section field-stack"><h3><span>2</span>填写文案</h3>
              <UFormField label="标题" required hint="建议 6–14 字"><UInput v-model="form.title" aria-label="Banner 标题" maxlength="40" placeholder="例如：新学期，练好每一课" :disabled="busy" required class="w-full" /></UFormField>
              <UFormField label="副标题" hint="可不填"><UInput v-model="form.subtitle" aria-label="Banner 副标题" maxlength="60" placeholder="补充一句内容介绍" :disabled="busy" class="w-full" /></UFormField>
              <UFormField label="上方小字" hint="可不填"><UInput v-model="form.kicker" aria-label="Banner 上方小字" maxlength="40" placeholder="例如：新学期精选" :disabled="busy" class="w-full" /></UFormField>
            </div>
            <div class="editor-section field-stack"><h3><span>3</span>设置点击去向</h3>
              <UFormField label="点击后"><USelect :model-value="form.target_type" :items="targetOptions" aria-label="Banner 跳转方式" :disabled="busy" class="w-full" @update:model-value="changeTarget" /></UFormField>
              <UFormField v-if="form.target_type === 'category'" label="目标分类" required><USelect v-model="form.target_value" :items="categoryOptions" placeholder="选择分类" :disabled="busy" class="w-full" /></UFormField>
              <UFormField v-else-if="form.target_type === 'subject'" label="目标学科" required><USelect v-model="form.target_value" :items="subjectOptions" placeholder="选择学科" :disabled="busy" class="w-full" /></UFormField>
              <UFormField v-else-if="form.target_type === 'keyword'" label="搜索关键词" required><UInput v-model="form.target_value" aria-label="Banner 搜索关键词" maxlength="64" placeholder="例如：阅读" :disabled="busy" class="w-full" /></UFormField>
              <UFormField v-else-if="form.target_type === 'paper'" label="选择习题" required><PublishedPaperPicker :model-value="form.target_value || null" :label="paperLabel" :disabled="busy" @update:model-value="form.target_value = $event || ''" @selected="paperLabel = $event.title" /></UFormField>
              <UFormField v-if="form.target_type !== 'none'" label="按钮文案" hint="建议 2–6 字"><UInput v-model="form.action_label" aria-label="Banner 按钮文案" maxlength="20" placeholder="去看看" :disabled="busy" class="w-full" /></UFormField>
              <div class="publish-options"><UFormField label="展示顺序" hint="数值越小越靠前"><UInput v-model.number="form.sort_order" aria-label="Banner 展示顺序" type="number" min="0" max="100000" :disabled="busy" class="w-full" /></UFormField><USwitch v-model="form.is_visible" label="在首页展示" :disabled="busy" /></div>
            </div>
          </div>
          <aside class="preview-pane"><div class="preview-heading"><UIcon name="i-lucide-smartphone" /><strong>手机效果预览</strong><span>375 px</span></div><div class="phone-preview"><div class="phone-search"><UIcon name="i-lucide-search" /><span>搜知识点、习题名称</span><small>全部年级⌄</small></div><BannerPreview :content="form" :image-url="previewUrl" /><div class="phone-subjects"><span>语文</span><span>数学</span><span>英语</span><span>全部学科</span></div></div><p class="preview-help">图片在上、文案在下，保持图片本身的颜色。含文字的海报建议选「完整展示」，避免裁掉信息。</p><p v-if="removingImage" class="preview-pending">保存后将移除原图，改为文字卡片。</p><p v-else-if="pendingFile" class="preview-pending">当前预览为待保存图片。</p></aside>
        </form>
      </template>
      <template #footer><div class="editor-footer"><UButton v-if="recovery.conflict.value" label="载入最新并保留我的修改" :loading="recovery.recovering.value" @click="recovery.reload" /><UAlert v-if="formError" :title="formError" color="error" variant="soft" class="editor-error" /><div class="footer-actions"><span class="save-stage" role="status">{{ saveStage || '图片、文案与展示状态将在保存后生效' }}</span><UButton label="取消" color="neutral" variant="outline" :disabled="busy || checking" @click="draft.setOpen(false)" /><UButton type="submit" form="banner-form" label="保存 Banner" icon="i-lucide-check" :loading="busy" :disabled="busy || checking || !canSave" /></div></div></template>
    </UModal>

    <UModal v-model:open="removeOpen" title="删除 Banner" :dismissible="!busy" :close="!busy"><template #body><p>确认删除「{{ removing?.title }}」？配图会一并删除。</p></template><template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="busy" @click="removeOpen = false" /><UButton label="确认删除" color="error" icon="i-lucide-trash-2" :loading="busy" :disabled="busy" @click="confirmRemove" /></template></UModal>
  </section>
</template>

<style scoped>
.banner-toolbar { align-items: flex-start; gap: 18px; }
.banner-summary { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
.banner-summary strong { font-size: 18px; font-weight: 600; }
.section-hint { margin: 0; max-width: 660px; color: var(--ui-text-muted); font-size: 12px; line-height: 1.7; }
.banner-guide { display: flex; align-items: center; gap: 9px; padding: 13px 16px; margin-bottom: 22px; border: 1px solid #e1e9e3; border-radius: 10px; background: #f6f9f5; font-size: 12px; color: #647568; line-height: 1.8; }
.banner-guide > span:first-child { flex: none; }
.banner-gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(305px, 1fr)); gap: 20px; }
.banner-item { min-width: 0; padding: 16px; border: 1px solid var(--ui-border); border-radius: 14px; background: var(--ui-bg); }
.banner-item-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 13px; font-size: 11px; color: var(--ui-text-muted); }
.banner-item-info { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin: 14px 0; font-size: 11px; color: var(--ui-text-muted); }
.banner-item-info > span { min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.banner-item-actions { display: flex; justify-content: space-between; gap: 8px; }
.banner-item-actions .actions-row { gap: 2px; }
.banner-updated { display: block; margin-top: 12px; font-size: 10px; color: var(--ui-text-dimmed); }
.banner-empty { min-height: 310px; border: 1px dashed var(--ui-border); border-radius: 14px; }
.banner-empty p { margin: 8px 0 20px; font-size: 12px; }
.banner-editor { display: grid; grid-template-columns: minmax(0, 1fr) 375px; gap: 30px; align-items: start; }
.banner-fields { min-width: 0; }
.editor-section { margin-bottom: 26px; padding-bottom: 24px; border-bottom: 1px solid var(--ui-border-muted); }
.editor-section:last-child { margin-bottom: 0; padding-bottom: 0; border-bottom: 0; }
.editor-section h3 { display: flex; align-items: center; gap: 9px; margin: 0 0 16px; font-size: 14px; font-weight: 600; }
.editor-section h3 > span { display: flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 7px; background: #eaf3eb; color: #307e61; font-size: 11px; }
.upload-area { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 16px; border: 1px dashed #bacabd; border-radius: 11px; background: #f8faf7; }
.upload-symbol { flex: none; font-size: 27px; color: #73967a; }
.upload-copy { display: flex; flex: 1; min-width: 140px; flex-direction: column; gap: 4px; font-size: 12px; }
.upload-copy strong { word-break: break-all; font-weight: 500; }
.upload-copy span { font-size: 11px; color: var(--ui-text-muted); }
.image-choices { display: flex; align-items: center; gap: 3px; min-height: 38px; margin-top: 4px; }
.draft-indicator, .image-note { font-size: 11px; color: var(--ui-text-muted); }
.draft-indicator { margin-left: auto; color: #98762f; }
.fit-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 8px; }
.fit-options legend { margin-bottom: 8px; color: var(--ui-text-toned); font-size: 12px; }
.fit-options label { display: flex; align-items: flex-start; gap: 7px; padding: 11px; border: 1px solid var(--ui-border); border-radius: 9px; cursor: pointer; }
.fit-options label.selected { border-color: #78a384; background: #f2f8f0; }
.fit-options input { margin-top: 3px; accent-color: #307e61; }
.fit-options strong { display: block; font-size: 12px; font-weight: 500; }
.fit-options small { display: block; margin-top: 4px; font-size: 10px; line-height: 1.7; color: var(--ui-text-muted); }
.publish-options { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 20px; padding-top: 6px; }
.preview-pane { position: sticky; top: 0; }
.preview-heading { display: flex; align-items: center; gap: 7px; margin-bottom: 12px; font-size: 12px; color: var(--ui-text-muted); }
.preview-heading strong { font-weight: 500; color: var(--ui-text-toned); }
.preview-heading > span:last-child { margin-left: auto; font-size: 10px; }
.phone-preview { width: 375px; max-width: 100%; padding: 20px; border: 1px solid #e1e7de; border-radius: 23px; background: #f7f9f6; }
.phone-search { display: flex; align-items: center; gap: 6px; height: 37px; margin-bottom: 16px; padding: 0 10px; border: 1px solid #e3eae2; border-radius: 11px; background: #fff; font-size: 10px; color: #7c8a7e; }
.phone-search small { margin-left: auto; font-size: 10px; }
.phone-subjects { display: grid; grid-template-columns: repeat(4, 1fr); gap: 11px; text-align: center; margin-top: 17px; font-size: 10px; color: #657764; }
.phone-subjects > span { padding: 13px 0; border-radius: 10px; background: #e9eee4; }
.phone-subjects > span:first-child { background: #f8e9e2; }.phone-subjects > span:nth-child(2) { background: #e9effb; }.phone-subjects > span:nth-child(3) { background: #e9f4eb; }
.preview-help { margin: 14px 6px 0; font-size: 11px; line-height: 1.8; color: var(--ui-text-muted); }
.preview-pending { margin: 10px 6px; color: #98762f; font-size: 11px; }
.editor-footer { width: 100%; }
.editor-error { margin-bottom: 12px; }
.footer-actions { display: flex; align-items: center; justify-content: flex-end; gap: 10px; }
.save-stage { flex: 1; font-size: 11px; color: var(--ui-text-muted); }
@media (max-width: 900px) { .banner-editor { grid-template-columns: minmax(0, 1fr); } .preview-pane { position: static; grid-row: 1; } .phone-preview { margin: 0 auto; } .preview-help { text-align: center; } }
@media (max-width: 500px) { .banner-gallery { grid-template-columns: minmax(0, 1fr); } .banner-toolbar { flex-direction: column; } .fit-options { grid-template-columns: minmax(0, 1fr); } .save-stage { display: none; } }
</style>
