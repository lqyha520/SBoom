<script setup lang="ts">
import { computed, onActivated, onDeactivated, ref } from 'vue'
import { useAdminLeaveGuard } from '../navigation'
import { useAdminRefresh } from '../admin-page'
import { useBeforeUnload } from '../unsaved'
import * as api from '../api'
import { clearImageConfig, fetchImageConfig, saveImageConfig } from '../image-api'
import { imagePayload, modelDrafts, modelError, newModel, textPayload, type ModelDraft, type ModelKind } from '../model-profiles'

const props = defineProps<{ kind: ModelKind }>()
const isImage = computed(() => props.kind === 'image')
const title = computed(() => isImage.value ? '图片生成服务' : '全局模型服务')
const models = ref<ModelDraft[]>([])
const selectedId = ref('')
const emptySelection = newModel(props.kind)
const selected = computed(() => models.value.find(model => model.id === selectedId.value) ?? emptySelection)
const enabledCount = computed(() => models.value.filter(model => model.enabled).length)
const loading = ref(true), loadError = ref(''), busy = ref(''), message = ref(''), ok = ref(true)
const baseline = ref(''), clearOpen = ref(false), removeId = ref('')
const revision = ref(''), conflict = ref(false), reloadOpen = ref(false)
const fetchedModels = ref<Record<string, string[]>>({})
const listError = ref('')
const removeOpen = computed({ get: () => !!removeId.value, set: value => { if (!value) removeId.value = '' } })
const dirty = computed(() => !!baseline.value && baseline.value !== JSON.stringify(models.value))
const pageActive = ref(true)
onActivated(() => { pageActive.value = true })
onDeactivated(() => { pageActive.value = false })
useBeforeUnload(computed(() => pageActive.value && dirty.value))
useAdminLeaveGuard(() => !pageActive.value || (!busy.value && (!dirty.value || window.confirm('有未保存的模型配置，确认离开？'))))
const formats = [{ label: '自动', value: 'auto' }, { label: 'Base64 图片', value: 'b64_json' }, { label: '图片 URL', value: 'url' }]
const requestModes = [{ label: '自动识别', value: 'auto' }, { label: '异步任务', value: 'async' }, { label: '同步返回', value: 'sync' }]
let loadSequence = 0

function accept(value: api.GlobalLlmConfig | Awaited<ReturnType<typeof fetchImageConfig>>) {
  models.value = modelDrafts(value, props.kind)
  revision.value = value.revision ?? ''
  conflict.value = false
  if (!models.value.some(model => model.id === selectedId.value)) selectedId.value = models.value[0]?.id ?? ''
  baseline.value = JSON.stringify(models.value)
}
async function reloadLatest() {
  if (busy.value) return
  busy.value = 'reload'
  try {
    const value = await (isImage.value ? fetchImageConfig() : api.fetchLlmConfig())
    accept(value); reloadOpen.value = false; message.value = '已载入最新配置'; ok.value = true
  } catch (error) { message.value = error instanceof Error ? error.message : '读取最新配置失败'; ok.value = false }
  finally { busy.value = '' }
}
async function load() {
  if (dirty.value || busy.value) return
  const sequence = ++loadSequence
  loading.value = true; loadError.value = ''
  try {
    const value = await (isImage.value ? fetchImageConfig() : api.fetchLlmConfig())
    if (sequence === loadSequence && !dirty.value) accept(value)
  } catch (error) { if (sequence === loadSequence) loadError.value = error instanceof Error ? error.message : '配置加载失败' }
  finally { if (sequence === loadSequence) loading.value = false }
}
function add() {
  if (busy.value || models.value.length >= 8) return
  const model = newModel(props.kind)
  models.value.push(model); selectedId.value = model.id; message.value = ''
}
function selectModel(id: string) {
  selectedId.value = id
  message.value = ''
  listError.value = ''
}
function forgetFetched(id: string) {
  if (!(id in fetchedModels.value)) return
  const next = { ...fetchedModels.value }
  delete next[id]
  fetchedModels.value = next
  listError.value = ''
}
async function fetchModels() {
  if (busy.value || loading.value || loadError.value) return
  const model = selected.value
  // 模型名称可以稍后再选，但地址、超时和密钥必须先通过校验。
  const invalid = modelError({ ...model, model: model.model.trim() || 'probe' }, props.kind, true)
  listError.value = ''
  if (invalid) { listError.value = invalid; return }
  busy.value = 'models'
  try {
    const result = await api.fetchLlmModels({
      id: model.id, baseUrl: model.baseUrl.trim(), apiKey: model.apiKey.trim(), timeout: model.timeout,
    })
    fetchedModels.value = { ...fetchedModels.value, [model.id]: result.models }
  } catch (error) {
    listError.value = error instanceof Error ? error.message : '模型列表拉取失败，请手动填写模型名称'
  } finally { busy.value = '' }
}
function move(index: number, direction: number) {
  if (busy.value || index + direction < 0 || index + direction >= models.value.length) return
  const [model] = models.value.splice(index, 1)
  models.value.splice(index + direction, 0, model!)
}
function remove() {
  if (busy.value) return
  models.value = models.value.filter(model => model.id !== removeId.value)
  if (selectedId.value === removeId.value) selectedId.value = models.value[0]?.id ?? ''
  removeId.value = ''
}
async function execute(action: 'save' | 'test' | 'clear') {
  if (busy.value || loading.value || loadError.value) return
  message.value = ''
  if (action === 'save' || action === 'test') {
    const candidates = action === 'test' ? [selected.value] : models.value
    for (const model of candidates) {
      const error = modelError(model, props.kind, action === 'test')
      if (error) {
        selectedId.value = model.id; ok.value = false; message.value = `模型 ${models.value.indexOf(model) + 1}：${error}`; return
      }
    }
  }
  busy.value = action
  try {
    if (action === 'save') {
      const result = isImage.value ? await saveImageConfig(imagePayload(models.value, revision.value)) : await api.saveLlmConfig(textPayload(models.value, revision.value))
      accept(result); message.value = '模型配置已保存'
    } else if (action === 'test' && selected.value) {
      const model = selected.value
      const result = await api.testLlm({ id: model.id, baseUrl: model.baseUrl.trim(), model: model.model.trim(), apiKey: model.apiKey.trim(), timeout: model.timeout, maxTokens: model.maxTokens })
      message.value = '连接成功：' + result.reply
    } else if (action === 'clear') {
      const result = await (isImage.value ? clearImageConfig(revision.value) : api.clearLlmConfig(revision.value))
      accept(result)
      clearOpen.value = false; message.value = '模型配置与已保存密钥已清除'
    }
    ok.value = true
  } catch (error) {
    ok.value = false; message.value = error instanceof Error ? error.message : '操作失败，请重试'
    if (error instanceof api.ApiError && error.status === 409) { conflict.value = true; clearOpen.value = false }
  }
  finally { busy.value = '' }
}
useAdminRefresh(load, () => { loadSequence++; loading.value = false })
</script>

<template>
  <section class="model-settings" :aria-label="isImage ? '图片生成服务' : '全局模型配置'">
    <div class="section-toolbar">
      <h2>{{ title }}</h2>
      <UBadge :color="enabledCount ? 'success' : 'warning'" variant="subtle">{{ enabledCount ? `${enabledCount} 个已启用` : '未启用模型' }}</UBadge>
    </div>
    <UAlert v-if="loadError" :title="loadError" color="error" :actions="[{ label: '重试', onClick: load }]" />
    <div v-if="loading" role="status" aria-label="正在加载模型配置"><USkeleton v-for="n in 4" :key="n" class="h-14 mb-3" /></div>
    <template v-else-if="!loadError">
      <div class="model-layout">
        <div class="model-list">
          <div class="list-heading"><h3>调用优先级</h3><UTooltip text="添加模型"><UButton icon="i-lucide-plus" aria-label="添加模型" color="neutral" variant="outline" :disabled="!!busy || models.length >= 8" @click="add" /></UTooltip></div>
          <ol class="priority-list">
            <li v-for="(model, index) in models" :key="model.id" :class="{ selected: model.id === selectedId }">
              <button type="button" class="model-select" :aria-pressed="model.id === selectedId" :disabled="!!busy" @click="selectModel(model.id)">
                <span class="priority-number">{{ index + 1 }}</span>
                <span class="model-label"><strong>{{ model.name || model.model || '新模型' }}</strong><span>{{ model.enabled ? '已启用' : '已停用' }}</span></span>
              </button>
              <div class="model-tools">
                <UTooltip text="提高优先级"><UButton icon="i-lucide-arrow-up" :aria-label="`上移模型 ${index + 1}`" size="xs" color="neutral" variant="ghost" :disabled="!!busy || index === 0" @click="move(index, -1)" /></UTooltip>
                <UTooltip text="降低优先级"><UButton icon="i-lucide-arrow-down" :aria-label="`下移模型 ${index + 1}`" size="xs" color="neutral" variant="ghost" :disabled="!!busy || index === models.length - 1" @click="move(index, 1)" /></UTooltip>
                <UTooltip text="移除模型"><UButton icon="i-lucide-trash-2" :aria-label="`移除模型 ${index + 1}`" size="xs" color="error" variant="ghost" :disabled="!!busy" @click="removeId = model.id" /></UTooltip>
              </div>
            </li>
          </ol>
          <div v-if="!models.length" class="empty-models"><UIcon name="i-lucide-server" class="size-8" /><p>暂无模型</p><UButton icon="i-lucide-plus" label="添加模型" :disabled="!!busy" @click="add" /></div>
        </div>
        <form v-if="selectedId" class="settings-form model-form" @submit.prevent="execute('save')">
          <div class="profile-heading"><h3>模型 {{ models.indexOf(selected) + 1 }}</h3><USwitch v-model="selected.enabled" label="启用" :disabled="!!busy" /></div>
          <UFormField label="备注名称"><UInput v-model="selected.name" :disabled="!!busy" maxlength="80" placeholder="可选" /></UFormField>
          <UFormField :label="isImage ? '生图接口地址' : '接口地址'" required><UInput v-model="selected.baseUrl" type="url" placeholder="https://api.example.com/v1" :disabled="!!busy" required maxlength="500" icon="i-lucide-globe" @update:model-value="forgetFetched(selected.id)" /></UFormField>
          <div class="field-grid">
            <UFormField :label="isImage ? '生图模型名称' : '模型名称'" required>
              <div class="model-name-row">
                <UInput v-model="selected.model" placeholder="模型 ID" :disabled="!!busy" required maxlength="120" />
                <UButton v-if="!isImage" label="拉取模型" icon="i-lucide-refresh-cw" color="neutral" variant="outline" :loading="busy === 'models'" :disabled="!!busy" @click="fetchModels" />
              </div>
            </UFormField>
            <UFormField :label="isImage ? '生图超时（秒）' : '超时时间（秒）'"><UInputNumber v-model="selected.timeout" :min="isImage ? 30 : 10" :max="600" :step="10" :disabled="!!busy" /></UFormField>
          </div>
          <UFormField v-if="!isImage && fetchedModels[selected.id]?.length" label="从拉取结果选择" :description="`已拉取 ${fetchedModels[selected.id]?.length ?? 0} 个模型，选择后会覆盖上方模型名称。`">
            <USelect v-model="selected.model" :items="fetchedModels[selected.id] ?? []" placeholder="选择模型" :disabled="!!busy" aria-label="从拉取结果选择" />
          </UFormField>
          <UAlert v-if="!isImage && listError" :title="listError" color="error" variant="soft" />
          <div v-if="isImage" class="field-grid">
            <UFormField label="图片尺寸"><UInput v-model="selected.size" :disabled="!!busy" required maxlength="30" /></UFormField>
            <UFormField label="图片返回格式"><USelect v-model="selected.responseFormat" :items="formats" :disabled="!!busy" /></UFormField>
          </div>
          <UFormField v-else label="模型最大输出 token"><UInputNumber v-model="selected.maxTokens" :min="1024" :max="131072" :step="1024" :disabled="!!busy" /></UFormField>
          <UFormField v-if="isImage" label="生图调用方式" description="服务商要求提交任务后查询结果时，选择异步任务。"><USelect v-model="selected.requestMode" :items="requestModes" :disabled="!!busy" /></UFormField>
          <UFormField :label="isImage ? '生图 API 密钥' : 'API 密钥'"><UInput v-model="selected.apiKey" type="password" autocomplete="new-password" :placeholder="selected.hasKey ? '留空保留已保存的密钥' : 'sk-...'" :required="selected.enabled && !selected.hasKey" :disabled="!!busy" maxlength="4000" icon="i-lucide-key-round" /></UFormField>
          <div class="actions-row"><UBadge :color="selected.hasKey ? 'success' : 'warning'" variant="subtle" icon="i-lucide-key-round">{{ selected.hasKey ? '密钥已保存' : '未配置密钥' }}</UBadge><UButton v-if="!isImage" label="测试连接" icon="i-lucide-plug" color="neutral" variant="outline" :loading="busy === 'test'" :disabled="!!busy" @click="execute('test')" /></div>
          <button type="submit" hidden tabindex="-1" aria-hidden="true" />
        </form>
      </div>
      <UAlert v-if="models.length > 1" title="超时的上游请求可能仍会计费。" color="warning" variant="soft" icon="i-lucide-triangle-alert" class="mt-5" />
      <UAlert v-if="message && !clearOpen" :color="ok ? 'success' : 'error'" :title="message" variant="soft" class="mt-5" role="status" />
      <UAlert v-if="conflict" title="本地修改已保留，服务器配置未被覆盖。" color="warning" variant="soft" class="mt-3" :actions="[{ label: '载入最新配置', disabled: !!busy, onClick: () => { reloadOpen = true } }]" />
      <div class="actions-row model-actions">
        <UButton :label="isImage ? '保存生图配置' : '保存配置'" icon="i-lucide-save" :loading="busy === 'save'" :disabled="!!busy || !dirty" @click="execute('save')" />
        <UBadge v-if="dirty" color="warning" variant="subtle">未保存</UBadge>
        <UButton :label="isImage ? '清除生图配置' : '清除全局配置'" icon="i-lucide-trash-2" color="error" variant="outline" :disabled="!!busy || !models.length" @click="clearOpen = true; message = ''" />
      </div>
    </template>
    <UModal v-model:open="clearOpen" :title="isImage ? '清除生图配置' : '清除全局模型配置'" :dismissible="!busy" :close="!busy">
      <template #body><UAlert title="所有模型及已保存密钥将被删除，此类生成服务将停用。" color="warning" variant="soft" /><UAlert v-if="message && !ok" :title="message" color="error" class="mt-3" /></template>
      <template #footer><UButton label="取消" color="neutral" variant="outline" :disabled="!!busy" @click="clearOpen = false" /><UButton label="确认清除" color="error" :loading="busy === 'clear'" :disabled="!!busy" @click="execute('clear')" /></template>
    </UModal>
    <UModal v-model:open="removeOpen" title="移除模型">
      <template #body><p>保存配置后，此模型及其已保存密钥将被删除。</p></template>
      <template #footer><UButton label="取消" color="neutral" variant="outline" @click="removeId = ''" /><UButton label="确认移除" color="error" @click="remove" /></template>
    </UModal>
    <UModal v-model:open="reloadOpen" title="载入最新配置" :dismissible="!busy" :close="!busy">
      <template #body><p>当前列表的未保存修改将被放弃，替换为服务器上的最新模型配置。</p><UAlert v-if="message && !ok" :title="message" color="error" class="mt-3" /></template>
      <template #footer><UButton label="保留本地修改" color="neutral" variant="outline" :disabled="!!busy" @click="reloadOpen = false" /><UButton label="确认载入" :disabled="!!busy" :loading="busy === 'reload'" @click="reloadLatest" /></template>
    </UModal>
  </section>
</template>

<style scoped>
.model-settings { max-width:1100px; }
.model-layout { display:grid;grid-template-columns:minmax(220px, 280px) minmax(0, 1fr);gap:28px;align-items:start; }
.list-heading,.profile-heading { display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:16px; }
h3 { font-size:14px;font-weight:600; }
.priority-list { display:grid;gap:8px;list-style:none;padding:0;margin:0; }
.priority-list li { border:1px solid var(--ui-border);border-radius:6px;overflow:hidden; }
.priority-list li.selected { border-color:var(--ui-primary);background:var(--ui-bg-elevated); }
.model-select { display:flex;align-items:center;gap:12px;padding:12px;width:100%;text-align:left;cursor:pointer; }
.priority-number { flex:none;font-size:13px;color:var(--ui-text-muted);width:20px;text-align:center; }
.model-label { min-width:0;display:grid;gap:4px; }
.model-label strong { font-size:14px;overflow-wrap:anywhere; }
.model-label>span { font-size:12px;color:var(--ui-text-muted); }
.model-tools { display:flex;justify-content:flex-end;gap:4px;padding:0 8px 8px; }
.model-form { min-width:0;border-left:1px solid var(--ui-border);padding-left:28px; }
.model-name-row { display:flex;align-items:center;gap:8px; }
.model-name-row > :first-child { flex:1;min-width:0; }
.model-name-row > :last-child { flex:none; }
.model-actions { margin-top:24px;padding-top:20px;border-top:1px solid var(--ui-border); }
.empty-models { display:grid;justify-items:center;gap:14px;padding:30px 12px;color:var(--ui-text-muted); }
@media (max-width: 800px) {
  .model-layout { grid-template-columns:minmax(0,1fr);gap:24px; }
  .model-form { padding-left:0;border-left:0;padding-top:24px;border-top:1px solid var(--ui-border); }
}
</style>
