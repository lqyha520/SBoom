import { createApp } from 'vue'
import { installLoadRecovery } from '../../shared/load-recovery'
installLoadRecovery()
import ui from '@nuxt/ui/vue-plugin'
import App from './App.vue'
import './styles.css'
import { permissionDirective } from './permissions'

createApp(App).use(ui).directive('permission', permissionDirective).mount('#app')
