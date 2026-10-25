<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import GameNav from './GameNav.vue'
import {
  advanceSpell, checkSpell, clearSpellSelection, newSpell, restoreSpell, selectSpellTile,
  SPELL_QUESTIONS, spellDifficulties, spellHint, spellStars, restartSpell, switchSpellDifficulty,
  type SpellDifficulty, type SpellTile,
} from './word-spell'

const props = withDefaults(defineProps<{ storageKey?: string }>(), { storageKey: 'lc_game_word_spell_v1_guest' })
function readSave() {
  try { return restoreSpell(localStorage.getItem(props.storageKey)) } catch { return null }
}
const save = ref(readSave() || newSpell())
const resetDifficulty = ref<SpellDifficulty | null>(null)
const helpOpen = ref(false)
const saveError = ref(false)
const feedback = ref('')
const hintLetter = ref('')
const round = computed(() => save.value.round)
const question = computed(() => round.value.questions[round.value.index])
const difficulty = computed(() => spellDifficulties.find(item => item.id === save.value.difficulty)!)
const selectedTiles = computed(() => round.value.selected
  .map(id => question.value.tiles.find(tile => tile.id === id))
  .filter((tile): tile is SpellTile => Boolean(tile)))
const solved = computed(() => round.value.solved)
const finished = computed(() => round.value.finished)
const stars = computed(() => spellStars(round.value))
const answeredCount = computed(() => finished.value ? SPELL_QUESTIONS : round.value.index + (solved.value ? 1 : 0))
const firstLetter = computed(() => question.value.word[0])

function pick(tileId: string) {
  if (solved.value) return
  if (!selectSpellTile(save.value, tileId)) {
    if (round.value.selected.length >= question.value.word.length) feedback.value = '字母已经排满了，可以先取下一个再换。'
    return
  }
  feedback.value = ''
}
function check() {
  if (round.value.selected.length !== question.value.word.length) {
    feedback.value = `还差 ${question.value.word.length - round.value.selected.length} 个字母，把单词排满吧。`
    return
  }
  const result = checkSpell(save.value)
  if (result === null) return
  feedback.value = result ? '' : '字母都在，顺序还不对。听一听开头，再排一次。'
}
function clearAll() {
  clearSpellSelection(save.value)
  feedback.value = ''
}
function showHint() {
  const letter = spellHint(save.value)
  if (letter) hintLetter.value = letter
}
function next() {
  if (advanceSpell(save.value) === null) return
  feedback.value = ''
  hintLetter.value = ''
}
function again() {
  restartSpell(save.value)
  feedback.value = ''
  hintLetter.value = ''
}
function speak(word: string) {
  try {
    if (!('speechSynthesis' in window)) return
    const utterance = new SpeechSynthesisUtterance(word)
    utterance.lang = 'en-US'
    utterance.rate = .78
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(utterance)
  } catch { /* 浏览器不支持朗读时静默跳过 */ }
}
function requestDifficulty(id: SpellDifficulty) {
  if (id !== save.value.difficulty) resetDifficulty.value = id
}
function applyDifficulty() {
  if (!resetDifficulty.value) return
  if (resetDifficulty.value === save.value.difficulty) restartSpell(save.value)
  else switchSpellDifficulty(save.value, resetDifficulty.value)
  resetDifficulty.value = null
  feedback.value = ''
  hintLetter.value = ''
}
watch(save, value => {
  try { localStorage.setItem(props.storageKey, JSON.stringify(value)); saveError.value = false }
  catch { saveError.value = true }
}, { deep: true, immediate: true, flush: 'post' })
watch(() => props.storageKey, () => {
  save.value = readSave() || newSpell()
  feedback.value = ''
  hintLetter.value = ''
})
</script>

<template>
  <div class="spell-game">
    <GameNav active="word-spell" />
    <main class="spell-content">
      <header class="spell-heading">
        <div class="spell-title"><span class="eyebrow">拼词星球 · 英语启蒙</span><h1>单词拼写<span>.</span></h1></div>
        <div class="spell-toolbar">
          <div class="difficulty-switch" role="group" aria-label="游戏难度">
            <button v-for="item in spellDifficulties" :key="item.id" :title="item.age" :aria-pressed="save.difficulty === item.id" :class="{ selected: save.difficulty === item.id }" @click="requestDifficulty(item.id)">{{ item.name }}</button>
          </div>
          <UTooltip text="怎么玩"><button class="round-tool" aria-label="怎么玩" @click="helpOpen = true"><UIcon name="i-lucide-circle-help" /></button></UTooltip>
        </div>
      </header>

      <section class="spell-status" aria-label="拼词进度">
        <div class="status-title"><span><UIcon name="i-lucide-spell-check-2" /></span><div><strong>拼词任务</strong><small>{{ difficulty.name }} · {{ difficulty.detail }}</small></div></div>
        <div class="spell-progress">
          <span class="progress-caption">拼好的单词<strong>{{ answeredCount }} / {{ SPELL_QUESTIONS }}</strong></span>
          <div class="progress-rail" aria-hidden="true"><i v-for="n in SPELL_QUESTIONS" :key="n" :class="{ done: n <= answeredCount, current: !finished && !solved && n === round.index + 1 }" /></div>
        </div>
        <div class="status-stat"><span><UIcon name="i-lucide-lightbulb" />提示</span><strong>{{ round.hints }}</strong></div>
        <div class="status-stat"><span><UIcon name="i-lucide-refresh-cw" />重拼</span><strong>{{ round.mistakes }}</strong></div>
        <div class="status-best"><span><UIcon name="i-lucide-star" />最佳</span><div class="mini-stars" :aria-label="`${difficulty.name}最佳${save.best[save.difficulty]}颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.best[save.difficulty] }" /></div></div>
      </section>

      <section v-if="!finished" class="spell-board">
        <div class="word-scene" aria-label="单词提示">
          <span class="scene-orbit orbit-a" aria-hidden="true" /><span class="scene-orbit orbit-b" aria-hidden="true" />
          <span class="scene-star star-a" aria-hidden="true">✦</span><span class="scene-star star-b" aria-hidden="true">✦</span><span class="scene-star star-c" aria-hidden="true">·</span>
          <div class="emoji-card"><span class="word-emoji" role="img" :aria-label="question.meaning">{{ question.emoji }}</span><span class="emoji-shadow" aria-hidden="true" /></div>
          <span class="meaning-pill">{{ question.meaning }}</span>
          <div class="scene-copy"><span>请拼出这个单词</span><strong>{{ question.word.length }} 个字母</strong></div>
          <div class="scene-footer"><span><i />第 {{ round.index + 1 }} 个单词</span><span>{{ solved ? '拼对啦！' : '慢慢来，你可以的' }}</span></div>
        </div>

        <div class="spell-panel">
          <div class="panel-heading"><div><span class="panel-kicker">拼写纸</span><h2>{{ solved ? question.word : '把字母排成单词' }}</h2></div><span v-if="solved" class="solved-mark"><UIcon name="i-lucide-party-popper" /></span></div>
          <div class="letter-slots" :class="{ solved }" role="group" aria-label="单词字母顺序">
            <button v-for="index in question.word.length" :key="index" class="letter-slot" :class="{ filled: selectedTiles[index - 1], done: solved }" :data-slot-index="index - 1" :aria-label="selectedTiles[index - 1] ? `取下第${index}个字母 ${selectedTiles[index - 1].letter}` : `第${index}个字母还空着`" :disabled="solved" @click="selectedTiles[index - 1] && pick(selectedTiles[index - 1].id)">
              <strong v-if="selectedTiles[index - 1]">{{ selectedTiles[index - 1].letter }}</strong>
              <span v-else aria-hidden="true">·</span>
            </button>
          </div>
          <div class="letter-bank" role="group" aria-label="字母卡片">
            <button v-for="tile in question.tiles" :key="tile.id" class="letter-tile" :class="{ picked: round.selected.includes(tile.id), hinted: !solved && hintLetter && tile.letter === hintLetter }" :data-tile-id="tile.id" :aria-pressed="round.selected.includes(tile.id)" :aria-label="`字母 ${tile.letter}`" :disabled="solved" @click="pick(tile.id)">{{ tile.letter }}<small v-if="round.selected.includes(tile.id)">{{ round.selected.indexOf(tile.id) + 1 }}</small></button>
          </div>
          <div v-if="hintLetter && !solved" class="spell-hint" role="status"><UIcon name="i-lucide-lightbulb" />第一个字母是「{{ firstLetter }}」</div>
          <div v-if="solved" class="solved-card" role="status" aria-label="答题反馈">
            <span class="solved-icon"><UIcon name="i-lucide-circle-check" /></span>
            <div><strong>拼对啦！</strong><p>{{ question.word }} · {{ question.meaning }}</p></div>
            <button class="speak-button" :aria-label="`朗读单词 ${question.word}`" @click="speak(question.word)"><UIcon name="i-lucide-volume-2" /></button>
          </div>
          <div v-else-if="feedback" class="spell-feedback" role="status" aria-label="答题反馈"><UIcon name="i-lucide-message-circle" />{{ feedback }}</div>
          <div v-else class="spell-tip"><UIcon name="i-lucide-mouse-pointer-2" />点字母卡片放进上面的格子里，点错了再点一次取回。</div>
          <div class="panel-actions"><button class="ghost-button" :disabled="!round.selected.length || solved" @click="clearAll"><UIcon name="i-lucide-undo-2" />清空</button><button class="hint-button" :disabled="solved" @click="showHint"><UIcon name="i-lucide-lightbulb" />{{ hintLetter ? '再提示一次' : '第一个字母' }}</button></div>
          <button v-if="!solved" class="primary-action" :disabled="round.selected.length !== question.word.length" @click="check"><UIcon name="i-lucide-spell-check-2" />检查拼写<UIcon name="i-lucide-arrow-right" /></button>
          <button v-else class="primary-action" @click="next">{{ round.index === SPELL_QUESTIONS - 1 ? '查看拼词报告' : '下一个单词' }}<UIcon name="i-lucide-arrow-right" /></button>
        </div>
      </section>

      <section v-else class="spell-report">
        <div class="report-stars" :aria-label="`本局获得${stars}颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= stars }" /></div>
        <span class="eyebrow">第 {{ save.rounds }} 次拼词 · {{ difficulty.name }}</span>
        <h2>{{ stars === 3 ? '字母排得整整齐齐，拼词小能手！' : '单词都拼好啦，再读一遍会更熟！' }}</h2>
        <p>{{ round.mistakes === 0 ? '八个单词一次拼对，字母顺序记得真清楚。' : `这次重新拼了 ${round.mistakes} 次，试着按发音一段一段地记字母。` }}</p>
        <div class="report-stats">
          <div><span>拼对单词</span><strong>{{ SPELL_QUESTIONS }}<small> 个</small></strong></div>
          <div><span>重新拼写</span><strong>{{ round.mistakes }}<small> 次</small></strong></div>
          <div><span>累计单词</span><strong>{{ save.totalWords }}<small> 个</small></strong></div>
        </div>
        <div class="report-best"><span>最佳记录</span><div v-for="item in spellDifficulties" :key="item.id" :class="{ active: item.id === save.difficulty }"><span>{{ item.name }}</span><i><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.best[item.id] }" /></i></div></div>
        <div class="report-actions"><button class="secondary-action" @click="helpOpen = true"><UIcon name="i-lucide-circle-help" />看看玩法</button><button class="primary-action" @click="again"><UIcon name="i-lucide-rotate-ccw" />再拼一组</button></div>
      </section>

      <footer class="spell-footer"><span><UIcon name="i-lucide-heart" />每一次尝试，都是成长</span><span role="status" aria-label="进度保存状态"><UIcon :name="saveError ? 'i-lucide-cloud-off' : 'i-lucide-cloud-check'" />{{ saveError ? '本机暂时无法保存进度' : '进度已保存在本机' }}</span></footer>
    </main>

    <UModal :open="helpOpen" title="看图片，拼单词" description="把打乱的字母排成正确的英文单词。" :close="{ 'aria-label': '关闭玩法说明' }" :ui="{ content: 'game-modal' }" @update:open="helpOpen = $event"><template #body><ol class="help-list"><li>先看看图片和中文意思，想一想对应的英文单词。</li><li>按字母顺序点选下面的字母卡片，字母会排进上面的格子里。</li><li>点错了就再点一次字母卡片，或者点格子里的字母取下来。</li><li>排满后点“检查拼写”。拼对后可以按小喇叭听一听单词的读音。</li><li>同一个单词可能有重复的字母，看清每个字母卡片右下角的序号哦。</li></ol><button class="primary-action" @click="helpOpen = false">明白了，开始拼词<UIcon name="i-lucide-spell-check-2" /></button></template></UModal>
    <UModal :open="resetDifficulty !== null" :title="resetDifficulty === save.difficulty ? '重新开始这组单词？' : '切换游戏难度？'" description="新的单词会从第一个开始，当前进度会清空，最佳记录会保留。" :close="{ 'aria-label': '关闭难度确认' }" :ui="{ content: 'game-modal' }" @update:open="!$event && (resetDifficulty = null)"><template #body><div class="modal-actions"><button class="secondary-action" @click="resetDifficulty = null">继续当前拼写</button><button class="primary-action" @click="applyDifficulty">{{ resetDifficulty === save.difficulty ? '重新开始' : '切换并开始' }}<UIcon name="i-lucide-arrow-right" /></button></div></template></UModal>
  </div>
</template>

<style scoped>
.spell-game { --spell-ink: #2f4748; --spell-muted: #84999a; --spell-teal: #3f8580; --spell-border: #dceae7; min-height: 100dvh; background: #f4faf9; color: var(--spell-ink); font-family: var(--font-ui); letter-spacing: 0; }
.spell-game button { cursor: pointer; transition: background .16s, transform .16s, box-shadow .16s; }
.spell-game button:disabled { cursor: default; }
.spell-game button:focus-visible { outline: 3px solid #76a9b8; outline-offset: 3px; }
.spell-content { max-width: 1120px; margin: auto; padding: 30px 36px 18px; }
.eyebrow { display: block; color: var(--spell-muted); font-size: 11px; line-height: 1.6; }
.spell-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 22px; }
.spell-title h1 { font-size: 32px; font-weight: 750; line-height: 1.35; margin: 3px 0 0; }
.spell-title h1 > span { color: #e39a67; margin-left: 3px; }
.spell-toolbar { display: flex; align-items: center; gap: 9px; }
.difficulty-switch { display: flex; align-items: center; gap: 3px; background: #e8f2f0; padding: 4px; border-radius: 8px; margin-right: 6px; }
.difficulty-switch button { height: 35px; padding: 0 15px; background: transparent; border-radius: 5px; color: #8ea4a3; font-size: 12px; white-space: nowrap; }
.difficulty-switch button.selected { color: var(--spell-teal); background: #fff; box-shadow: 0 1px 4px #2f474814; font-weight: 650; }
.round-tool { width: 36px; height: 36px; display: grid; place-items: center; color: #8ba1a0; background: transparent; border-radius: 6px; }
.round-tool:hover { background: #e8f2f0; }
.round-tool > span { width: 18px; height: 18px; }
.spell-status { display: flex; align-items: center; gap: 34px; padding: 15px 0; border-top: 1px solid var(--spell-border); border-bottom: 1px solid var(--spell-border); margin-bottom: 22px; }
.status-title { display: flex; align-items: center; gap: 11px; }
.status-title > span { width: 38px; height: 38px; display: grid; place-items: center; background: #e3f2ef; color: #4e918a; border-radius: 50%; }
.status-title > span > span { width: 20px; height: 20px; }
.status-title > div { display: flex; flex-direction: column; gap: 3px; }
.status-title strong { font-size: 13px; font-weight: 650; }
.status-title small { font-size: 10px; color: var(--spell-muted); }
.spell-progress { flex: 1; max-width: 300px; display: flex; flex-direction: column; gap: 7px; }
.progress-caption { display: flex; justify-content: space-between; gap: 10px; color: var(--spell-muted); font-size: 10px; }
.progress-caption strong { color: var(--spell-teal); font-weight: 600; font-variant-numeric: tabular-nums; }
.progress-rail { display: flex; gap: 5px; }
.progress-rail i { flex: 1; height: 5px; border-radius: 4px; background: #e1eeeb; transition: background .3s; }
.progress-rail i.done { background: #78b0a6; }
.progress-rail i.current { background: #e5b06e; box-shadow: 0 0 0 3px #e5b06e26; }
.status-stat { display: flex; align-items: center; gap: 7px; color: var(--spell-muted); font-size: 11px; border-left: 1px solid var(--spell-border); padding-left: 22px; }
.status-stat > span { display: flex; align-items: center; gap: 4px; }
.status-stat > span > span { width: 14px; height: 14px; color: #c3a264; }
.status-stat strong { font-size: 17px; color: var(--spell-ink); font-variant-numeric: tabular-nums; }
.status-best { display: flex; flex-direction: column; gap: 5px; margin-left: auto; color: var(--spell-muted); font-size: 10px; }
.status-best > span { display: flex; align-items: center; gap: 4px; }
.status-best > span > span { width: 13px; height: 13px; color: #c8a55f; }
.mini-stars { display: flex; gap: 3px; }
.mini-stars > span { width: 13px; height: 13px; color: #dcebe8; }
.mini-stars > .earned { color: #d7ac61; }
.spell-board { display: grid; grid-template-columns: minmax(0, .92fr) minmax(380px, 1.08fr); gap: 24px; align-items: stretch; }
.word-scene { position: relative; overflow: hidden; display: flex; flex-direction: column; align-items: center; min-height: 480px; padding: 30px 24px; border-radius: 12px; background: radial-gradient(circle at 50% 36%, #ffffff 0 12%, transparent 13%), linear-gradient(165deg, #e6f6f2 0%, #d3ece8 46%, #c2e2de 100%); border: 1px solid #d2e8e4; }
.scene-orbit { position: absolute; border: 1px dashed #ffffff9e; border-radius: 50%; }
.orbit-a { width: 290px; height: 290px; top: 56px; }
.orbit-b { width: 370px; height: 370px; top: 16px; border-color: #ffffff73; }
.scene-star { position: absolute; color: #ffffffd9; }
.star-a { top: 34px; left: 46px; font-size: 17px; }.star-b { top: 104px; right: 54px; font-size: 12px; }.star-c { bottom: 96px; left: 60px; font-size: 24px; }
.emoji-card { position: relative; z-index: 1; width: clamp(120px, 18vw, 170px); aspect-ratio: 1; margin-top: 42px; display: grid; place-items: center; border-radius: 38% 62% 55% 45% / 45% 42% 58% 55%; background: #fffdf6; box-shadow: 0 16px 34px #3c7b7330, inset 0 -8px 0 #f4ead5; animation: float-emoji 4.5s ease-in-out infinite; }
.word-emoji { font-size: clamp(60px, 10vw, 88px); line-height: 1; }
.emoji-shadow { position: absolute; bottom: 15px; width: 46%; height: 8px; border-radius: 50%; background: #6c968c24; filter: blur(2px); }
.meaning-pill { position: relative; z-index: 1; margin-top: 23px; padding: 8px 20px; border-radius: 30px; background: #ffffffca; color: #4f7a74; font-size: 16px; font-weight: 650; box-shadow: 0 4px 14px #3f7c7417; }
.scene-copy { position: relative; z-index: 1; margin-top: 17px; text-align: center; }
.scene-copy span { display: block; color: #779a95; font-size: 10px; letter-spacing: 2px; }
.scene-copy strong { display: block; margin-top: 5px; color: #4c756f; font-size: 13px; font-weight: 600; }
.scene-footer { position: relative; z-index: 1; width: 100%; display: flex; justify-content: space-between; gap: 8px; margin-top: auto; padding-top: 22px; color: #739792; font-size: 9px; }
.scene-footer > span:first-child { display: flex; align-items: center; gap: 6px; }
.scene-footer i { width: 5px; height: 5px; border-radius: 50%; background: #e6a76e; box-shadow: 0 0 0 3px #e6a76e26; }
.spell-panel { display: flex; flex-direction: column; min-width: 0; padding: 24px; border: 1px solid var(--spell-border); border-radius: 12px; background: #fff; }
.panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding-bottom: 14px; border-bottom: 1px dashed #dcebe7; }
.panel-kicker { color: #9aacab; font-size: 9px; letter-spacing: 1px; }
.panel-heading h2 { margin-top: 4px; font-size: 20px; font-weight: 700; letter-spacing: .5px; }
.panel-heading h2::first-letter { text-transform: lowercase; }
.solved-mark { width: 30px; height: 30px; display: grid; place-items: center; border-radius: 50%; background: #f9ecd8; color: #ca9b55; }
.solved-mark > span { width: 17px; height: 17px; }
.letter-slots { display: flex; flex-wrap: wrap; justify-content: center; gap: 6px; min-height: 58px; margin: 22px 0 19px; padding: 9px; border-radius: 9px; background: #f7fbfa; border: 1px solid #e6f1ef; }
.letter-slot { width: clamp(31px, 5.2vw, 45px); aspect-ratio: .9; display: grid; place-items: center; border: 1px solid #d9e8e5; border-radius: 6px; background: #fff; color: #3d6c66; font-size: clamp(19px, 3vw, 25px); font-weight: 650; }
.letter-slot:not(:disabled):hover { border-color: #a9cbc4; }
.letter-slot.filled { background: #edf7f3; border-color: #b9d8d0; }
.letter-slot.done { background: #e9f6ec; border-color: #a9cfb0; color: #4d8a5f; }
.letter-slot > span { color: #c8d8d5; font-weight: 400; }
.letter-bank { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; }
.letter-tile { position: relative; width: clamp(46px, 7.4vw, 58px); aspect-ratio: 1; border: 1px solid #d9e7e4; border-radius: 8px; background: #fbfdfc; color: #416f69; font-size: 22px; font-weight: 650; box-shadow: 0 2px 0 #e4efec; }
.letter-tile:not(:disabled):hover { border-color: #9dc7c0; background: #f3faf8; transform: translateY(-2px); }
.letter-tile:not(:disabled):active { transform: translateY(1px); box-shadow: 0 1px 0 #e4efec; }
.letter-tile.picked { background: #e7f4ef; border-color: #a5cbc3; color: #3e756e; box-shadow: 0 2px 0 #d2e6e0; }
.letter-tile.hinted:not(.picked) { border-color: #e0b474; box-shadow: 0 0 0 3px #e0b47426; }
.letter-tile small { position: absolute; right: 4px; bottom: 3px; width: 13px; height: 13px; display: grid; place-items: center; border-radius: 50%; background: #cfe4de; color: #5c837b; font-size: 8px; font-weight: 500; }
.spell-hint { display: flex; align-items: center; justify-content: center; gap: 5px; margin-top: 14px; padding: 8px 10px; border-radius: 6px; background: #fdf5e5; color: #a5824b; font-size: 10px; }
.spell-hint > span { width: 13px; height: 13px; }
.solved-card { display: flex; align-items: center; gap: 9px; margin-top: 15px; padding: 11px 12px; border-radius: 8px; background: #edf7ee; color: #658a6d; animation: answer-in .3s ease; }
.solved-icon { flex: none; width: 28px; height: 28px; display: grid; place-items: center; border-radius: 50%; background: #ffffffb8; color: #5f9a6c; }
.solved-icon > span { width: 16px; height: 16px; }
.solved-card strong { font-size: 11px; font-weight: 650; }
.solved-card p { margin-top: 2px; font-size: 10px; line-height: 1.6; color: #7d9982; }
.speak-button { margin-left: auto; flex: none; width: 37px; height: 37px; display: grid; place-items: center; border-radius: 50%; background: #fff; color: #5b9270; border: 1px solid #cfe3d2; }
.speak-button:hover { background: #f7fcf8; }
.speak-button > span { width: 17px; height: 17px; }
.spell-feedback { display: flex; align-items: flex-start; gap: 7px; margin-top: 15px; padding: 10px 11px; border-radius: 7px; background: #fdf2e4; color: #aa7b50; font-size: 10px; line-height: 1.75; }
.spell-feedback > span { width: 14px; height: 14px; flex: none; margin-top: 1px; }
.spell-tip { display: flex; align-items: center; justify-content: center; gap: 5px; margin-top: 15px; color: #a3b4b2; font-size: 9px; }
.spell-tip > span { width: 12px; height: 12px; }
.panel-actions { display: flex; gap: 8px; margin: 18px 0 12px; }
.ghost-button, .hint-button { flex: 1; min-height: 38px; display: flex; align-items: center; justify-content: center; gap: 5px; border-radius: 6px; font-size: 10px; }
.ghost-button { background: #f8fbfa; border: 1px solid #e3efec; color: #96aaa7; }
.ghost-button:disabled, .hint-button:disabled { opacity: .55; }
.hint-button { background: #fffaf0; border: 1px solid #eadbc1; color: #a58550; }
.ghost-button > span, .hint-button > span { width: 13px; height: 13px; }
.primary-action, .secondary-action { min-height: 44px; display: flex; align-items: center; justify-content: center; gap: 7px; border-radius: 7px; font-size: 12px; font-weight: 600; padding: 10px 14px; }
.primary-action { background: var(--spell-teal); color: #fff; border: 1px solid transparent; }
.primary-action:hover { background: #34716d; }
.primary-action:disabled { background: #cfe0dd; color: #f7fbfa; }
.primary-action > span { width: 15px; height: 15px; }
.spell-panel > .primary-action { width: 100%; margin-top: auto; }
.secondary-action { background: #fff; border: 1px solid var(--spell-border); color: #8ca09e; }
.spell-report { padding: 34px clamp(20px, 6vw, 70px); border: 1px solid var(--spell-border); border-radius: 10px; background: #fff; text-align: center; }
.report-stars { display: flex; justify-content: center; gap: 10px; margin-bottom: 14px; }
.report-stars > span { width: 34px; height: 34px; color: #e0edea; }
.report-stars > .earned { color: #d9ae61; filter: drop-shadow(0 2px 5px #d9ae612e); }
.spell-report h2 { font-size: 24px; margin: 5px 0 8px; }
.spell-report > p { color: var(--spell-muted); font-size: 11px; line-height: 1.8; }
.report-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); max-width: 480px; margin: 22px auto; padding: 17px 0; border-top: 1px dashed var(--spell-border); border-bottom: 1px dashed var(--spell-border); }
.report-stats div { display: flex; flex-direction: column; gap: 7px; }
.report-stats div + div { border-left: 1px solid #edf4f3; }
.report-stats span { font-size: 10px; color: var(--spell-muted); }
.report-stats strong { font-size: 23px; color: var(--spell-teal); }
.report-stats small { font-size: 11px; font-weight: 400; color: #9badab; }
.report-best { display: flex; justify-content: center; flex-wrap: wrap; gap: 8px 20px; color: var(--spell-muted); font-size: 10px; margin-bottom: 22px; }
.report-best > span { font-weight: 600; }
.report-best > div { display: flex; align-items: center; gap: 5px; }
.report-best > div.active { color: var(--spell-teal); font-weight: 600; }
.report-best i { display: flex; gap: 2px; font-style: normal; }
.report-best i > span { width: 12px; height: 12px; color: #e0edea; }
.report-best i > .earned { color: #d9ae61; }
.report-actions { display: flex; justify-content: center; gap: 10px; max-width: 410px; margin: auto; }
.report-actions .primary-action { flex: 1.3; }
.report-actions .secondary-action { flex: 1; }
.spell-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; color: #a3b5b3; font-size: 9px; margin-top: 21px; }
.spell-footer > span { display: flex; align-items: center; gap: 5px; }
.spell-footer > span > span { width: 12px; height: 12px; }
.help-list { color: #728683; font-size: 13px; line-height: 1.9; padding-left: 20px; list-style-type: decimal; margin-bottom: 22px; }
.help-list li + li { margin-top: 12px; }
.modal-actions { display: flex; gap: 10px; }
.modal-actions > button { flex: 1; }
@keyframes float-emoji { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-7px); } }
@keyframes answer-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
@media (max-width: 960px) { .spell-content { padding: 26px 24px 16px; } .spell-board { grid-template-columns: minmax(0, .85fr) minmax(360px, 1.15fr); gap: 18px; } .spell-status { gap: 22px; } .status-best { display: none; } .word-scene { min-height: 440px; } }
@media (max-width: 760px) { .spell-heading { align-items: flex-start; } .spell-title h1 { font-size: 28px; } .spell-board { grid-template-columns: minmax(0, 1fr); } .word-scene { min-height: 310px; padding: 22px; } .emoji-card { width: 120px; margin-top: 16px; } .word-emoji { font-size: 60px; } .orbit-a { width: 220px; height: 220px; top: 20px; } .orbit-b { width: 280px; height: 280px; top: -6px; } .scene-footer { margin-top: 18px; } .spell-status { flex-wrap: wrap; gap: 14px 22px; } .spell-progress { order: 5; flex-basis: 100%; max-width: none; } .status-best { display: flex; margin-left: 0; } .status-stat { padding-left: 16px; } }
@media (max-width: 540px) { .spell-content { padding: 21px 16px 14px; } .spell-heading { flex-wrap: wrap; gap: 12px; margin-bottom: 16px; } .spell-title { width: 100%; } .spell-title h1 { font-size: 27px; } .spell-toolbar { width: 100%; gap: 5px; } .difficulty-switch { margin-right: auto; padding: 3px; } .difficulty-switch button { padding: 0 12px; min-height: 38px; font-size: 11px; } .round-tool { width: 32px; height: 40px; } .spell-status { padding: 12px 0; margin-bottom: 16px; gap: 12px 14px; } .status-title > span { width: 32px; height: 32px; } .status-title strong { font-size: 12px; } .status-stat { font-size: 10px; gap: 5px; } .status-stat strong { font-size: 15px; } .status-best { flex-direction: row; align-items: center; gap: 7px; } .word-scene { min-height: 272px; border-radius: 10px; } .emoji-card { width: 100px; margin-top: 8px; } .word-emoji { font-size: 52px; } .meaning-pill { margin-top: 15px; padding: 6px 16px; font-size: 14px; } .scene-copy { margin-top: 11px; } .scene-footer { font-size: 8px; padding-top: 12px; } .spell-panel { padding: 19px 15px; border-radius: 10px; } .letter-slots { gap: 4px; margin: 17px 0 15px; padding: 8px 5px; } .letter-slot { width: clamp(27px, 8vw, 40px); font-size: 20px; } .letter-bank { gap: 6px; } .letter-tile { width: clamp(42px, 12.6vw, 54px); font-size: 20px; } .spell-tip { text-align: center; font-size: 8px; } .spell-footer { font-size: 8px; } .spell-report { padding: 26px 18px; } .spell-report h2 { font-size: 20px; } .report-stars > span { width: 28px; height: 28px; } .report-actions { flex-direction: column-reverse; } .report-actions .primary-action, .report-actions .secondary-action { flex: none; } }
@media (max-width: 360px) { .status-stat:nth-of-type(4) { display: none; } .difficulty-switch button { padding: 0 9px; } .letter-slot { width: 26px; font-size: 18px; } .letter-tile { width: 40px; font-size: 19px; } }
@media (prefers-reduced-motion: reduce) { .emoji-card, .solved-card { animation: none; } .letter-tile:hover { transform: none; } }
</style>
