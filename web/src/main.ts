import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ui from '@nuxt/ui/vue-plugin'
import App from './App.vue'
import { useAuthStore } from './stores/auth'
import './styles/tokens.css'
import './styles/base.css'
import './styles/paper.css'

// 多用户引导：先解析会话（写好 lc_uid 供数据命名空间使用），再挂载应用
async function bootstrap() {
  const app = createApp(App)
  const pinia = createPinia()
  app.use(pinia)
  app.use(ui)

  const auth = useAuthStore()
  await auth.init()

  app.mount('#app')
}

bootstrap()
