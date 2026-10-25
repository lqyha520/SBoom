<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import GameNav from './GameNav.vue'
import {
  advanceIdiom, answerIdiom, idiomById, idiomDifficulties, idiomStars, IDIOM_QUESTIONS,
  newIdiom, restartIdiom, restoreIdiom, switchIdiomDifficulty, type IdiomDifficulty,
} from './idiom-fill'

const props = withDefaults(defineProps<{ storageKey?: string }>(), { storageKey: 'lc_game_idiom_fill_v1_guest' })
function readSave() {
  try { return restoreIdiom(localStorage.getItem(props.storageKey)) } catch { return null }
}
const save = ref(readSave() || newIdiom())
const resetDifficulty = ref<IdiomDifficulty | null>(null)
const helpOpen = ref(false)
const saveError = ref(false)
const round = computed(() => save.value.round)
const question = computed(() => round.value.questions[round.value.index])
const source = computed(() => idiomById(round.value.difficulty, question.value.idiomId)!)
const difficulty = computed(() => idiomDifficulties.find(item => item.id === save.value.difficulty)!)
const answered = computed(() => round.value.answered)
const isCorrect = computed(() => answered.value === source.value.answer)
const finished = computed(() => round.value.finished)
const stars = computed(() => idiomStars(round.value))
const answeredCount = computed(() => finished.value ? IDIOM_QUESTIONS : round.value.index + (answered.value === null ? 0 : 1))
const blankChar = computed(() => answered.value ?? '？')
const displayChars = computed(() => source.value.text.split('').map((char, index) => ({
  char,
  blank: index === source.value.blank,
  display: index === source.value.blank ? blankChar.value : char,
})))

function choose(char: string) {
  answerIdiom(save.value, char)
}
function next() {
  advanceIdiom(save.value)
}
function again() {
  restartIdiom(save.value)
}
function requestDifficulty(id: IdiomDifficulty) {
  if (id !== save.value.difficulty) resetDifficulty.value = id
}
function applyDifficulty() {
  if (!resetDifficulty.value) return
  if (resetDifficulty.value === save.value.difficulty) restartIdiom(save.value)
  else switchIdiomDifficulty(save.value, resetDifficulty.value)
  resetDifficulty.value = null
}
watch(save, value => {
  try { localStorage.setItem(props.storageKey, JSON.stringify(value)); saveError.value = false }
  catch { saveError.value = true }
}, { deep: true, immediate: true, flush: 'post' })
watch(() => props.storageKey, () => { save.value = readSave() || newIdiom() })
</script>

<template>
  <div class="idiom-game">
    <GameNav active="idiom-fill" />
    <main class="idiom-content">
      <header class="idiom-heading">
        <div class="idiom-title"><span class="eyebrow">墨香书院 · 语文积累</span><h1>成语补字<span>.</span></h1></div>
        <div class="idiom-toolbar">
          <div class="difficulty-switch" role="group" aria-label="游戏难度">
            <button v-for="item in idiomDifficulties" :key="item.id" :title="item.age" :aria-pressed="save.difficulty === item.id" :class="{ selected: save.difficulty === item.id }" @click="requestDifficulty(item.id)">{{ item.name }}</button>
          </div>
          <UTooltip text="怎么玩"><button class="round-tool" aria-label="怎么玩" @click="helpOpen = true"><UIcon name="i-lucide-circle-help" /></button></UTooltip>
        </div>
      </header>

      <section class="idiom-status" aria-label="成语进度">
        <div class="status-title"><span><UIcon name="i-lucide-book-marked" /></span><div><strong>成语小课堂</strong><small>{{ difficulty.name }} · {{ difficulty.detail }}</small></div></div>
        <div class="idiom-progress">
          <span class="progress-caption">学过的成语<strong>{{ answeredCount }} / {{ IDIOM_QUESTIONS }}</strong></span>
          <div class="progress-rail" aria-hidden="true"><i v-for="n in IDIOM_QUESTIONS" :key="n" :class="{ done: n <= answeredCount, current: !finished && answered === null && n === round.index + 1 }" /></div>
        </div>
        <div class="status-stat"><span><UIcon name="i-lucide-circle-check" />答对</span><strong>{{ round.correct }}</strong></div>
        <div class="status-stat"><span><UIcon name="i-lucide-pencil" />再想</span><strong>{{ round.mistakes }}</strong></div>
        <div class="status-best"><span><UIcon name="i-lucide-star" />最佳</span><div class="mini-stars" :aria-label="`${difficulty.name}最佳${save.best[save.difficulty]}颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.best[save.difficulty] }" /></div></div>
      </section>

      <section v-if="!finished" class="idiom-stage">
        <span class="stage-corner corner-one" aria-hidden="true">墨</span><span class="stage-corner corner-two" aria-hidden="true">香</span>
        <div class="stage-meta"><span class="question-count">第 {{ round.index + 1 }} / {{ IDIOM_QUESTIONS }} 题</span><span class="meaning-badge"><UIcon name="i-lucide-search" />看意思，补汉字</span></div>
        <div class="meaning-card">
          <span>这个成语的意思是</span>
          <p>{{ source.meaning }}</p>
        </div>
        <div class="idiom-line" role="img" :aria-label="answered === null ? '成语中缺了一个字' : `你选择了${answered}字`">
          <span v-for="(item, index) in displayChars" :key="index" :class="{ blank: item.blank, filled: item.blank && answered !== null, right: item.blank && answered !== null && isCorrect, wrong: item.blank && answered !== null && !isCorrect }">{{ item.display }}</span>
        </div>
        <p class="option-prompt">选出缺少的那个字</p>
        <div class="option-grid" role="group" aria-label="汉字选项">
          <button v-for="char in question.options" :key="char" :data-char="char" :class="{ right: answered !== null && char === source.answer, wrong: answered === char && char !== source.answer }" :disabled="answered !== null" :aria-label="`选择汉字 ${char}`" @click="choose(char)"><span class="option-char">{{ char }}</span><small>{{ answered === null ? '点我补上' : char === source.answer ? '正确' : answered === char ? '再想想' : '' }}</small></button>
        </div>
        <div v-if="answered !== null" class="answer-card" :class="{ good: isCorrect }" role="status" aria-label="答题反馈">
          <span class="feedback-mark"><UIcon :name="isCorrect ? 'i-lucide-circle-check' : 'i-lucide-lightbulb'" /></span>
          <div><strong>{{ isCorrect ? '补对啦，成语完整了！' : `这里应该是「${source.answer}」字。` }}</strong><p class="idiom-full">{{ source.text }}<small>{{ source.pinyin }}</small></p><p>{{ source.meaning }}</p></div>
        </div>
        <p v-else class="stage-tip"><UIcon name="i-lucide-mouse-pointer-2" />先读一读意思，再看看哪个字最合适。</p>
        <button v-if="answered !== null" class="primary-action" @click="next">{{ round.index === IDIOM_QUESTIONS - 1 ? '查看学习成果' : '下一个成语' }}<UIcon name="i-lucide-arrow-right" /></button>
      </section>

      <section v-else class="idiom-report">
        <div class="report-stars" :aria-label="`本局获得${stars}颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= stars }" /></div>
        <span class="eyebrow">第 {{ save.rounds }} 次成语课 · {{ difficulty.name }}</span>
        <h2>{{ stars === 3 ? '字字准确，成语小达人！' : '成语都学完啦，再认一认更牢！' }}</h2>
        <p>{{ round.mistakes === 0 ? '八个成语全部补对，字义也记得很清楚。' : `这次有 ${round.mistakes} 个成语需要再想一想，读读拼音和意思，下次一定行。` }}</p>
        <div class="report-stats">
          <div><span>答对成语</span><strong>{{ round.correct }}<small> / {{ IDIOM_QUESTIONS }}</small></strong></div>
          <div><span>再想一次</span><strong>{{ round.mistakes }}<small> 个</small></strong></div>
          <div><span>累计学会</span><strong>{{ save.totalCorrect }}<small> 个</small></strong></div>
        </div>
        <div class="report-best"><span>最佳记录</span><div v-for="item in idiomDifficulties" :key="item.id" :class="{ active: item.id === save.difficulty }"><span>{{ item.name }}</span><i><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.best[item.id] }" /></i></div></div>
        <div class="report-actions"><button class="secondary-action" @click="helpOpen = true"><UIcon name="i-lucide-circle-help" />看看玩法</button><button class="primary-action" @click="again"><UIcon name="i-lucide-rotate-ccw" />再来一组</button></div>
      </section>

      <footer class="idiom-footer"><span><UIcon name="i-lucide-heart" />每一次尝试，都是成长</span><span role="status" aria-label="进度保存状态"><UIcon :name="saveError ? 'i-lucide-cloud-off' : 'i-lucide-cloud-check'" />{{ saveError ? '本机暂时无法保存进度' : '进度已保存在本机' }}</span></footer>
    </main>

    <UModal :open="helpOpen" title="看意思，补汉字" description="每个成语都藏着一个空位，选出正确的汉字。" :close="{ 'aria-label': '关闭玩法说明' }" :ui="{ content: 'game-modal' }" @update:open="helpOpen = $event"><template #body><ol class="help-list"><li>先读一读卡片上的意思，想一想哪个成语合适。</li><li>再看成语里缺了哪个字，从四个选项中选出正确的字。</li><li>选好后会显示完整成语、拼音和意思，读一遍记得更牢。</li><li>每个难度有八个成语，全部答对可以获得三颗星。</li></ol><button class="primary-action" @click="helpOpen = false">明白了，开始补字<UIcon name="i-lucide-book-marked" /></button></template></UModal>
    <UModal :open="resetDifficulty !== null" :title="resetDifficulty === save.difficulty ? '重新开始这堂成语课？' : '切换游戏难度？'" description="新的一组会从第一个成语开始，当前进度会清空，最佳记录会保留。" :close="{ 'aria-label': '关闭难度确认' }" :ui="{ content: 'game-modal' }" @update:open="!$event && (resetDifficulty = null)"><template #body><div class="modal-actions"><button class="secondary-action" @click="resetDifficulty = null">继续当前学习</button><button class="primary-action" @click="applyDifficulty">{{ resetDifficulty === save.difficulty ? '重新开始' : '切换并开始' }}<UIcon name="i-lucide-arrow-right" /></button></div></template></UModal>
  </div>
</template>

<style scoped>
.idiom-game { --idiom-ink: #463a35; --idiom-muted: #9b8b81; --idiom-red: #b05243; --idiom-paper: #fbf5ea; --idiom-border: #eaddcb; min-height: 100dvh; background: #f8f1e6; color: var(--idiom-ink); font-family: var(--font-ui); letter-spacing: 0; }
.idiom-game button { cursor: pointer; transition: background .16s, transform .16s, box-shadow .16s; }
.idiom-game button:disabled { cursor: default; }
.idiom-game button:focus-visible { outline: 3px solid #b98a7c; outline-offset: 3px; }
.idiom-content { max-width: 900px; margin: auto; padding: 30px 36px 18px; }
.eyebrow { display: block; color: var(--idiom-muted); font-size: 11px; line-height: 1.6; }
.idiom-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 22px; }
.idiom-title h1 { font-size: 32px; font-weight: 750; line-height: 1.35; margin: 3px 0 0; }
.idiom-title h1 > span { color: var(--idiom-red); margin-left: 3px; }
.idiom-toolbar { display: flex; align-items: center; gap: 9px; }
.difficulty-switch { display: flex; align-items: center; gap: 3px; background: #f1e6d6; padding: 4px; border-radius: 8px; margin-right: 6px; }
.difficulty-switch button { height: 35px; padding: 0 15px; background: transparent; border-radius: 5px; color: #9f9082; font-size: 12px; white-space: nowrap; }
.difficulty-switch button.selected { color: var(--idiom-red); background: #fffaf0; box-shadow: 0 1px 4px #463a3514; font-weight: 650; }
.round-tool { width: 36px; height: 36px; display: grid; place-items: center; color: #a09082; background: transparent; border-radius: 6px; }
.round-tool:hover { background: #f1e6d6; }
.round-tool > span { width: 18px; height: 18px; }
.idiom-status { display: flex; align-items: center; gap: 34px; padding: 15px 0; border-top: 1px solid var(--idiom-border); border-bottom: 1px solid var(--idiom-border); margin-bottom: 22px; }
.status-title { display: flex; align-items: center; gap: 11px; }
.status-title > span { width: 38px; height: 38px; display: grid; place-items: center; background: #f5e7dc; color: #b2705c; border-radius: 50%; }
.status-title > span > span { width: 20px; height: 20px; }
.status-title > div { display: flex; flex-direction: column; gap: 3px; }
.status-title strong { font-size: 13px; font-weight: 650; }
.status-title small { font-size: 10px; color: var(--idiom-muted); }
.idiom-progress { flex: 1; max-width: 300px; display: flex; flex-direction: column; gap: 7px; }
.progress-caption { display: flex; justify-content: space-between; gap: 10px; color: var(--idiom-muted); font-size: 10px; }
.progress-caption strong { color: var(--idiom-red); font-weight: 600; font-variant-numeric: tabular-nums; }
.progress-rail { display: flex; gap: 5px; }
.progress-rail i { flex: 1; height: 5px; border-radius: 4px; background: #eee2d1; transition: background .3s; }
.progress-rail i.done { background: #c5856f; }
.progress-rail i.current { background: #d3aa62; box-shadow: 0 0 0 3px #d3aa6226; }
.status-stat { display: flex; align-items: center; gap: 7px; color: var(--idiom-muted); font-size: 11px; border-left: 1px solid var(--idiom-border); padding-left: 22px; }
.status-stat > span { display: flex; align-items: center; gap: 4px; }
.status-stat > span > span { width: 14px; height: 14px; color: #bd9d68; }
.status-stat:nth-of-type(4) > span > span { color: #b98a7c; }
.status-stat strong { font-size: 17px; color: var(--idiom-ink); font-variant-numeric: tabular-nums; }
.status-best { display: flex; flex-direction: column; gap: 5px; margin-left: auto; color: var(--idiom-muted); font-size: 10px; }
.status-best > span { display: flex; align-items: center; gap: 4px; }
.status-best > span > span { width: 13px; height: 13px; color: #c6a466; }
.mini-stars { display: flex; gap: 3px; }
.mini-stars > span { width: 13px; height: 13px; color: #e8ddce; }
.mini-stars > .earned { color: #d0a75c; }
.idiom-stage { position: relative; padding: 27px clamp(20px, 5vw, 52px) 26px; border: 1px solid #e7d8c3; border-radius: 10px; background: radial-gradient(circle at 96% 0, #f8eadb 0 20%, transparent 21%), linear-gradient(160deg, #fffdf7, #fbf4e7); box-shadow: 0 10px 28px #8b6f4a12; }
.stage-corner { position: absolute; top: 18px; color: #e4d1b8; font-size: 11px; border: 1px solid #e4d1b8; padding: 3px 4px; border-radius: 3px; }
.corner-one { left: 18px; }.corner-two { left: 42px; }
.stage-meta { display: flex; align-items: center; gap: 12px; }
.question-count { color: var(--idiom-muted); font-size: 10px; }
.meaning-badge { margin-left: auto; display: flex; align-items: center; gap: 4px; padding: 4px 8px; border-radius: 20px; background: #f6ecdf; color: #a98561; font-size: 9px; }
.meaning-badge > span { width: 12px; height: 12px; }
.meaning-card { display: flex; align-items: baseline; gap: 12px; margin: 17px 0 22px; padding: 13px 15px; border-left: 3px solid #d2ab76; background: #fdf8ed; border-radius: 0 6px 6px 0; }
.meaning-card > span { flex: none; color: #b09065; font-size: 9px; }
.meaning-card p { color: #786a5c; font-size: 13px; line-height: 1.75; }
.idiom-line { display: flex; justify-content: center; gap: clamp(8px, 2vw, 16px); padding: 10px 0 4px; }
.idiom-line > span { width: clamp(46px, 9vw, 66px); aspect-ratio: 1; display: grid; place-items: center; border: 1px solid #e6d9c5; border-radius: 8px; background: #fffdf8; color: #4e4139; font-size: clamp(28px, 5vw, 39px); font-weight: 650; font-family: var(--font-serif, 'Songti SC', serif); box-shadow: 0 2px 0 #e8dcc9; }
.idiom-line > span.blank { border-style: dashed; border-color: #d1b184; background: #fdf6e8; color: #c2a67d; }
.idiom-line > span.filled { border-style: solid; }
.idiom-line > span.right { border-color: #a9c6a5; background: #f0f7ed; color: #5e8466; box-shadow: 0 2px 0 #dce9d8; }
.idiom-line > span.wrong { border-color: #dfb198; background: #fdf1e9; color: #b7745a; box-shadow: 0 2px 0 #f0dfd3; animation: idiom-shake .3s ease; }
.option-prompt { margin: 22px 0 10px; text-align: center; color: #a19284; font-size: 10px; }
.option-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.option-grid button { display: flex; flex-direction: column; align-items: center; gap: 3px; min-height: 76px; padding: 9px 6px; border: 1px solid #e5d8c4; border-radius: 8px; background: #fffdf7; }
.option-grid button:not(:disabled):hover { border-color: #c9a87c; background: #fffaf0; transform: translateY(-2px); }
.option-grid button.right { border-color: #9fc09e; background: #f0f7ec; }
.option-grid button.wrong { border-color: #e0aa8d; background: #fdf1e8; animation: idiom-shake .3s ease; }
.option-char { font-size: 31px; font-weight: 650; line-height: 1.25; color: #58483e; font-family: var(--font-serif, 'Songti SC', serif); }
.option-grid button.right .option-char { color: #5d8a67; }
.option-grid button.wrong .option-char { color: #b7745a; }
.option-grid small { color: #b3a392; font-size: 8px; }
.option-grid button.right small { color: #75a07f; }
.option-grid button.wrong small { color: #bd866e; }
.answer-card { display: flex; align-items: flex-start; gap: 9px; margin-top: 15px; padding: 11px 12px; border-radius: 7px; background: #fcf1e7; color: #a77a5d; animation: answer-in .3s ease; }
.answer-card.good { background: #eff7ec; color: #719079; }
.feedback-mark { flex: none; width: 27px; height: 27px; display: grid; place-items: center; border-radius: 50%; background: #ffffffa8; }
.feedback-mark > span { width: 16px; height: 16px; }
.answer-card strong { font-size: 11px; font-weight: 650; }
.answer-card p { font-size: 10px; line-height: 1.8; margin-top: 3px; opacity: .9; }
.answer-card .idiom-full { display: flex; align-items: baseline; gap: 8px; color: #5f7f68; font-size: 15px; letter-spacing: 2px; font-weight: 600; }
.answer-card .idiom-full small { color: #8ca18c; font-size: 9px; letter-spacing: 0; font-weight: 400; }
.stage-tip { display: flex; align-items: center; justify-content: center; gap: 5px; margin-top: 15px; color: #b0a294; font-size: 9px; }
.stage-tip > span { width: 12px; height: 12px; }
.primary-action, .secondary-action { min-height: 44px; display: flex; align-items: center; justify-content: center; gap: 7px; border-radius: 7px; font-size: 12px; font-weight: 600; padding: 10px 14px; }
.primary-action { background: var(--idiom-red); color: #fff; border: 1px solid transparent; }
.primary-action:hover { background: #9c473a; }
.primary-action > span { width: 15px; height: 15px; }
.idiom-stage > .primary-action { width: 100%; margin-top: 16px; }
.secondary-action { background: #fffaf2; border: 1px solid var(--idiom-border); color: #9a8877; }
.idiom-report { padding: 34px clamp(20px, 6vw, 70px); border: 1px solid var(--idiom-border); border-radius: 10px; background: #fffdf7; text-align: center; }
.report-stars { display: flex; justify-content: center; gap: 10px; margin-bottom: 14px; }
.report-stars > span { width: 34px; height: 34px; color: #eae1d4; }
.report-stars > .earned { color: #d2a75c; filter: drop-shadow(0 2px 5px #d2a75c2e); }
.idiom-report h2 { font-size: 24px; margin: 5px 0 8px; }
.idiom-report > p { color: var(--idiom-muted); font-size: 11px; line-height: 1.8; }
.report-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); max-width: 480px; margin: 22px auto; padding: 17px 0; border-top: 1px dashed var(--idiom-border); border-bottom: 1px dashed var(--idiom-border); }
.report-stats div { display: flex; flex-direction: column; gap: 7px; }
.report-stats div + div { border-left: 1px solid #f1e8dc; }
.report-stats span { font-size: 10px; color: var(--idiom-muted); }
.report-stats strong { font-size: 23px; color: var(--idiom-red); }
.report-stats small { font-size: 11px; font-weight: 400; color: #a89787; }
.report-best { display: flex; justify-content: center; flex-wrap: wrap; gap: 8px 20px; color: var(--idiom-muted); font-size: 10px; margin-bottom: 22px; }
.report-best > span { font-weight: 600; }
.report-best > div { display: flex; align-items: center; gap: 5px; }
.report-best > div.active { color: var(--idiom-red); font-weight: 600; }
.report-best i { display: flex; gap: 2px; font-style: normal; }
.report-best i > span { width: 12px; height: 12px; color: #eae1d4; }
.report-best i > .earned { color: #d2a75c; }
.report-actions { display: flex; justify-content: center; gap: 10px; max-width: 410px; margin: auto; }
.report-actions .primary-action { flex: 1.3; }
.report-actions .secondary-action { flex: 1; }
.idiom-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; color: #b0a394; font-size: 9px; margin-top: 21px; }
.idiom-footer > span { display: flex; align-items: center; gap: 5px; }
.idiom-footer > span > span { width: 12px; height: 12px; }
.help-list { color: #7c6d62; font-size: 13px; line-height: 1.9; padding-left: 20px; list-style-type: decimal; margin-bottom: 22px; }
.help-list li + li { margin-top: 12px; }
.modal-actions { display: flex; gap: 10px; }
.modal-actions > button { flex: 1; }
@keyframes idiom-shake { 25% { transform: translateX(-3px); } 70% { transform: translateX(3px); } }
@keyframes answer-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
@media (max-width: 800px) { .idiom-content { padding: 26px 24px 16px; } .idiom-status { gap: 22px; } .status-best { display: none; } }
@media (max-width: 640px) { .idiom-heading { align-items: flex-start; } .idiom-title h1 { font-size: 28px; } .idiom-status { flex-wrap: wrap; gap: 13px 18px; } .idiom-progress { order: 5; flex-basis: 100%; max-width: none; } .status-best { display: flex; margin-left: 0; } .status-stat { padding-left: 16px; } }
@media (max-width: 540px) { .idiom-content { padding: 21px 16px 14px; } .idiom-heading { flex-wrap: wrap; gap: 12px; margin-bottom: 16px; } .idiom-title { width: 100%; } .idiom-title h1 { font-size: 27px; } .idiom-toolbar { width: 100%; gap: 5px; } .difficulty-switch { margin-right: auto; padding: 3px; } .difficulty-switch button { padding: 0 12px; min-height: 38px; font-size: 11px; } .round-tool { width: 32px; height: 40px; } .idiom-status { padding: 12px 0; margin-bottom: 16px; gap: 12px 14px; } .status-title > span { width: 32px; height: 32px; } .status-title strong { font-size: 12px; } .status-stat { font-size: 10px; gap: 5px; } .status-stat strong { font-size: 15px; } .status-best { flex-direction: row; align-items: center; gap: 7px; } .idiom-stage { padding: 21px 16px 20px; } .stage-corner { display: none; } .meaning-card { flex-direction: column; gap: 4px; padding: 11px 12px; } .meaning-card p { font-size: 12px; } .idiom-line { gap: 7px; } .idiom-line > span { width: clamp(42px, 18vw, 58px); font-size: clamp(25px, 10vw, 33px); } .option-grid { gap: 7px; } .option-grid button { min-height: 68px; padding: 7px 4px; } .option-char { font-size: 27px; } .answer-card { padding: 10px; } .answer-card .idiom-full { flex-wrap: wrap; font-size: 14px; gap: 3px 7px; } .idiom-report { padding: 26px 18px; } .idiom-report h2 { font-size: 20px; } .report-stars > span { width: 28px; height: 28px; } .report-actions { flex-direction: column-reverse; } .report-actions .primary-action, .report-actions .secondary-action { flex: none; } .idiom-footer { font-size: 8px; } }
@media (max-width: 360px) { .status-stat:nth-of-type(4) { display: none; } .difficulty-switch button { padding: 0 9px; } .idiom-line > span { width: 38px; font-size: 23px; } .option-char { font-size: 24px; } .option-grid small { font-size: 7px; } }
@media (prefers-reduced-motion: reduce) { .idiom-line > span.wrong, .option-grid button.wrong, .answer-card { animation: none; } .option-grid button:hover { transform: none; } }
</style>
