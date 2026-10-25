<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import GameNav from './GameNav.vue'
import {
  advancePoem, checkPoem, clearPoemSelection, newPoem, poemDifficulties, poemHint,
  poemStars, POEM_QUESTIONS, restartPoem, restorePoem, selectPoemTile, switchPoemDifficulty,
  type PoemDifficulty, type PoemTile,
} from './poem-order'

const props = withDefaults(defineProps<{ storageKey?: string }>(), { storageKey: 'lc_game_poem_order_v1_guest' })
function readSave() {
  try { return restorePoem(localStorage.getItem(props.storageKey)) } catch { return null }
}
const save = ref(readSave() || newPoem())
const resetDifficulty = ref<PoemDifficulty | null>(null)
const helpOpen = ref(false)
const saveError = ref(false)
const feedback = ref('')
const hint = ref('')
const round = computed(() => save.value.round)
const question = computed(() => round.value.questions[round.value.index])
const difficulty = computed(() => poemDifficulties.find(item => item.id === save.value.difficulty)!)
const selectedTiles = computed(() => round.value.selected
  .map(id => question.value.tiles.find(tile => tile.id === id))
  .filter((tile): tile is PoemTile => Boolean(tile)))
const answeredCount = computed(() => round.value.finished ? POEM_QUESTIONS : round.value.index + (round.value.solved ? 1 : 0))
const finished = computed(() => round.value.finished)
const stars = computed(() => poemStars(round.value))
const fullPoem = computed(() => question.value.answer
  .map(id => question.value.tiles.find(tile => tile.id === id)?.text ?? ''))
const trayCount = computed(() => question.value.tiles.length)

function pick(tileId: string) {
  if (round.value.solved) return
  if (!selectPoemTile(save.value, tileId)) {
    if (round.value.selected.length >= question.value.lineCount) {
      feedback.value = '四句都排满了。可以点已选的诗句取下来，再换一句。'
    }
    return
  }
  feedback.value = ''
}
function check() {
  if (round.value.selected.length !== question.value.lineCount) {
    feedback.value = `还有 ${question.value.lineCount - round.value.selected.length} 句空着，先把纸条都排好。`
    return
  }
  const result = checkPoem(save.value)
  if (result === null) return
  feedback.value = result
    ? `排对啦！这是${question.value.author}的《${question.value.title}》。`
    : '顺序还不太对，试着从第一句开始，顺着读一读。'
  if (result) hint.value = ''
}
function clearAll() {
  clearPoemSelection(save.value)
  feedback.value = ''
}
function showHint() {
  const text = poemHint(save.value)
  if (text) hint.value = text
}
function next() {
  const result = advancePoem(save.value)
  if (result === null) return
  feedback.value = ''
  hint.value = ''
}
function again() {
  restartPoem(save.value)
  feedback.value = ''
  hint.value = ''
}
function requestDifficulty(id: PoemDifficulty) {
  if (id !== save.value.difficulty) resetDifficulty.value = id
}
function applyDifficulty() {
  if (!resetDifficulty.value) return
  if (resetDifficulty.value === save.value.difficulty) restartPoem(save.value)
  else switchPoemDifficulty(save.value, resetDifficulty.value)
  resetDifficulty.value = null
  feedback.value = ''
  hint.value = ''
}
watch(save, value => {
  try { localStorage.setItem(props.storageKey, JSON.stringify(value)); saveError.value = false }
  catch { saveError.value = true }
}, { deep: true, immediate: true, flush: 'post' })
watch(() => props.storageKey, () => {
  save.value = readSave() || newPoem()
  feedback.value = ''
  hint.value = ''
})
</script>

<template>
  <div class="poem-game">
    <GameNav active="poem-order" />
    <main class="poem-content">
      <header class="poem-heading">
        <div class="poem-title"><span class="eyebrow">拾光诗舍 · 语文诵读</span><h1>诗句排队<span>.</span></h1></div>
        <div class="poem-toolbar">
          <div class="difficulty-switch" role="group" aria-label="游戏难度">
            <button v-for="item in poemDifficulties" :key="item.id" :title="item.age" :aria-pressed="save.difficulty === item.id" :class="{ selected: save.difficulty === item.id }" @click="requestDifficulty(item.id)">{{ item.name }}</button>
          </div>
          <UTooltip text="怎么玩"><button class="round-tool" aria-label="怎么玩" @click="helpOpen = true"><UIcon name="i-lucide-circle-help" /></button></UTooltip>
        </div>
      </header>

      <section class="poem-status" aria-label="排诗进度">
        <div class="status-title"><span><UIcon name="i-lucide-scroll-text" /></span><div><strong>今日诗会</strong><small>{{ difficulty.name }} · {{ difficulty.detail }}</small></div></div>
        <div class="poem-progress">
          <span class="progress-caption">排好的诗<strong>{{ answeredCount }} / {{ POEM_QUESTIONS }}</strong></span>
          <div class="progress-rail" aria-hidden="true"><i v-for="n in POEM_QUESTIONS" :key="n" :class="{ done: n <= answeredCount, current: !finished && !round.solved && n === round.index + 1 }" /></div>
        </div>
        <div class="status-stat"><span><UIcon name="i-lucide-lightbulb" />提示</span><strong>{{ round.hints }}</strong></div>
        <div class="status-stat"><span><UIcon name="i-lucide-pen-line" />重排</span><strong>{{ round.mistakes }}</strong></div>
        <div class="status-best"><span><UIcon name="i-lucide-star" />最佳</span><div class="mini-stars" :aria-label="`${difficulty.name}最佳${save.best[save.difficulty]}颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.best[save.difficulty] }" /></div></div>
      </section>

      <section v-if="!finished" class="poem-board">
        <article class="poem-sheet" aria-label="排诗纸">
          <span class="paper-line line-one" aria-hidden="true" /><span class="paper-line line-two" aria-hidden="true" />
          <div class="sheet-heading">
            <div><span class="sheet-kicker">{{ difficulty.name }} · 第 {{ round.index + 1 }} 首</span><h2>《{{ question.title }}》</h2><p>{{ question.author }}</p></div>
            <span class="seal" aria-hidden="true">诗</span>
          </div>
          <div class="slot-list" role="group" aria-label="诗句顺序">
            <button v-for="index in question.lineCount" :key="index" class="poem-slot" :class="{ filled: selectedTiles[index - 1], done: round.solved }" :data-slot-index="index - 1" :aria-label="selectedTiles[index - 1] ? `取下第${index}句：${selectedTiles[index - 1].text}` : `第${index}句还空着`" @click="selectedTiles[index - 1] && pick(selectedTiles[index - 1].id)">
              <span class="slot-index">{{ index }}</span>
              <strong v-if="selectedTiles[index - 1]">{{ selectedTiles[index - 1].text }}</strong>
              <span v-else class="slot-empty">从这里开始读……</span>
              <UIcon v-if="round.solved" name="i-lucide-check" class="slot-check" />
            </button>
          </div>
          <div v-if="round.solved" class="poem-reveal" role="status" aria-label="排序反馈">
            <span class="reveal-mark"><UIcon name="i-lucide-feather" /></span>
            <p v-for="(line, index) in fullPoem" :key="index">{{ line }}</p>
            <small>—— {{ question.author }}《{{ question.title }}》</small>
          </div>
          <div v-else-if="feedback" class="poem-feedback" role="status" aria-label="排序反馈"><UIcon name="i-lucide-message-circle" />{{ feedback }}</div>
          <div v-else class="poem-tip"><UIcon name="i-lucide-mouse-pointer-2" />按顺序点选诗句，再排到上面的诗笺里。</div>
        </article>

        <aside class="tile-tray" aria-label="诗句纸条">
          <div class="tray-heading"><div><UIcon name="i-lucide-notes" /><h2>诗句纸条</h2></div><span>{{ trayCount }} 张</span></div>
          <p class="tray-copy">{{ save.difficulty === 'master' ? '有一句不属于这首诗，排的时候要把它留下来。' : '读一读每张纸条，把它们排成一首完整的诗。' }}</p>
          <div class="tile-list" role="group" aria-label="诗句纸条">
            <button v-for="tile in question.tiles" :key="tile.id" class="poem-tile" :class="{ picked: round.selected.includes(tile.id), hinted: hint && tile.text === hint }" :data-tile-id="tile.id" :aria-pressed="round.selected.includes(tile.id)" :aria-label="`诗句 ${tile.text}`" :disabled="round.solved" @click="pick(tile.id)">
              <span class="tile-grip" aria-hidden="true"><i /><i /><i /></span>
              <strong>{{ tile.text }}</strong>
              <span v-if="round.selected.includes(tile.id)" class="tile-order">{{ round.selected.indexOf(tile.id) + 1 }}</span>
            </button>
          </div>
          <div v-if="hint && !round.solved" class="tray-hint" role="status"><UIcon name="i-lucide-lightbulb" />第一句是「{{ hint }}」</div>
          <div class="tray-actions">
            <button class="ghost-button" :disabled="!round.selected.length || round.solved" @click="clearAll"><UIcon name="i-lucide-undo-2" />全部取下</button>
            <button class="hint-button" :disabled="round.solved" @click="showHint"><UIcon name="i-lucide-lightbulb" />{{ hint ? '再提示一次' : '给我提示' }}</button>
          </div>
          <button v-if="!round.solved" class="primary-action" :disabled="round.selected.length !== question.lineCount" @click="check"><UIcon name="i-lucide-book-open-check" />排好了，读一读<UIcon name="i-lucide-arrow-right" /></button>
          <button v-else class="primary-action" @click="next">{{ round.index === POEM_QUESTIONS - 1 ? '查看诗会成绩' : '下一首诗' }}<UIcon name="i-lucide-arrow-right" /></button>
        </aside>
      </section>

      <section v-else class="poem-report">
        <div class="report-stars" :aria-label="`本局获得${stars}颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= stars }" /></div>
        <span class="eyebrow">第 {{ save.rounds }} 次诗会 · {{ difficulty.name }}</span>
        <h2>{{ stars === 3 ? '一字不差，小诗人真棒！' : '诗都排好啦，再读一遍会更熟！' }}</h2>
        <p>{{ round.mistakes === 0 ? '八首诗一次排对，诗句的顺序记得真牢。' : `这次重排了 ${round.mistakes} 次，翻开提示 ${round.hints} 次，多读几遍就记住啦。` }}</p>
        <div class="report-stats">
          <div><span>完成诗篇</span><strong>{{ POEM_QUESTIONS }}<small> 首</small></strong></div>
          <div><span>重排次数</span><strong>{{ round.mistakes }}<small> 次</small></strong></div>
          <div><span>累计诵读</span><strong>{{ save.totalPoems }}<small> 首</small></strong></div>
        </div>
        <div class="report-best"><span>最佳记录</span><div v-for="item in poemDifficulties" :key="item.id" :class="{ active: item.id === save.difficulty }"><span>{{ item.name }}</span><i><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.best[item.id] }" /></i></div></div>
        <div class="report-actions"><button class="secondary-action" @click="helpOpen = true"><UIcon name="i-lucide-circle-help" />看看玩法</button><button class="primary-action" @click="again"><UIcon name="i-lucide-rotate-ccw" />再来一局</button></div>
      </section>

      <footer class="poem-footer"><span><UIcon name="i-lucide-heart" />每一次尝试，都是成长</span><span role="status" aria-label="进度保存状态"><UIcon :name="saveError ? 'i-lucide-cloud-off' : 'i-lucide-cloud-check'" />{{ saveError ? '本机暂时无法保存进度' : '进度已保存在本机' }}</span></footer>
    </main>

    <UModal :open="helpOpen" title="把诗句排成一首诗" description="读一读纸条，按诗里的顺序点选。" :close="{ 'aria-label': '关闭玩法说明' }" :ui="{ content: 'game-modal' }" @update:open="helpOpen = $event"><template #body><ol class="help-list"><li>先看诗题和作者，想一想这首诗是怎么背的。</li><li>按第一句到最后一句的顺序，点选右边的诗句纸条。</li><li>点错了可以再点一次取下，也可以点诗笺里的句子取下来。</li><li>四句排满后点“排好了，读一读”。全部排对就能进入下一首。</li><li>挑战难度会多出一句别的诗，要多读一遍把它认出来。</li></ol><button class="primary-action" @click="helpOpen = false">明白了，开始排诗<UIcon name="i-lucide-scroll-text" /></button></template></UModal>
    <UModal :open="resetDifficulty !== null" :title="resetDifficulty === save.difficulty ? '重新开始这场诗会？' : '切换游戏难度？'" description="新的诗会会从第一首开始，当前进度会清空，最佳记录会保留。" :close="{ 'aria-label': '关闭难度确认' }" :ui="{ content: 'game-modal' }" @update:open="!$event && (resetDifficulty = null)"><template #body><div class="modal-actions"><button class="secondary-action" @click="resetDifficulty = null">继续当前诗会</button><button class="primary-action" @click="applyDifficulty">{{ resetDifficulty === save.difficulty ? '重新开始' : '切换并开始' }}<UIcon name="i-lucide-arrow-right" /></button></div></template></UModal>
  </div>
</template>

<style scoped>
.poem-game { --poem-ink: #3d3a31; --poem-muted: #948c7b; --poem-green: #557862; --poem-red: #b2553e; --poem-border: #e6ddca; min-height: 100dvh; background: #f8f3e7; color: var(--poem-ink); font-family: var(--font-ui); letter-spacing: 0; }
.poem-game button { cursor: pointer; transition: background .16s, transform .16s, box-shadow .16s; }
.poem-game button:disabled { cursor: default; }
.poem-game button:focus-visible { outline: 3px solid #9c8e6a; outline-offset: 3px; }
.poem-content { max-width: 1160px; margin: auto; padding: 30px 36px 18px; }
.eyebrow { display: block; color: var(--poem-muted); font-size: 11px; line-height: 1.6; }
.poem-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 22px; }
.poem-title h1 { font-size: 32px; font-weight: 750; line-height: 1.35; margin: 3px 0 0; }
.poem-title h1 > span { color: var(--poem-red); margin-left: 3px; }
.poem-toolbar { display: flex; align-items: center; gap: 9px; }
.difficulty-switch { display: flex; align-items: center; gap: 3px; background: #efe8d8; padding: 4px; border-radius: 8px; margin-right: 6px; }
.difficulty-switch button { height: 35px; padding: 0 15px; background: transparent; border-radius: 5px; color: #9b9280; font-size: 12px; white-space: nowrap; }
.difficulty-switch button.selected { color: var(--poem-green); background: #fffdf7; box-shadow: 0 1px 4px #3d3a3114; font-weight: 650; }
.round-tool { width: 36px; height: 36px; display: grid; place-items: center; color: #968d7a; background: transparent; border-radius: 6px; }
.round-tool:hover { background: #efe8d8; }
.round-tool > span { width: 18px; height: 18px; }
.poem-status { display: flex; align-items: center; gap: 34px; padding: 15px 0; border-top: 1px solid var(--poem-border); border-bottom: 1px solid var(--poem-border); margin-bottom: 22px; }
.status-title { display: flex; align-items: center; gap: 11px; }
.status-title > span { width: 38px; height: 38px; display: grid; place-items: center; background: #e9eee4; color: #62806b; border-radius: 50%; }
.status-title > span > span { width: 20px; height: 20px; }
.status-title > div { display: flex; flex-direction: column; gap: 3px; }
.status-title strong { font-size: 13px; font-weight: 650; }
.status-title small { font-size: 10px; color: var(--poem-muted); }
.poem-progress { flex: 1; max-width: 300px; display: flex; flex-direction: column; gap: 7px; }
.progress-caption { display: flex; justify-content: space-between; gap: 10px; color: var(--poem-muted); font-size: 10px; }
.progress-caption strong { color: var(--poem-green); font-weight: 600; font-variant-numeric: tabular-nums; }
.progress-rail { display: flex; gap: 5px; }
.progress-rail i { flex: 1; height: 5px; border-radius: 4px; background: #ece5d6; transition: background .3s; }
.progress-rail i.done { background: #7d9a84; }
.progress-rail i.current { background: #cba268; box-shadow: 0 0 0 3px #cba26826; }
.status-stat { display: flex; align-items: center; gap: 7px; color: var(--poem-muted); font-size: 11px; border-left: 1px solid var(--poem-border); padding-left: 22px; }
.status-stat > span { display: flex; align-items: center; gap: 4px; }
.status-stat > span > span { width: 14px; height: 14px; color: #bfa164; }
.status-stat strong { font-size: 17px; color: var(--poem-ink); font-variant-numeric: tabular-nums; }
.status-best { display: flex; flex-direction: column; gap: 5px; margin-left: auto; color: var(--poem-muted); font-size: 10px; }
.status-best > span { display: flex; align-items: center; gap: 4px; }
.status-best > span > span { width: 13px; height: 13px; color: #bfa164; }
.mini-stars { display: flex; gap: 3px; }
.mini-stars > span { width: 13px; height: 13px; color: #e5dece; }
.mini-stars > .earned { color: #d2a758; }
.poem-board { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(320px, .85fr); gap: 24px; align-items: stretch; }
.poem-sheet { position: relative; overflow: hidden; padding: 30px clamp(20px, 4vw, 42px) 28px; border: 1px solid #e2d6bf; border-radius: 10px; background: linear-gradient(160deg, #fffdf6, #fbf6e9); box-shadow: 0 10px 28px #8b79551a; }
.paper-line { position: absolute; top: 0; bottom: 0; width: 1px; background: #e8ddc7; }
.line-one { left: 34px; }.line-two { right: 34px; }
.sheet-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding-bottom: 20px; border-bottom: 1px dashed #e3d7c0; }
.sheet-kicker { color: var(--poem-red); font-size: 10px; letter-spacing: 1px; }
.sheet-heading h2 { margin: 7px 0 3px; font-size: 27px; font-weight: 700; letter-spacing: 2px; }
.sheet-heading p { color: var(--poem-muted); font-size: 11px; }
.seal { flex: none; width: 38px; height: 38px; display: grid; place-items: center; border: 2px solid #bf6550; border-radius: 5px; color: #b2553e; font-size: 19px; font-weight: 700; transform: rotate(4deg); opacity: .85; }
.slot-list { display: flex; flex-direction: column; gap: 9px; margin-top: 20px; }
.poem-slot { display: flex; align-items: center; gap: 12px; width: 100%; min-height: 49px; padding: 8px 14px; border: 1px dashed #dfd2b9; border-radius: 7px; background: #fffbef; color: #4b463b; text-align: left; }
.poem-slot.filled { border-style: solid; border-color: #cfd9c8; background: #f5f8ef; }
.poem-slot.filled:not(.done):hover { border-color: #a9bfa4; transform: translateX(2px); }
.poem-slot.done { border-color: #b9d0bd; background: #eff5ea; }
.slot-index { flex: none; width: 22px; height: 22px; display: grid; place-items: center; border-radius: 50%; background: #eee5d3; color: #9b8c6f; font-size: 10px; font-variant-numeric: tabular-nums; }
.poem-slot.filled .slot-index { background: #dfe9d8; color: #5f7f67; }
.slot-empty { color: #b7ac97; font-size: 12px; letter-spacing: 1px; }
.poem-slot strong { font-size: clamp(17px, 2.4vw, 21px); font-weight: 600; letter-spacing: 3px; }
.slot-check { margin-left: auto; width: 17px; height: 17px; color: #6f9478; }
.poem-reveal { display: flex; flex-direction: column; align-items: center; gap: 4px; margin-top: 19px; padding: 15px 12px 13px; background: #f3f7ed; border-radius: 8px; animation: reveal-in .35s ease; }
.reveal-mark { width: 29px; height: 29px; display: grid; place-items: center; border-radius: 50%; background: #e2ecd9; color: #65856c; margin-bottom: 3px; }
.reveal-mark > span { width: 16px; height: 16px; }
.poem-reveal p { font-size: 15px; letter-spacing: 4px; line-height: 1.9; color: #556b58; }
.poem-reveal small { margin-top: 4px; color: #8b9b84; font-size: 10px; }
.poem-feedback { display: flex; align-items: flex-start; gap: 7px; margin-top: 18px; padding: 11px 12px; border-radius: 7px; background: #fbf0e2; color: #a4754f; font-size: 11px; line-height: 1.8; }
.poem-feedback > span { width: 15px; height: 15px; flex: none; margin-top: 1px; }
.poem-tip { display: flex; align-items: center; gap: 6px; margin-top: 18px; color: #aaa08b; font-size: 10px; }
.poem-tip > span { width: 14px; height: 14px; }
.tile-tray { display: flex; flex-direction: column; padding: 24px; border: 1px solid var(--poem-border); border-radius: 10px; background: #fffdf8; }
.tray-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-bottom: 13px; border-bottom: 1px solid #f0e9da; }
.tray-heading > div { display: flex; align-items: center; gap: 8px; }
.tray-heading > div > span { width: 19px; height: 19px; color: #7e917d; }
.tray-heading h2 { font-size: 16px; font-weight: 700; }
.tray-heading > span { padding: 4px 8px; border-radius: 20px; background: #f3eddf; color: #9c8f77; font-size: 10px; }
.tray-copy { margin: 13px 0 15px; color: #9b917e; font-size: 10px; line-height: 1.8; }
.tile-list { display: flex; flex-direction: column; gap: 8px; }
.poem-tile { position: relative; display: flex; align-items: center; gap: 9px; min-height: 45px; padding: 8px 36px 8px 12px; border: 1px solid #e3d9c6; border-radius: 6px; background: #fffaf0; color: #5a5345; text-align: left; }
.poem-tile:not(:disabled):hover { border-color: #c8b791; background: #fff7e6; transform: translateX(2px); }
.poem-tile.picked { border-color: #b7c9b1; background: #eff5e9; color: #5b715f; }
.poem-tile.hinted:not(.picked) { border-color: #d9b471; box-shadow: 0 0 0 3px #d9b47122; }
.poem-tile strong { font-size: 15px; font-weight: 600; letter-spacing: 3px; }
.tile-grip { display: flex; flex-direction: column; gap: 2px; flex: none; opacity: .5; }
.tile-grip i { width: 4px; height: 1px; background: currentColor; }
.tile-order { position: absolute; right: 10px; width: 20px; height: 20px; display: grid; place-items: center; border-radius: 50%; background: #dfe9d8; color: #64806a; font-size: 10px; }
.tray-hint { display: flex; align-items: flex-start; gap: 6px; margin-top: 12px; padding: 9px 10px; border-radius: 6px; background: #fcf3dd; color: #a08148; font-size: 10px; line-height: 1.7; }
.tray-hint > span { width: 13px; height: 13px; flex: none; margin-top: 1px; }
.tray-actions { display: flex; gap: 8px; margin: 15px 0 12px; }
.ghost-button, .hint-button { display: flex; flex: 1; align-items: center; justify-content: center; gap: 5px; min-height: 38px; border-radius: 6px; font-size: 10px; }
.ghost-button { background: #faf6ec; border: 1px solid #ece4d4; color: #9c927e; }
.ghost-button:disabled { opacity: .55; }
.hint-button { background: #fffaf0; border: 1px solid #e3d9c6; color: #9b814e; }
.hint-button:disabled { opacity: .55; }
.ghost-button > span, .hint-button > span { width: 13px; height: 13px; }
.primary-action, .secondary-action { min-height: 44px; display: flex; align-items: center; justify-content: center; gap: 7px; border-radius: 7px; font-size: 12px; font-weight: 600; padding: 10px 14px; }
.primary-action { background: var(--poem-green); color: #fff; border: 1px solid transparent; }
.primary-action:hover { background: #486a54; }
.primary-action:disabled { background: #d9d3c4; color: #fffdf6; }
.primary-action > span { width: 15px; height: 15px; }
.tile-tray .primary-action { width: 100%; margin-top: auto; }
.secondary-action { background: #fffdf8; border: 1px solid var(--poem-border); color: #8e846f; }
.poem-report { padding: 34px clamp(20px, 6vw, 70px); border: 1px solid var(--poem-border); border-radius: 10px; background: #fffdf8; text-align: center; }
.report-stars { display: flex; justify-content: center; gap: 10px; margin-bottom: 14px; }
.report-stars > span { width: 34px; height: 34px; color: #e7e0d2; }
.report-stars > .earned { color: #d7ad5d; filter: drop-shadow(0 2px 5px #d7ad5d2e); }
.poem-report h2 { font-size: 24px; margin: 5px 0 8px; }
.poem-report > p { color: var(--poem-muted); font-size: 11px; line-height: 1.8; }
.report-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); max-width: 480px; margin: 22px auto; padding: 17px 0; border-top: 1px dashed var(--poem-border); border-bottom: 1px dashed var(--poem-border); }
.report-stats div { display: flex; flex-direction: column; gap: 7px; }
.report-stats div + div { border-left: 1px solid #f1ebde; }
.report-stats span { font-size: 10px; color: var(--poem-muted); }
.report-stats strong { font-size: 23px; color: var(--poem-green); }
.report-stats small { font-size: 11px; font-weight: 400; color: #a49b88; }
.report-best { display: flex; justify-content: center; flex-wrap: wrap; gap: 8px 20px; color: var(--poem-muted); font-size: 10px; margin-bottom: 22px; }
.report-best > span { font-weight: 600; }
.report-best > div { display: flex; align-items: center; gap: 5px; }
.report-best > div.active { color: var(--poem-green); font-weight: 600; }
.report-best i { display: flex; gap: 2px; font-style: normal; }
.report-best i > span { width: 12px; height: 12px; color: #e7e0d2; }
.report-best i > .earned { color: #d7ad5d; }
.report-actions { display: flex; justify-content: center; gap: 10px; max-width: 410px; margin: auto; }
.report-actions .primary-action { flex: 1.3; }
.report-actions .secondary-action { flex: 1; }
.poem-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; color: #aaa190; font-size: 9px; margin-top: 21px; }
.poem-footer > span { display: flex; align-items: center; gap: 5px; }
.poem-footer > span > span { width: 12px; height: 12px; }
.help-list { color: #7c7566; font-size: 13px; line-height: 1.9; padding-left: 20px; list-style-type: decimal; margin-bottom: 22px; }
.help-list li + li { margin-top: 12px; }
.modal-actions { display: flex; gap: 10px; }
.modal-actions > button { flex: 1; }
@keyframes reveal-in { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: none; } }
@media (max-width: 980px) { .poem-content { padding: 26px 24px 16px; } .poem-board { grid-template-columns: minmax(0, 1fr) minmax(300px, .9fr); gap: 18px; } .poem-status { gap: 22px; } .status-best { display: none; } }
@media (max-width: 760px) { .poem-heading { align-items: flex-start; } .poem-title h1 { font-size: 28px; } .poem-board { grid-template-columns: minmax(0, 1fr); } .poem-status { flex-wrap: wrap; gap: 14px 22px; } .poem-progress { order: 5; flex-basis: 100%; max-width: none; } .status-best { display: flex; margin-left: 0; } .status-stat { padding-left: 16px; } }
@media (max-width: 540px) { .poem-content { padding: 21px 16px 14px; } .poem-heading { flex-wrap: wrap; gap: 12px; margin-bottom: 16px; } .poem-title { width: 100%; } .poem-title h1 { font-size: 27px; } .poem-toolbar { width: 100%; gap: 5px; } .difficulty-switch { margin-right: auto; padding: 3px; } .difficulty-switch button { padding: 0 12px; min-height: 38px; font-size: 11px; } .round-tool { width: 32px; height: 40px; } .poem-status { padding: 12px 0; margin-bottom: 16px; gap: 12px 14px; } .status-title > span { width: 32px; height: 32px; } .status-title strong { font-size: 12px; } .status-stat { font-size: 10px; gap: 5px; } .status-stat strong { font-size: 15px; } .status-best { flex-direction: row; align-items: center; gap: 7px; } .poem-sheet { padding: 23px 18px 22px; } .paper-line { display: none; } .sheet-heading h2 { font-size: 23px; } .seal { width: 32px; height: 32px; font-size: 16px; } .poem-slot { gap: 9px; padding: 7px 10px; } .poem-slot strong { letter-spacing: 2px; } .poem-slot .slot-empty { font-size: 11px; } .poem-reveal p { font-size: 14px; letter-spacing: 2px; } .tile-tray { padding: 20px 16px; } .poem-tile strong { font-size: 14px; letter-spacing: 2px; } .poem-footer { font-size: 8px; } .poem-report { padding: 26px 18px; } .poem-report h2 { font-size: 20px; } .report-stars > span { width: 28px; height: 28px; } .report-actions { flex-direction: column-reverse; } .report-actions .primary-action, .report-actions .secondary-action { flex: none; } }
@media (max-width: 360px) { .status-stat:nth-of-type(4) { display: none; } .difficulty-switch button { padding: 0 9px; } .sheet-heading h2 { font-size: 21px; } .poem-slot strong { font-size: 16px; } }
@media (prefers-reduced-motion: reduce) { .poem-reveal { animation: none; } .poem-slot.filled:hover, .poem-tile:hover { transform: none; } }
</style>
