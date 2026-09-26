import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ui from '@nuxt/ui/vue-plugin'
import App from './App.vue'
import { useAuthStore } from './stores/auth'
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
  app.mount('#app')
  void auth.init()
}

bootstrap()
