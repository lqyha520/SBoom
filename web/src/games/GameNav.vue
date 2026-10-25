<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
defineProps<{ active: 'little-shop' | 'robot-maze' | 'rocket-math' | 'memory-match' | 'fraction-pizza' | 'poem-order' | 'idiom-fill' | 'word-spell' | 'word-market' | 'clock-town' }>()
const nav = ref<HTMLElement | null>(null)
let observer: ResizeObserver | null = null
function centerActive() {
  const container = nav.value
  const current = container?.querySelector<HTMLElement>('a[aria-current="page"]')
  if (!container || !current || container.scrollWidth <= container.clientWidth) return
  const view = container.getBoundingClientRect()
  const link = current.getBoundingClientRect()
  if (link.left >= view.left && link.right <= view.right) return
  container.scrollLeft += link.left - view.left - (view.width - link.width) / 2
}
onMounted(() => {
  centerActive()
  observer = new ResizeObserver(centerActive)
  if (nav.value) {
    observer.observe(nav.value)
    nav.value.querySelectorAll('a').forEach(link => observer!.observe(link))
  }
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <header class="games-nav">
    <a class="games-brand" href="#/games/little-shop"><span><UIcon name="i-lucide-gamepad-2" /></span>学习游戏</a>
    <nav ref="nav" aria-label="游戏导航">
      <a href="#/games/little-shop" :aria-current="active === 'little-shop' ? 'page' : undefined" :class="{ selected: active === 'little-shop' }"><UIcon name="i-lucide-store" />小小店长</a>
      <a href="#/games/robot-maze" :aria-current="active === 'robot-maze' ? 'page' : undefined" :class="{ selected: active === 'robot-maze' }"><UIcon name="i-lucide-bot" />机器人闯迷宫</a>
      <a href="#/games/rocket-math" :aria-current="active === 'rocket-math' ? 'page' : undefined" :class="{ selected: active === 'rocket-math' }"><UIcon name="i-lucide-rocket" />口算火箭</a>
      <a href="#/games/memory-match" :aria-current="active === 'memory-match' ? 'page' : undefined" :class="{ selected: active === 'memory-match' }"><UIcon name="i-lucide-brain" />记忆翻牌</a>
      <a href="#/games/fraction-pizza" :aria-current="active === 'fraction-pizza' ? 'page' : undefined" :class="{ selected: active === 'fraction-pizza' }"><UIcon name="i-lucide-pizza" />披萨分数</a>
      <a href="#/games/poem-order" :aria-current="active === 'poem-order' ? 'page' : undefined" :class="{ selected: active === 'poem-order' }"><UIcon name="i-lucide-scroll-text" />诗句排队</a>
      <a href="#/games/idiom-fill" :aria-current="active === 'idiom-fill' ? 'page' : undefined" :class="{ selected: active === 'idiom-fill' }"><UIcon name="i-lucide-book-marked" />成语补字</a>
      <a href="#/games/word-spell" :aria-current="active === 'word-spell' ? 'page' : undefined" :class="{ selected: active === 'word-spell' }"><UIcon name="i-lucide-spell-check-2" />单词拼写</a>
      <a href="#/games/word-market" :aria-current="active === 'word-market' ? 'page' : undefined" :class="{ selected: active === 'word-market' }"><UIcon name="i-lucide-shopping-basket" />单词集市</a>
      <a href="#/games/clock-town" :aria-current="active === 'clock-town' ? 'page' : undefined" :class="{ selected: active === 'clock-town' }"><UIcon name="i-lucide-clock-3" />时钟小镇</a>
    </nav>
    <a class="workspace-link" href="/"><UIcon name="i-lucide-arrow-left" /><span>返回工作台</span></a>
  </header>
</template>

<style scoped>
.games-nav { min-height: 68px; padding: 12px 40px; display: flex; align-items: center; gap: 46px; border-bottom: 1px solid #e3e9e9; background: #fff; color: #344c4b; font-family: var(--font-ui); }
.games-nav a { text-decoration: none; display: flex; align-items: center; gap: 8px; }
.games-brand { font-size: 17px; font-weight: 700; white-space: nowrap; }
.games-brand > span { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 8px; background: #e5f0e9; color: #4b8772; }
.games-nav nav { flex: 1; min-width: 0; display: flex; gap: 8px; overflow-x: auto; scrollbar-width: none; }
.games-nav nav::-webkit-scrollbar { display: none; }
.games-nav nav a { flex: none; font-size: 13px; padding: 9px 12px; color: #7c8b8d; border-radius: 6px; white-space: nowrap; }
.games-nav nav a.selected { background: #edf5f3; color: #427d69; font-weight: 650; }
.games-nav nav a:hover { background: #f1f5f4; }
.games-nav nav a > span, .workspace-link > span:first-child { width: 17px; height: 17px; }
.workspace-link { margin-left: auto; color: #81908c; font-size: 12px; white-space: nowrap; }
.games-nav a:focus-visible { outline: 3px solid #679cc2; outline-offset: 3px; }
@media (max-width: 1100px) { .games-nav { gap: 22px; padding: 12px 24px; } .games-nav nav { gap: 3px; } .games-nav nav a { padding: 9px 9px; font-size: 12px; } }
@media (max-width: 900px) { .games-nav { padding: 12px 22px; gap: 14px; } .games-brand { flex: none; } .games-nav nav { flex: 1; min-width: 0; overflow-x: auto; scrollbar-width: none; } .games-nav nav::-webkit-scrollbar { display: none; } .games-nav nav a { flex: none; padding: 9px 8px; font-size: 12px; } .workspace-link { flex: none; } }
@media (max-width: 550px) { .games-nav { flex-wrap: wrap; padding: 12px 18px 8px; gap: 10px; } .games-brand { font-size: 15px; } .games-brand > span { width: 30px; height: 30px; } .games-nav nav { order: 3; width: 100%; flex: none; padding-bottom: 2px; } .games-nav nav a { padding: 9px 10px; } .workspace-link { font-size: 11px; } }
</style>
