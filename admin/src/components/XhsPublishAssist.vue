<script setup lang="ts">
import { permissionDirective as vPermission, canAdmin } from '../permissions'
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import XhsAssets from './XhsAssets.vue'
import { assetBlob, assetFileName, getAsset, type Asset } from '../xhs-workspace'
import { draftImages } from '../xhs-content-export'
import { listXhsAccounts, type XhsAccount } from '../xhs-accounts'
import { navigateAdmin } from '../navigation'
import { checkPublication, publicationChecks } from '../xhs-publication'
import { getWorkflow, workflowError, type PublicationData, type WorkflowRecord } from '../xhs-workflow'
import { assistRequest, mediaBase64, validateMedia, type AssistMedia, type AssistState } from '../xhs-publish-assist'

const props = defineProps<{ record: WorkflowRecord<PublicationData> | null; dirty: boolean; selectedMedia?: AssistMedia[] }>()
const libraryOpen = ref(false)
const accounts = ref<XhsAccount[]>([]), accountId = ref('')
const chosenAccount = computed(() => accounts.value.find(item => item.id === accountId.value))
const state = ref<AssistState | null>(null), error = ref(''), busy = ref(false)
const localMedia = ref<AssistMedia[]>([]), accountConfirmed = ref(false), mediaConfirmed = ref(false)
const media = computed({ get: () => props.selectedMedia ?? localMedia.value, set: value => { localMedia.value = value } })
let active = true, stateSequence = 0, timer: ReturnType<typeof setTimeout> | undefined
const usable = computed(() => !!props.record && props.record.status === 'ready' && !props.record.data.published_at && !props.dirty && publicationChecks.every(item => props.record!.data[item.key]))
const session = computed(() => state.value?.session)
const matching = computed(() => session.value?.account_id === accountId.value && session.value?.record_id === props.record?.id && session.value?.revision === props.record?.revision)
const working = computed(() => busy.value || !!state.value?.busy)
const canFill = computed(() => usable.value && matching.value && session.value?.browser_open && !session.value.touched && !working.value && media.value.length && accountConfirmed.value && mediaConfirmed.value)
function clearMedia() { localMedia.value.forEach(item => URL.revokeObjectURL(item.url)); localMedia.value = []; mediaConfirmed.value = false }
function stopPolling() { if (timer) clearTimeout(timer); timer = undefined }
function applyState(result: AssistState) {
  if (!active) return
  state.value = result
  stopPolling()
  if (result.busy) timer = setTimeout(() => { void refreshState() }, 1200)
}
async function refreshState() {
  if (!accountId.value) return
  const id = accountId.value, sequence = ++stateSequence
  try { const result = await assistRequest('/publisher/state?account_id='+encodeURIComponent(id)); if (accountId.value === id && sequence === stateSequence) { applyState(result); error.value = '' } }
  catch (cause) { if (active && id === accountId.value && sequence === stateSequence) { error.value = workflowError(cause); stopPolling() } }
}
async function loadAccounts() {
  if (!canAdmin('xhsAccounts')) return
  try {
    const result = await listXhsAccounts()
    if (!active) return
    accounts.value = result.items.filter(item => !item.archived)
    let remembered = ''
    try { remembered = props.record?.data.account_id || localStorage.getItem('xhs-publication-account:'+props.record?.id) || '' } catch { /* 隐私模式下手动选择。 */ }
    if (!accounts.value.some(item => item.id === accountId.value)) accountId.value = accounts.value.some(item => item.id === remembered) ? remembered : accounts.value.length === 1 ? accounts.value[0]!.id : ''
    await refreshState()
  } catch (cause) { if (active) error.value = workflowError(cause) }
}
async function open(fresh = false) {
  if (!usable.value || working.value || !props.record || !chosenAccount.value) return
  if (fresh && !window.confirm('请先检查旧窗口以及小红书草稿和已发布笔记，避免重复上传或发布。确定新建空白辅助窗口？旧窗口会保留。')) return
  busy.value = true; error.value = ''; accountConfirmed.value = false
  ++stateSequence
  try {
    const health = await assistRequest<{ version: number }>('/health')
    if (health.version < 4) throw new Error('本机服务版本较旧，需要更新到支持辅助发布的版本。')
    applyState(await assistRequest('/publisher/open', { account_id: accountId.value, record_id: props.record.id, revision: props.record.revision, new_session: fresh, acknowledged: fresh }))
  } catch (cause) { error.value = workflowError(cause) }
  finally { busy.value = false }
}
function replaceMedia(files: File[]) {
  validateMedia(files)
  clearMedia()
  media.value = files.map(file => ({ file, url: URL.createObjectURL(file) }))
}
function selectFiles(event: Event) {
  const input = event.target as HTMLInputElement, files = Array.from(input.files || [])
  input.value = ''
  if (!files.length) return
  error.value = ''
  try { replaceMedia(files) } catch (cause) { error.value = workflowError(cause) }
}
async function generateMedia() {
  if (!props.record?.data.draft_snapshot) return
  const id = props.record.id, revision = props.record.revision
  busy.value = true; error.value = ''
  try {
    const blobs = await draftImages(props.record.data.draft_snapshot)
    if (active && props.record?.id === id && props.record.revision === revision) replaceMedia(blobs.map((blob, index) => new File([blob], `${String(index + 1).padStart(2, '0')}.png`, { type: 'image/png' })))
  } catch (cause) { error.value = workflowError(cause) }
  finally { busy.value = false }
}
async function useLibrary(assets: Asset[]) {
  const recordId = props.record?.id, revision = props.record?.revision
  busy.value = true; error.value = ''
  try {
    validateMedia(assets.map(asset=>({type:asset.media_type,size:asset.size_bytes})))
    const files: File[] = []
    for (const selected of assets) {
      const asset = await getAsset(selected.id)
      if (asset.data.archived || asset.data.rights === 'unknown') throw new Error('请先核实素材来源并恢复归档素材。')
      files.push(new File([await assetBlob(asset)], assetFileName(asset), { type: asset.media_type }))
    }
    if (!active || props.dirty || props.record?.id !== recordId || props.record?.revision !== revision) throw new Error('发布记录已变化，请重新选择素材。')
    replaceMedia(files); libraryOpen.value = false
  } catch (cause) { error.value = workflowError(cause) } finally { busy.value = false }
}
function move(index: number, direction: number) {
  const target = index + direction
  if (target < 0 || target >= media.value.length) return
  const item = media.value.splice(index, 1)[0]!
  media.value.splice(target, 0, item); mediaConfirmed.value = false
}
function remove(index: number) { URL.revokeObjectURL(media.value[index]!.url); media.value.splice(index, 1); mediaConfirmed.value = false }
async function fill() {
  if (!canFill.value || !props.record || !session.value) return
  const record = props.record, token = session.value.token, selectedAccount = accountId.value
  busy.value = true; error.value = ''
  ++stateSequence
  try {
    // 再读保存版本，避免另一页已经修改文案或登记发布后仍发送旧内容。
    const latest = await getWorkflow<PublicationData>('publications', record.id)
    if (latest.revision !== record.revision || latest.status !== 'ready' || latest.data.published_at) throw new Error('发布记录已变化，请刷新并重新完成复核。')
    const assessment = await checkPublication(latest.data, latest.id, latest.parent_id || undefined)
    if (assessment.blockers.length) throw new Error('请先完成发布前检查：' + assessment.blockers.join('；'))
    const content = latest.data.source === 'custom' ? latest.data.custom_content : latest.data.draft_snapshot
    if (!content) throw new Error('缺少已保存的发布文案。')
    validateMedia(media.value.map(item => item.file))
    const files = []
    for (const item of media.value) files.push({ type: item.file.type, base64: await mediaBase64(item.file) })
    if (!active || selectedAccount !== accountId.value || props.dirty || props.record?.revision !== record.revision || props.record.id !== record.id) return
    applyState(await assistRequest('/publisher/prepare', { token, account_id: selectedAccount, record_id: record.id, revision: record.revision,
      headline: content.headline, body: [content.body, content.hashtags].filter(Boolean).join('\n\n'), media: files,
      reviewed: true, account_confirmed: accountConfirmed.value, media_confirmed: mediaConfirmed.value }))
  } catch (cause) {
    error.value = workflowError(cause)
    // 不重发写请求；单独读取可恢复本机正在执行的任务。
    try { applyState(await assistRequest('/publisher/state?account_id='+encodeURIComponent(selectedAccount))) } catch { /* 保留原错误与手动查看入口。 */ }
  } finally { busy.value = false }
}
watch(() => [props.record?.id, props.record?.revision, props.dirty], () => { accountConfirmed.value = false; clearMedia() })
watch(() => props.selectedMedia, () => { mediaConfirmed.value = false })
watch(accountId, id => {
  stopPolling(); state.value = null; accountConfirmed.value = false; mediaConfirmed.value = false
  try { if (id) localStorage.setItem('xhs-publication-account:'+props.record?.id, id) } catch { /* 仍可使用当前选择。 */ }
  void refreshState()
})
onMounted(() => { void loadAccounts() })
onActivated(() => { if (!active) { active = true; void loadAccounts() } })
onDeactivated(() => { active = false; accountConfirmed.value = false; stopPolling() })
onBeforeUnmount(() => { active = false; stopPolling(); clearMedia() })
</script>

<template>
  <div class="workflow-card" aria-label="辅助发布">
    <h3>辅助发布 · 最后由你点击发布</h3><UButton v-permission="'xhsAssets:view'" v-if="!selectedMedia" label="从素材库选择" variant="outline" :disabled="!usable || working" @click="libraryOpen=true" /><UModal v-model:open="libraryOpen" title="选择发布素材" :dismissible="!busy" :ui="{content:'max-w-5xl'}"><template #body><XhsAssets v-if="libraryOpen" picker="media" @choose="useLibrary" /><UAlert v-if="error" :title="error" color="error" /></template></UModal>
    <p class="workflow-hint">选择账号 → 打开窗口并核对登录 → 填入第一步选好的图片和文案 → 在小红书点击发布。</p>
    <UAlert v-if="!usable" title="请先保存文案、完成发布前检查，并保存为“已复核，待手动发布”。" color="warning" class="my-4" />
    <div class="workflow-actions mt-4">
      <label class="workflow-field"><span>选择本机账号浏览器</span><USelect v-model="accountId" aria-label="辅助发布账号" placeholder="请选择账号" :items="accounts.map(item=>({label:item.name,value:item.id}))" :disabled="working" /></label>
      <UButton v-permission="'xhsAccounts:view'" label="管理小红书账号" variant="outline" :disabled="working" @click="navigateAdmin('xhsAccounts')" />
      <UButton label="刷新账号列表" variant="ghost" :disabled="working" @click="loadAccounts" />
    </div>
    <p v-if="!accounts.length" class="workflow-hint mt-3">请先在“账号管理”新增账号并登录，然后回来选择对应浏览器。</p>
    <div class="workflow-actions mt-4">
      <UButton v-permission="'xhsPublishing:run'" label="打开辅助发布窗口" :disabled="!usable || working || !chosenAccount" @click="open()" />
      <UButton label="查看辅助状态" variant="outline" :disabled="busy" @click="refreshState" />
      <UButton v-permission="'xhsPublishing:run'" label="新建空白辅助窗口" variant="ghost" :disabled="!usable || working || !chosenAccount" @click="open(true)" />
    </div>
    <p class="workflow-hint mt-3">使用所选账号的独立浏览器；采集开关不会关闭它。填入期间请不要操作窗口。话题关联、视频封面、商业合作和 AI 标识需要在官方页面确认。</p>
    <div v-if="session" class="workflow-step mt-4" role="status">
      <template v-if="matching"><strong>{{ session.status === 'prepared' ? '已辅助填入，尚未发布' : session.status === 'filling' ? '正在填入' : session.status === 'paused' ? '已暂停，请检查窗口' : '等待登录与确认' }}</strong><p>{{ session.message }}</p><p v-if="!session.browser_open">原窗口已关闭；新建前请检查小红书草稿与已发布笔记。</p></template>
      <p v-else>本机还有另一条记录或旧版本的辅助窗口，请先检查，再新建当前内容的窗口。</p>
    </div>
    <UAlert v-if="error" :title="error" color="error" class="my-4" />
    <fieldset class="assist-media mt-4" :disabled="working || !usable || !!(matching && session?.touched)">
      <legend>本次发布素材</legend>
      <div v-if="!selectedMedia" class="workflow-actions my-3">
        <UButton v-if="record?.data.source==='linked'" label="生成关联笔记配图" variant="outline" @click="generateMedia" />
        <label class="workflow-field"><span>选择图片或视频（重新选择会替换本次列表）</span><input type="file" accept="image/png,image/jpeg,image/webp,video/mp4" multiple aria-label="辅助发布素材" @change="selectFiles" /></label>
      </div>
      <p class="workflow-hint">1–9 张 PNG／JPEG／WebP，每张 ≤10 MB、合计 ≤30 MB；或 1 个 MP4 ≤40 MB。更大的视频请在官方页面自行上传。</p>
      <div class="assist-previews">
        <figure v-for="(item,index) in media" :key="item.url">
          <video v-if="item.file.type==='video/mp4'" :src="item.url" controls preload="metadata" />
          <img v-else :src="item.url" :alt="'发布素材 '+(index+1)" />
          <figcaption>{{ index+1 }} · {{ item.file.name }} · {{ (item.file.size/1024/1024).toFixed(1) }} MB</figcaption>
          <div v-if="!selectedMedia" class="workflow-actions"><UButton :aria-label="'前移素材 '+(index+1)" label="前移" variant="ghost" :disabled="index===0" @click="move(index,-1)" /><UButton :aria-label="'后移素材 '+(index+1)" label="后移" variant="ghost" :disabled="index===media.length-1" @click="move(index,1)" /><UButton :aria-label="'移除素材 '+(index+1)" label="移除" variant="ghost" @click="remove(index)" /></div>
        </figure>
      </div>
      <div class="workflow-editor mt-4">
        <UCheckbox v-model="accountConfirmed" :disabled="!matching || !session?.browser_open" :label="'我已在“'+(chosenAccount?.name || '未选择')+'”窗口核对实际登录账号为：'+(record?.data.account || '尚未填写')" />
        <UCheckbox v-model="mediaConfirmed" :disabled="!media.length" label="我已预览本次素材、顺序和来源授权，同意将这些素材和文案填入小红书页面" />
      </div>
    </fieldset>
    <div class="workflow-actions mt-4"><UButton v-permission="'xhsPublishing:publish'" label="填入文案与素材" :loading="working" :disabled="!canFill" @click="fill" /></div>
    <p v-if="selectedMedia && !media.length" class="workflow-hint mt-3">还没选图片，请回到“1 · 选图片、写文案”。</p>
    <p class="workflow-hint mt-3">填入后，在小红书窗口等待图片处理完成、核对内容，再由你点击“发布”。成功后可回来登记链接。</p>
  </div>
</template>

<style scoped>
.assist-media { border:0;padding:0;min-width:0; }
.assist-media legend { font-weight:600; }
.assist-previews { display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:16px;margin-top:16px; }
.assist-previews img,.assist-previews video { width:100%;height:240px;object-fit:contain;background:var(--ui-bg-muted);border-radius:8px; }
.assist-previews figcaption { overflow-wrap:anywhere;font-size:13px;padding:8px 0; }
.assist-media input { max-width:100%; }
</style>
