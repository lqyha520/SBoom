<script setup lang="ts">
import { permissionDirective as vPermission, canAdmin } from '../permissions'
import '../xhs-workflow.css'
import XhsAssetThumbnail from './XhsAssetThumbnail.vue'
import XhsDraftRecovery from './XhsDraftRecovery.vue'
import type { UserInfo } from '../api'
import { useXhsDraftBackup } from '../xhs-draft-backup'
import { useXhsAssetUploads } from '../xhs-asset-uploads'
import { useBeforeUnload } from '../unsaved'
import { computed, onActivated, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { downloadBlob } from '../../../shared/download'
import { adminRoute, useAdminLeaveGuard } from '../navigation'
import { draftImages } from '../xhs-content-export'
import { newDraft, workflowError } from '../xhs-workflow'
import { assetBlob, assetPreview, assetDefaults, assetFileName, assetRights, deleteAsset, listAssets, saveAsset, saveCoverTemplate, type Asset, type AssetMetadata, type CoverTemplate } from '../xhs-workspace'
const props = defineProps<{ user?: Pick<UserInfo, 'id'>; picker?: 'media' | 'template' }>()
const emit = defineEmits<{ choose: [assets: Asset[]] }>()
const uploadInput = ref<HTMLInputElement | null>(null)
const items = ref<Asset[]>([]), total = ref(0), used = ref(0), q = ref(''), kind = ref(props.picker === 'template' ? 'template' : 'all'), page = ref(1), archived = ref(false)
const loading = ref(false), busy = ref(false), error = ref(''), notice = ref(''), selected = ref<Asset | null>(null), editing = ref(false), baseline = ref('')
const metadata = ref<AssetMetadata>(assetDefaults()), tags = ref(''), chosen = ref<Asset[]>([]), preview = ref<{ url: string; type: string; title: string } | null>(null)
const template = ref<CoverTemplate>({ theme: 'green', cover_title: '', cover_subtitle: '', cards: [] })
const state = () => JSON.stringify([metadata.value, tags.value, template.value])
const dirty = computed(() => editing.value && state() !== baseline.value)
const visible = computed(() => items.value.filter(item => props.picker !== 'media' || !item.template))
const backup = useXhsDraftBackup({ adminId: props.user?.id || 0, scope: () => `assets:${selected.value?.id || 'new'}`, enabled: () => !props.picker && !!props.user && editing.value,
  dirty: () => dirty.value, snapshot: () => ({ metadata: metadata.value, tags: tags.value, template: template.value }), revision: () => String(selected.value?.revision || 0),
  restore: value => { metadata.value = value.metadata; tags.value = value.tags; template.value = value.template } })
const batch = useXhsAssetUploads(async rows => { await load(); if (rows.length === 1 && rows[0]?.asset) edit(rows[0].asset) })
const { rows: uploads, uploading, stopped: uploadStopped, error: uploadError } = batch
useBeforeUnload(uploading)
useAdminLeaveGuard(() => {
  if (props.picker !== undefined || adminRoute.tab !== 'xhsAssets') return true
  if (uploading.value) { error.value = '本批正在上传，请停止后续上传并等待当前文件完成。'; return false }
  backup.persist(); return !dirty.value || window.confirm('素材资料尚未保存，确定离开？本机备份可在再次编辑此素材时取回。')
})
let sequence = 0
async function load() { const seq = ++sequence; loading.value = true; try { const result = await listAssets(q.value, kind.value==='all' ? (props.picker==='media' ? 'media' : '') : kind.value, archived.value, page.value); if (seq === sequence) { items.value = result.items; total.value = result.total; used.value = result.used_bytes; if (page.value > Math.max(1, Math.ceil(result.total / 20))) page.value = Math.max(1, Math.ceil(result.total / 20)) } } catch (cause) { if (seq === sequence) error.value = workflowError(cause) } finally { if (seq === sequence) loading.value = false } }
function edit(item: Asset | null) { selected.value = item; metadata.value = item ? JSON.parse(JSON.stringify(item.data)) : assetDefaults(); tags.value = metadata.value.tags.join('，'); template.value = item?.template ? JSON.parse(JSON.stringify(item.template)) : { theme: 'green', cover_title: '', cover_subtitle: '', cards: [] }; baseline.value = state(); editing.value = true; error.value = '' }
function closeEditor() { if (!busy.value && (!dirty.value || window.confirm('放弃未保存的素材资料？'))) editing.value = false }
async function upload(event: Event) {
  const input = event.target as HTMLInputElement, files = Array.from(input.files || []); input.value = ''
  if (files.length && !busy.value) await batch.choose(files)
}

async function save() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    const data = { ...metadata.value, tags: [...new Set(tags.value.split(/[,，\n]/).map(tag => tag.trim()).filter(Boolean))] }
    if (!data.title.trim()) throw new Error('请填写素材名称。')
    if (selected.value) await saveAsset(selected.value, data)
    else await saveCoverTemplate(data, template.value)
    backup.clear(); editing.value = false; notice.value = '素材资料已保存。'; await load()
  } catch (cause) { error.value = workflowError(cause) } finally { busy.value = false }
}
async function archive(item: Asset) { if (busy.value) return; busy.value = true; error.value = ''; try { await saveAsset(item, { ...item.data, archived: !item.data.archived }); chosen.value = chosen.value.filter(value => value.id !== item.id); await load() } catch (cause) { error.value = workflowError(cause) } finally { busy.value = false } }
async function remove(item: Asset) { if (busy.value || !window.confirm(`永久删除“${item.data.title}”？请先下载备份，删除后无法从素材库恢复。已导出的文件与已应用的模板快照不受影响。`)) return; busy.value = true; try { await deleteAsset(item); await load() } catch (cause) { error.value = workflowError(cause) } finally { busy.value = false } }
function clearPreview() { if (preview.value) URL.revokeObjectURL(preview.value.url); preview.value = null }
async function show(item: Asset) { busy.value = true; error.value = ''; try { const blob = item.template ? (await draftImages({ ...newDraft(), ...item.template }))[0]! : await (canAdmin('xhsAssets', 'export') ? assetBlob(item) : assetPreview(item)); clearPreview(); preview.value = { url: URL.createObjectURL(blob), type: item.template ? 'image/png' : blob.type || item.media_type, title: item.data.title } } catch (cause) { error.value = workflowError(cause) } finally { busy.value = false } }
async function download(item: Asset) { busy.value = true; try { downloadBlob(item.template ? new Blob([JSON.stringify(item.template, null, 2)], { type: 'application/json' }) : await assetBlob(item), item.template ? item.data.title + '.json' : assetFileName(item)) } catch (cause) { error.value = workflowError(cause) } finally { busy.value = false } }
function toggle(item: Asset) { if (item.data.archived || item.data.rights === 'unknown') return; if (props.picker === 'template') { emit('choose', [item]); return }; const index = chosen.value.findIndex(value => value.id === item.id); if (index >= 0) chosen.value.splice(index, 1); else if (chosen.value.length < 9) chosen.value.push(item) }
watch([kind, archived], () => { chosen.value = []; if (page.value !== 1) page.value = 1; else void load() }); watch(page, load)
onMounted(load); onActivated(() => { if (!loading.value) void load() }); onBeforeUnmount(() => { ++sequence; clearPreview() })
</script>
<template><section class="xhs-assets xhs-workflow" :class="{'admin-section':!picker}" aria-label="素材库"><header class="workflow-heading"><div><h2>{{ picker ? '选择素材' : '素材库' }}</h2><p>图片、MP4 和封面模板集中保存。来源待核实的素材可预览，核实后再选用。</p></div><div v-if="!picker" class="workflow-actions"><UButton v-permission="'xhsAssets:create'" label="上传图片 / 视频" icon="i-lucide-upload" :loading="uploading" :disabled="busy || uploading" @click="uploadInput?.click()" /><input v-permission="'xhsAssets:create'" ref="uploadInput" class="sr-only" type="file" accept="image/png,image/jpeg,image/webp,video/mp4" multiple aria-label="上传素材文件" :disabled="busy || uploading" @change="upload" /><UButton v-permission="'xhsAssets:create'" label="新建封面模板" :disabled="busy" @click="edit(null)" /></div></header>
<UAlert v-if="error" :title="error" color="error" role="alert" /><UAlert v-if="notice" :title="notice" color="success" /><UAlert v-if="uploadError" :title="uploadError" color="error" />
<div v-if="uploads.length" class="workflow-step upload-results"><p>每批最多 20 个文件／200 MB，逐个上传。文件上传成功后仍需补充来源与授权。{{ uploadStopped?'已停止后续上传。':'' }}</p><div class="workflow-actions"><UButton v-if="uploading" label="停止后续上传" variant="outline" @click="batch.stop" /><UButton v-permission="'xhsAssets:create'" v-else-if="uploads.some(row=>row.status==='failed'||row.status==='pending')" label="重试失败或未上传文件" variant="outline" @click="batch.run(true)" /></div><ul aria-label="本批上传结果"><li v-for="(row,index) in uploads" :key="index"><strong>{{ row.file.name }}</strong><span>{{ row.status==='pending'?'等待上传':row.status==='uploading'?'正在上传':row.message }}</span><UButton v-permission="'xhsAssets:update'" v-if="row.asset && !uploading" label="编辑来源" size="xs" variant="link" @click="edit(row.asset)" /></li></ul></div>
<form class="workflow-actions asset-search my-4" @submit.prevent="page=1;load()"><UInput v-model="q" class="asset-query" aria-label="搜索素材" placeholder="搜索名称或标签" maxlength="120" /><USelect v-if="picker!=='template'" v-model="kind" class="asset-type" aria-label="素材类型" :items="[{value:'all',label:'全部类型'},{value:'image',label:'图片'},{value:'video',label:'视频'},...(!picker?[{value:'template',label:'封面模板'}]:[])]" /><UCheckbox v-if="!picker" v-model="archived" label="查看归档素材" /><UButton label="搜索素材" type="submit" variant="outline" :loading="loading" /></form><p v-if="!picker" class="workflow-hint">已用 {{ (used/1024/1024).toFixed(1) }} / 500 MB · 图片 ≤10 MB，视频 ≤40 MB。归档保留原文件；归档后可下载或永久删除以释放空间。</p>
<div class="asset-grid"><article v-for="item in visible" :key="item.id" :aria-label="'素材 '+item.data.title"><XhsAssetThumbnail :asset="item" /><div class="asset-kind"><UIcon :name="item.template?'i-lucide-layout-template':item.media_type.startsWith('video/')?'i-lucide-video':'i-lucide-image'" class="size-8" /><span>{{ item.template?'封面模板':item.media_type.startsWith('video/')?'MP4 视频':'图片' }} · {{ (item.size_bytes/1024).toFixed(0) }} KB</span></div><h3>{{ item.data.title }}</h3><p>{{ item.data.tags.join(' · ') || '未设置标签' }}</p><p>{{ assetRights[item.data.rights] }}</p><small v-if="item.data.source">{{ item.data.source }}</small><div class="workflow-actions"><UButton label="预览" size="sm" variant="outline" :disabled="busy" @click="show(item)" /><UButton v-if="picker" :label="chosen.some(value=>value.id===item.id)?'取消选择':'选用素材'" size="sm" :disabled="busy || item.data.rights==='unknown' || item.data.archived" @click="toggle(item)" /><template v-else><UButton v-permission="'xhsAssets:update'" label="编辑来源" size="sm" variant="ghost" @click="edit(item)" /><UButton v-permission="'xhsAssets:export'" label="下载" size="sm" variant="ghost" :disabled="busy" @click="download(item)" /><UButton v-permission="'xhsAssets:update'" :label="item.data.archived?'恢复':'归档'" size="sm" variant="ghost" :disabled="busy" @click="archive(item)" /><UButton v-permission="'xhsAssets:delete'" v-if="item.data.archived" label="永久删除" size="sm" color="error" variant="ghost" :disabled="busy" @click="remove(item)" /></template></div></article></div><p v-if="!loading && !visible.length" class="workflow-empty">没有符合条件的素材。{{ picker?'可到素材库上传文件并核实来源。':'先上传原创图片或视频，也可保存封面模板。' }}</p><UPagination v-if="total>20" v-model:page="page" :total="total" :items-per-page="20" />
<div v-if="picker==='media'" class="workflow-actions my-4"><span>按选择顺序使用：{{ chosen.map(item=>item.data.title).join(' → ') || '尚未选择' }}</span><UButton label="使用所选素材" :disabled="!chosen.length || busy" @click="emit('choose',chosen.slice())" /></div>
<UModal :open="editing" :title="selected?'编辑素材资料':'新建封面模板'" @update:open="value=>{if(!value)closeEditor()}"><template #body><XhsDraftRecovery :backup="backup" /><div class="workflow-editor" :inert="busy || !!backup.recovery.value"><label class="workflow-field"><span>素材名称</span><UInput v-model="metadata.title" aria-label="素材名称" maxlength="120" /></label><label class="workflow-field"><span>标签（逗号分隔）</span><UInput v-model="tags" aria-label="素材标签" maxlength="600" /></label><label class="workflow-field"><span>来源状态</span><USelect v-model="metadata.rights" aria-label="素材来源状态" :items="Object.entries(assetRights).map(([value,label])=>({value,label}))" /></label><label class="workflow-field"><span>来源与授权依据</span><UTextarea v-model="metadata.source" aria-label="素材授权依据" :rows="3" maxlength="2000" placeholder="记录原创说明、授权方或授权文件位置" /></label><label class="workflow-field"><span>备注</span><UTextarea v-model="metadata.notes" :rows="2" maxlength="2000" /></label><template v-if="!selected"><label class="workflow-field"><span>封面标题</span><UInput v-model="template.cover_title" aria-label="模板封面标题" maxlength="40" /></label><label class="workflow-field"><span>封面副标题</span><UInput v-model="template.cover_subtitle" maxlength="120" /></label><USelect v-model="template.theme" aria-label="模板配色" :items="[{value:'green',label:'清新绿'},{value:'orange',label:'暖橙'},{value:'blue',label:'学习蓝'}]" /></template><UAlert v-if="error" :title="error" color="error" /></div></template><template #footer><UButton label="取消" variant="outline" :disabled="busy" @click="closeEditor" /><UButton v-permission="'xhsAssets:' + (selected ? 'update' : 'create')" label="保存素材资料" :loading="busy" :disabled="!!backup.recovery.value" @click="save" /></template></UModal>
<UModal :open="!!preview" :title="preview?.title || '素材预览'" @update:open="value=>{if(!value)clearPreview()}"><template #body><video v-if="preview?.type==='video/mp4'" :src="preview.url" controls class="asset-preview" /><img v-else-if="preview" :src="preview.url" :alt="preview.title" class="asset-preview" /></template></UModal></section></template>
<style scoped>.asset-search :deep(.asset-query){width:min(100%,280px)}.asset-search :deep(.asset-type){width:160px}.asset-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,260px),1fr));gap:16px;margin:20px 0}.asset-grid article{display:grid;align-content:start;gap:12px;padding:20px;background:var(--ui-bg);border:1px solid var(--ui-border);border-radius:14px;min-width:0;overflow-wrap:anywhere}.asset-kind{display:flex;align-items:center;gap:12px;color:var(--ui-primary)}h3{font-weight:650}.asset-grid p,.asset-grid small,.asset-kind span{font-size:12px;color:var(--ui-text-muted)}.asset-preview{max-width:100%;max-height:65vh;margin:auto}.upload-control{display:grid;gap:8px;font-size:13px}.upload-control input{max-width:250px}.xhs-assets{min-width:0}</style>

<style scoped>.upload-results ul{display:grid;gap:10px;margin-top:12px}.upload-results li{display:flex;gap:12px;align-items:center;flex-wrap:wrap;font-size:13px}.upload-results li strong{overflow-wrap:anywhere}.upload-results li span{color:var(--ui-text-muted)}</style>
