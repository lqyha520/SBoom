<script setup lang="ts">
import { permissionDirective as vPermission } from '../permissions'
import { onBeforeUnmount, ref, watch } from 'vue'
import JSZip from 'jszip'
import { downloadBlob } from '../../../shared/download'
import { randomId } from '../../../shared/webcrypto'
import { draftImages } from '../xhs-content-export'
import { validateMedia, type AssistMedia } from '../xhs-publish-assist'
import { cachePublicationFile, readPublicationFile, type PublicationMedia } from '../xhs-media-cache'
import { assetBlob, assetFileName, getAsset, type Asset } from '../xhs-workspace'
import { workflowError, type DraftData } from '../xhs-workflow'
import XhsAssets from './XhsAssets.vue'

const props = defineProps<{ owner: number; references?: PublicationMedia[]; draft?: DraftData; disabled?: boolean }>()
const media = defineModel<AssistMedia[]>({ required: true })
const emit = defineEmits<{ change: [references: PublicationMedia[]]; availability: [ready: boolean] }>()
const libraryOpen = ref(false), busy = ref(false), error = ref(''), cacheNotice = ref(''), caching = ref(false)
const missing = ref<PublicationMedia[]>([])
let active = true, sequence = 0
function clear() { media.value.forEach(item => URL.revokeObjectURL(item.url)); media.value = [] }
function replace(files: File[], assets = new Map<File, string>()) {
  if (files.length) validateMedia(files)
  error.value = ''; missing.value = []
  const previous = new Map(media.value.map(item => [item.file, item]))
  const retained = new Set(files)
  media.value.forEach(item => { if (!retained.has(item.file)) URL.revokeObjectURL(item.url) })
  const next = files.map(file => previous.get(file) || ({ file, url: URL.createObjectURL(file), reference: {
    id: randomId(), asset_id: assets.get(file) || '', name: file.name.slice(0, 255), media_type: file.type,
    size_bytes: file.size, last_modified: file.lastModified,
  } }))
  media.value = next
  emit('change', next.map(item => item.reference!))
  emit('availability', true)
  const snapshot = next, owner = props.owner, seq = sequence
  const uncached = snapshot.filter(item => !item.reference!.asset_id && !previous.has(item.file))
  if (!uncached.length) return
  cacheNotice.value = '正在将配图暂存到本机…'
  caching.value = true
  void (async () => {
    try {
      for (const item of uncached) await cachePublicationFile(owner, item.reference!, item.file, snapshot.map(value => value.reference!.id))
      if (active && seq === sequence) cacheNotice.value = '配图已暂存到本机；保存草稿后可在本浏览器恢复。'
    } catch { if (active && seq === sequence) cacheNotice.value = '本机配图暂存失败，请先下载备份；刷新后需要重新选择。' }
    finally { if (active && seq === sequence) caching.value = false }
  })()
}
async function restore() {
  const seq = ++sequence, references = props.references || [], owner = props.owner
  busy.value = true; error.value = ''; cacheNotice.value = ''; missing.value = []; emit('availability', false)
  const loaded: AssistMedia[] = [], unavailable: PublicationMedia[] = []
  let accepted = false
  caching.value = false
  clear()
  try {
    for (const reference of references) {
      let file: File | null = null
      try {
        if (reference.asset_id) {
          const asset = await getAsset(reference.asset_id)
          if (asset.data.archived || asset.data.rights === 'unknown') throw new Error('素材来源尚未核实或已归档')
          const blob = await assetBlob(asset)
          if (blob.size !== reference.size_bytes || blob.type !== reference.media_type) throw new Error('素材信息不符')
          file = new File([blob], reference.name, { type: reference.media_type, lastModified: reference.last_modified })
        } else file = await readPublicationFile(owner, reference)
        if (!file) throw new Error('本机文件已清理或来自其他设备')
        if (!active || seq !== sequence) return
        loaded.push({ file, reference, url: URL.createObjectURL(file) })
      } catch { unavailable.push(reference) }
      if (!active || seq !== sequence) return
    }
    if (loaded.length) validateMedia(loaded.map(item => item.file))
    media.value = loaded; missing.value = unavailable; accepted = true
    emit('availability', unavailable.length === 0)
  } catch (cause) { if (active && seq === sequence) { error.value = workflowError(cause); missing.value = references } }
  finally {
    if (!accepted) loaded.forEach(item => URL.revokeObjectURL(item.url))
    if (active && seq === sequence) busy.value = false
  }
}
watch(() => [props.owner, JSON.stringify(props.references || [])] as const, ([owner, references], previous) => {
  if (owner !== previous?.[0] || references !== JSON.stringify(media.value.map(item => item.reference)) || missing.value.length) void restore()
}, { immediate: true })
function select(event: Event) {
  const input = event.target as HTMLInputElement, files = Array.from(input.files || [])
  input.value = ''
  if (!files.length || props.disabled || busy.value || caching.value || missing.value.length) return
  try { replace([...media.value.map(item => item.file), ...files]) } catch (cause) { error.value = workflowError(cause) }
}
function move(index: number, direction: number) {
  if (props.disabled || busy.value || caching.value) return
  const files = media.value.map(item => item.file), target = index + direction
  if (target < 0 || target >= files.length) return
  files.splice(target, 0, files.splice(index, 1)[0]!); replace(files)
}
function remove(index: number) { if (!props.disabled && !busy.value && !caching.value) replace(media.value.filter((_, i) => i !== index).map(item => item.file)) }
function removeMissing() { if (!props.disabled && !busy.value && !caching.value) replace(media.value.map(item => item.file)) }
async function generate() {
  if (!props.draft || props.disabled || busy.value || caching.value) return
  const seq = ++sequence
  busy.value = true; error.value = ''
  try {
    const images = await draftImages(JSON.parse(JSON.stringify(props.draft)))
    if (active && seq === sequence && !props.disabled) replace(images.map((blob, i) => new File([blob], `${String(i + 1).padStart(2, '0')}.png`, { type: 'image/png' })))
  } catch (cause) { if (active && seq === sequence) error.value = workflowError(cause) }
  finally { if (active && seq === sequence) busy.value = false }
}
async function useLibrary(assets: Asset[]) {
  if (props.disabled || busy.value || caching.value) return
  const seq = ++sequence
  busy.value = true; error.value = ''
  try {
    validateMedia([...media.value.map(item => item.file), ...assets.map(asset => ({ type: asset.media_type, size: asset.size_bytes }))])
    const files: File[] = [], links = new Map<File, string>()
    for (const selected of assets) {
      const asset = await getAsset(selected.id)
      if (asset.data.archived || asset.data.rights === 'unknown') throw new Error('请先核实素材来源并恢复归档素材。')
      const file = new File([await assetBlob(asset)], assetFileName(asset), { type: asset.media_type })
      files.push(file); links.set(file, asset.id)
      if (!active || seq !== sequence) return
    }
    if (active && seq === sequence && !props.disabled) { replace([...media.value.map(item => item.file), ...files], links); libraryOpen.value = false }
  } catch (cause) { if (active && seq === sequence) error.value = workflowError(cause) }
  finally { if (active && seq === sequence) busy.value = false }
}
async function download() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    const zip = new JSZip()
    media.value.forEach((item, i) => zip.file(`${String(i + 1).padStart(2, '0')}-${item.file.name.replace(/[\\/:*?"<>|]/g, '_')}`, item.file))
    downloadBlob(await zip.generateAsync({ type: 'blob' }), '发布配图-解压后按序上传.zip')
  } catch (cause) { error.value = workflowError(cause) } finally { busy.value = false }
}
function beforeUnload(event: BeforeUnloadEvent) { if (busy.value || caching.value) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => { active = false; ++sequence; clear(); window.removeEventListener('beforeunload', beforeUnload) })
defineExpose({ download })
</script>

<template>
  <div class="workflow-card" aria-label="选择发布图片">
    <h3>先选图片 <small v-if="media.length">已选 {{ media.length }} 个文件</small></h3>
    <p class="workflow-hint">第一张是封面。选好后可以调整顺序，再填写下面的标题和正文。</p>
    <fieldset :disabled="disabled || busy || caching || !!missing.length" class="publication-media">
      <label class="media-picker"><UIcon name="i-lucide-image-plus" class="size-7" /><strong>{{ media.length ? '继续添加图片' : '选择本机图片' }}</strong><span>点击下面的“选择文件”，可一次选择多张</span><input type="file" multiple accept="image/png,image/jpeg,image/webp,video/mp4" aria-label="选择图文图片" @change="select" /></label>
      <div class="workflow-actions my-3"><UButton v-permission="'xhsAssets:view'" label="从素材库选择" variant="outline" @click="libraryOpen=true" /><UButton v-if="draft" label="生成关联笔记配图" variant="outline" @click="generate" /></div>
      <p class="workflow-hint">最多 9 张图片，每张 ≤10 MB、合计 ≤30 MB；或 1 个 MP4 ≤40 MB。</p>
      <div class="publication-previews">
        <figure v-for="(item,i) in media" :key="item.url">
          <video v-if="item.file.type==='video/mp4'" :src="item.url" controls preload="metadata" /><img v-else :src="item.url" :alt="'发布图片 '+(i+1)" />
          <figcaption><strong>{{ item.file.type==='video/mp4' ? '视频' : i===0 ? '1 · 封面' : (i+1)+' · 内页' }}</strong><span>{{ item.file.name }}</span></figcaption>
          <div class="workflow-actions"><UButton label="前移" size="xs" :aria-label="'前移图片 '+(i+1)" variant="ghost" :disabled="i===0" @click="move(i,-1)" /><UButton label="后移" size="xs" :aria-label="'后移图片 '+(i+1)" variant="ghost" :disabled="i===media.length-1" @click="move(i,1)" /><UButton label="移除" size="xs" :aria-label="'移除图片 '+(i+1)" variant="ghost" @click="remove(i)" /></div>
        </figure>
      </div>
    </fieldset>
    <p class="workflow-hint mt-3">保存草稿会保留素材引用和顺序；素材库文件可重新读取，本机文件仅在当前浏览器暂存（最多 256 MiB，优先清理旧文件），重要图片请下载备份。</p>
    <p v-if="cacheNotice" role="status" class="workflow-hint">{{ cacheNotice }}</p>
    <div v-if="missing.length" role="alert"><p>以下配图暂时无法恢复：{{ missing.map(item => item.name).join('、') }}。请重试，或移除缺失项后重新选择。</p><UButton label="重试恢复配图" :disabled="busy" @click="restore" /><UButton label="移除缺失配图" :disabled="busy || disabled" @click="removeMissing" /></div>
    <UAlert v-if="error" :title="error" color="error" class="mt-3" />
    <UModal v-model:open="libraryOpen" title="选择发布素材" :dismissible="!busy" :ui="{content:'max-w-5xl'}"><template #body><XhsAssets v-if="libraryOpen" picker="media" @choose="useLibrary" /><UAlert v-if="error" :title="error" color="error" /></template></UModal>
  </div>
</template>

<style scoped>
h3 small { margin-left:10px;font-size:13px;font-weight:400;color:var(--ui-text-muted); }
.publication-media { border:0;padding:0;min-width:0; }
.media-picker { display:flex;flex-direction:column;align-items:center;gap:10px;padding:24px 16px;margin-top:16px;border:2px dashed var(--ui-border);border-radius:12px;background:var(--ui-bg-muted);text-align:center; }
.media-picker:hover { border-color:var(--ui-primary); }
.media-picker:focus-within { outline:2px solid var(--ui-primary);outline-offset:2px; }
.media-picker input { width:100%;max-width:440px;min-height:40px;padding:6px;border:1px solid var(--ui-border);border-radius:8px;background:var(--ui-bg);font-size:14px;cursor:pointer; }
.media-picker input::file-selector-button { margin-right:12px;padding:8px 14px;border:0;border-radius:6px;background:#087955;color:white;cursor:pointer; }
.media-picker span { font-size:13px;color:var(--ui-text-muted); }
.publication-previews { display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px;margin-top:16px; }
.publication-previews figure { min-width:0; }
.publication-previews img,.publication-previews video { width:100%;height:220px;object-fit:contain;background:var(--ui-bg-muted);border-radius:8px; }
figcaption { display:grid;gap:4px;padding:8px 0;font-size:13px;overflow-wrap:anywhere; }
@media(max-width:700px) { .publication-previews { grid-template-columns:repeat(2,minmax(0,1fr));gap:12px; } .publication-previews img,.publication-previews video { height:150px; } .publication-previews .workflow-actions { gap:2px; } }
</style>
