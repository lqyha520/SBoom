import { computed, shallowRef } from 'vue'
import { useAdminPage } from './admin-page'
import { getPlans, type PaymentChannel } from './growth'

/** 支付能力独立于业务列表加载，失败或刷新时撤回旧能力，离页后忽略迟到响应。 */
export function useAdminPaymentConfig() {
  const config = shallowRef<Awaited<ReturnType<typeof getPlans>> | null>(null)
  const page = useAdminPage(async valid => {
    const result = await getPlans()
    if (valid()) config.value = result
  }, () => { config.value = null })
  function load() {
    config.value = null
    return page.load()
  }
  function ready(channel: PaymentChannel) {
    return !!(channel === 'virtual' ? config.value?.virtual_configuration?.ready : config.value?.configuration?.ready)
  }
  return { loading: page.loading, error: page.error, checkoutEnabled: computed(() => !!config.value?.checkout_enabled), ready, load }
}
