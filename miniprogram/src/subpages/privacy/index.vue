<script setup lang="ts">
import { computed, ref, watch } from 'vue'
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
未登录也可浏览首页、习题库、分类、标签和专题，以及允许公开预览的习题。收藏分组、文件下载、个人消息与问题反馈需要登录。小程序账号独立于出题工作台，首次微信登录创建普通用户账号。展示昵称可编辑，登录账号保持不变。

## 会员与访问范围
普通用户和有效 VIP 会员可访问的内容由运营管理员配置。在线开通启用时，以套餐页及订单确认的名称、价格和天数为准，微信确认付款后开通权益；未启用时可联系客服。已有有效期按购买天数顺延。整单退款需申请并经审核，退款成功后撤回本订单对应的未使用会员时长，其他订单和人工续期时长保留。

## 习题与文件
习题内容由发布方审核与提供。发现错误或涉及版权问题时，可从资料详情提交反馈。修订后原有收藏与公共链接保留，后续获取的是新版本，更新内容以详情页的版本说明为准。习题下架、账号停用或会员到期将影响后续访问，已经另存的文件由用户自行管理。

## 个人信息
账号标识、昵称、收藏分组、最近浏览、反馈、使用统计与设备缓存的处理方式见隐私政策。实际运营者应提供用户联系、账号注销及数据请求渠道。`,
  },
  privacy: {
    title: '隐私政策',
    body: `## 账号与会员
小程序账号与出题工作台账号独立，不关联工作台的私人资料。首次微信登录会创建普通小程序账号，服务端保留微信标识的摘要，并加密保存 OpenID，用于核对本人支付和发送经你主动订阅的微信提醒，不向客户端返回 OpenID 或微信 session_key。账号密码登录保存密码的加盐哈希。你可以自行设置展示昵称，并主动选择微信头像或头像图片。只有点击保存后才上传所选图片和昵称，取消不会更新。头像仅用于账号展示，服务端保存缩放后的标准图片，不保留原图和位置等元数据；只有本人和运营管理员可以读取，恢复默认或注销账号时删除。未选择不会获取微信昵称或头像。昵称修改不改变登录账号。管理员可设置会员身份、到期时间和账号状态，并保留变更记录。我们不申请手机号、位置、通讯录或读取整个相册的权限。

## 习题数据
习题由管理员确认后发布。游客可以浏览标题、分类等公开信息及免费预览；VIP 内容继续受会员权限保护。PDF 下载需要登录，并按后台设置的普通用户或 VIP 权限提供。收藏、收藏分组、下载请求记录和最近浏览按小程序账号独立保存，不向其他普通用户展示。最近浏览最多保留 100 份资料，支持自行清空；删除分组不会取消组内收藏。后台汇总每份习题的收藏和下载请求人数。

## 反馈与使用统计
你提交的问题、关联资料和管理员回复用于处理资料纠错、下载问题和会员咨询；内部处理备注仅后台可见。请勿在反馈中填写密码等敏感信息。登录后，为改善服务，我们记录按账号去重的活跃标记、无结果搜索词以及客户端报告的 PDF 获取或打开结果，汇总最近 30 天的使用趋势。使用事件按 60 天滚动保留，在记录新事件时清理过期数据。下载成功报告不代表文件已经另存到设备。

## 资料需求、消息与交易
资料需求的名称、年级、学科和补充说明用于安排补充内容，运营管理员可查看汇总需求。反馈回复、资料修订、需求处理、会员和订单进度会形成仅本人可见的站内消息，按 180 天滚动保留。只有你在微信中主动接受订阅后，才会向微信服务发送对应账号标识和简短服务提醒；没有订阅不影响站内消息。
在线支付启用后，订单保存套餐及金额快照、支付和退款状态、微信交易号，用于履约、退款审核和账单核对；支付由微信处理，本服务不保存银行卡号或支付密码。

## 设备缓存
小程序在本机保存短期登录凭证，并按账号保存年级、科目偏好和最多 12 条最近搜索；搜索记录可自行清空。偏好和搜索记录在退出后保留，便于再次登录使用。预览和打开 PDF 时会产生临时文件。退出登录会清理本应用维护的临时文件引用与登录凭证。通过微信菜单另存或发送的文件由你自行管理。

## 数据与访问权限
你可以取消收藏。习题下架、VIP 到期或访问权限变更后，服务端将限制后续获取，但无法撤回已经另存的文件。退出登录会撤销当前会话，管理员禁用账号会撤销全部小程序会话。你可在账号设置申请注销并在审核前撤回；未结订单和退款需先处理。审核通过后清理账号个人资料、收藏、浏览、需求、反馈与消息，终止会员权益并撤销会话。按规定保留的交易记录会解除账号关联并清除支付用户标识。设备上自行保存的文件、偏好和备份需分别管理；数据导出及备份保留问题请联系运营管理员。

## 服务部署
本版本为自部署软件。实际运营者、联系方式、存储区域与备份保留期限由部署方确定，正式发布前应在此补充，并在微信小程序后台配置相符的用户隐私保护指引。`,
  },
}

const kind = ref<DocKey>('privacy')
const loaded = ref<Partial<Record<DocKey, SiteDocument>>>({})
const loading = ref(false)
const error = ref('')
let sequence = 0

const currentDoc = computed(() => loaded.value[kind.value] || null)
const title = computed(() => currentDoc.value?.title || offline[kind.value].title)
const blocks = computed(() => (currentDoc.value?.body || offline[kind.value].body)
  .split('\n').map(line => line.trim()).filter(Boolean)
  .map(line => (line.startsWith('## ') ? { heading: line.slice(3).trim(), text: '' } : { heading: '', text: line })))
const updated = computed(() => (currentDoc.value
  ? new Date(currentDoc.value.updated_at * 1000).toLocaleDateString('zh-CN') + ' 更新'
  : '更新日期：2026 年 9 月 16 日'))

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
// wd-tabs 的 change 事件先于 v-model 更新触发，用它加载会拿到旧 tab 导致内容与高亮相反；改为 watch kind
watch(kind, load)
</script>

<template>
  <view class="privacy-page"><view class="page-navigation-sticky"><PageChrome back /></view><view class="page-shell privacy">
    <wd-tabs v-model="kind" line-theme="text"><wd-tab name="agreement" title="用户协议" /><wd-tab name="privacy" title="隐私政策" /></wd-tabs>
    <view v-if="error" class="error-strip"><text class="grow">{{ error }}</text><wd-button icon="refresh" variant="text" type="danger" role="button" aria-label="重新加载协议内容" @click="load" /></view>
    <text class="page-title legal-title">{{ title }}</text>
    <text class="page-subtitle" role="status">{{ loading && !currentDoc ? '正在加载最新内容…' : currentDoc ? updated : '当前显示离线说明，联网后可重试加载最新版本' }}</text>
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
.privacy-text { display: block; margin-bottom:12px;line-height: 1.95; font-size: 15px; color: var(--lc-text); overflow-wrap: anywhere; }
.legal-loading { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 26px 0; color: var(--lc-muted); font-size: 12px; }
</style>
