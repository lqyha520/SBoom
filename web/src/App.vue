<script setup lang="ts">
import { lazyComponent } from '../../shared/async-component'
import { zh_cn } from '@nuxt/ui/locale'
import { useAuthStore, userPrefix } from './stores/auth'
import { loadWorkspace } from './workspace-loaders'
import { computed, onBeforeUnmount, ref } from 'vue'

const auth = useAuthStore()
const LoginView = lazyComponent(() => import('./components/LoginView.vue'))
const Workspace = lazyComponent(loadWorkspace)
const GameWorkbench = lazyComponent(() => import('./games/GameWorkbench.vue'))
const RobotMaze = lazyComponent(() => import('./games/RobotMaze.vue'))
const RocketMath = lazyComponent(() => import('./games/RocketMath.vue'))
const MemoryMatch = lazyComponent(() => import('./games/MemoryMatch.vue'))
const FractionPizza = lazyComponent(() => import('./games/FractionPizza.vue'))
const PoemOrder = lazyComponent(() => import('./games/PoemOrder.vue'))
const IdiomFill = lazyComponent(() => import('./games/IdiomFill.vue'))
const WordSpell = lazyComponent(() => import('./games/WordSpell.vue'))
const WordMarket = lazyComponent(() => import('./games/WordMarket.vue'))
const ClockTown = lazyComponent(() => import('./games/ClockTown.vue'))
// 游戏路由不等登录恢复，刷新时 auth.user 还是空的；用上次记住的账号 ID 保持同一存档。
const rememberedUid = (() => { try { return localStorage.getItem('lc_uid') || '' } catch { return '' } })()
const gameSavePrefix = computed(() => {
  const uid = auth.user?.id ?? rememberedUid
  return uid ? `${userPrefix(uid)}game_` : ''
})
const gameRoute = ref(location.hash)
const gameMode = ref(location.hash.startsWith('#/games'))
function syncPage() {
  gameRoute.value = location.hash
  gameMode.value = location.hash.startsWith('#/games')
  if (!gameMode.value && auth.user) { location.reload(); return }
  if (!gameMode.value && !auth.ready) void auth.init()
}
window.addEventListener('hashchange', syncPage)
onBeforeUnmount(() => window.removeEventListener('hashchange', syncPage))
</script>

<template>
  <UApp :locale="zh_cn" :toaster="{ position: 'top-right' }">
    <RobotMaze v-if="gameMode && gameRoute === '#/games/robot-maze'" :storage-key="gameSavePrefix ? gameSavePrefix + 'robot_maze_v1' : undefined" />
    <RocketMath v-else-if="gameMode && gameRoute === '#/games/rocket-math'" :storage-key="gameSavePrefix ? gameSavePrefix + 'rocket_math_v1' : undefined" />
    <MemoryMatch v-else-if="gameMode && gameRoute === '#/games/memory-match'" :storage-key="gameSavePrefix ? gameSavePrefix + 'memory_match_v1' : undefined" />
    <FractionPizza v-else-if="gameMode && gameRoute === '#/games/fraction-pizza'" :storage-key="gameSavePrefix ? gameSavePrefix + 'fraction_pizza_v1' : undefined" />
    <PoemOrder v-else-if="gameMode && gameRoute === '#/games/poem-order'" :storage-key="gameSavePrefix ? gameSavePrefix + 'poem_order_v1' : undefined" />
    <IdiomFill v-else-if="gameMode && gameRoute === '#/games/idiom-fill'" :storage-key="gameSavePrefix ? gameSavePrefix + 'idiom_fill_v1' : undefined" />
    <WordSpell v-else-if="gameMode && gameRoute === '#/games/word-spell'" :storage-key="gameSavePrefix ? gameSavePrefix + 'word_spell_v1' : undefined" />
    <WordMarket v-else-if="gameMode && gameRoute === '#/games/word-market'" :storage-key="gameSavePrefix ? gameSavePrefix + 'word_market_v1' : undefined" />
    <ClockTown v-else-if="gameMode && gameRoute === '#/games/clock-town'" :storage-key="gameSavePrefix ? gameSavePrefix + 'clock_town_v1' : undefined" />
    <GameWorkbench v-else-if="gameMode" :storage-key="gameSavePrefix ? gameSavePrefix + 'little_shop_v1' : undefined" />
    <div v-else-if="!auth.ready" class="loading-screen" role="status">
      <UIcon name="i-lucide-loader-circle" class="size-6 animate-spin text-primary" />
      <p>正在加载工作台</p>
    </div>
    <div v-else-if="auth.bootError" class="loading-screen p-6">
      <UAlert title="暂时无法连接工作台" :description="auth.bootError" color="error" role="alert" class="max-w-md" />
      <UButton label="重新连接" icon="i-lucide-refresh-cw" @click="auth.init()" />
    </div>
    <Suspense v-else>
      <Workspace v-if="auth.user" :key="auth.user.id" />
      <LoginView v-else />
      <template #fallback>
        <div class="loading-screen" role="status">
          <UIcon name="i-lucide-loader-circle" class="size-6 animate-spin text-primary" />
          <p>正在加载工作台</p>
        </div>
      </template>
    </Suspense>
  </UApp>
</template>
