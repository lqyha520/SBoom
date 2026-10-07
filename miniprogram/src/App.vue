<script setup lang="ts">
import { installPrivacy } from './services/privacy'
import { onLaunch, onShow, onHide, onError, onUnhandledRejection } from '@dcloudio/uni-app'
import { initializeRuntime, recordDiagnostic, flushDiagnostics } from './services/runtime'
import { ensureSession } from './services/session'
import { hideNativeTabBar } from './services/tabbar-overlay'

onLaunch(() => { installPrivacy(); initializeRuntime(); void ensureSession() })
onError(() => recordDiagnostic('runtime'))
onUnhandledRejection(() => recordDiagnostic('promise'))
onShow(hideNativeTabBar)
onHide(flushDiagnostics)
</script>

<style lang="scss">
@use './styles.scss';
</style>
