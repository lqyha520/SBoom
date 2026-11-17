import type { AdminTab } from './navigation'
import { canAdmin } from './permissions'

export interface NavItem { id: AdminTab; label: string; icon: string }
export interface NavGroup { id: string; label: string; icon: string; items: NavItem[] }
export const userServiceTabs = [
  { id: 'resourceRequests', label: '资料需求', icon: 'i-lucide-list-plus', description: '安排制作，补齐用户需要的资料', source: '小程序用户', hint: '汇总同类需求，回复处理进度，并关联已补齐的资料。' },
  { id: 'supportCenter', label: '小程序反馈', icon: 'i-lucide-messages-square', description: '处理使用问题，回复用户反馈', source: '小程序用户', hint: '处理资料纠错、下载和会员问题，回复处理进度并记录内部备注。' },
  { id: 'feedback', label: '出题质量反馈', icon: 'i-lucide-message-square-text', description: '查看题目质量与超纲反馈', source: '出题工作台用户', hint: '查看一般和超纲反馈，核对对应试卷；此处目前仅提供反馈查看。' },
] as const
export type UserServiceTab = typeof userServiceTabs[number]['id']
export const isUserServiceTab = (tab: AdminTab): tab is UserServiceTab => userServiceTabs.some(item => item.id === tab)
export const xhsContentTabs: NavItem[] = [
  { id: 'xhsResearch', label: '选题调研', icon: 'i-lucide-search' },
  { id: 'xhsIdeas', label: '选题库', icon: 'i-lucide-lightbulb' },
  { id: 'xhsMaterials', label: '资料制作', icon: 'i-lucide-notebook-pen' },
  { id: 'xhsDrafts', label: '笔记制作', icon: 'i-lucide-panels-top-left' },
  { id: 'xhsPublishing', label: '发布管理', icon: 'i-lucide-calendar-days' },
]
export const isXhsContentTab = (tab: AdminTab) => xhsContentTabs.some(item => item.id === tab)
export const adminSidebarTab = (tab: AdminTab): AdminTab => isXhsContentTab(tab) ? (xhsContentTabs.find(item => canAdmin(item.id))?.id || tab) : isUserServiceTab(tab) ? (userServiceTabs.find(item => canAdmin(item.id))?.id || tab) : tab
export const adminGroups: NavGroup[] = [
  { id: 'home', label: '工作台', icon: 'i-lucide-layout-dashboard', items: [
    { id: 'overview', label: '待办与概览', icon: 'i-lucide-layout-dashboard' },
    { id: 'miniAnalytics', label: '内容数据看板', icon: 'i-lucide-chart-column' },
  ] },
  { id: 'content', label: '内容资料', icon: 'i-lucide-library', items: [
    { id: 'papers', label: '公共习题', icon: 'i-lucide-library' },
    { id: 'topics', label: '专题合集', icon: 'i-lucide-folders' },
    { id: 'categories', label: '分类管理', icon: 'i-lucide-folder-tree' },
    { id: 'catalogTags', label: '教材与知识点', icon: 'i-lucide-tags' },
  ] },
  { id: 'xiaohongshu', label: '小红书工作台', icon: 'i-lucide-chart-no-axes-combined', items: [
    { id: 'xhsResearch', label: '内容工作台', icon: 'i-lucide-panels-top-left' },
    { id: 'xhsAnalytics', label: '效果复盘', icon: 'i-lucide-chart-line' },
    { id: 'xhsAssets', label: '素材库', icon: 'i-lucide-images' },
    { id: 'xhsAccounts', label: '账号管理', icon: 'i-lucide-contact-round' },
  ] },
  { id: 'service', label: '用户服务', icon: 'i-lucide-users-round', items: [
    { id: 'miniUsers', label: '小程序用户', icon: 'i-lucide-contact-round' },
    { id: 'users', label: '出题用户', icon: 'i-lucide-users-round' },
    { id: 'resourceRequests', label: '用户服务中心', icon: 'i-lucide-messages-square' },
    { id: 'accountClosures', label: '注销申请', icon: 'i-lucide-user-round-x' },
  ] },
  { id: 'commerce', label: '会员交易', icon: 'i-lucide-credit-card', items: [
    { id: 'orders', label: '会员订单', icon: 'i-lucide-receipt-text' },
    { id: 'membershipPlans', label: '会员套餐', icon: 'i-lucide-badge-check' },
    { id: 'membershipCards', label: '会员卡密', icon: 'i-lucide-key-round' },
  ] },
  { id: 'promotion', label: '推广运营', icon: 'i-lucide-megaphone', items: [
    { id: 'referrals', label: '推广管理', icon: 'i-lucide-share-2' },
    { id: 'referralEarnings', label: '我的推广收益', icon: 'i-lucide-wallet' },
    { id: 'referralRules', label: '奖励规则', icon: 'i-lucide-book-open' },
  ] },
  { id: 'finance', label: '财务中心', icon: 'i-lucide-landmark', items: [
    { id: 'financeOverview', label: '财务工作台', icon: 'i-lucide-layout-dashboard' },
    { id: 'financeSettlements', label: '结算管理', icon: 'i-lucide-calculator' },
    { id: 'financePayments', label: '付款管理', icon: 'i-lucide-credit-card' },
    { id: 'financeBills', label: '账单对账', icon: 'i-lucide-file-check-2' },
    { id: 'financeExpenses', label: '成本台账', icon: 'i-lucide-receipt-text' },
    { id: 'financeMonthly', label: '月度对账', icon: 'i-lucide-calendar-days' },
    { id: 'financeSettings', label: '财务设置', icon: 'i-lucide-shield-check' },
    { id: 'financeLedger', label: '经营账本', icon: 'i-lucide-book-marked' },
  ] },
  { id: 'operations', label: '运营配置', icon: 'i-lucide-panels-top-left', items: [
    { id: 'membershipContact', label: '会员与联系设置', icon: 'i-lucide-contact' },
    { id: 'banners', label: '首页推荐图', icon: 'i-lucide-gallery-horizontal-end' },
    { id: 'notices', label: '公告与弹窗', icon: 'i-lucide-megaphone' },
    { id: 'delivery', label: '订阅提醒', icon: 'i-lucide-bell-ring' },
    { id: 'documents', label: '协议与隐私页', icon: 'i-lucide-scroll-text' },
  ] },
  { id: 'system', label: '系统设置', icon: 'i-lucide-settings-2', items: [
    { id: 'adminAccounts', label: '管理员账号', icon: 'i-lucide-shield-check' },
    { id: 'llm', label: '模型配置', icon: 'i-lucide-cpu' },
    { id: 'typeAccess', label: '题型权限', icon: 'i-lucide-shield-check' },
    { id: 'dictionary', label: '年级科目字典', icon: 'i-lucide-list-tree' },
    { id: 'logs', label: '系统日志', icon: 'i-lucide-terminal' },
    { id: 'accountSecurity', label: '我的账号安全', icon: 'i-lucide-shield-check' },
  ] },
]

/** 侧栏合并业务入口，快速导航仍可直达页内的具体功能。 */
export const adminPageGroups: NavGroup[] = adminGroups.map(group => group.id === 'xiaohongshu'
  ? { ...group, items: [...xhsContentTabs, ...group.items.filter(item => !isXhsContentTab(item.id))] }
  : group.id === 'service' ? { ...group, items: group.items.flatMap(item => isUserServiceTab(item.id) ? [...userServiceTabs] : [item]) } : group)

export function searchAdminNavigation(query: string, includePages = false) {
  const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  return allowedAdminGroups(includePages).map(group => ({ ...group, items: group.items.filter(item =>
    words.every(word => `${group.label} ${item.label} ${isUserServiceTab(item.id) ? '用户服务中心 ' + (includePages ? userServiceTabs.find(tab => tab.id === item.id)!.label : userServiceTabs.map(tab => tab.label).join(' ')) : ''} ${item.id === 'membershipContact' ? '客服 微信 电话 邮箱 二维码 会员权益 服务时间' : ''} ${item.id === 'banners' ? 'banner' : ''} ${isXhsContentTab(item.id) ? '内容工作台' : ''} ${!includePages && item.id === 'xhsResearch' ? xhsContentTabs.map(tab => tab.label).join(' ') : ''}`.toLocaleLowerCase().includes(word)),
  ) })).filter(group => group.items.length)
}

export function allowedAdminGroups(includePages = false): NavGroup[] {
  return (includePages ? adminPageGroups : adminGroups).map(group => ({ ...group, items: group.items.flatMap(item => {
    if (!includePages && (item.id === 'xhsResearch' || item.id === 'resourceRequests')) {
      const stages = item.id === 'xhsResearch' ? xhsContentTabs : userServiceTabs
      const first = stages.find(stage => canAdmin(stage.id))
      return first ? [{ ...item, id: first.id }] : []
    }
    return canAdmin(item.id) ? [item] : []
  }) })).filter(group => group.items.length)
}
