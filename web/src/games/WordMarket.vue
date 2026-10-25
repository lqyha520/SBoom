<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import GameNav from './GameNav.vue'
import { englishWord } from './english-words'
import {
  advanceMarket, answerMarket, MARKET_QUESTIONS, marketDifficulties, marketStars,
  newMarket, restartMarket, restoreMarket, switchMarketDifficulty, type MarketDifficulty,
} from './word-market'

const props = withDefaults(defineProps<{ storageKey?: string }>(), { storageKey: 'lc_game_word_market_v1_guest' })
function readSave() {
  try { return restoreMarket(localStorage.getItem(props.storageKey)) } catch { return null }
}
const save = ref(readSave() || newMarket())
const resetDifficulty = ref<MarketDifficulty | null>(null)
const helpOpen = ref(false)
const saveError = ref(false)
const round = computed(() => save.value.round)
const question = computed(() => round.value.questions[round.value.index])
const source = computed(() => englishWord(round.value.difficulty, question.value.wordId)!)
const difficulty = computed(() => marketDifficulties.find(item => item.id === save.value.difficulty)!)
const answered = computed(() => round.value.answered)
const isCorrect = computed(() => answered.value === question.value.wordId)
const finished = computed(() => round.value.finished)
const stars = computed(() => marketStars(round.value))
const answeredCount = computed(() => finished.value ? MARKET_QUESTIONS : round.value.index + (answered.value === null ? 0 : 1))

function choose(word: string) {
  answerMarket(save.value, word)
}
function next() {
  advanceMarket(save.value)
}
function again() {
  restartMarket(save.value)
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
function requestDifficulty(id: MarketDifficulty) {
  if (id !== save.value.difficulty) resetDifficulty.value = id
}
function applyDifficulty() {
  if (!resetDifficulty.value) return
  if (resetDifficulty.value === save.value.difficulty) restartMarket(save.value)
  else switchMarketDifficulty(save.value, resetDifficulty.value)
  resetDifficulty.value = null
}
watch(save, value => {
  try { localStorage.setItem(props.storageKey, JSON.stringify(value)); saveError.value = false }
  catch { saveError.value = true }
}, { deep: true, immediate: true, flush: 'post' })
watch(() => props.storageKey, () => { save.value = readSave() || newMarket() })
</script>

<template>
  <div class="market-game">
    <GameNav active="word-market" />
    <main class="market-content">
      <header class="market-heading">
        <div class="market-title"><span class="eyebrow">阳光单词集市 · 英语认读</span><h1>单词集市<span>.</span></h1></div>
        <div class="market-toolbar">
          <div class="difficulty-switch" role="group" aria-label="游戏难度">
            <button v-for="item in marketDifficulties" :key="item.id" :title="item.age" :aria-pressed="save.difficulty === item.id" :class="{ selected: save.difficulty === item.id }" @click="requestDifficulty(item.id)">{{ item.name }}</button>
          </div>
          <UTooltip text="怎么玩"><button class="round-tool" aria-label="怎么玩" @click="helpOpen = true"><UIcon name="i-lucide-circle-help" /></button></UTooltip>
        </div>
      </header>

      <section class="market-status" aria-label="集市进度">
        <div class="status-title"><span><UIcon name="i-lucide-store" /></span><div><strong>单词小摊</strong><small>{{ difficulty.name }} · {{ difficulty.detail }}</small></div></div>
        <div class="market-progress">
          <span class="progress-caption">卖出的单词<strong>{{ answeredCount }} / {{ MARKET_QUESTIONS }}</strong></span>
          <div class="progress-rail" aria-hidden="true"><i v-for="n in MARKET_QUESTIONS" :key="n" :class="{ done: n <= answeredCount, current: !finished && answered === null && n === round.index + 1 }" /></div>
        </div>
        <div class="status-stat"><span><UIcon name="i-lucide-circle-check" />答对</span><strong>{{ round.correct }}</strong></div>
        <div class="status-stat"><span><UIcon name="i-lucide-map-pin" />再逛</span><strong>{{ round.mistakes }}</strong></div>
        <div class="status-best"><span><UIcon name="i-lucide-star" />最佳</span><div class="mini-stars" :aria-label="`${difficulty.name}最佳${save.best[save.difficulty]}颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.best[save.difficulty] }" /></div></div>
      </section>

      <section v-if="!finished" class="market-stall">
        <div class="stall-awning" aria-hidden="true" />
        <div class="stall-meta"><span class="stall-number">第 {{ round.index + 1 }} / {{ MARKET_QUESTIONS }} 个单词</span><span class="stall-badge"><UIcon name="i-lucide-tag" />看图片，找单词</span></div>
        <div class="stall-card">
          <div class="prompt-card">
            <span class="prompt-emoji" role="img" :aria-label="source.meaning">{{ source.emoji }}</span>
            <div class="prompt-copy"><span>这个词的意思是</span><strong>{{ source.meaning }}</strong><small>{{ source.word.length }} 个字母</small></div>
          </div>
          <div class="prompt-arrow" aria-hidden="true"><UIcon name="i-lucide-arrow-right" /></div>
          <div class="word-options" role="group" aria-label="英文单词选项">
            <button v-for="(word, index) in question.options" :key="word" class="word-option" :class="{ right: answered !== null && word === question.wordId, wrong: answered === word && word !== question.wordId }" :data-word="word" :disabled="answered !== null" :aria-label="`选择单词 ${word}`" @click="choose(word)">
              <span class="option-label">{{ String.fromCharCode(65 + index) }}</span>
              <strong>{{ word }}</strong>
              <UIcon v-if="answered !== null && word === question.wordId" name="i-lucide-circle-check" class="option-mark" />
              <UIcon v-else-if="answered === word" name="i-lucide-x" class="option-mark" />
            </button>
          </div>
        </div>
        <div v-if="answered !== null" class="market-feedback" :class="{ good: isCorrect }" role="status" aria-label="答题反馈">
          <span class="feedback-mark"><UIcon :name="isCorrect ? 'i-lucide-party-popper' : 'i-lucide-lightbulb'" /></span>
          <div><strong>{{ isCorrect ? '找到啦，单词和图片是好朋友！' : '再认一认，这个单词是这样写的。' }}</strong><p><span class="feedback-emoji" aria-hidden="true">{{ source.emoji }}</span>{{ question.wordId }} · {{ source.meaning }}</p></div>
          <button class="speak-button" :aria-label="`朗读单词 ${question.wordId}`" @click="speak(question.wordId)"><UIcon name="i-lucide-volume-2" /></button>
        </div>
        <p v-else class="market-tip"><UIcon name="i-lucide-mouse-pointer-2" />读一读四个单词，选出和图片意思相配的那一个。</p>
        <button v-if="answered !== null" class="primary-action" @click="next">{{ round.index === MARKET_QUESTIONS - 1 ? '查看集市成绩' : '下一个单词' }}<UIcon name="i-lucide-arrow-right" /></button>
      </section>

      <section v-else class="market-report">
        <div class="report-stars" :aria-label="`本局获得${stars}颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= stars }" /></div>
        <span class="eyebrow">第 {{ save.rounds }} 次集市 · {{ difficulty.name }}</span>
        <h2>{{ stars === 3 ? '单词全卖光，集市小老板真厉害！' : '集市收摊啦，单词都认出来了！' }}</h2>
        <p>{{ round.mistakes === 0 ? '八个单词全部认对，一次也没有拿错。' : `这次有 ${round.mistakes} 个单词需要再看一眼，多读几遍就记住啦。` }}</p>
        <div class="report-stats">
          <div><span>答对单词</span><strong>{{ round.correct }}<small> / {{ MARKET_QUESTIONS }}</small></strong></div>
          <div><span>再逛一次</span><strong>{{ round.mistakes }}<small> 个</small></strong></div>
          <div><span>累计认识</span><strong>{{ save.totalCorrect }}<small> 个</small></strong></div>
        </div>
        <div class="report-best"><span>最佳记录</span><div v-for="item in marketDifficulties" :key="item.id" :class="{ active: item.id === save.difficulty }"><span>{{ item.name }}</span><i><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.best[item.id] }" /></i></div></div>
        <div class="report-actions"><button class="secondary-action" @click="helpOpen = true"><UIcon name="i-lucide-circle-help" />看看玩法</button><button class="primary-action" @click="again"><UIcon name="i-lucide-rotate-ccw" />再逛一次</button></div>
      </section>

      <footer class="market-footer"><span><UIcon name="i-lucide-heart" />每一次尝试，都是成长</span><span role="status" aria-label="进度保存状态"><UIcon :name="saveError ? 'i-lucide-cloud-off' : 'i-lucide-cloud-check'" />{{ saveError ? '本机暂时无法保存进度' : '进度已保存在本机' }}</span></footer>
    </main>

    <UModal :open="helpOpen" title="逛集市，认单词" description="看看图片和中文，从四个英文单词里选出正确的那个。" :close="{ 'aria-label': '关闭玩法说明' }" :ui="{ content: 'game-modal' }" @update:open="helpOpen = $event"><template #body><ol class="help-list"><li>先看摊位上的图片和中文意思，猜一猜对应的英文单词。</li><li>四个单词里只有一个意思是对的，细心读一读再点选。</li><li>选好后会显示完整的单词和意思。点小喇叭还可以听一听读音。</li><li>八个单词逛完就能看到成绩。全部一次选对可以获得三颗星。</li></ol><button class="primary-action" @click="helpOpen = false">明白了，去逛集市<UIcon name="i-lucide-store" /></button></template></UModal>
    <UModal :open="resetDifficulty !== null" :title="resetDifficulty === save.difficulty ? '重新开始逛集市？' : '切换游戏难度？'" description="新的一轮会从第一个单词开始，当前进度会清空，最佳记录会保留。" :close="{ 'aria-label': '关闭难度确认' }" :ui="{ content: 'game-modal' }" @update:open="!$event && (resetDifficulty = null)"><template #body><div class="modal-actions"><button class="secondary-action" @click="resetDifficulty = null">继续当前集市</button><button class="primary-action" @click="applyDifficulty">{{ resetDifficulty === save.difficulty ? '重新开始' : '切换并开始' }}<UIcon name="i-lucide-arrow-right" /></button></div></template></UModal>
  </div>
</template>

<style scoped>
.market-game { --market-ink: #4a3b30; --market-muted: #9c897a; --market-red: #c56348; --market-cream: #fdf6e9; --market-border: #eddfca; min-height: 100dvh; background: #faf3e7; color: var(--market-ink); font-family: var(--font-ui); letter-spacing: 0; }
.market-game button { cursor: pointer; transition: background .16s, transform .16s, box-shadow .16s; }
.market-game button:disabled { cursor: default; }
.market-game button:focus-visible { outline: 3px solid #c08b6e; outline-offset: 3px; }
.market-content { max-width: 940px; margin: auto; padding: 30px 36px 18px; }
.eyebrow { display: block; color: var(--market-muted); font-size: 11px; line-height: 1.6; }
.market-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 22px; }
.market-title h1 { font-size: 32px; font-weight: 750; line-height: 1.35; margin: 3px 0 0; }
.market-title h1 > span { color: var(--market-red); margin-left: 3px; }
.market-toolbar { display: flex; align-items: center; gap: 9px; }
.difficulty-switch { display: flex; align-items: center; gap: 3px; background: #f4e8d6; padding: 4px; border-radius: 8px; margin-right: 6px; }
.difficulty-switch button { height: 35px; padding: 0 15px; background: transparent; border-radius: 5px; color: #a49280; font-size: 12px; white-space: nowrap; }
.difficulty-switch button.selected { color: var(--market-red); background: #fffaf0; box-shadow: 0 1px 4px #4a3b3014; font-weight: 650; }
.round-tool { width: 36px; height: 36px; display: grid; place-items: center; color: #a3907f; background: transparent; border-radius: 6px; }
.round-tool:hover { background: #f4e8d6; }
.round-tool > span { width: 18px; height: 18px; }
.market-status { display: flex; align-items: center; gap: 34px; padding: 15px 0; border-top: 1px solid var(--market-border); border-bottom: 1px solid var(--market-border); margin-bottom: 22px; }
.status-title { display: flex; align-items: center; gap: 11px; }
.status-title > span { width: 38px; height: 38px; display: grid; place-items: center; background: #f8e9d9; color: #b8775b; border-radius: 50%; }
.status-title > span > span { width: 20px; height: 20px; }
.status-title > div { display: flex; flex-direction: column; gap: 3px; }
.status-title strong { font-size: 13px; font-weight: 650; }
.status-title small { font-size: 10px; color: var(--market-muted); }
.market-progress { flex: 1; max-width: 300px; display: flex; flex-direction: column; gap: 7px; }
.progress-caption { display: flex; justify-content: space-between; gap: 10px; color: var(--market-muted); font-size: 10px; }
.progress-caption strong { color: var(--market-red); font-weight: 600; font-variant-numeric: tabular-nums; }
.progress-rail { display: flex; gap: 5px; }
.progress-rail i { flex: 1; height: 5px; border-radius: 4px; background: #f0e3d2; transition: background .3s; }
.progress-rail i.done { background: #d0916f; }
.progress-rail i.current { background: #dfb266; box-shadow: 0 0 0 3px #dfb26626; }
.status-stat { display: flex; align-items: center; gap: 7px; color: var(--market-muted); font-size: 11px; border-left: 1px solid var(--market-border); padding-left: 22px; }
.status-stat > span { display: flex; align-items: center; gap: 4px; }
.status-stat > span > span { width: 14px; height: 14px; color: #c3a064; }
.status-stat:nth-of-type(4) > span > span { color: #c28a70; }
.status-stat strong { font-size: 17px; color: var(--market-ink); font-variant-numeric: tabular-nums; }
.status-best { display: flex; flex-direction: column; gap: 5px; margin-left: auto; color: var(--market-muted); font-size: 10px; }
.status-best > span { display: flex; align-items: center; gap: 4px; }
.status-best > span > span { width: 13px; height: 13px; color: #c9a45b; }
.mini-stars { display: flex; gap: 3px; }
.mini-stars > span { width: 13px; height: 13px; color: #efe4d4; }
.mini-stars > .earned { color: #d7ac61; }
.market-stall { position: relative; overflow: hidden; padding: 30px clamp(20px, 5vw, 48px) 26px; border: 1px solid #e9d8bf; border-radius: 11px; background: linear-gradient(170deg, #fffdf7, #fdf5e6); box-shadow: 0 12px 30px #94754d14; }
.stall-awning { position: absolute; top: 0; left: 0; right: 0; height: 15px; background: repeating-linear-gradient(90deg, #d98b6b 0 28px, #f6e3c8 28px 56px); opacity: .8; }
.stall-meta { display: flex; align-items: center; gap: 12px; margin-bottom: 17px; }
.stall-number { color: var(--market-muted); font-size: 10px; }
.stall-badge { margin-left: auto; display: flex; align-items: center; gap: 4px; padding: 4px 9px; border-radius: 20px; background: #f8eddd; color: #ac8761; font-size: 9px; }
.stall-badge > span { width: 12px; height: 12px; }
.stall-card { display: grid; grid-template-columns: minmax(0, .78fr) 30px minmax(0, 1.22fr); align-items: center; gap: 10px; }
.prompt-card { display: flex; flex-direction: column; align-items: center; padding: 23px 16px 20px; border: 1px solid #eadbc3; border-radius: 10px; background: #fffcf5; box-shadow: inset 0 -6px 0 #f8efdf; }
.prompt-emoji { font-size: clamp(62px, 10vw, 84px); line-height: 1.15; }
.prompt-copy { margin-top: 13px; text-align: center; }
.prompt-copy span { display: block; color: #ac9a86; font-size: 9px; }
.prompt-copy strong { display: block; margin-top: 4px; color: #5e4939; font-size: 23px; font-weight: 700; letter-spacing: 1px; }
.prompt-copy small { display: block; margin-top: 4px; color: #bbab99; font-size: 8px; }
.prompt-arrow { display: grid; place-items: center; color: #d4bfa5; }
.prompt-arrow > span { width: 20px; height: 20px; }
.word-options { display: flex; flex-direction: column; gap: 9px; }
.word-option { position: relative; display: flex; align-items: center; gap: 11px; min-height: 62px; padding: 10px 42px 10px 12px; border: 1px solid #e9dcc8; border-radius: 8px; background: #fffdf8; color: #5d4d3e; text-align: left; }
.word-option:not(:disabled):hover { border-color: #d2ae84; background: #fff9ed; transform: translateX(3px); }
.word-option.right { border-color: #9fc39e; background: #f0f7ec; color: #54805d; }
.word-option.wrong { border-color: #e1ab8f; background: #fdf0e7; color: #b37056; animation: market-shake .3s ease; }
.option-label { flex: none; width: 23px; height: 23px; display: grid; place-items: center; border-radius: 50%; background: #f5ead9; color: #b2956e; font-size: 9px; }
.word-option.right .option-label { background: #dcebd8; color: #66936e; }
.word-option.wrong .option-label { background: #f7e1d4; color: #ba866d; }
.word-option strong { font-size: clamp(19px, 3vw, 24px); font-weight: 650; letter-spacing: .5px; }
.option-mark { position: absolute; right: 13px; width: 18px; height: 18px; color: #71a07a; }
.word-option.wrong .option-mark { color: #c0876c; }
.market-feedback { display: flex; align-items: center; gap: 9px; margin-top: 15px; padding: 11px 12px; border-radius: 8px; background: #fdf0e5; color: #a87c5e; animation: answer-in .3s ease; }
.market-feedback.good { background: #eff7ec; color: #6f9277; }
.feedback-mark { flex: none; width: 28px; height: 28px; display: grid; place-items: center; border-radius: 50%; background: #ffffffa8; }
.feedback-mark > span { width: 16px; height: 16px; }
.market-feedback strong { font-size: 11px; font-weight: 650; }
.market-feedback p { display: flex; align-items: center; gap: 5px; margin-top: 3px; font-size: 11px; opacity: .92; }
.feedback-emoji { font-size: 15px; }
.speak-button { margin-left: auto; flex: none; width: 37px; height: 37px; display: grid; place-items: center; border-radius: 50%; background: #fff; color: #6f9477; border: 1px solid #d6e6d5; }
.speak-button:hover { background: #f8fcf8; }
.speak-button > span { width: 17px; height: 17px; }
.market-tip { display: flex; align-items: center; justify-content: center; gap: 5px; margin-top: 16px; color: #b3a089; font-size: 9px; }
.market-tip > span { width: 12px; height: 12px; }
.primary-action, .secondary-action { min-height: 44px; display: flex; align-items: center; justify-content: center; gap: 7px; border-radius: 7px; font-size: 12px; font-weight: 600; padding: 10px 14px; }
.primary-action { background: var(--market-red); color: #fff; border: 1px solid transparent; }
.primary-action:hover { background: #b0573e; }
.primary-action > span { width: 15px; height: 15px; }
.market-stall > .primary-action { width: 100%; margin-top: 16px; }
.secondary-action { background: #fffaf1; border: 1px solid var(--market-border); color: #9b8976; }
.market-report { padding: 34px clamp(20px, 6vw, 70px); border: 1px solid var(--market-border); border-radius: 10px; background: #fffdf8; text-align: center; }
.report-stars { display: flex; justify-content: center; gap: 10px; margin-bottom: 14px; }
.report-stars > span { width: 34px; height: 34px; color: #efe4d4; }
.report-stars > .earned { color: #d7ac61; filter: drop-shadow(0 2px 5px #d7ac612e); }
.market-report h2 { font-size: 24px; margin: 5px 0 8px; }
.market-report > p { color: var(--market-muted); font-size: 11px; line-height: 1.8; }
.report-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); max-width: 480px; margin: 22px auto; padding: 17px 0; border-top: 1px dashed var(--market-border); border-bottom: 1px dashed var(--market-border); }
.report-stats div { display: flex; flex-direction: column; gap: 7px; }
.report-stats div + div { border-left: 1px solid #f4eadc; }
.report-stats span { font-size: 10px; color: var(--market-muted); }
.report-stats strong { font-size: 23px; color: var(--market-red); }
.report-stats small { font-size: 11px; font-weight: 400; color: #ac9b88; }
.report-best { display: flex; justify-content: center; flex-wrap: wrap; gap: 8px 20px; color: var(--market-muted); font-size: 10px; margin-bottom: 22px; }
.report-best > span { font-weight: 600; }
.report-best > div { display: flex; align-items: center; gap: 5px; }
.report-best > div.active { color: var(--market-red); font-weight: 600; }
.report-best i { display: flex; gap: 2px; font-style: normal; }
.report-best i > span { width: 12px; height: 12px; color: #efe4d4; }
.report-best i > .earned { color: #d7ac61; }
.report-actions { display: flex; justify-content: center; gap: 10px; max-width: 410px; margin: auto; }
.report-actions .primary-action { flex: 1.3; }
.report-actions .secondary-action { flex: 1; }
.market-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; color: #b5a591; font-size: 9px; margin-top: 21px; }
.market-footer > span { display: flex; align-items: center; gap: 5px; }
.market-footer > span > span { width: 12px; height: 12px; }
.help-list { color: #82705f; font-size: 13px; line-height: 1.9; padding-left: 20px; list-style-type: decimal; margin-bottom: 22px; }
.help-list li + li { margin-top: 12px; }
.modal-actions { display: flex; gap: 10px; }
.modal-actions > button { flex: 1; }
@keyframes market-shake { 25% { transform: translateX(-3px); } 70% { transform: translateX(3px); } }
@keyframes answer-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
@media (max-width: 840px) { .market-content { padding: 26px 24px 16px; } .market-status { gap: 22px; } .status-best { display: none; } .market-stall { padding-left: 26px; padding-right: 26px; } }
@media (max-width: 700px) { .market-heading { align-items: flex-start; } .market-title h1 { font-size: 28px; } .market-status { flex-wrap: wrap; gap: 14px 22px; } .market-progress { order: 5; flex-basis: 100%; max-width: none; } .status-best { display: flex; margin-left: 0; } .status-stat { padding-left: 16px; } .stall-card { grid-template-columns: minmax(0, 1fr); gap: 13px; } .prompt-card { flex-direction: row; justify-content: center; gap: 16px; padding: 14px 16px; } .prompt-emoji { font-size: 58px; } .prompt-copy { margin-top: 0; text-align: left; } .prompt-copy strong { font-size: 21px; } .prompt-arrow { display: none; } .word-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); } .word-option { min-height: 58px; padding-right: 10px; } .option-mark { display: none; } }
@media (max-width: 540px) { .market-content { padding: 21px 16px 14px; } .market-heading { flex-wrap: wrap; gap: 12px; margin-bottom: 16px; } .market-title { width: 100%; } .market-title h1 { font-size: 27px; } .market-toolbar { width: 100%; gap: 5px; } .difficulty-switch { margin-right: auto; padding: 3px; } .difficulty-switch button { padding: 0 12px; min-height: 38px; font-size: 11px; } .round-tool { width: 32px; height: 40px; } .market-status { padding: 12px 0; margin-bottom: 16px; gap: 12px 14px; } .status-title > span { width: 32px; height: 32px; } .status-title strong { font-size: 12px; } .status-stat { font-size: 10px; gap: 5px; } .status-stat strong { font-size: 15px; } .status-best { flex-direction: row; align-items: center; gap: 7px; } .market-stall { padding: 24px 15px 20px; border-radius: 9px; } .stall-awning { height: 12px; } .stall-meta { margin-bottom: 13px; } .prompt-card { gap: 12px; padding: 12px; } .prompt-emoji { font-size: 50px; } .prompt-copy strong { font-size: 19px; } .word-options { gap: 7px; } .word-option { min-height: 54px; gap: 8px; padding: 8px 9px; } .option-label { width: 20px; height: 20px; } .word-option strong { font-size: 18px; } .market-feedback { padding: 10px; } .market-feedback p { font-size: 10px; } .speak-button { width: 34px; height: 34px; } .market-report { padding: 26px 18px; } .market-report h2 { font-size: 20px; } .report-stars > span { width: 28px; height: 28px; } .report-actions { flex-direction: column-reverse; } .report-actions .primary-action, .report-actions .secondary-action { flex: none; } .market-footer { font-size: 8px; } }
@media (max-width: 360px) { .status-stat:nth-of-type(4) { display: none; } .difficulty-switch button { padding: 0 9px; } .prompt-emoji { font-size: 44px; } .word-option strong { font-size: 16px; } .option-label { display: none; } .market-stall { padding-left: 12px; padding-right: 12px; } }
@media (prefers-reduced-motion: reduce) { .word-option.wrong, .market-feedback { animation: none; } .word-option:hover { transform: none; } }
</style>
