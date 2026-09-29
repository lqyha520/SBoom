export const loadWorkspace = () => import('./Workspace.vue')
export const loadLeftPanel = () => import('./components/LeftPanel.vue')
export const loadMiddleColumn = () => import('./components/MiddleColumn.vue')
export const loadPreviewPane = () => import('./components/PreviewPane.vue')

/** 登录记录只用于预取代码，账号数据仍由会话校验决定。 */
export function prefetchWorkspace() {
  void Promise.allSettled([loadWorkspace(), loadLeftPanel(), loadMiddleColumn(), loadPreviewPane()])
}
