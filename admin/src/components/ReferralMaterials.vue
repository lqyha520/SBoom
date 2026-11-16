<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { campaignQr, type Campaign } from '../referral-operations'
import { promotionPoster } from '../promotion-poster'
import { posterArtwork, posterStyles, useReferralPoster, type PosterDraft } from '../referral-poster'
import { downloadBlob } from '../../../shared/download'

const props = defineProps<{ campaign: Campaign | null; actor: number }>()
const emit = defineEmits<{ close: [] }>()
const draft = reactive<PosterDraft>({ title: '', caption: '', style: 'editorial', direction: '', version: 'release' })
const { job, busy: generating, error: generationError, pending, generate, recover, abandon, updateDraft } = useReferralPoster(() => props.actor, () => props.campaign?.id || '')
const qr = ref<Blob | null>(null), art = ref<Blob | null>(null), poster = ref<Blob | null>(null)
const qrUrl = ref(''), artUrl = ref(''), posterUrl = ref(''), error = ref(''), notice = ref('')
const qrBusy = ref(false), artBusy = ref(false), composing = ref(false)
const busy = computed(() => generating.value || qrBusy.value || artBusy.value)
let epoch = 0, renderId = 0, timer: ReturnType<typeof setTimeout> | undefined
function revoke(url: typeof qrUrl) { if (url.value) URL.revokeObjectURL(url.value); url.value = '' }
function clearPoster() { renderId++; clearTimeout(timer); revoke(posterUrl); poster.value = null; composing.value = false }
function reset() {
  epoch++; clearPoster(); revoke(qrUrl); revoke(artUrl); qr.value = null; art.value = null; error.value = ''; notice.value = ''; qrBusy.value = false; artBusy.value = false
  Object.assign(draft, job.value?.draft || { title: props.campaign?.name || '', caption: '精选学习资料，让练习更有方向。扫码进入习题库，发现适合自己的练习内容。', style: 'editorial', direction: '', version: 'release' })
}
watch(() => [props.actor, props.campaign?.id], reset, { immediate: true })
onBeforeUnmount(() => { epoch++; clearPoster(); revoke(qrUrl); revoke(artUrl) })
async function previewQr() {
  if (!props.campaign || qrBusy.value) return false
  const current = epoch, version = draft.version; qrBusy.value = true; error.value = ''
  try {
    const result = await campaignQr(props.actor, props.campaign.id, version)
    if (current !== epoch || version !== draft.version) return false
    revoke(qrUrl); qr.value = result; qrUrl.value = URL.createObjectURL(result); return true
  } catch (cause) { if (current === epoch) error.value = cause instanceof Error ? cause.message : '活动码加载失败'; return false }
  finally { if (current === epoch) qrBusy.value = false }
}
async function loadArt() {
  const result = job.value?.result
  if (!result || !props.campaign) return
  const current = epoch; artBusy.value = true; error.value = ''
  try {
    const blob = await posterArtwork(result)
    if (current !== epoch || result.asset_id !== job.value?.result?.asset_id) return
    revoke(artUrl); art.value = blob; artUrl.value = URL.createObjectURL(blob)
    if (!qr.value) await previewQr()
  } catch (cause) { if (current === epoch) error.value = cause instanceof Error ? cause.message : '原图加载失败，请重试' }
  finally { if (current === epoch) artBusy.value = false }
}
watch(() => job.value?.result?.asset_id, () => { if (job.value?.result) void loadArt() }, { immediate: true })
watch(() => draft.version, () => { qr.value = null; revoke(qrUrl); clearPoster(); if (art.value) void previewQr() })
watch([art, qr, () => JSON.stringify(draft)], () => {
  clearPoster()
  if (!art.value || !qr.value || !draft.title.trim()) return
  const current = renderId, input = { ...draft }, background = art.value, code = qr.value
  composing.value = true
  timer = setTimeout(async () => {
    try {
      const blob = await promotionPoster(background, code, input)
      if (current !== renderId) return
      poster.value = blob; posterUrl.value = URL.createObjectURL(blob); updateDraft(input)
    } catch (cause) { if (current === renderId) error.value = cause instanceof Error ? cause.message : '海报排版失败' }
    finally { if (current === renderId) composing.value = false }
  }, 180)
})
async function create() {
  if (busy.value || pending.value || !draft.title.trim()) return
  notice.value = ''; error.value = ''
  if (!qr.value && !await previewQr()) return
  await generate({ ...draft })
}
async function copy() {
  try { await navigator.clipboard.writeText(draft.title + '\n\n' + draft.caption); notice.value = '配套文案已复制' }
  catch { error.value = '复制失败，请在文案框内手动选择并复制' }
}
function downloadPoster() { if (poster.value) { downloadBlob(poster.value, '推广海报-' + props.campaign?.id + '.png'); notice.value = '海报已下载' } }
function downloadQr() { if (qr.value) downloadBlob(qr.value, '活动码-' + props.campaign?.id + (qr.value.type.includes('jpeg') ? '.jpg' : '.png')) }
</script>
<template>
  <USlideover :open="!!campaign" title="推广素材" description="用 AI 创作主视觉，让每一份学习资料都值得分享" :ui="{ content: 'sm:max-w-6xl' }" :dismissible="!busy" @update:open="(open: boolean) => { if (!open && !busy) emit('close') }">
    <template #body><div v-if="campaign" class="poster-studio">
      <div class="field-stack poster-controls">
        <div><p class="poster-eyebrow">CAMPAIGN STUDIO</p><h3 class="font-semibold">{{ campaign.name }}</h3><p class="text-sm text-muted">{{ campaign.source }} · {{ { home: '首页', topic: '专题', paper: '资料详情' }[campaign.landing_kind || 'home'] }}</p></div>
        <UAlert v-if="error || generationError" :title="error || generationError" color="error" /><UAlert v-if="notice" :title="notice" color="success" />
        <fieldset :disabled="busy || pending" class="poster-styles"><legend class="text-sm font-medium mb-2">选择视觉风格</legend>
          <label v-for="style in posterStyles" :key="style.value" :class="['poster-style', style.value, { selected: draft.style === style.value }]">
            <input v-model="draft.style" type="radio" name="poster-style" :value="style.value"><span class="style-swatch" aria-hidden="true"></span><span><strong>{{ style.label }}</strong><small>{{ style.description }}</small></span>
          </label>
        </fieldset>
        <UFormField label="海报标题"><UTextarea v-model="draft.title" maxlength="80" :rows="2" class="w-full" :disabled="busy || pending" /></UFormField>
        <UFormField label="配套文案" :hint="`${draft.caption.length}/120`"><UTextarea v-model="draft.caption" maxlength="120" :rows="3" class="w-full" :disabled="busy || pending" /></UFormField>
        <UFormField label="画面偏好" hint="选填"><UTextarea v-model="draft.direction" maxlength="500" :rows="2" placeholder="例如：打开的书本变成森林，暖色阳光，少量植物" class="w-full" :disabled="busy || pending" /></UFormField>
        <UFormField label="小程序版本"><USelect v-model="draft.version" aria-label="素材小程序版本" :disabled="busy || pending" class="w-full" :items="[{ value: 'release', label: '正式版' }, { value: 'trial', label: '体验版' }, { value: 'develop', label: '开发版' }]" /></UFormField>
        <UButton :label="generating ? 'AI 正在创作主视觉…' : art ? '重新生成主视觉' : 'AI 生成海报'" icon="i-lucide-sparkles" :loading="generating" :disabled="busy || pending || !campaign.active || !draft.title.trim()" block size="lg" @click="create" />
        <p class="text-xs text-muted">使用后台已配置的图片模型。修改文字会即时更新预览；切换风格或画面偏好后，点击重新生成。</p>
        <div v-if="pending" class="field-stack"><p class="text-sm text-muted">请求已保存，刷新或重新打开后可以继续查询。</p><div class="actions-row"><UButton label="查询原图" :disabled="busy" variant="soft" @click="recover" /><UButton label="放弃跟踪" :disabled="busy" color="neutral" variant="ghost" @click="abandon" /></div></div>
        <div class="poster-qr"><img v-if="qrUrl" :src="qrUrl" alt="当前活动真实小程序码" width="76" height="76"><div class="field-stack"><UButton label="预览活动码" icon="i-lucide-qr-code" size="sm" variant="ghost" :disabled="busy || !campaign.active" @click="previewQr" /><UButton label="下载活动码" size="sm" variant="ghost" :disabled="!qr || busy" @click="downloadQr" /></div></div>
      </div>
      <div class="poster-preview-column">
        <div class="poster-preview-bar"><span>海报预览</span><span>1080 × 1440 · PNG</span></div>
        <div class="poster-preview-stage" :aria-busy="busy || composing">
          <img v-if="posterUrl || artUrl" :src="posterUrl || artUrl" :alt="posterUrl ? 'AI 推广海报完整预览' : 'AI 生成的海报原画'" class="poster-image">
          <div v-else class="poster-empty"><UIcon name="i-lucide-palette" class="size-12" /><h4>为好内容，画一个好开场</h4><p>选择喜欢的风格，让 AI 为活动创作专属画面。</p><span>真实活动码 · 清晰中文 · 高清下载</span></div>
          <div v-if="busy || composing" class="poster-loading" role="status"><UIcon name="i-lucide-loader-circle" class="size-5 animate-spin" />{{ generating ? '正在绘制，通常需要 1–3 分钟' : composing ? '正在更新排版' : '正在加载素材' }}</div>
        </div>
        <div class="actions-row"><UButton label="下载推广海报" icon="i-lucide-image-down" :disabled="!poster || busy || composing" @click="downloadPoster" /><UButton label="复制文案" icon="i-lucide-copy" color="neutral" variant="outline" @click="copy" /><UButton v-if="job?.result && !art" label="重新加载原图" variant="soft" :disabled="busy" @click="loadArt" /></div>
        <p class="text-xs text-muted">预览即下载效果。正式分发前，请扫码确认落地内容。</p>
      </div>
    </div></template>
  </USlideover>
</template>
<style scoped>
.poster-studio{display:grid;grid-template-columns:320px minmax(0,1fr);gap:32px;align-items:start}.poster-controls{min-width:0}.poster-eyebrow{font-size:10px;letter-spacing:.18em;color:var(--ui-text-muted);margin-bottom:8px}.poster-styles{display:grid;gap:8px;min-width:0}.poster-style{display:flex;align-items:center;gap:12px;border:1px solid var(--ui-border);border-radius:12px;padding:10px;cursor:pointer}.poster-style.selected{border-color:var(--ui-primary);box-shadow:0 0 0 1px var(--ui-primary)}.poster-style input{accent-color:var(--ui-primary)}.poster-style strong{display:block;font-size:13px}.poster-style small{color:var(--ui-text-muted);font-size:11px}.style-swatch{width:38px;height:38px;border-radius:9px;background:linear-gradient(135deg,#fff8ef 40%,#d85536 40%,#d85536 67%,#213d37 67%)}.playful .style-swatch{background:linear-gradient(135deg,#f1f8ed 40%,#dbb85d 40%,#dbb85d 67%,#558979 67%)}.minimal .style-swatch{background:linear-gradient(135deg,#eff6ff 40%,#3a6dde 40%,#3a6dde 67%,#e8bd41 67%)}.poster-preview-column{display:grid;gap:14px;min-width:0;position:sticky;top:0}.poster-preview-bar{display:flex;justify-content:space-between;gap:8px;font-size:12px;color:var(--ui-text-muted)}.poster-preview-stage{position:relative;display:grid;place-items:center;min-width:0;min-height:400px;aspect-ratio:3/4;border-radius:16px;background:#ecece8;overflow:hidden}.poster-image{display:block;width:100%;height:100%;object-fit:contain}.poster-empty{padding:30px;text-align:center;color:#657069}.poster-empty h4{font-size:20px;margin:22px 0 12px;color:#35463d}.poster-empty p{font-size:13px;line-height:1.8}.poster-empty span{display:block;font-size:11px;margin-top:32px}.poster-loading{position:absolute;inset:auto 16px 16px;display:flex;align-items:center;justify-content:center;gap:10px;border-radius:12px;padding:14px;background:#fffef5ed;color:#294638;font-size:13px;box-shadow:0 4px 20px #0000000a}.poster-qr{display:flex;align-items:center;gap:16px;border-top:1px solid var(--ui-border);padding-top:12px}.poster-qr img{background:white;border-radius:8px}@media(max-width:767px){.poster-studio{grid-template-columns:minmax(0,1fr);gap:24px}.poster-preview-column{position:static}.poster-preview-stage{min-height:0}.poster-empty{min-height:370px;display:flex;flex-direction:column;align-items:center;justify-content:center}}
</style>
