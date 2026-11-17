<script setup lang="ts">
import { captureReferral, configureReferralTracking } from './services/referral'
import { request } from './services/api'
import { installPrivacy } from './services/privacy'
import { onLaunch, onShow, onHide, onError, onUnhandledRejection } from '@dcloudio/uni-app'
import { initializeRuntime, recordDiagnostic, flushDiagnostics } from './services/runtime'
import { ensureSession } from './services/session'
import { hideNativeTabBar } from './services/tabbar-overlay'

configureReferralTracking({ enter: (code, entry_key) => request('/api/v1/mini/referral-entry', 'POST', { code, entry_key }, { anonymous: true }), start: visit_id => request('/api/v1/mini/referral-start', 'POST', { visit_id }, { anonymous: true }) })
onLaunch(options => { captureReferral(options); installPrivacy(); initializeRuntime(); void ensureSession() })
onError(() => recordDiagnostic('runtime'))
onUnhandledRejection(() => recordDiagnostic('promise'))
onShow((options?: { path?: string; query?: Record<string, unknown> }) => { captureReferral(options); hideNativeTabBar() })
onHide(flushDiagnostics)
</script>

<style lang="scss">
@use './styles.scss';
</style>
