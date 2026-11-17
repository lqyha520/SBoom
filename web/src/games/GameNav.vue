<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { games, gameHref, type GameId } from './catalog'
defineProps<{ active?: GameId }>()
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
    <a class="games-brand" href="#/games"><span><UIcon name="i-lucide-gamepad-2" /></span>学习游戏中心</a>
    <nav v-if="active" ref="nav" aria-label="游戏导航">
      <a v-for="game in games" :key="game.id" :href="gameHref(game.id)" :aria-current="active === game.id ? 'page' : undefined" :class="{ selected: active === game.id }"><UIcon :name="game.icon" />{{ game.title }}</a>
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
