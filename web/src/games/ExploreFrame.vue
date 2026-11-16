<script setup lang="ts">
import { computed,ref,watch } from 'vue'
import GameNav from './GameNav.vue'
import { games,type GameId } from './catalog'
import { puzzleDifficulties } from './puzzle-games'
import type { ExperienceDifficulty } from './experience-types'
import { pauseGameActivity } from './game-activity'
const props=defineProps<{gameId:GameId;difficulty:ExperienceDifficulty;progress:string;rounds:number;finished:boolean;feedback:string;saveError:boolean;canUndo:boolean;resetOpen:boolean;targetDifficulty:ExperienceDifficulty;rules:string[];creative?:boolean;stage?:number}>()
const emit=defineEmits<{difficulty:[id:ExperienceDifficulty];undo:[];restart:[];reset:[];cancel:[];hint:[]}>()
const helpOpen=ref(false)
watch(helpOpen,open=>{if(open)pauseGameActivity()})
const game=computed(()=>games.find(game=>game.id===props.gameId)!)
</script>
<template>
  <div class="explore-play"><GameNav :active="gameId" /><main class="explore-content">
    <header class="explore-heading"><div><span class="explore-kicker">{{ game.subject }} · {{ game.skills }}</span><h1>{{ game.title }}<span>.</span></h1><p>{{ game.description }}</p></div><div class="explore-heading-tools"><div v-if="!creative" class="explore-difficulties" role="group" aria-label="游戏难度"><button v-for="item in puzzleDifficulties" :key="item.id" :aria-pressed="item.id===difficulty" :class="{selected:item.id===difficulty}" @click="item.id!==difficulty && emit('difficulty',item.id)">{{ item.name }}</button></div><button class="explore-help" aria-label="怎么玩" @click="helpOpen=true"><UIcon name="i-lucide-circle-help" /></button></div></header>
    <section class="explore-status" aria-label="游戏进度"><span><UIcon :name="game.icon" />{{ progress }}</span><span>{{ creative?'已保存作品':'已完成' }} <strong>{{ rounds }}</strong>{{ creative?' 幅':' 轮' }}</span></section>
    <p v-if="!creative" class="challenge-stage">探索旅程 · 第 {{ stage || 1 }} 关</p><p v-if="saveError" role="alert" class="explore-notice">浏览器暂时无法保存进度，本局仍可继续。</p>
    <div class="explore-layout"><section class="explore-stage" :aria-label="game.title+'游戏区'"><slot /><div v-if="finished && !creative" class="explore-success" role="status" aria-label="完成反馈"><span>✦ ✦ ✦</span><h2>这次探索完成啦！</h2><p>观察、尝试和创造，都有自己的收获。</p><button class="explore-primary" @click="emit('restart')">下一段探索 <UIcon name="i-lucide-arrow-right" /></button></div></section>
      <aside class="explore-sidebar"><div class="explore-controls"><button :disabled="finished && !creative" @click="emit('hint')"><UIcon name="i-lucide-lightbulb" />给我提示</button><button :disabled="!canUndo || finished && !creative" @click="emit('undo')"><UIcon name="i-lucide-undo-2" />撤回一步</button><button @click="emit('restart')"><UIcon name="i-lucide-refresh-cw" />重新开始</button></div><p v-if="feedback" class="explore-feedback" role="status" aria-label="操作反馈">{{ feedback }}</p><div class="explore-rules"><span class="explore-kicker">小小玩法指南</span><h2>开始你的探索。</h2><p v-for="(rule,index) in rules" :key="rule"><b>{{ index+1 }}</b>{{ rule }}</p></div><p class="explore-footnote">进度保存在当前浏览器，随时可以回来继续。</p></aside></div>
  </main>
  <UModal v-model:open="helpOpen" :title="game.title+'怎么玩'" description="选择自己的节奏，观察每一次变化。"><template #body><ol class="explore-help-rules"><li v-for="rule in rules" :key="rule">{{ rule }}</li></ol></template><template #footer><button class="explore-primary" @click="helpOpen=false">知道啦</button></template></UModal>
  <UModal :open="resetOpen" :title="targetDifficulty===difficulty?'开始新的一轮？':'切换游戏难度？'" description="当前轮会重新开始，已完成次数和最佳星星保留。" @update:open="!$event && emit('cancel')"><template #footer><button class="explore-secondary" @click="emit('cancel')">继续当前游戏</button><button class="explore-primary" @click="emit('reset')">开始新一轮</button></template></UModal>
  </div>
</template>
<style src="./explore-play.css"></style>
