<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import PageChrome from '../../components/PageChrome.vue'
import { localDate } from '../../presentation'
import { errorMessage, fetchSiteDocument } from '../../services/api'
import { LEGAL_VERSION, openPrivacy, requirePrivacy } from '../../services/privacy'
import type { SiteDocument } from '../../types'

type DocKey = 'agreement' | 'privacy'

/** 离线兜底文案：正式内容以后台「协议与隐私页」为准，这里只在拉取失败时使用 */
const offline: Record<DocKey, { title: string; body: string }> = {
  agreement: {
    title: '用户协议',
    body: `## 服务范围与协议效力
本协议适用于本小程序及其配套的账号、资料浏览、收藏、会员、消息、资料需求和反馈功能。出题工作台使用独立账号，其工作区资料不与本小程序账号合并；工作台另有规则或隐私说明的，按相应页面展示内容执行。你开始使用本小程序或注册、登录前，应阅读本协议及隐私政策；不同意的，请停止使用需要账号的功能。
本服务主要提供学习资料的展示、预览、下载、会员访问和用户服务。具体可用功能以小程序页面当前展示为准；未登录用户可以使用页面开放的浏览和预览功能，收藏分组、资料下载、个人消息、资料需求和反馈等功能可能要求登录。

## 账号与使用安全
你应提供或维护真实、准确且可联系的账号资料，并妥善保管登录凭证。通过微信登录时，账号与经微信验证的身份关联；通过用户名和密码登录时，应设置并保管密码。未经本人同意，不得转让、出租、出借或共享账号。因你保管不善或主动分享凭证造成的损失，由责任方依法承担。
如发现账号被盗用、异常登录或资料泄露，请尽快通过小程序内“我的—联系客服”反馈。为保护账号和服务安全，我们可在核验后采取限制登录、撤销会话或要求重新验证等措施。
未成年人应在监护人指导下使用本服务。未满十四周岁的儿童使用账号或提交个人信息前，应由监护人阅读并同意本协议及隐私政策，并协助其使用。监护人可通过客服渠道提出查询、更正或删除请求。

## 资料、预览与会员服务
资料的可浏览、预览和下载范围由资料详情及后台权限设置决定。会员类型、有效期、价格、适用平台和具体权益以购买页面及订单确认信息为准；服务开通、续期和退款按订单状态、页面规则及适用法律处理。支付未确认时，不应重复发起可能产生重复扣款的支付；可先查询订单或联系客服。
资料由发布方整理并经运营审核后提供。不同地区、教材版本、教学进度和使用目的可能存在差异；资料仅供学习参考，不能替代教师指导、学校正式教学安排或权利人发布的正式材料。你应结合实际情况核对题目、答案、解析和适用范围。发现错误、侵权或不适宜内容时，请从资料详情提交反馈。
资料可能因纠错、版权要求、内容调整、权限变更或停止运营而更新、下架或限制访问。重要修订可通过详情页版本说明、站内消息或公告说明。权限变化影响后续在线访问和下载；已下载或通过其他方式另存的文件无法由本服务远程撤回，其保管和使用由你自行负责。
未经许可，不得批量抓取、复制后公开传播、出售、出租、破解访问控制，或以其他方式侵害资料、软件、商标及其他权利人的合法权益。个人学习使用也应遵守资料页面的授权说明及适用法律。

## 用户提交内容
你在反馈或资料需求中提交的文字、资料名称、年级、学科及补充说明应合法、真实，并限于处理问题或需求所需范围。请勿提交密码、支付凭证中的完整敏感信息、身份证件号码、未成年人真实姓名及学校等不必要的个人信息，亦不得提交违法、侵权、侮辱、骚扰或危害他人安全的内容。
你保留对自行提交内容依法享有的权利，并授权运营者在处理需求、反馈、纠错、客服沟通及服务安全所必要的范围内查看、保存和使用；该授权不改变内容权属，也不包含未经另行同意的公开发布或商业转授权。相关记录的处理方式见隐私政策。

## 规范使用与服务管理
不得利用本服务从事违法活动、绕过权限校验、攻击或干扰系统、探测他人账号或数据、上传恶意程序，或妨碍其他用户正常使用。违反规定、存在安全风险或收到有权机关要求时，我们可采取警告、限制功能、暂停账号、撤销访问权限等必要措施，并在法律允许的范围内告知处理原因。
我们会尽合理努力维护服务稳定，但网络、微信平台、设备、维护或不可抗力可能导致服务中断、延迟或部分功能不可用。我们会在条件允许时恢复服务、保存可恢复的数据，并通过公告或客服渠道处理受影响的问题。

## 订单、退款与账号注销
会员订单以订单页展示的商品、服务期限、价格和支付状态为准。退款申请应通过订单页面或客服渠道提交；是否可退、退款金额和处理进度按适用法律、订单规则及实际履行情况处理。退款成功后，按订单对应规则调整该订单带来的未使用权益，不影响其他独立订单或另行授予的权益。
你可以在账号设置中提交注销申请，申请处理前可按页面操作撤回。为完成未结订单、退款或其他依法必须先处理的事项，注销可能暂缓。注销完成后，账号及与账号关联的收藏、浏览、需求、反馈、消息和会话将按隐私政策删除或去标识化；依法或为财务、交易争议处理所必需保留的最少订单记录除外。注销后无法恢复原账号和权益。

## 协议更新与争议处理
我们可因服务变化或法律要求修订本协议，并在小程序展示更新内容和更新时间。涉及你重要权益的变更，将以合理方式提示；法律要求重新取得同意的，会在继续提供相关功能前征得同意。你继续使用更新后的服务，即表示接受更新内容；不同意的，应停止使用并可申请注销。
本协议的订立、履行及争议处理适用中华人民共和国法律。发生争议时，双方应先通过客服渠道协商；协商不成的，依法向有管辖权的人民法院提起诉讼。本条不排除消费者依法享有的权利。

## 联系方式
如对账号、会员、资料、反馈或本协议有疑问，可通过小程序“我的—联系客服”页面展示的渠道联系服务运营者。`,
  },
  privacy: {
    title: '隐私政策',
    body: `## 适用范围与处理者
本政策适用于本小程序及其账号、资料浏览、收藏、下载、会员、消息、资料需求和反馈服务，说明服务运营者如何处理与这些功能有关的个人信息。出题工作台使用独立账号和数据空间，不与本小程序账号合并；工作台功能按其页面展示的规则和隐私说明处理。
你可以通过小程序“我的—联系客服”页面展示的渠道，就个人信息处理提出问题或请求。我们会核验请求人与账号的关系，并在法律规定期限内答复。

## 我们处理的信息
账号和登录：使用微信登录时，小程序向微信发起登录并取得一次性登录凭证，服务端将凭证交由微信验证。为识别账号、保持登录、支付核验及订阅消息投递，服务端保存微信身份标识的摘要，并在需要时加密保存 OpenID 和当前微信会话密钥；不会向小程序客户端返回 OpenID 或会话密钥。使用用户名和密码登录时，服务端保存用户名及经过加盐处理的密码哈希，不保存明文密码。首次微信登录可创建小程序账号。
个人资料：你可自行编辑展示昵称，并主动选择预设头像、微信头像或本机图片。只有你确认保存后，所选昵称或图片才会提交；取消选择不会更新。自行选择的头像会被缩放处理为标准图片，去除原图中的 EXIF 等元数据，仅用于账号展示。运营管理员可为账号处理客服、会员和安全事项而查看必要资料。恢复默认头像或注销账号时会删除已保存的头像。
服务记录：使用收藏、收藏分组、下载、资料需求、反馈、订单、退款、消息和注销功能时，我们处理完成该功能所需的账号标识、资料编号或名称、提交文字、状态、时间及处理结果。资料需求包括你填写的资料名称、年级、学科和补充说明；反馈可能包括关联资料、问题描述、客服回复及仅供内部处理的备注。
使用统计：登录后，我们为服务维护记录按账号去重的每日活跃标记、未命中搜索的关键词，以及小程序报告的资料获取或打开结果和对应资料编号，用于统计服务使用趋势、排查下载问题和改进资料。搜索记录本身保存在你的设备上；服务端不会因每次成功搜索而保存完整搜索历史。下载成功记录只代表客户端报告获取或打开成功，不代表你已将文件保存到设备。
设备及运行日志：小程序会在本机保存登录凭证、年级和学科偏好、最多 12 条最近搜索以及尚未提交的资料需求和反馈草稿，便于继续使用；草稿按账号隔离，仅保存在当前设备，提交后才会传到服务端。预览或打开文件可能生成临时文件。为保障系统运行与安全，服务器或其网络设施可能产生必要访问日志，例如访问时间、请求路径、IP 地址、客户端类型和响应状态；日志按实际部署的安全和运维配置管理。
我们不会主动索取你的手机号、通讯录或精确位置，也不会读取整个相册。选择头像时仅使用微信提供的头像选择能力或你主动选取的图片；当你主动复制账号等内容时，会在微信隐私授权允许后调用剪贴板完成复制，不用于后台读取或分析剪贴板内容。

## 使用目的与处理依据
我们仅在提供和维护服务所需范围内处理个人信息，包括：创建和验证账号、维持会话及保护账号安全；展示个人资料和处理收藏、浏览、下载、需求及反馈；提供会员权益、订单支付、退款和账务核对；发送你主动订阅的服务通知；统计与排查功能质量；履行法律义务、处理争议和防范滥用。
如某项功能需要处理额外信息，我们会在功能触发处说明其目的和必要性，并在法律要求时取得你的同意。你拒绝提供非必要信息，不影响基本浏览；拒绝账号、支付或消息等必要信息时，相应功能可能无法使用。

## 微信及其他服务提供方
微信平台为本小程序提供登录、隐私授权、头像选择、订阅消息和支付等能力。登录时，服务端向微信验证一次性登录凭证；你使用微信支付或虚拟支付时，订单所需的账号标识、商品、金额和交易信息会由微信处理；你主动同意订阅消息后，我们会将发送服务通知所需的微信标识、模板字段和简短通知内容提交给微信。微信对这些信息的处理还受微信隐私保护指引及其平台规则约束。
为提供本服务，账号资料、服务记录和文件存放在运营者管理的服务器及数据库中。运营者可能委托提供主机、网络、安全、备份或技术维护的服务商处理必要数据，并要求其按约定和法律要求保护信息、不得超出委托目的使用。依法应向行政、司法机关提供信息时，我们会在法定范围内配合。
我们不会出售个人信息，也不会为第三方广告目的共享个人信息。除你主动选择的微信功能、受托服务商、取得单独同意或法律要求外，不会向其他第三方提供可识别你的个人信息。公开资料的汇总统计尽量采用不直接识别个人的方式。

## 保存地点与期限
服务数据保存在运营者管理或委托管理的服务端。服务器所在地区、备份周期和运维日志期限依实际部署配置管理；备份仅用于故障恢复，按配置周期覆盖或清理。设备本地数据和你另存、转发的文件不受服务端删除控制。
登录会话在到期、退出登录或账号注销时失效；资料浏览记录最多保存最近 100 份，可在账号页面清空；使用统计事件保存 60 天后滚动清理；站内消息保存 180 天后滚动清理。年级、学科偏好和最近搜索保留在设备中，直至你清除应用数据、清空记录或按页面操作删除。未提交的资料需求和反馈草稿有效期为七天，提交成功或按页面操作清空后删除。
反馈、资料需求、收藏、下载请求和账号关联的服务记录，通常在处理服务、回应争议和维护账号期间保存；账号注销完成时按下一节处理。支付订单及依法需要留存的财务、交易凭证会在实现交易、退款、审计或履行法定义务所需期间保存。法律规定的保存期限届满或处理目的实现后，我们会删除或去标识化相关信息；因备份轮换造成的延迟清除，按实际备份周期完成。

## 你的权利与账号注销
你可以在小程序内查看或修改展示昵称、管理收藏、清空最近浏览和搜索记录、撤销尚未处理的注销申请，并通过客服渠道请求查询、更正、删除或限制处理个人信息。你也可以拒绝或撤回微信订阅消息授权；撤回不影响此前已经完成的处理，但不会影响站内消息。
你可以在账号设置提交注销申请，处理完成前可按页面操作撤回。存在未完成订单或退款时，需先完成或处理相关事项。注销通过后，我们会删除账号、头像、会话、收藏、浏览、反馈、资料需求、使用统计、站内消息和其他可删除的账号关联数据，并撤销会员权益。订单中的账号关联和支付标识会按系统能力解除或清除；为履行财务、交易及争议处理义务而必须保留的最少记录会限制访问并在法定期限届满后删除。注销处理记录可在去标识化后保留用于证明申请处理过程。
退出登录只撤销当前会话，不会自动删除账号或服务端数据。设备中已另存的 PDF、搜索偏好和未提交草稿需在设备或小程序页面另行清理；通过微信分享或保存到其他应用的内容由你自行管理。

## 未成年人信息
本服务面向学习场景。未满十四周岁的儿童应由监护人阅读本政策并在监护人同意和指导下使用。请监护人和儿童不要提交儿童真实姓名、学校、联系方式、精确位置、面部照片或与处理需求无关的身份信息。若监护人发现儿童未经同意提供了个人信息，可通过小程序客服请求核验并删除。

## 信息安全与政策变更
我们采取访问控制、凭证加密或哈希处理、传输保护、权限审查和安全维护等措施，降低信息被未经授权访问、泄露、篡改或丢失的风险。互联网传输及电子存储无法保证绝对安全；如发生依法需要告知的个人信息安全事件，我们将按法律要求采取补救措施并通知受影响用户或主管部门。
本政策更新后会在小程序页面展示更新内容和更新时间。涉及处理目的、方式、信息种类或用户权利的重大变化时，我们会以适当方式提示；法律要求重新取得同意的，会在实施前征得同意。

## 联系与投诉
如对本政策或个人信息处理有疑问、意见或请求，请通过小程序“我的—联系客服”页面展示的渠道联系服务运营者。`,
  },
}

const kind = ref<DocKey>('privacy')
const loaded = ref<Partial<Record<DocKey, SiteDocument>>>({})
const loading = ref(false)
const error = ref('')
const authorizing = ref(false)
let sequence = 0

const currentDoc = computed(() => loaded.value[kind.value] || null)
const title = computed(() => currentDoc.value?.title || offline[kind.value].title)
const blocks = computed(() => (currentDoc.value?.body || offline[kind.value].body)
  .split('\n').map(line => line.trim()).filter(Boolean)
  .map(line => (line.startsWith('## ') ? { heading: line.slice(3).trim(), text: '' } : { heading: '', text: line })))
const updated = computed(() => (currentDoc.value
  ? localDate(currentDoc.value.updated_at) + ' 更新'
  : '离线说明更新日期：' + LEGAL_VERSION))

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
/** 已同意时微信直接返回成功；未同意会弹出授权窗口，由页面的 PrivacyConsent 承接。 */
async function authorizePrivacy() {
  if (authorizing.value) return
  authorizing.value = true
  try {
    await requirePrivacy()
    uni.showToast({ title: '已同意微信隐私授权', icon: 'none' })
  } catch {
    uni.showModal({
      title: '暂时无法完成授权',
      content: '如果刚才点了「暂不同意」，请等待约 10 秒再试；也可以先查看微信隐私保护指引，确认内容后再授权。',
      showCancel: false,
      confirmText: '知道了',
    })
  } finally { authorizing.value = false }
}
// wd-tabs 的 change 事件先于 v-model 更新触发，用它加载会拿到旧 tab 导致内容与高亮相反；改为 watch kind
watch(kind, load)
</script>

<template>
  <view class="privacy-page"><view class="page-navigation-sticky"><PageChrome back /></view><view class="page-shell privacy">
    <wd-tabs v-model="kind" line-theme="text"><wd-tab name="agreement" title="用户协议" /><wd-tab name="privacy" title="隐私政策" /></wd-tabs>
    <!-- #ifdef MP-WEIXIN -->
    <view class="wx-privacy">
      <view class="wx-privacy-head"><wd-icon name="safe" size="16px" /><text class="wx-privacy-heading">微信隐私保护指引</text></view>
      <text class="wx-privacy-note">复制账号、使用头像昵称前，需要先同意微信的用户隐私保护指引。授权是否需要更新，以微信当前提示为准。</text>
      <view class="wx-privacy-actions">
        <button class="wx-privacy-btn" hover-class="control-pressed" role="button" aria-label="查看微信隐私保护指引" @click="openPrivacy">查看指引</button>
        <button class="wx-privacy-btn primary" hover-class="control-pressed" role="button" aria-label="同意微信隐私授权" :disabled="authorizing" @click="authorizePrivacy">{{ authorizing ? '正在授权' : '同意授权' }}</button>
      </view>
    </view>
    <!-- #endif -->
    <view v-if="error" class="error-strip"><text class="grow">{{ error }}</text><wd-button icon="refresh" variant="text" type="danger" role="button" aria-label="重新加载协议内容" @click="load">重试</wd-button></view>
    <text class="page-title legal-title">{{ title }}</text>
    <view v-if="kind === 'privacy'" class="privacy-text"><text>推广来源说明：通过推广码或分享卡片进入时，我们会在本机暂存推广标识，最长 7 天。首次注册时记录直接邀请人及归属管理员，并在订单中保存当时的归属，用于推广统计、交易核对和售后处理。归属管理员可查看其推广用户及订单的必要信息；普通邀请用户不能查看受邀人的账号或付款明细。未通过推广入口注册的用户记为自然注册。</text></view>
    <text class="page-subtitle" role="status">{{ loading && !currentDoc ? '正在加载最新内容…' : currentDoc ? updated : updated + '；当前显示离线说明，联网后可重试加载最新版本' }}</text>
    <template v-for="(block, index) in blocks" :key="index">
      <text v-if="block.heading" class="privacy-heading">{{ block.heading }}</text>
      <text v-else class="privacy-text">{{ block.text }}</text>
    </template>
    <view v-if="loading" class="legal-loading"><wd-loading size="18px" /><text>正在加载</text></view>
  </view></view>
</template>

<style scoped>
.privacy { padding-top: 0; }
.wx-privacy { margin-top: 14px; padding: 14px; border: 1px solid var(--lc-card-line); border-radius: 14px; background: var(--lc-card); }
.wx-privacy-head { display: flex; align-items: center; gap: 8px; color: var(--lc-primary); }
.wx-privacy-heading { color: var(--lc-text); font-size: 14px; font-weight: 600; }
.wx-privacy-note { display: block; margin-top: 6px; color: var(--lc-secondary); font-size: 12px; line-height: 1.7; }
.wx-privacy-actions { display: flex; gap: 10px; margin-top: 12px; }
.wx-privacy-btn { flex: 1; min-height: 44px; margin: 0; padding: 0 12px; border: 1px solid var(--lc-border); border-radius: 10px; color: var(--lc-text); background: var(--lc-background); font-size: 13px; line-height: 42px; }
.wx-privacy-btn::after { border: 0; }
.wx-privacy-btn.primary { border-color: transparent; color: #fff; background: var(--lc-primary); }
.wx-privacy-btn[disabled] { opacity: .6; }
.legal-title { margin-top: 16px; font-size: 23px; }
.privacy-heading { display: block; margin: 28px 0 12px; font-size: 17px; font-weight: 600; color: var(--lc-text); }
.privacy-text { display: block; margin-bottom:12px;line-height: 1.95; font-size: 15px; color: var(--lc-text); overflow-wrap: anywhere; }
.legal-loading { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 26px 0; color: var(--lc-muted); font-size: 12px; }
</style>
