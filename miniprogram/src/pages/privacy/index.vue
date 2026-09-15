<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import PageChrome from '../../components/PageChrome.vue'
import { errorMessage, fetchSiteDocument } from '../../services/api'
import type { SiteDocument } from '../../types'

type DocKey = 'agreement' | 'privacy'

/** 离线兜底文案：正式内容以后台「协议与隐私页」为准，这里只在拉取失败时使用 */
const offline: Record<DocKey, { title: string; body: string }> = {
  agreement: {
    title: '用户协议',
    body: `## 账号与服务
本服务向登录用户提供已发布习题的浏览、收藏与文件下载。小程序账号独立于出题工作台，首次微信登录创建普通用户账号。

## 会员与访问范围
普通用户和有效 VIP 会员可访问的内容由运营管理员配置。开通、续期与到期时间以运营方确认和账号中显示的信息为准，当前版本不提供在线付费开通功能。

## 习题与文件
习题内容由发布方审核与提供。发现错误或涉及版权问题时，请联系运营管理员处理。习题下架、账号停用或会员到期将影响后续访问，已经另存的文件由用户自行管理。

## 个人信息
账号标识、收藏、下载请求记录与设备缓存的处理方式见隐私政策。实际运营者应提供用户联系、账号注销及数据请求渠道。`,
  },
  privacy: {
    title: '隐私政策',
    body: `## 账号与会员
小程序账号与出题工作台账号独立，不关联工作台的私人资料。首次微信登录会创建普通小程序账号，服务端保留微信标识的摘要，不向客户端返回微信 session_key。账号密码登录保存密码的加盐哈希。

## 习题数据
习题由管理员确认后发布。所有登录用户可以浏览标题、分类等公开信息；完整内容、答案、预览图片和 PDF 按后台设置的普通用户或 VIP 权限提供。收藏与下载请求记录按小程序账号独立保存。

## 设备缓存
小程序在本机保存短期登录凭证，预览和打开 PDF 时会产生临时文件。退出登录会清理本应用维护的临时文件引用与登录凭证。

## 数据与访问权限
你可以取消收藏。习题下架、VIP 到期或访问权限变更后，服务端将限制后续获取，但无法撤回已经另存的文件。账号注销、数据导出及备份保留问题请联系本服务的运营管理员。

## 服务部署
本版本为自部署软件。实际运营者、联系方式、存储区域与备份保留期限由部署方确定，正式发布前应在此补充。`,
  },
}

const kind = ref<DocKey>('privacy')
const loaded = ref<Partial<Record<DocKey, SiteDocument>>>({})
const loading = ref(false)
const error = ref('')
let sequence = 0

const currentDoc = computed(() => loaded.value[kind.value] || null)
const usingOffline = computed(() => !!error.value || !currentDoc.value)
const title = computed(() => currentDoc.value?.title || offline[kind.value].title)
const blocks = computed(() => (currentDoc.value?.body || offline[kind.value].body)
  .split('\n').map(line => line.trim()).filter(Boolean)
  .map(line => (line.startsWith('## ') ? { heading: line.slice(3).trim(), text: '' } : { heading: '', text: line })))
const updated = computed(() => (currentDoc.value
  ? new Date(currentDoc.value.updated_at * 1000).toLocaleDateString('zh-CN') + ' 更新'
  : '更新日期：2026 年 9 月 14 日'))

async function load() {
  const current = ++sequence
  loading.value = true; error.value = ''
  try {
    const value = await fetchSiteDocument(kind.value)
    if (current === sequence) loaded.value = { ...loaded.value, [kind.value]: value }
  } catch (cause) { if (current === sequence) error.value = errorMessage(cause) }
  finally { if (current === sequence) loading.value = false }
}
onLoad(options => { if (options?.kind === 'agreement') kind.value = 'agreement' })
onShow(load)
</script>

<template>
  <view class="privacy-page"><PageChrome back /><view class="page-shell privacy">
    <wd-tabs v-model="kind" line-theme="text" @change="load"><wd-tab name="agreement" title="用户协议" /><wd-tab name="privacy" title="隐私政策" /></wd-tabs>
    <view v-if="error" class="error-strip"><text class="grow">{{ error }}</text><wd-button icon="refresh" variant="text" type="danger" role="button" aria-label="重新加载协议内容" @click="load" /></view>
    <text class="page-title legal-title">{{ title }}</text>
    <text class="page-subtitle">{{ usingOffline ? '离线版本 · 内容以后台配置为准' : updated }}</text>
    <template v-for="(block, index) in blocks" :key="index">
      <text v-if="block.heading" class="privacy-heading">{{ block.heading }}</text>
      <text v-else class="privacy-text">{{ block.text }}</text>
    </template>
    <view v-if="loading" class="legal-loading"><wd-loading size="18px" /><text>正在加载</text></view>
  </view></view>
</template>

<style scoped>
.privacy { padding-top: 0; }
.legal-title { margin-top: 24px; font-size: 23px; }
.privacy-heading { display: block; margin: 28px 0 12px; font-size: 17px; font-weight: 600; color: var(--lc-text); }
.privacy-text { display: block; line-height: 1.95; font-size: 14px; color: var(--lc-secondary); overflow-wrap: anywhere; }
.legal-loading { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 26px 0; color: var(--lc-muted); font-size: 12px; }
</style>
