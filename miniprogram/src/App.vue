<script setup lang="ts">
import { onLaunch, onShow, onError, onUnhandledRejection } from '@dcloudio/uni-app'
import { initializeRuntime, recordDiagnostic } from './services/runtime'
import { ensureSession } from './services/session'
import { hideNativeTabBar } from './services/tabbar-overlay'

onLaunch(() => { initializeRuntime(); void ensureSession() })
onError(() => recordDiagnostic('runtime'))
onUnhandledRejection(() => recordDiagnostic('promise'))
onShow(hideNativeTabBar)
</script>

<style lang="scss">
@use './styles.scss';
</style>
