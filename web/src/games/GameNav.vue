<script setup lang="ts">
defineProps<{ active: 'little-shop' | 'robot-maze' }>()
</script>

<template>
  <header class="games-nav">
    <a class="games-brand" href="#/games/little-shop"><span><UIcon name="i-lucide-gamepad-2" /></span>学习游戏</a>
    <nav aria-label="游戏导航">
      <a href="#/games/little-shop" :aria-current="active === 'little-shop' ? 'page' : undefined" :class="{ selected: active === 'little-shop' }"><UIcon name="i-lucide-store" />小小店长</a>
      <a href="#/games/robot-maze" :aria-current="active === 'robot-maze' ? 'page' : undefined" :class="{ selected: active === 'robot-maze' }"><UIcon name="i-lucide-bot" />机器人闯迷宫</a>
    </nav>
    <a class="workspace-link" href="/"><UIcon name="i-lucide-arrow-left" /><span>返回工作台</span></a>
  </header>
</template>

<style scoped>
.games-nav { min-height: 68px; padding: 12px 40px; display: flex; align-items: center; gap: 46px; border-bottom: 1px solid #e3e9e9; background: #fff; color: #344c4b; font-family: var(--font-ui); }
.games-nav a { text-decoration: none; display: flex; align-items: center; gap: 8px; }
.games-brand { font-size: 17px; font-weight: 700; white-space: nowrap; }
.games-brand > span { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 8px; background: #e5f0e9; color: #4b8772; }
.games-nav nav { display: flex; gap: 8px; }
.games-nav nav a { font-size: 13px; padding: 9px 12px; color: #7c8b8d; border-radius: 6px; white-space: nowrap; }
.games-nav nav a.selected { background: #edf5f3; color: #427d69; font-weight: 650; }
.games-nav nav a:hover { background: #f1f5f4; }
.games-nav nav a > span, .workspace-link > span:first-child { width: 17px; height: 17px; }
.workspace-link { margin-left: auto; color: #81908c; font-size: 12px; white-space: nowrap; }
.games-nav a:focus-visible { outline: 3px solid #679cc2; outline-offset: 3px; }
@media (max-width: 800px) { .games-nav { padding: 12px 22px; gap: 20px; } .games-nav nav a { padding: 9px 8px; font-size: 12px; } }
@media (max-width: 550px) { .games-nav { flex-wrap: wrap; padding: 12px 18px 8px; gap: 10px; } .games-brand { font-size: 15px; } .games-brand > span { width: 30px; height: 30px; } .games-nav nav { order: 3; width: 100%; } .games-nav nav a { flex: 1; justify-content: center; } .workspace-link { font-size: 11px; } }
</style>
