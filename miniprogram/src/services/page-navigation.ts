/** 页面栈满时替换顶页；平台仍拒绝跳转时给出可见反馈。 */
export function navigatePage(options: UniApp.NavigateToOptions) {
  uni.navigateTo({ ...options, fail: () => uni.redirectTo({ url: options.url, fail: () => {
    uni.showToast({ title: '页面暂时无法打开，请返回后重试', icon: 'none' })
  } }) })
}
