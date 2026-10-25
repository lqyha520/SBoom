<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import GameNav from './GameNav.vue'
import {
  flipMemoryCard, memoryConfigFor, memoryDifficulties, memoryStars, newMemory,
  resolveMemory, restartMemory, restoreMemory, switchMemoryDifficulty,
  type MemoryCard, type MemoryDifficulty,
} from './memory-match'

const props = withDefaults(defineProps<{ storageKey?: string }>(), { storageKey: 'lc_game_memory_match_v1_guest' })
function readSave() {
  try { return restoreMemory(localStorage.getItem(props.storageKey)) } catch { return null }
}
const save = ref(readSave() || newMemory())
const resetDifficulty = ref<MemoryDifficulty | null>(null)
const helpOpen = ref(false)
const resultOpen = ref(false)
const saveError = ref(false)
const message = ref('一次翻两张，把算式和它相等的答案配成一对。')
const round = computed(() => save.value.round)
const config = computed(() => memoryConfigFor(save.value.difficulty))
const difficulty = computed(() => memoryDifficulties.find(item => item.id === save.value.difficulty)!)
const pairs = computed(() => round.value.cards.length / 2)
const matchedPairs = computed(() => round.value.matched.length)
const stars = computed(() => memoryStars(round.value))
const pendingMismatch = computed(() => {
  if (round.value.flipped.length !== 2) return false
  const [first, second] = round.value.flipped.map(id => round.value.cards[id])
  return first.pairId !== second.pairId
})
let timer: ReturnType<typeof setTimeout> | undefined
function clearTimer() { if (timer !== undefined) clearTimeout(timer); timer = undefined }
function isFaceUp(card: MemoryCard) {
  return round.value.finished || round.value.flipped.includes(card.id) || round.value.matched.includes(card.pairId)
}
function cardLabel(card: MemoryCard) {
  const matched = round.value.matched.includes(card.pairId)
  if (!isFaceUp(card)) return `未翻开的第 ${card.id + 1} 张卡片`
  return `${matched ? '已配对，' : ''}${card.face === 'expression' ? '算式' : '答案'} ${card.text}`
}
function selectCard(id: number) {
  const result = flipMemoryCard(round.value, id)
  if (result === 'first') message.value = '记住这张牌，再找和它相等的另一张。'
  if (result === 'matched' || result === 'mismatch') {
    message.value = result === 'matched' ? '配对成功，继续找下一对！' : '这两张不是一对，记住它们的位置。'
    clearTimer()
    timer = setTimeout(() => {
      timer = undefined
      const outcome = resolveMemory(save.value)
      if (outcome === 'finished') {
        message.value = '所有卡片都配对成功，太厉害了！'
        resultOpen.value = true
      }
    }, result === 'matched' ? 430 : 820)
  }
}
function restart() {
  clearTimer(); restartMemory(save.value); resultOpen.value = false
  message.value = '一次翻两张，把算式和它相等的答案配成一对。'
}
function requestDifficulty(id: MemoryDifficulty) {
  if (id !== save.value.difficulty) resetDifficulty.value = id
}
function applyDifficulty() {
  if (!resetDifficulty.value) return
  clearTimer()
  if (resetDifficulty.value === save.value.difficulty) restartMemory(save.value)
  else switchMemoryDifficulty(save.value, resetDifficulty.value)
  resultOpen.value = false; resetDifficulty.value = null
  message.value = '一次翻两张，把算式和它相等的答案配成一对。'
}
watch(save, value => {
  try { localStorage.setItem(props.storageKey, JSON.stringify(value)); saveError.value = false }
  catch { saveError.value = true }
}, { deep: true, immediate: true, flush: 'post' })
watch(() => props.storageKey, () => {
  clearTimer(); save.value = readSave() || newMemory(); resultOpen.value = false
  message.value = '一次翻两张，把算式和它相等的答案配成一对。'
})
onBeforeUnmount(clearTimer)
</script>

<template>
  <div class="memory-game">
    <GameNav active="memory-match" />
    <main class="memory-content">
      <header class="memory-heading">
        <div class="memory-title"><span class="eyebrow">小狐狸的卡片桌 · 记忆与心算</span><h1>记忆翻牌<span>.</span></h1></div>
        <div class="memory-toolbar">
          <div class="difficulty-switch" role="group" aria-label="游戏难度">
            <button v-for="item in memoryDifficulties" :key="item.id" :title="item.age" :aria-pressed="save.difficulty === item.id" :class="{ selected: save.difficulty === item.id }" @click="requestDifficulty(item.id)">{{ item.name }}</button>
          </div>
          <UTooltip text="怎么玩"><button class="round-tool" aria-label="怎么玩" @click="helpOpen = true"><UIcon name="i-lucide-circle-help" /></button></UTooltip>
        </div>
      </header>

      <section class="memory-status" aria-label="配对进度">
        <div class="status-title"><span><UIcon name="i-lucide-layers" /></span><div><strong>配对挑战</strong><small>{{ difficulty.name }} · {{ config.detail }}</small></div></div>
        <div class="pair-progress">
          <span class="progress-caption">找到的配对<strong>{{ matchedPairs }} / {{ pairs }}</strong></span>
          <div class="progress-pips" :aria-label="`已找到 ${matchedPairs} 对，共 ${pairs} 对`"><i v-for="n in pairs" :key="n" :class="{ done: n <= matchedPairs }" /></div>
        </div>
        <div class="status-stat"><span><UIcon name="i-lucide-repeat-2" />翻牌</span><strong>{{ round.moves }}</strong></div>
        <div class="status-stat"><span><UIcon name="i-lucide-trophy" />完成</span><strong>{{ save.rounds }}</strong></div>
        <div class="status-best"><span><UIcon name="i-lucide-star" />最佳</span><div class="mini-stars" :aria-label="`${difficulty.name}最佳${save.best[save.difficulty]}颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.best[save.difficulty] }" /></div></div>
      </section>

      <section class="memory-stage" aria-label="记忆翻牌桌面">
        <div class="stage-heading"><div><span class="eyebrow">第 {{ save.rounds + 1 }} 局 · {{ pairs }} 对卡片</span><h2>找到算式和答案的好朋友</h2></div><span class="move-note"><UIcon name="i-lucide-mouse-pointer-2" />一次翻开两张</span></div>
        <div class="memory-board" :class="save.difficulty" role="group" aria-label="卡片">
          <button v-for="card in round.cards" :key="card.id" class="memory-card" :class="{ 'face-up': isFaceUp(card), matched: round.matched.includes(card.pairId), mismatch: pendingMismatch && round.flipped.includes(card.id) }" :data-card-id="card.id" :aria-label="cardLabel(card)" :aria-pressed="isFaceUp(card)" :disabled="round.finished || round.flipped.includes(card.id) || round.matched.includes(card.pairId)" @click="selectCard(card.id)">
            <span class="card-inner">
              <span class="card-face card-cover" aria-hidden="true"><span class="cover-mark"><UIcon name="i-lucide-sparkles" /></span><small>{{ card.id % 4 === 0 ? '✿' : card.id % 3 === 0 ? '✦' : '·' }}</small></span>
              <span class="card-face card-content" :class="card.face" aria-hidden="true"><span class="face-kind">{{ card.face === 'expression' ? '算式' : '答案' }}</span><strong>{{ card.text }}</strong><span v-if="round.matched.includes(card.pairId)" class="matched-mark"><UIcon name="i-lucide-check" /></span></span>
            </span>
          </button>
        </div>
        <div class="stage-feedback" role="status" aria-label="翻牌反馈"><span :class="{ good: message.startsWith('配对') || message.startsWith('所有') }"><UIcon :name="message.startsWith('这两张') ? 'i-lucide-brain' : message.startsWith('配对') || message.startsWith('所有') ? 'i-lucide-circle-check' : 'i-lucide-hand-pointer'" /></span><p>{{ message }}</p></div>
        <div class="stage-tips"><span><UIcon name="i-lucide-lightbulb" />小提示：先记住算式，再找和它相等的答案。</span><span>三颗星：翻牌不超过 {{ pairs + 2 }} 次</span></div>
      </section>

      <footer class="memory-footer"><span><UIcon name="i-lucide-heart" />每一次尝试，都是成长</span><button @click="resetDifficulty = save.difficulty">重新洗牌</button><span role="status" aria-label="进度保存状态"><UIcon :name="saveError ? 'i-lucide-cloud-off' : 'i-lucide-cloud-check'" />{{ saveError ? '本机暂时无法保存进度' : '进度已保存在本机' }}</span></footer>
    </main>

    <UModal :open="resultOpen" title="全部配对成功！" description="算式和答案都找到了自己的好朋友。" :close="{ 'aria-label': '关闭完成提示' }" :ui="{ content: 'game-modal' }" @update:open="resultOpen = $event"><template #body><div class="result-panel"><span class="result-mark"><UIcon name="i-lucide-party-popper" /></span><div class="result-stars" :aria-label="`本局获得${stars}颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= stars }" /></div><p>用了 <strong>{{ round.moves }}</strong> 次翻牌，找到 <strong>{{ pairs }}</strong> 对好朋友。</p><div class="result-best"><span>{{ difficulty.name }}最佳记录</span><div class="mini-stars"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.best[save.difficulty] }" /></div></div><button class="primary-action" @click="restart"><UIcon name="i-lucide-rotate-ccw" />再来一局</button></div></template></UModal>
    <UModal :open="helpOpen" title="翻开卡片找朋友" description="算式和它的答案，是一对好朋友。" :close="{ 'aria-label': '关闭玩法说明' }" :ui="{ content: 'game-modal' }" @update:open="helpOpen = $event"><template #body><ol class="help-list"><li>每次翻开两张卡片。如果一张是算式、另一张是它相等的答案，就配对成功。</li><li>不是一对也没关系，记住它们的位置，下一次就能更快找到。</li><li>配对全部 {{ pairs }} 对卡片后完成这一局。翻牌次数越少，得到的星星越多。</li><li>难度越高，卡片越多；挑战难度里还要用心算乘法找答案。</li></ol><button class="primary-action" @click="helpOpen = false">明白了，开始翻牌<UIcon name="i-lucide-layers" /></button></template></UModal>
    <UModal :open="resetDifficulty !== null" :title="resetDifficulty === save.difficulty ? '重新洗牌？' : '切换游戏难度？'" description="这一局的翻牌进度会清空，已经获得的最佳记录会保留。" :close="{ 'aria-label': '关闭难度确认' }" :ui="{ content: 'game-modal' }" @update:open="!$event && (resetDifficulty = null)"><template #body><div class="modal-actions"><button class="secondary-action" @click="resetDifficulty = null">继续这一局</button><button class="primary-action" @click="applyDifficulty">{{ resetDifficulty === save.difficulty ? '重新洗牌' : '切换并开始' }}<UIcon name="i-lucide-arrow-right" /></button></div></template></UModal>
  </div>
</template>

<style scoped>
.memory-game { --memory-ink: #403b52; --memory-muted: #8f899f; --memory-violet: #7866a8; --memory-border: #eae3ef; min-height: 100dvh; background: #faf8fc; color: var(--memory-ink); font-family: var(--font-ui); letter-spacing: 0; }
.memory-game button { cursor: pointer; transition: background .16s, box-shadow .16s; }
.memory-game button:disabled { cursor: default; }
.memory-game button:focus-visible { outline: 3px solid #9d8dcc; outline-offset: 3px; }
.memory-content { max-width: 1160px; margin: auto; padding: 30px 36px 18px; }
.eyebrow { display: block; color: var(--memory-muted); font-size: 11px; line-height: 1.6; }
.memory-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 22px; }
.memory-title h1 { font-size: 32px; font-weight: 750; line-height: 1.35; margin: 3px 0 0; }
.memory-title h1 > span { color: #c9a55f; margin-left: 3px; }
.memory-toolbar { display: flex; align-items: center; gap: 9px; }
.difficulty-switch { display: flex; align-items: center; gap: 3px; background: #f0ebf6; padding: 4px; border-radius: 8px; margin-right: 6px; }
.difficulty-switch button { height: 35px; padding: 0 15px; background: transparent; border-radius: 5px; color: #948da5; font-size: 12px; white-space: nowrap; }
.difficulty-switch button.selected { color: var(--memory-violet); background: #fff; box-shadow: 0 1px 4px #403b5212; font-weight: 650; }
.round-tool { width: 36px; height: 36px; display: grid; place-items: center; color: #9189a3; background: transparent; border-radius: 6px; }
.round-tool:hover { background: #f0ebf6; }
.round-tool > span { width: 18px; height: 18px; }
.memory-status { display: flex; align-items: center; gap: 34px; padding: 15px 0; border-top: 1px solid var(--memory-border); border-bottom: 1px solid var(--memory-border); margin-bottom: 22px; }
.status-title { display: flex; align-items: center; gap: 11px; }
.status-title > span { width: 38px; height: 38px; display: grid; place-items: center; background: #f2ecf9; color: #8672b3; border-radius: 50%; }
.status-title > span > span { width: 20px; height: 20px; }
.status-title > div { display: flex; flex-direction: column; gap: 3px; }
.status-title strong { font-size: 13px; font-weight: 650; }
.status-title small { font-size: 10px; color: var(--memory-muted); }
.pair-progress { flex: 1; max-width: 300px; display: flex; flex-direction: column; gap: 7px; }
.progress-caption { display: flex; justify-content: space-between; gap: 10px; color: var(--memory-muted); font-size: 10px; }
.progress-caption strong { color: var(--memory-violet); font-weight: 600; font-variant-numeric: tabular-nums; }
.progress-pips { display: flex; gap: 4px; }
.progress-pips i { flex: 1; max-width: 26px; height: 5px; border-radius: 4px; background: #ece7f2; transition: background .3s; }
.progress-pips i.done { background: #a291c4; }
.status-stat { display: flex; align-items: center; gap: 7px; color: var(--memory-muted); font-size: 11px; border-left: 1px solid var(--memory-border); padding-left: 22px; }
.status-stat > span { display: flex; align-items: center; gap: 4px; }
.status-stat > span > span { width: 14px; height: 14px; color: #b3a277; }
.status-stat strong { font-size: 17px; color: var(--memory-ink); font-variant-numeric: tabular-nums; }
.status-best { display: flex; flex-direction: column; gap: 5px; margin-left: auto; color: var(--memory-muted); font-size: 10px; }
.status-best > span { display: flex; align-items: center; gap: 4px; }
.status-best > span > span { width: 13px; height: 13px; color: #c9a55f; }
.mini-stars { display: flex; gap: 3px; }
.mini-stars > span { width: 13px; height: 13px; color: #e5e0ea; }
.mini-stars > .earned { color: #d9b263; }
.memory-stage { position: relative; border-radius: 12px; border: 1px solid #efe8f3; background: radial-gradient(circle at 14% 12%, #fdf8ef 0 18%, transparent 19%), radial-gradient(circle at 86% 10%, #f7edf6 0 15%, transparent 16%), linear-gradient(155deg, #fbf7f1, #f6eff7 62%, #f2eef8); padding: 24px clamp(16px, 4vw, 40px) 20px; }
.stage-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; margin-bottom: 18px; }
.stage-heading h2 { font-size: 19px; font-weight: 700; margin-top: 3px; }
.move-note { display: flex; align-items: center; gap: 5px; color: #a29aad; font-size: 10px; padding-bottom: 3px; white-space: nowrap; }
.move-note > span { width: 13px; height: 13px; }
.memory-board { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: clamp(8px, 1.6vw, 13px); max-width: 760px; margin: 0 auto; }
.memory-board.master { grid-template-columns: repeat(5, minmax(0, 1fr)); max-width: 820px; }
.memory-card { position: relative; aspect-ratio: 1 / 1.09; width: 100%; border: 0; padding: 0; background: transparent; perspective: 800px; border-radius: 11px; }
.memory-card:disabled { opacity: 1; }
.card-inner { display: block; position: relative; width: 100%; height: 100%; transform-style: preserve-3d; transition: transform .42s cubic-bezier(.2,.75,.3,1), translate .18s; }
.memory-card.face-up .card-inner { transform: rotateY(180deg); }
.memory-card:not(.face-up):not(:disabled):hover .card-inner { translate: 0 -3px; }
.memory-card:not(.face-up):not(:disabled):active .card-inner { translate: 0 1px; }
.card-face { position: absolute; inset: 0; border-radius: 11px; backface-visibility: hidden; -webkit-backface-visibility: hidden; display: flex; flex-direction: column; align-items: center; justify-content: center; overflow: hidden; }
.card-cover { background: linear-gradient(150deg, #8e7cb8, #73619e 58%, #66558e); border: 1px solid #67568f; box-shadow: 0 3px 0 #58497b, inset 0 1px 0 #ffffff35; color: #f4eeff; }
.card-cover::before { content: ''; position: absolute; inset: 9px; border: 1px solid #ffffff2e; border-radius: 7px; }
.card-cover::after { content: ''; position: absolute; width: 78%; height: 78%; border-radius: 50%; background: radial-gradient(circle, #ffffff10 0 28%, transparent 29%), radial-gradient(circle, #ffffff0b 0 18%, transparent 19%); background-position: 0 0, 17px 22px; }
.cover-mark { position: relative; z-index: 1; width: 32%; aspect-ratio: 1; display: grid; place-items: center; border-radius: 50%; background: #ffffff1b; color: #f7ebc9; }
.cover-mark > span { width: 55%; height: 55%; }
.card-cover small { position: relative; z-index: 1; margin-top: 7px; font-size: 9px; letter-spacing: 2px; color: #ffffff85; }
.card-content { transform: rotateY(180deg); background: #fffdf8; border: 1px solid #e8decd; box-shadow: 0 3px 0 #e2d7c5; color: #7b669d; }
.card-content.answer { background: #fdf7e7; border-color: #ecdfbf; box-shadow: 0 3px 0 #e5d6b0; color: #b08140; }
.face-kind { position: absolute; top: 9px; left: 10px; font-size: 8px; color: #b7ab9d; letter-spacing: 1px; }
.card-content strong { font-size: clamp(17px, 3.4vw, 26px); font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; padding: 0 5px; }
.memory-board.master .card-content strong { font-size: clamp(15px, 2.4vw, 22px); }
.matched-mark { position: absolute; right: 7px; bottom: 6px; width: 18px; height: 18px; border-radius: 50%; background: #e7f2e8; color: #6d9a78; display: grid; place-items: center; }
.matched-mark > span { width: 11px; height: 11px; }
.memory-card.matched .card-content { border-color: #b9d3bf; box-shadow: 0 3px 0 #d5e5d8; opacity: .82; }
.memory-card.mismatch { animation: card-shake .4s ease; }
.stage-feedback { max-width: 760px; margin: 17px auto 0; min-height: 38px; display: flex; align-items: center; justify-content: center; gap: 7px; color: #958c9f; font-size: 11px; text-align: center; }
.memory-board.master + .stage-feedback { max-width: 820px; }
.stage-feedback > span { width: 25px; height: 25px; display: grid; place-items: center; border-radius: 50%; background: #ffffffa8; color: #a696bd; flex: none; }
.stage-feedback > span.good { background: #e8f3ea; color: #6d9978; }
.stage-feedback > span > span { width: 14px; height: 14px; }
.stage-tips { display: flex; justify-content: space-between; gap: 12px; max-width: 760px; margin: 13px auto 0; padding-top: 13px; border-top: 1px dashed #e5dbe7; color: #aaa1b3; font-size: 9px; }
.memory-board.master + .stage-feedback + .stage-tips { max-width: 820px; }
.stage-tips > span { display: flex; align-items: center; gap: 4px; }
.stage-tips > span > span { width: 11px; height: 11px; color: #c0a669; }
.primary-action, .secondary-action { min-height: 44px; display: flex; align-items: center; justify-content: center; gap: 7px; border-radius: 7px; font-size: 12px; font-weight: 600; padding: 10px 14px; }
.primary-action { background: var(--memory-violet); color: #fff; border: 1px solid transparent; }
.primary-action:hover { background: #695795; }
.primary-action > span { width: 15px; height: 15px; }
.secondary-action { background: #fff; border: 1px solid var(--memory-border); color: #847c93; }
.secondary-action:hover { background: #faf8fc; }
.memory-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; color: #aaa3b3; font-size: 9px; margin-top: 21px; }
.memory-footer > span { display: flex; align-items: center; gap: 5px; }
.memory-footer > span > span { width: 12px; height: 12px; }
.memory-footer button { color: #a49bb0; text-decoration: underline; text-underline-offset: 3px; }
.result-panel { text-align: center; }
.result-mark { width: 62px; height: 62px; margin: 0 auto 13px; display: grid; place-items: center; border-radius: 50%; background: #f7edd3; color: #c39f54; }
.result-mark > span { width: 31px; height: 31px; }
.result-stars { display: flex; justify-content: center; gap: 9px; margin-bottom: 12px; }
.result-stars > span { width: 27px; height: 27px; color: #e3dee9; }
.result-stars > .earned { color: #dab263; }
.result-panel p { font-size: 12px; color: #8e869b; line-height: 1.8; margin-bottom: 14px; }
.result-panel p strong { color: #6f5b98; }
.result-best { display: inline-flex; align-items: center; gap: 7px; font-size: 10px; color: #a49bb0; margin-bottom: 20px; }
.result-panel .primary-action { width: 100%; }
.help-list { color: #756e84; font-size: 13px; line-height: 1.9; padding-left: 20px; list-style-type: decimal; margin-bottom: 22px; }
.help-list li + li { margin-top: 12px; }
.modal-actions { display: flex; gap: 10px; }
.modal-actions > button { flex: 1; }
@keyframes card-shake { 20% { transform: translateX(-4px); } 55% { transform: translateX(4px); } 85% { transform: translateX(-2px); } }
@media (max-width: 900px) { .memory-content { padding: 26px 24px 16px; } .memory-status { gap: 22px; } .status-best { display: none; } .memory-stage { padding-left: 22px; padding-right: 22px; } }
@media (max-width: 680px) { .memory-heading { align-items: flex-start; } .memory-title h1 { font-size: 28px; } .memory-status { flex-wrap: wrap; gap: 13px 18px; } .pair-progress { order: 5; flex-basis: 100%; max-width: none; } .status-best { display: flex; margin-left: 0; } .status-stat { padding-left: 16px; } .memory-stage { padding: 18px 14px 15px; } .stage-heading { margin-bottom: 14px; } .stage-heading h2 { font-size: 17px; } .memory-board.master { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
@media (max-width: 540px) { .memory-content { padding: 21px 16px 14px; } .memory-heading { flex-wrap: wrap; gap: 12px; margin-bottom: 16px; } .memory-title { width: 100%; } .memory-title h1 { font-size: 27px; } .memory-toolbar { width: 100%; gap: 5px; } .difficulty-switch { margin-right: auto; padding: 3px; } .difficulty-switch button { padding: 0 14px; min-height: 38px; } .round-tool { width: 32px; height: 40px; } .memory-status { padding: 12px 0; margin-bottom: 17px; } .status-title > span { width: 32px; height: 32px; } .status-title strong { font-size: 12px; } .status-stat { font-size: 10px; gap: 5px; } .status-stat strong { font-size: 15px; } .status-best { flex-direction: row; align-items: center; gap: 7px; } .memory-stage { border-radius: 10px; } .stage-heading .eyebrow { font-size: 10px; } .move-note { display: none; } .memory-board { gap: 7px; } .card-face { border-radius: 9px; } .face-kind { top: 6px; left: 6px; font-size: 7px; } .matched-mark { width: 15px; height: 15px; right: 4px; bottom: 4px; } .matched-mark > span { width: 9px; height: 9px; } .stage-feedback { margin-top: 13px; min-height: 34px; font-size: 10px; } .stage-tips { flex-direction: column; gap: 5px; font-size: 8px; } .memory-footer { flex-wrap: wrap; gap: 8px; font-size: 8px; } }
@media (max-width: 360px) { .status-stat:nth-of-type(4) { display: none; } .difficulty-switch button { padding: 0 10px; } .memory-board { gap: 6px; } .card-content strong { font-size: 16px; } .memory-board.master .card-content strong { font-size: 14px; } .memory-stage { padding-left: 11px; padding-right: 11px; } }
@media (prefers-reduced-motion: reduce) { .card-inner { transition: none; } .memory-card.mismatch { animation: none; } }
</style>
