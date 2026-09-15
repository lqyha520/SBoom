<script setup lang="ts">
import { onLaunch, onShow } from '@dcloudio/uni-app'
import { ensureSession } from './services/session'
import { hideNativeTabBar } from './services/tabbar-overlay'

onLaunch(() => { void ensureSession() })
onShow(hideNativeTabBar)
</script>

<style lang="scss">
@use './styles.scss';
</style>
