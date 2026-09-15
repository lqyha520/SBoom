<script setup lang="ts">
import { onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { hideNativeTabBar, tabBarObscured } from '../services/tabbar-overlay'

const props = defineProps<{ current: 'home' | 'library' | 'favorites' | 'account' }>()
const tabs = [
  { name: 'home', label: '首页', icon: 'house' },
  { name: 'library', label: '习题库', icon: 'book-open' },
  { name: 'favorites', label: '收藏', icon: 'heart' },
  { name: 'account', label: '我的', icon: 'user-round' },
]
function change(event: { value: string | number }) {
  const tab = tabs.find(item => item.name === event.value)
  if (tab && tab.name !== props.current) uni.switchTab({ url: '/pages/' + tab.name + '/index' })
}
onMounted(hideNativeTabBar)
onShow(hideNativeTabBar)
</script>

<template>
  <view v-if="!tabBarObscured" class="app-tabbar" role="navigation" aria-label="主导航">
    <wd-tabbar :model-value="current" shape="round" active-color="#307e61" inactive-color="#637168" custom-class="app-tabbar-inner" @change="change">
      <wd-tabbar-item v-for="tab in tabs" :key="tab.name" :name="tab.name" :title="tab.label" role="button" :aria-label="tab.label" :aria-current="current === tab.name ? 'page' : undefined" :custom-class="current === tab.name ? 'app-tab-active' : ''"><template #icon><image class="tab-icon" :src="'/static/tabs/' + tab.icon + (current === tab.name ? '-active' : '') + '.png'" mode="aspectFit" aria-hidden="true" /></template></wd-tabbar-item>
    </wd-tabbar>
  </view>
</template>

<style scoped>
.app-tabbar { position: fixed; bottom: 0; left: 50%; transform: translateX(-50%); z-index: 50; width: 100%; max-width: 520px; padding: 8px 18px calc(14px + env(safe-area-inset-bottom)); background: #ffffffed; }
.app-tabbar :deep(.app-tabbar-inner) { --wot-tabbar-height: 60px; --wot-tabbar-round-margin-horizontal: 0; --wot-tabbar-round-shadow: 0 4px 20px #24352b08; border: 1px solid var(--lc-border); padding: 6px 7px; gap: 3px; }
.app-tabbar :deep(.wd-tabbar-item) { border-radius: 999px; min-width: 0; min-height: 46px; }
.app-tabbar :deep(.app-tab-active) { background: var(--lc-primary-soft); }
.app-tabbar :deep(.wd-tabbar-item__body) { gap: 4px; }
.tab-icon { display: block; width: 19px; height: 19px; }
</style>
