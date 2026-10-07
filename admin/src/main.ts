import { createApp } from 'vue'
import { installLoadRecovery } from '../../shared/load-recovery'
installLoadRecovery()
import ui from '@nuxt/ui/vue-plugin'
import App from './App.vue'
import './styles.css'

createApp(App).use(ui).mount('#app')
