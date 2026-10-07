import { defineAsyncComponent, defineComponent, h } from 'vue'
import type { Component } from 'vue'
import { recoverLoad } from './load-recovery'

const LoadError = defineComponent({
  setup: () => () => h('div', { role: 'alert', style: 'padding:24px;text-align:center' }, [
    h('p', '页面暂时无法加载，请检查网络或刷新页面。'),
    h('button', { onClick: () => void recoverLoad() }, '刷新页面'),
  ]),
})

export function lazyComponent(loader: () => Promise<{ default: Component }>) {
  return defineAsyncComponent({ loader, errorComponent: LoadError,
    onError(_error, retry, fail, attempts) {
      if (attempts < 2) setTimeout(retry, 500)
      else fail()
    },
  })
}
