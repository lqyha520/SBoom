<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { hideNativeTabBar, tabBarObscured } from '../services/tabbar-overlay'
import { inboxState } from '../services/growth'

type TabName = 'home' | 'library' | 'favorites' | 'account'
const props = defineProps<{ current: TabName }>()
const switching = ref(false)
const tabs = [
  { name: 'home', label: '首页', icon: 'house' },
  { name: 'library', label: '习题库', icon: 'book-open' },
  { name: 'favorites', label: '收藏', icon: 'heart' },
  { name: 'account', label: '我的', icon: 'user-round' },
] as const
function change(name: TabName) {
  if (name === props.current || switching.value) return
  switching.value = true
  uni.switchTab({
    url: '/pages/' + name + '/index',
    fail: () => uni.showToast({ title: '页面打开失败，请重试', icon: 'none' }),
    complete: () => { switching.value = false },
  })
}
onMounted(hideNativeTabBar)
onShow(hideNativeTabBar)
</script>

<template>
  <view v-if="!tabBarObscured" class="app-tabbar" role="navigation" aria-label="主导航">
    <button
      v-for="tab in tabs"
      :key="tab.name"
      class="app-tab-item"
      :class="{ 'app-tab-active': current === tab.name }"
      hover-class="app-tab-pressed"
      :hover-start-time="0"
      :hover-stay-time="80"
      role="button"
      :aria-label="tab.name === 'account' && inboxState.unread ? tab.label + '，' + inboxState.unread + ' 条未读消息' : tab.label"
      :aria-current="current === tab.name ? 'page' : undefined"
      @click="change(tab.name)"
    >
      <view class="tab-icon-wrap">
        <image class="tab-icon" :src="'/static/tabs/' + tab.icon + (current === tab.name ? '-active' : '') + '.png'" mode="aspectFit" aria-hidden="true" />
        <view v-if="tab.name === 'account' && inboxState.unread" class="tab-unread" aria-hidden="true" />
      </view>
      <text class="tab-label">{{ tab.label }}</text>
    </button>
  </view>
</template>

<style scoped>
.app-tabbar, .app-tab-item, .tab-unread { box-sizing: border-box; }
.app-tabbar { position: fixed; bottom: 0; left: 50%; transform: translateX(-50%); z-index: 50; display: flex; align-items: stretch; width: 100%; max-width: 520px; padding: 3px 12px max(4px, var(--lc-tabbar-safe-bottom, env(safe-area-inset-bottom, 0px))); border-top: 1px solid #e6ece6; background: #fff; box-shadow: 0 -4px 18px #24352b04; }
.app-tab-item { display: flex; flex: 1; flex-direction: column; align-items: center; justify-content: center; gap: 2px; min-width: 0; min-height: 46px; margin: 0; padding: 0; border: 0; border-radius: 12px; background: transparent; color: #6c7b72; font-size: 12px; font-weight: 400; line-height: 16px; }
.tab-icon-wrap { position: relative; display: flex; align-items: center; justify-content: center; flex: none; width: 48px; height: 28px; border-radius: 10px; transition: background-color .16s, transform .16s; }
.tab-icon { display: block; width: 24px; height: 24px; }
.tab-label { display: block; max-width: 100%; line-height: 16px; white-space: nowrap; }
.app-tab-active { color: var(--lc-primary); font-weight: 600; }
.app-tab-active .tab-icon-wrap { background: var(--lc-primary-soft); }
.app-tab-item:active .tab-icon-wrap, .app-tab-pressed .tab-icon-wrap { transform: scale(.92); background: var(--lc-primary-soft); }
.tab-unread { position: absolute; right: 6px; top: 1px; width: 8px; height: 8px; border: 2px solid #fff; border-radius: 50%; background: var(--lc-coral); }
@media (hover: hover) { .app-tab-item:hover .tab-icon-wrap { background: var(--lc-primary-soft); } }
</style>
