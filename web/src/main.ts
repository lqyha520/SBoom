import { createApp } from 'vue'
import { installLoadRecovery } from '../../shared/load-recovery'
installLoadRecovery()
import { createPinia } from 'pinia'
import ui from '@nuxt/ui/vue-plugin'
import App from './App.vue'
import { useAuthStore } from './stores/auth'
import { prefetchWorkspace } from './workspace-loaders'
import { useExamStore } from './stores/exam'
import { setRecoverySave } from '../../shared/load-recovery'
import './styles/tokens.css'
import './styles/base.css'
import './styles/paper.css'

// 先挂载认证门显示加载状态；Workspace 仅在会话解析成功后创建。
function bootstrap() {
  const app = createApp(App)
  const pinia = createPinia()
  app.use(pinia)
  app.use(ui)

  const auth = useAuthStore()
  setRecoverySave(async () => {
    const store = useExamStore()
    return !store.ownerId || await store.flushDraft()
  })
  app.mount('#app')
  try { if (localStorage.getItem('lc_uid')) prefetchWorkspace() } catch { /* 仍可正常登录。 */ }
  void auth.init()
}

bootstrap()
