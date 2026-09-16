<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onReachBottom } from '@dcloudio/uni-app'
import ServicePage from '../../components/ServicePage.vue'
import { useConsumerPage } from '../../services/consumer-page'
import { fetchRequests, fetchResourceRequest, submitRequest, requestStatus, type ResourceRequest } from '../../services/growth'
import { openCatalogPaper } from '../../services/navigation'
import { formatDate } from '../../content'
// Route query fields initialize the form without replacing ServicePage props.
defineOptions({ inheritAttrs: false })
const items = ref<ResourceRequest[]>([]), more = ref(false), title = ref(''), grade = ref(''), subject = ref(''), details = ref(''), highlight = ref('')
const focused = ref<ResourceRequest | null>(null)
const displayed = computed(() => focused.value ? [focused.value, ...items.value.filter(item => item.id !== focused.value?.id)] : items.value)
let seed = { title: '', grade: '', subject: '' }
onLoad(options => { seed = { title: String(options?.title || '').slice(0, 120), grade: String(options?.grade || '').slice(0, 80), subject: String(options?.subject || '').slice(0, 80) }; resetForm(); highlight.value = String(options?.id || '') })
function resetForm() { title.value = seed.title; grade.value = seed.grade; subject.value = seed.subject; details.value = '' }
async function load(valid: () => boolean, append = false) {
  const result = await fetchRequests(append ? items.value.length : 0)
  if (valid()) { items.value = append ? [...items.value, ...result.items.filter(item => !items.value.some(old => old.id === item.id))] : result.items; more.value = result.has_more }
  if (!append && highlight.value && valid()) { const selected = await fetchResourceRequest(highlight.value); if (valid()) focused.value = selected }
}
const page = useConsumerPage(load, () => { items.value = []; focused.value = null; more.value = false; resetForm() })
const { error, loading, busy } = page
function submit() {
  if (title.value.trim().length < 2) { error.value = '请填写至少 2 个字的资料名称'; return }
  void page.act(async valid => { await submitRequest({ title: title.value.trim(), grade: grade.value.trim(), subject: subject.value.trim(), details: details.value.trim() }); if (!valid()) return; seed = { title: '', grade: grade.value, subject: subject.value }; resetForm(); await load(valid); if (valid()) uni.showToast({ title: '需求已提交', icon: 'none' }) })
}
function loadMore() { if (more.value) void page.act(valid => load(valid, true)) }
onReachBottom(loadMore)
</script>
<template>
  <ServicePage title="资料需求" description="没找到需要的资料？告诉我们，处理进度会同步到消息中心。每天可新增 5 条需求。" :error="error" :loading="loading" @retry="page.refresh">
    <view class="service-card service-fields">
      <text class="service-card-title">我需要的资料</text>
      <view role="group" aria-label="资料名称"><text class="field-label">资料名称</text><wd-input v-model="title" placeholder="例如：六年级分数应用题" :maxlength="120" :disabled="busy" /></view>
      <view role="group" aria-label="年级"><text class="field-label">年级（选填）</text><wd-input v-model="grade" placeholder="例如：小学六年级" :maxlength="80" :disabled="busy" /></view>
      <view role="group" aria-label="学科"><text class="field-label">学科（选填）</text><wd-input v-model="subject" placeholder="例如：数学" :maxlength="80" :disabled="busy" /></view>
      <view role="group" aria-label="补充说明"><text class="field-label">补充说明（选填）</text><wd-textarea v-model="details" placeholder="教材版本、单元、题型等补充说明" :maxlength="1000" show-word-limit :disabled="busy" /></view>
      <wd-button role="button" block :loading="busy" :disabled="busy || loading" @click="submit">提交资料需求</wd-button>
    </view>
    <view class="service-row history-title"><text class="service-card-title">我的需求记录</text><wd-button role="button" variant="text" size="small" :disabled="busy || loading" @click="page.refresh">刷新进度</wd-button></view>
    <view v-for="item in displayed" :key="item.id" class="service-card" :class="{ highlighted: item.id === highlight }"><view class="service-row"><text class="service-card-title">{{ item.title }}</text><wd-tag variant="light">{{ requestStatus[item.status] }}</wd-tag></view><text class="service-meta">{{ [item.grade, item.subject].filter(Boolean).join(' · ') }} · {{ formatDate(item.created_at) }}</text><text v-if="item.details" class="service-copy">{{ item.details }}</text><view v-if="item.reply" class="service-reply">{{ item.reply }}</view><view v-if="item.catalog_id" class="service-actions"><wd-button role="button" size="small" variant="plain" @click="openCatalogPaper(item.catalog_id)">查看补齐资料</wd-button></view></view>
    <view v-if="!items.length && !loading && !error" class="service-empty"><wd-empty icon="no-content" tip="还没有提交过资料需求" /></view><view v-if="more" class="loading-line"><wd-button role="button" variant="text" :disabled="busy || loading" @click="loadMore">加载更多记录</wd-button></view>
  </ServicePage>
</template>
<style scoped>.history-title { margin:24px 0 14px; }.highlighted { border-color:var(--lc-primary); }</style>
