<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { lazyComponent } from '../../../shared/async-component'
import { useAuthStore, UID_KEY } from '../stores/auth'
import { AUTH_CHANGED_EVENT } from '../api'
import { games, cloudGames, gameFromHash, gameKey, type CloudGameId } from './catalog'
import { GAME_SAVE_EVENT } from './game-storage'
import { GameCloud, type GameConflict } from './cloud-saves'
import GameCenter from './GameCenter.vue'
import { useGameFavorites } from './use-game-favorites'
import { pauseGameActivity } from './game-activity'

const puzzleComponent = lazyComponent(() => import('./PuzzlePlay.vue'))
const brainComponent = lazyComponent(() => import('./BrainPlay.vue'))
const components = {
  'little-shop': lazyComponent(() => import('./GameWorkbench.vue')), 'robot-maze': lazyComponent(() => import('./RobotMaze.vue')),
  'rocket-math': lazyComponent(() => import('./RocketMath.vue')), 'memory-match': lazyComponent(() => import('./MemoryMatch.vue')),
  'fraction-pizza': lazyComponent(() => import('./FractionPizza.vue')), 'poem-order': lazyComponent(() => import('./PoemOrder.vue')),
  'idiom-fill': lazyComponent(() => import('./IdiomFill.vue')), 'word-spell': lazyComponent(() => import('./WordSpell.vue')),
  'word-market': lazyComponent(() => import('./WordMarket.vue')), 'clock-town': lazyComponent(() => import('./ClockTown.vue')),
  'shape-sudoku': puzzleComponent, 'sliding-puzzle': puzzleComponent, 'lights-out': puzzleComponent,
  'tower-hanoi': puzzleComponent, 'picture-logic': puzzleComponent, 'pipe-connect': puzzleComponent,
  'tangram': brainComponent, 'sokoban': brainComponent, 'pattern-train': brainComponent, 'one-stroke': brainComponent,
  'balance-scale': brainComponent, 'color-sort': brainComponent, 'mirror-draw': brainComponent, 'spot-difference': brainComponent,
  'rhythm-band': lazyComponent(() => import('./RhythmBand.vue')), 'little-farm': lazyComponent(() => import('./LittleFarm.vue')),
  'science-lab': lazyComponent(() => import('./ScienceLab.vue')), 'forest-rescue': lazyComponent(() => import('./ForestRescue.vue')),
  'creative-studio': lazyComponent(() => import('./CreativeStudio.vue')), 'animal-catch': lazyComponent(() => import('./AnimalCatch.vue')),
  'daily-life': lazyComponent(() => import('./DailyLife.vue')), 'eco-guardian': lazyComponent(() => import('./EcoGuardian.vue')),
}
const auth = useAuthStore()
const route = ref(location.hash)
const active = computed(() => gameFromHash(route.value))
const owner = ref(auth.user ? String(auth.user.id) : remembered()), loading = ref(!!owner.value), revision = ref(0), restored = ref(0), expired = ref(false)
const status = ref('游客进度保存在当前浏览器'), error = ref(''), conflicts = ref<GameConflict[]>([])
const { favorites, notice: favoriteNotice, toggle: toggleFavorite } = useGameFavorites(owner)
const focused = ref(false)
const unknownGame = computed(() => !active.value && !/^#\/games\/?$/.test(route.value))
const originalTitle = document.title
const originalScrollRestoration = history.scrollRestoration
history.scrollRestoration = 'manual'
watch(active, async game => {
  document.title = game ? `${game.title} · 学习游戏中心` : '学习游戏中心'
  if (!game) focused.value = false
  else { await nextTick(); window.scrollTo(0, 0) }
}, { immediate: true })
function focusGame() { pauseGameActivity(); focused.value = !focused.value; window.scrollTo(0, 0) }
function escapeFocus(event: KeyboardEvent) { if (event.key === 'Escape' && !document.querySelector('[role="dialog"]')) focused.value = false }
let cloud: GameCloud | undefined
let mounting = true
let starting = false
function remembered() { try { return localStorage.getItem(UID_KEY) || '' } catch { return '' } }
async function start() {
  if (starting || expired.value) return
  owner.value = auth.user ? String(auth.user.id) : remembered()
  if (!owner.value) return
  starting = true
  loading.value = true
  try {
    if (!auth.ready || auth.bootError) await auth.init()
    if (!mounting || expired.value) return
    if (auth.bootError) { status.value = '本机进度可继续使用'; error.value = '暂时无法确认登录状态，联网后可重试云同步'; return }
    owner.value = auth.user ? String(auth.user.id) : ''
    if (!owner.value) { status.value = '游客进度保存在当前浏览器'; return }
    cloud?.dispose()
    const instance = new GameCloud(owner.value, id => {
      if (cloud !== instance || !mounting) return
      status.value = instance.status; error.value = instance.error; conflicts.value = [...instance.conflicts]; revision.value++
      if (id === active.value?.id) restored.value++
    })
    cloud = instance
    await instance.refresh()
  } finally { starting = false; if (mounting) loading.value = false }
}
function retry() { if (cloud) void cloud.refresh(); else void start() }
function syncRoute() { route.value = location.hash; revision.value++ }
function saved(event: Event) {
  revision.value++
  const key = (event as CustomEvent<{ key: string }>).detail.key
  const game = cloudGames.find(game => gameKey(game.id, owner.value) === key)
  if (game) cloud?.schedule(game.id)
}
function invalidate() { pauseGameActivity(); expired.value = true; cloud?.dispose() }
function storageChanged(event: StorageEvent) { if (event.key === UID_KEY && event.newValue !== (owner.value || null)) invalidate() }
function resolve(id: CloudGameId, choice: 'cloud' | 'local') { void cloud?.resolve(id, choice) }
function reload() { location.reload() }
onMounted(() => {
  window.addEventListener('hashchange', syncRoute); window.addEventListener(GAME_SAVE_EVENT, saved)
  window.addEventListener(AUTH_CHANGED_EVENT, invalidate); window.addEventListener('storage', storageChanged); window.addEventListener('online', retry)
  window.addEventListener('keydown', escapeFocus)
  void start()
})
onBeforeUnmount(() => {
  mounting = false; cloud?.dispose()
  window.removeEventListener('hashchange', syncRoute); window.removeEventListener(GAME_SAVE_EVENT, saved)
  window.removeEventListener(AUTH_CHANGED_EVENT, invalidate); window.removeEventListener('storage', storageChanged); window.removeEventListener('online', retry)
  window.removeEventListener('keydown', escapeFocus)
  document.title = originalTitle
  history.scrollRestoration = originalScrollRestoration
})
</script>

<template>
  <div class="games-page" :class="{ focused, 'has-active-game': !!active && !expired }">
    <div class="cloud-bar"><span role="status" :aria-label="active?.localOnly ? '游戏进度保存状态' : '云存档同步状态'"><UIcon :name="owner && !active?.localOnly ? 'i-lucide-cloud' : 'i-lucide-hard-drive'" />{{ active?.localOnly ? '本游戏进度保存在当前浏览器' : loading ? '正在读取游戏进度…' : status }}</span><button v-if="owner && !expired && !active?.localOnly" :disabled="loading" @click="retry">{{ error ? '重试同步' : '同步进度' }}</button><a v-else-if="!expired && !owner && !active?.localOnly" href="/">登录工作台，跨设备继续</a></div>
    <div v-if="expired" class="games-message" role="alert"><p>登录状态已变化，本机进度已保留。请刷新后继续。</p><button @click="reload">刷新页面</button></div>
    <template v-else>
      <div v-if="error && !active?.localOnly" class="games-message" role="alert">{{ error }}</div>
      <div v-for="conflict in conflicts" :key="conflict.id" class="games-message" role="alert"><strong>{{ games.find(game => game.id === conflict.id)?.title }}有两份不同的进度</strong><p>云端更新于 {{ new Date(conflict.remote.updated_at * 1000).toLocaleString() }}。请选择继续使用哪一份；使用云端时会在本机保留原存档副本。</p><button @click="resolve(conflict.id, 'local')">保留本机并同步</button><button @click="resolve(conflict.id, 'cloud')">使用云端进度</button></div>
      <div v-if="loading && !active?.localOnly" class="games-loading" role="status">正在核对存档，请稍候…</div>
      <Suspense v-else-if="active" :key="`${owner}:${active.id}:${restored}`">
        <component :is="components[active.id]" v-bind="active.localOnly ? { gameId: active.id } : {}" :storage-key="gameKey(active.id, owner)" />
        <template #fallback><div class="games-loading" role="status"><UIcon name="i-lucide-loader-circle" class="size-6 animate-spin" /><p>正在打开{{ active.title }}…</p></div></template>
      </Suspense>
      <template v-else><div v-if="unknownGame" class="games-message" role="status">这个游戏地址暂时无法使用，可以从下面的列表重新选择。</div><GameCenter :owner="owner" :revision="revision" /></template>
      <aside v-if="active" class="game-session-tools" aria-label="游戏快捷操作">
        <a href="#/games"><UIcon name="i-lucide-layout-grid" />返回游戏列表</a>
        <button :aria-pressed="favorites.includes(active.id)" :class="{ saved: favorites.includes(active.id) }" @click="toggleFavorite(active.id)"><UIcon name="i-lucide-heart" />{{ favorites.includes(active.id) ? '已收藏' : '收藏游戏' }}</button>
        <button :aria-pressed="focused" @click="focusGame"><UIcon :name="focused ? 'i-lucide-minimize-2' : 'i-lucide-maximize-2'" />{{ focused ? '退出专注' : '专注游戏' }}</button>
        <p v-if="favoriteNotice" class="game-session-notice" role="status">{{ favoriteNotice }}</p>
      </aside>
    </template>
  </div>
</template>

<style scoped>
.cloud-bar{display:flex;align-items:center;justify-content:flex-end;gap:16px;padding:7px 30px;min-height:34px;background:#f2f6f0;border-bottom:1px solid #e4ebdf;font-size:11px;color:#72816c}.cloud-bar>span{display:flex;align-items:center;gap:6px}.cloud-bar button,.cloud-bar a{color:#467151;text-decoration:underline;cursor:pointer}.cloud-bar button:disabled{opacity:.5}.games-message{padding:16px 24px;background:#fff5df;color:#735d33;font-size:13px;line-height:1.7}.games-message button{margin:8px 12px 0 0;padding:6px 12px;border:1px solid #c9b581;border-radius:6px;background:#fff}.games-loading{padding:60px;text-align:center;color:#6b7d69}.cloud-bar a:focus-visible,button:focus-visible{outline:3px solid #86ad92;outline-offset:3px}@media(max-width:600px){.cloud-bar{padding:8px 16px;gap:10px;justify-content:space-between;font-size:10px;flex-wrap:wrap}.games-message{padding:12px 16px}}
</style>
<style src="./game-website.css"></style>
