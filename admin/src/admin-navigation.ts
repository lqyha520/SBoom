import type { AdminTab } from './navigation'

export interface NavItem { id: AdminTab; label: string; icon: string }
export interface NavGroup { id: string; label: string; items: NavItem[] }
export const adminGroups: NavGroup[] = [
  { id: 'home', label: '工作首页', items: [
    { id: 'overview', label: '待办与概览', icon: 'i-lucide-layout-dashboard' },
  ] },
  { id: 'content', label: '内容管理', items: [
    { id: 'papers', label: '公共习题', icon: 'i-lucide-library' },
    { id: 'topics', label: '专题合集', icon: 'i-lucide-folders' },
    { id: 'categories', label: '分类管理', icon: 'i-lucide-folder-tree' },
    { id: 'catalogTags', label: '教材与知识点', icon: 'i-lucide-tags' },
    { id: 'banners', label: '首页推荐图', icon: 'i-lucide-gallery-horizontal-end' },
    { id: 'notices', label: '公告与弹窗', icon: 'i-lucide-megaphone' },
    { id: 'documents', label: '协议与隐私页', icon: 'i-lucide-scroll-text' },
    { id: 'dictionary', label: '年级科目字典', icon: 'i-lucide-list-tree' },
    { id: 'miniAnalytics', label: '内容数据看板', icon: 'i-lucide-chart-column' },
  ] },
  { id: 'service', label: '用户与服务', items: [
    { id: 'miniUsers', label: '小程序用户', icon: 'i-lucide-contact-round' },
    { id: 'users', label: '出题用户', icon: 'i-lucide-users-round' },
    { id: 'resourceRequests', label: '资料需求', icon: 'i-lucide-list-plus' },
    { id: 'supportCenter', label: '小程序服务与反馈', icon: 'i-lucide-messages-square' },
    { id: 'feedback', label: '出题用户反馈', icon: 'i-lucide-message-square-text' },
    { id: 'accountClosures', label: '注销申请', icon: 'i-lucide-user-round-x' },
    { id: 'delivery', label: '订阅提醒', icon: 'i-lucide-bell-ring' },
  ] },
  { id: 'commerce', label: '会员与订单', items: [
    { id: 'orders', label: '会员订单', icon: 'i-lucide-receipt-text' },
    { id: 'membershipPlans', label: '会员套餐', icon: 'i-lucide-badge-check' },
    { id: 'membershipCards', label: '会员卡密', icon: 'i-lucide-key-round' },
    { id: 'reconciliations', label: '账单核对', icon: 'i-lucide-file-check-2' },
  ] },
  { id: 'system', label: '系统设置', items: [
    { id: 'adminAccounts', label: '管理员账号', icon: 'i-lucide-shield-check' },
    { id: 'llm', label: '模型配置', icon: 'i-lucide-cpu' },
    { id: 'typeAccess', label: '题型权限', icon: 'i-lucide-shield-check' },
    { id: 'logs', label: '系统日志', icon: 'i-lucide-terminal' },
  ] },
]

export function searchAdminNavigation(query: string) {
  const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  return adminGroups.map(group => ({ ...group, items: group.items.filter(item =>
    words.every(word => `${group.label} ${item.label} ${item.id === 'banners' ? 'banner' : ''}`.toLocaleLowerCase().includes(word)),
  ) })).filter(group => group.items.length)
}
