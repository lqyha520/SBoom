<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import GameNav from './GameNav.vue'
import {
  advanceRocket, answerRocket, newRocket, restartRocket, restoreRocket,
  ROCKET_QUESTIONS, rocketDifficulties, rocketStars, switchRocketDifficulty,
  type RocketDifficulty,
} from './rocket-math'

const props = withDefaults(defineProps<{ storageKey?: string }>(), { storageKey: 'lc_game_rocket_math_v1_guest' })
function readSave() {
  try { return restoreRocket(localStorage.getItem(props.storageKey)) } catch { return null }
}
const save = ref(readSave() || newRocket())
const resetDifficulty = ref<RocketDifficulty | null>(null)
const helpOpen = ref(false)
const sound = ref(false)
const saveError = ref(false)
const flight = computed(() => save.value.flight)
const question = computed(() => flight.value.questions[flight.value.index])
const answered = computed(() => flight.value.answered)
const isCorrect = computed(() => answered.value === question.value.answer)
const finished = computed(() => flight.value.finished)
const stars = computed(() => rocketStars(flight.value))
const answeredCount = computed(() => finished.value ? ROCKET_QUESTIONS : flight.value.index + (answered.value === null ? 0 : 1))
const progress = computed(() => answeredCount.value / ROCKET_QUESTIONS)
const rocketBottom = computed(() => 10 + progress.value * 58)
const difficulty = computed(() => rocketDifficulties.find(item => item.id === save.value.difficulty)!)
const explanation = computed(() => question.value.operator === '×'
  ? '想一想乘法口诀，再选出答案。'
  : question.value.operator === '+'
    ? '把两个数合起来，再数一数。'
    : '从大数里去掉小数，就是剩下的部分。')
let audio: AudioContext | null = null
function playTone(correct: boolean) {
  if (!sound.value) return
  try {
    audio ||= new AudioContext()
    void audio.resume()
    const oscillator = audio.createOscillator()
    const gain = audio.createGain()
    oscillator.connect(gain); gain.connect(audio.destination)
    oscillator.type = 'triangle'
    oscillator.frequency.setValueAtTime(correct ? 523 : 330, audio.currentTime)
    oscillator.frequency.setValueAtTime(correct ? 784 : 247, audio.currentTime + .09)
    gain.gain.setValueAtTime(.06, audio.currentTime)
    gain.gain.exponentialRampToValueAtTime(.001, audio.currentTime + .24)
    oscillator.start(); oscillator.stop(audio.currentTime + .24)
  } catch { sound.value = false }
}
function choose(value: number) {
  const result = answerRocket(save.value, value)
  if (result !== null) playTone(result)
}
function next() {
  const result = advanceRocket(save.value)
  if (result === 'finished') playTone(true)
}
function again() { restartRocket(save.value) }
function requestDifficulty(id: RocketDifficulty) {
  if (id !== save.value.difficulty) resetDifficulty.value = id
}
function applyDifficulty() {
  if (!resetDifficulty.value) return
  if (resetDifficulty.value === save.value.difficulty) restartRocket(save.value)
  else switchRocketDifficulty(save.value, resetDifficulty.value)
  resetDifficulty.value = null
}
watch(save, value => {
  try { localStorage.setItem(props.storageKey, JSON.stringify(value)); saveError.value = false }
  catch { saveError.value = true }
}, { deep: true, immediate: true, flush: 'post' })
watch(() => props.storageKey, () => { save.value = readSave() || newRocket() })
onBeforeUnmount(() => { void audio?.close() })
</script>

<template>
  <div class="rocket-game">
    <GameNav active="rocket-math" />
    <main class="rocket-content">
      <header class="rocket-heading">
        <div class="rocket-title"><span class="eyebrow">星空数学站 · 口算练习</span><h1>口算火箭<span>.</span></h1></div>
        <div class="rocket-toolbar">
          <div class="difficulty-switch" role="group" aria-label="游戏难度">
            <button v-for="item in rocketDifficulties" :key="item.id" :title="item.age" :aria-pressed="save.difficulty === item.id" :class="{ selected: save.difficulty === item.id }" @click="requestDifficulty(item.id)">{{ item.name }}</button>
          </div>
          <UTooltip :text="sound ? '关闭音效' : '开启音效'"><button class="round-tool" :aria-label="sound ? '关闭音效' : '开启音效'" :aria-pressed="sound" @click="sound = !sound"><UIcon :name="sound ? 'i-lucide-volume-2' : 'i-lucide-volume-x'" /></button></UTooltip>
          <UTooltip text="怎么玩"><button class="round-tool" aria-label="怎么玩" @click="helpOpen = true"><UIcon name="i-lucide-circle-help" /></button></UTooltip>
        </div>
      </header>

      <section class="flight-status" aria-label="飞行数据">
        <div class="flight-label"><span><UIcon name="i-lucide-rocket" /></span><div><strong>第 {{ save.flights + (finished ? 0 : 1) }} 次飞行</strong><small>{{ difficulty.name }} · {{ difficulty.detail }}</small></div></div>
        <div class="flight-progress">
          <span class="progress-caption">本程进度<strong>{{ answeredCount }} / {{ ROCKET_QUESTIONS }}</strong></span>
          <div class="progress-rail" aria-hidden="true"><i v-for="n in ROCKET_QUESTIONS" :key="n" :class="{ done: n <= answeredCount, current: !finished && answered === null && n === flight.index + 1 }" /></div>
        </div>
        <div class="flight-stat"><span><UIcon name="i-lucide-flame" />连对</span><strong>{{ flight.bestStreak }}</strong></div>
        <div class="flight-stat"><span><UIcon name="i-lucide-circle-check" />答对</span><strong>{{ flight.correct }}</strong></div>
        <div class="flight-best"><span><UIcon name="i-lucide-star" />最佳</span><div class="mini-stars" :aria-label="`${difficulty.name}最佳${save.best[save.difficulty]}颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.best[save.difficulty] }" /></div></div>
      </section>

      <section v-if="!finished" class="flight-layout">
        <div class="space-scene" role="img" :aria-label="`小火箭已完成 ${answeredCount} / ${ROCKET_QUESTIONS} 道题`">
          <span class="star-field" aria-hidden="true" />
          <span class="planet planet-one" aria-hidden="true" /><span class="planet planet-two" aria-hidden="true" />
          <span class="orbit-line" aria-hidden="true" />
          <div class="flight-path" aria-hidden="true"><i /><i /><i /></div>
          <div class="rocket-token" :class="{ boosting: answered !== null && isCorrect, wobble: answered !== null && !isCorrect }" :style="{ bottom: rocketBottom + '%' }">
            <span class="rocket-trail" aria-hidden="true" />
            <svg viewBox="0 0 100 120" aria-hidden="true">
              <ellipse cx="50" cy="114" rx="17" ry="4" fill="#1b2448" opacity=".28" />
              <path d="M39 90c-9 10-6 20 11 28 17-8 20-18 11-28z" fill="#f2b45c" />
              <path d="M44 94c-4 7-2 14 6 20 8-6 10-13 6-20z" fill="#fbe6a2" />
              <path d="M50 5c18 15 25 35 21 59H29C25 40 32 20 50 5Z" fill="#f7f4ea" stroke="#4b587f" stroke-width="2.4" stroke-linejoin="round" />
              <path d="M50 5c9 8 15 18 18 29H32c3-11 9-21 18-29Z" fill="#dfe8f5" />
              <circle cx="50" cy="38" r="12.5" fill="#86c3dc" stroke="#4b587f" stroke-width="2.2" />
              <circle cx="45" cy="33" r="4" fill="#d8f3fa" />
              <path d="M29 48 13 79l20-6z" fill="#e47e6d" stroke="#4b587f" stroke-width="2" stroke-linejoin="round" />
              <path d="M71 48l16 31-20-6z" fill="#e47e6d" stroke="#4b587f" stroke-width="2" stroke-linejoin="round" />
              <path d="M41 63h18l-4 15H45z" fill="#e47e6d" stroke="#4b587f" stroke-width="2" stroke-linejoin="round" />
              <path d="M37 89h26" stroke="#4b587f" stroke-width="3" stroke-linecap="round" />
              <path d="M50 16v7m-3-3h6" stroke="#b8c7dd" stroke-width="1.6" stroke-linecap="round" />
            </svg>
          </div>
          <span class="altitude">高度 {{ Math.round(progress * 100) }}%</span>
          <div class="scene-footer"><span><i class="base-dot" />地球基地</span><span>目标 · 算术星球</span></div>
        </div>

        <div class="question-panel">
          <div :key="flight.index" class="question-body">
            <div class="question-meta"><span class="question-count">第 {{ flight.index + 1 }} / {{ ROCKET_QUESTIONS }} 题</span><span v-if="flight.streak > 1" class="streak-pill"><UIcon name="i-lucide-flame" />连对 {{ flight.streak }}</span></div>
            <p class="question-prompt">算一算，选出正确答案</p>
            <div class="expression" :class="{ revealed: answered !== null }"><span>{{ question.left }}</span><b>{{ question.operator }}</b><span>{{ question.right }}</span><i>=</i><strong>{{ answered === null ? '?' : question.answer }}</strong></div>
            <div class="answer-grid" role="group" aria-label="答案选项">
              <button v-for="option in question.options" :key="option" :data-value="option" :class="{ right: answered !== null && option === question.answer, wrong: answered === option && option !== question.answer }" :disabled="answered !== null" :aria-label="`选择答案 ${option}`" @click="choose(option)">{{ option }}</button>
            </div>
            <div v-if="answered !== null" class="answer-feedback" :class="{ good: isCorrect }" role="status" aria-label="答题反馈">
              <span class="feedback-icon"><UIcon :name="isCorrect ? 'i-lucide-circle-check' : 'i-lucide-lightbulb'" /></span>
              <div><strong>{{ isCorrect ? '答对了，火箭升高一格！' : '差一点点，再看看这道题。' }}</strong><p>{{ question.expression }} = {{ question.answer }}。{{ explanation }}</p></div>
            </div>
            <p v-else class="answer-tip"><UIcon name="i-lucide-mouse-pointer-2" />心算好了，就点下面的答案。</p>
            <button v-if="answered !== null" class="primary-action" @click="next">{{ flight.index === ROCKET_QUESTIONS - 1 ? '查看飞行报告' : '下一题' }}<UIcon name="i-lucide-arrow-right" /></button>
          </div>
        </div>
      </section>

      <section v-else class="flight-report">
        <div class="report-stars" :aria-label="`本次飞行获得${stars}颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= stars }" /></div>
        <span class="eyebrow">本次飞行 · {{ difficulty.name }}</span>
        <h2>{{ stars === 3 ? '完美着陆，算术星球到啦！' : '顺利着陆，再练一次会更稳！' }}</h2>
        <p>{{ flight.mistakes === 0 ? '八道题全部答对，一次都没有偏航。' : `这次有 ${flight.mistakes} 道题需要再想一想，看看下面的解析，再来一次吧。` }}</p>
        <div class="report-stats">
          <div><span>答对题数</span><strong>{{ flight.correct }}<small> / {{ ROCKET_QUESTIONS }}</small></strong></div>
          <div><span>最长连对</span><strong>{{ flight.bestStreak }}<small> 题</small></strong></div>
          <div><span>累计完成</span><strong>{{ save.flights }}<small> 次</small></strong></div>
        </div>
        <div class="report-best"><span>最佳记录</span><div v-for="item in rocketDifficulties" :key="item.id" :class="{ active: item.id === save.difficulty }"><span>{{ item.name }}</span><i><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.best[item.id] }" /></i></div></div>
        <div class="report-actions"><button class="secondary-action" @click="helpOpen = true"><UIcon name="i-lucide-circle-help" />看看玩法</button><button class="primary-action" @click="again"><UIcon name="i-lucide-rocket" />再飞一次</button></div>
      </section>

      <footer class="rocket-footer"><span><UIcon name="i-lucide-heart" />每一次尝试，都是成长</span><span role="status" aria-label="进度保存状态"><UIcon :name="saveError ? 'i-lucide-cloud-off' : 'i-lucide-cloud-check'" />{{ saveError ? '本机暂时无法保存进度' : '进度已保存在本机' }}</span></footer>
    </main>

    <UModal :open="helpOpen" title="驾驶口算火箭" description="算对一道题，火箭就升高一格。" :close="{ 'aria-label': '关闭玩法说明' }" :ui="{ content: 'game-modal' }" @update:open="helpOpen = $event"><template #body><ol class="help-list"><li>看清楚中间的算式和运算符号，在心里算出答案。</li><li>点选一个答案。答对会升高一格；答错也没关系，会告诉你正确的算法。</li><li>八道题飞完，就能看到这次飞行报告。全部答对可以获得三颗星。</li><li>在右上角切换难度，可以练习 20 以内、100 以内的加减法，或者乘法口诀。</li></ol><button class="primary-action" @click="helpOpen = false">明白了，准备起飞<UIcon name="i-lucide-rocket" /></button></template></UModal>
    <UModal :open="resetDifficulty !== null" :title="resetDifficulty === save.difficulty ? '重新开始这次飞行？' : '切换游戏难度？'" description="新的飞行会从第一题开始，当前这一程的进度会清空，最佳记录会保留。" :close="{ 'aria-label': '关闭难度确认' }" :ui="{ content: 'game-modal' }" @update:open="!$event && (resetDifficulty = null)"><template #body><div class="modal-actions"><button class="secondary-action" @click="resetDifficulty = null">继续当前飞行</button><button class="primary-action" @click="applyDifficulty">{{ resetDifficulty === save.difficulty ? '重新开始' : '切换并起飞' }}<UIcon name="i-lucide-arrow-right" /></button></div></template></UModal>
  </div>
</template>

<style scoped>
.rocket-game { --rocket-ink: #323b5e; --rocket-muted: #858fae; --rocket-indigo: #5b6bb5; --rocket-border: #e3e6f1; min-height: 100dvh; background: #f7f8fc; color: var(--rocket-ink); font-family: var(--font-ui); letter-spacing: 0; }
.rocket-game button { cursor: pointer; transition: background .16s, transform .16s, box-shadow .16s; }
.rocket-game button:disabled { cursor: default; }
.rocket-game button:focus-visible { outline: 3px solid #8da6d8; outline-offset: 3px; }
.rocket-content { max-width: 1180px; margin: auto; padding: 30px 36px 18px; }
.eyebrow { display: block; color: var(--rocket-muted); font-size: 11px; line-height: 1.6; }
.rocket-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 22px; }
.rocket-title h1 { font-size: 32px; font-weight: 750; line-height: 1.35; margin: 3px 0 0; }
.rocket-title h1 > span { color: #e8b45f; margin-left: 3px; }
.rocket-toolbar { display: flex; align-items: center; gap: 9px; }
.difficulty-switch { display: flex; align-items: center; gap: 3px; background: #eef0f8; padding: 4px; border-radius: 8px; margin-right: 6px; }
.difficulty-switch button { height: 35px; padding: 0 14px; background: transparent; border-radius: 5px; color: #8b93ad; font-size: 12px; white-space: nowrap; }
.difficulty-switch button.selected { color: var(--rocket-indigo); background: #fff; box-shadow: 0 1px 4px #323b5e14; font-weight: 650; }
.round-tool { width: 36px; height: 36px; display: grid; place-items: center; color: #8590ad; background: transparent; border-radius: 6px; }
.round-tool:hover { background: #eef0f8; }
.round-tool > span { width: 18px; height: 18px; }
.flight-status { display: flex; align-items: center; gap: 34px; padding: 15px 0; border-top: 1px solid var(--rocket-border); border-bottom: 1px solid var(--rocket-border); margin-bottom: 22px; }
.flight-label { display: flex; align-items: center; gap: 11px; }
.flight-label > span { width: 38px; height: 38px; display: grid; place-items: center; background: #eaedfa; color: #6777c2; border-radius: 50%; }
.flight-label > span > span { width: 20px; height: 20px; }
.flight-label > div { display: flex; flex-direction: column; gap: 3px; }
.flight-label strong { font-size: 13px; font-weight: 650; }
.flight-label small { font-size: 10px; color: var(--rocket-muted); }
.flight-progress { flex: 1; max-width: 300px; display: flex; flex-direction: column; gap: 7px; }
.progress-caption { display: flex; justify-content: space-between; gap: 10px; color: var(--rocket-muted); font-size: 10px; }
.progress-caption strong { color: #6572ad; font-weight: 600; font-variant-numeric: tabular-nums; }
.progress-rail { display: flex; gap: 5px; }
.progress-rail i { flex: 1; height: 5px; border-radius: 4px; background: #e7e9f2; transition: background .3s; }
.progress-rail i.done { background: #8493d6; }
.progress-rail i.current { background: #ecc478; box-shadow: 0 0 0 3px #ecc47826; }
.flight-stat { display: flex; align-items: center; gap: 7px; color: var(--rocket-muted); font-size: 11px; }
.flight-stat + .flight-stat { border-left: 1px solid var(--rocket-border); padding-left: 22px; }
.flight-stat > span { display: flex; align-items: center; gap: 4px; }
.flight-stat > span > span { width: 14px; height: 14px; color: #c9a45b; }
.flight-stat:nth-of-type(4) > span > span { color: #7f9f86; }
.flight-stat strong { font-size: 17px; color: var(--rocket-ink); font-variant-numeric: tabular-nums; }
.flight-best { display: flex; flex-direction: column; gap: 5px; margin-left: auto; color: var(--rocket-muted); font-size: 10px; }
.flight-best > span { display: flex; align-items: center; gap: 4px; }
.flight-best > span > span { width: 13px; height: 13px; color: #c9a45b; }
.mini-stars { display: flex; gap: 3px; }
.mini-stars > span { width: 13px; height: 13px; color: #dfe2eb; }
.mini-stars > .earned { color: #d9b263; }
.flight-layout { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(360px, .95fr); gap: 26px; align-items: stretch; }
.space-scene { position: relative; min-height: 478px; border-radius: 10px; overflow: hidden; background: linear-gradient(180deg, #1f294e 0%, #354273 46%, #7c8cc1 78%, #dce4f6 100%); box-shadow: inset 0 0 80px #0b133433; }
.star-field { position: absolute; inset: 0; background-image: radial-gradient(1.6px 1.6px at 12% 18%, #ffffffdd 50%, transparent 51%), radial-gradient(1.2px 1.2px at 32% 8%, #ffffffbb 50%, transparent 51%), radial-gradient(1.8px 1.8px at 68% 14%, #fff3cfdd 50%, transparent 51%), radial-gradient(1px 1px at 85% 26%, #ffffffaa 50%, transparent 51%), radial-gradient(1.5px 1.5px at 22% 42%, #ffffffa8 50%, transparent 51%), radial-gradient(1.2px 1.2px at 76% 46%, #ffffffcc 50%, transparent 51%), radial-gradient(1px 1px at 46% 30%, #ffffff88 50%, transparent 51%), radial-gradient(1.6px 1.6px at 58% 58%, #ffffffb8 50%, transparent 51%), radial-gradient(1.1px 1.1px at 9% 62%, #ffffff8f 50%, transparent 51%), radial-gradient(1.4px 1.4px at 91% 66%, #ffffff9e 50%, transparent 51%); animation: twinkle 4s ease-in-out infinite alternate; }
.planet { position: absolute; border-radius: 50%; }
.planet-one { width: 76px; height: 76px; right: 28px; top: 46px; background: radial-gradient(circle at 32% 30%, #f6cf9a, #d9886c 64%, #a45f57); box-shadow: 0 0 0 10px #f0c79c12, 0 0 34px #f0b48026; }
.planet-one::after { content: ''; position: absolute; width: 110px; height: 26px; left: -17px; top: 27px; border: 4px solid #f4d8b090; border-radius: 50%; transform: rotate(-18deg); border-top-color: transparent; border-left-color: transparent; }
.planet-two { width: 30px; height: 30px; left: 34px; top: 96px; background: radial-gradient(circle at 34% 32%, #b8d9e8, #7896c4 72%); box-shadow: 0 0 0 6px #ffffff0d; }
.orbit-line { position: absolute; right: -46px; top: 22px; width: 210px; height: 210px; border: 1px dashed #ffffff2b; border-radius: 50%; transform: rotate(18deg); }
.flight-path { position: absolute; left: 50%; top: 14%; bottom: 17%; border-left: 2px dashed #ffffff2e; transform: translateX(-50%); }
.flight-path i { position: absolute; left: -4px; width: 6px; height: 6px; border-radius: 50%; background: #ffffff7d; }
.flight-path i:nth-child(1) { top: 8%; }.flight-path i:nth-child(2) { top: 48%; }.flight-path i:nth-child(3) { top: 88%; }
.rocket-token { position: absolute; left: 50%; width: clamp(70px, 16%, 102px); transform: translateX(-50%); transition: bottom .65s cubic-bezier(.2,.8,.3,1); z-index: 2; }
.rocket-token svg { width: 100%; height: auto; display: block; filter: drop-shadow(0 10px 10px #121a3a45); }
.rocket-trail { position: absolute; left: 50%; bottom: -22%; width: 12px; height: 30%; transform: translateX(-50%); background: linear-gradient(180deg, #f8c674aa, transparent); border-radius: 50%; filter: blur(2px); opacity: .55; }
.rocket-token.boosting { animation: rocket-boost .6s ease; }
.rocket-token.wobble { animation: rocket-wobble .45s ease; }
.altitude { position: absolute; top: 18px; left: 20px; padding: 6px 9px; border-radius: 5px; background: #ffffff12; border: 1px solid #ffffff1f; color: #e8ecffb8; font-size: 10px; backdrop-filter: blur(3px); }
.scene-footer { position: absolute; left: 0; bottom: 0; width: 100%; display: flex; justify-content: space-between; gap: 8px; padding: 12px 20px; color: #edf1ffc0; font-size: 10px; background: linear-gradient(180deg, transparent, #232c4c8a); }
.scene-footer > span:first-child { display: flex; align-items: center; gap: 6px; }
.base-dot { width: 5px; height: 5px; border-radius: 50%; background: #8fe0b4; box-shadow: 0 0 0 3px #8fe0b423; }
.question-panel { background: #fff; border: 1px solid var(--rocket-border); border-radius: 10px; padding: 24px; display: flex; min-width: 0; }
.question-body { width: 100%; display: flex; flex-direction: column; animation: question-in .32s ease-out; }
.question-meta { display: flex; align-items: center; gap: 10px; }
.question-count { font-size: 11px; color: var(--rocket-muted); }
.streak-pill { margin-left: auto; display: flex; align-items: center; gap: 4px; background: #fcf1dc; color: #c39045; font-size: 10px; padding: 4px 8px; border-radius: 20px; }
.streak-pill > span { width: 12px; height: 12px; }
.question-prompt { font-size: 12px; color: var(--rocket-muted); margin: 14px 0 6px; }
.expression { display: flex; align-items: center; gap: clamp(9px, 2vw, 17px); color: #3b466e; font-size: clamp(35px, 5.2vw, 52px); font-weight: 700; line-height: 1.35; font-variant-numeric: tabular-nums; }
.expression b { color: #8b97cf; font-weight: 500; }
.expression i { color: #c0c5d8; font-style: normal; font-weight: 400; }
.expression strong { color: #e8b45f; min-width: 1.4em; }
.expression.revealed strong { color: #65a183; }
.answer-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 21px 0 4px; }
.answer-grid button { min-height: 64px; border: 1px solid #e1e5f0; border-radius: 8px; background: #f8f9fd; color: #46527b; font-size: 23px; font-weight: 650; font-variant-numeric: tabular-nums; }
.answer-grid button:not(:disabled):hover { border-color: #a9b6e3; background: #f1f4ff; transform: translateY(-1px); }
.answer-grid button.right { background: #edf7f0; border-color: #9bc7aa; color: #4e8d6a; }
.answer-grid button.wrong { background: #fdf0e7; border-color: #e9b18f; color: #bd734c; animation: answer-shake .3s ease; }
.answer-tip { display: flex; align-items: center; gap: 5px; color: #a7aec5; font-size: 10px; margin-top: 10px; }
.answer-tip > span { width: 13px; height: 13px; }
.answer-feedback { display: flex; align-items: flex-start; gap: 9px; margin-top: 13px; padding: 11px 12px; background: #fcf4e8; color: #a67a50; border-radius: 7px; }
.answer-feedback.good { background: #eef7f0; color: #71927b; }
.feedback-icon { width: 27px; height: 27px; flex: none; display: grid; place-items: center; background: #ffffff9e; border-radius: 50%; }
.feedback-icon > span { width: 16px; height: 16px; }
.answer-feedback strong { font-size: 11px; font-weight: 650; }
.answer-feedback p { font-size: 10px; line-height: 1.8; margin: 3px 0 0; opacity: .86; }
.primary-action, .secondary-action { min-height: 44px; display: flex; align-items: center; justify-content: center; gap: 7px; border-radius: 7px; font-size: 12px; font-weight: 600; padding: 10px 14px; }
.primary-action { background: var(--rocket-indigo); color: #fff; border: 1px solid transparent; }
.primary-action:hover { background: #4d5da6; }
.primary-action > span { width: 15px; height: 15px; }
.question-panel .primary-action { width: 100%; margin-top: auto; }
.secondary-action { background: #fff; border: 1px solid var(--rocket-border); color: #7e88a5; }
.secondary-action:hover { background: #f7f8fd; }
.secondary-action > span { width: 14px; height: 14px; }
.flight-report { background: #fff; border: 1px solid var(--rocket-border); border-radius: 10px; padding: 34px clamp(20px, 6vw, 70px); text-align: center; }
.report-stars { display: flex; justify-content: center; gap: 10px; margin-bottom: 14px; }
.report-stars > span { width: 34px; height: 34px; color: #e2e5ee; }
.report-stars > .earned { color: #e4b75e; filter: drop-shadow(0 2px 5px #e4b75e2e); }
.flight-report h2 { font-size: 24px; margin: 5px 0 8px; }
.flight-report > p { color: var(--rocket-muted); font-size: 11px; line-height: 1.8; }
.report-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); max-width: 480px; margin: 22px auto; border-top: 1px dashed var(--rocket-border); border-bottom: 1px dashed var(--rocket-border); padding: 17px 0; }
.report-stats div { display: flex; flex-direction: column; gap: 7px; }
.report-stats div + div { border-left: 1px solid #eef0f6; }
.report-stats span { font-size: 10px; color: var(--rocket-muted); }
.report-stats strong { font-size: 23px; color: var(--rocket-indigo); }
.report-stats small { font-size: 11px; font-weight: 400; color: #9aa3bf; }
.report-best { display: flex; justify-content: center; flex-wrap: wrap; gap: 8px 20px; color: var(--rocket-muted); font-size: 10px; margin-bottom: 22px; }
.report-best > span { font-weight: 600; }
.report-best > div { display: flex; align-items: center; gap: 5px; }
.report-best > div.active { color: var(--rocket-indigo); font-weight: 600; }
.report-best i { display: flex; gap: 2px; font-style: normal; }
.report-best i > span { width: 12px; height: 12px; color: #e1e4ec; }
.report-best i > .earned { color: #dcb366; }
.report-actions { display: flex; justify-content: center; gap: 10px; max-width: 400px; margin: auto; }
.report-actions .primary-action { flex: 1.4; }
.report-actions .secondary-action { flex: 1; }
.rocket-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; color: #a5adc2; font-size: 9px; margin-top: 21px; }
.rocket-footer > span { display: flex; align-items: center; gap: 5px; }
.rocket-footer > span > span { width: 12px; height: 12px; }
.help-list { color: #6e7894; font-size: 13px; line-height: 1.9; padding-left: 20px; list-style-type: decimal; margin-bottom: 22px; }
.help-list li + li { margin-top: 12px; }
.modal-actions { display: flex; gap: 10px; }
.modal-actions > button { flex: 1; }
@keyframes question-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
@keyframes twinkle { from { opacity: .72; } to { opacity: 1; } }
@keyframes rocket-boost { 0%, 100% { transform: translateX(-50%) translateY(0) rotate(0); } 45% { transform: translateX(-50%) translateY(-9px) rotate(-2deg); } }
@keyframes rocket-wobble { 25% { transform: translateX(-53%) rotate(-3deg); } 70% { transform: translateX(-47%) rotate(3deg); } }
@keyframes answer-shake { 25% { transform: translateX(-3px); } 70% { transform: translateX(3px); } }
@media (max-width: 1000px) { .rocket-content { padding: 26px 24px 16px; } .flight-layout { grid-template-columns: minmax(0, 1fr) minmax(330px, 1fr); gap: 18px; } .space-scene { min-height: 440px; } .flight-status { gap: 22px; } .flight-best { display: none; } }
@media (max-width: 760px) { .rocket-heading { align-items: flex-start; } .rocket-title h1 { font-size: 28px; } .flight-layout { grid-template-columns: minmax(0, 1fr); } .space-scene { min-height: 300px; } .rocket-token { width: clamp(60px, 14%, 84px); } .question-panel { padding: 20px; } .answer-grid button { min-height: 58px; } .flight-status { flex-wrap: wrap; gap: 14px 22px; } .flight-progress { order: 4; flex-basis: 100%; max-width: none; } .flight-best { display: flex; margin-left: 0; } .flight-stat + .flight-stat { padding-left: 16px; } }
@media (max-width: 540px) { .rocket-content { padding: 21px 16px 14px; } .rocket-heading { flex-wrap: wrap; gap: 12px; margin-bottom: 16px; } .rocket-title { width: 100%; } .rocket-title h1 { font-size: 27px; } .rocket-toolbar { width: 100%; gap: 5px; } .difficulty-switch { margin-right: auto; padding: 3px; } .difficulty-switch button { padding: 0 11px; min-height: 38px; font-size: 11px; } .round-tool { width: 32px; height: 40px; } .flight-status { padding: 12px 0; margin-bottom: 16px; gap: 12px 14px; } .flight-label > span { width: 32px; height: 32px; } .flight-label strong { font-size: 12px; } .flight-stat { font-size: 10px; } .flight-stat strong { font-size: 15px; } .flight-best { flex-direction: row; align-items: center; gap: 7px; } .space-scene { min-height: 270px; } .planet-one { width: 58px; height: 58px; right: 18px; top: 35px; } .planet-one::after { width: 86px; left: -14px; top: 21px; } .planet-two { left: 20px; top: 70px; width: 23px; height: 23px; } .orbit-line { width: 160px; height: 160px; right: -36px; } .altitude { top: 12px; left: 12px; } .question-panel { padding: 18px 16px; } .expression { gap: 10px; font-size: 40px; } .answer-grid { gap: 8px; margin-top: 17px; } .answer-grid button { min-height: 55px; font-size: 21px; } .answer-feedback { padding: 10px; } .rocket-footer { font-size: 8px; } .flight-report { padding: 26px 18px; } .flight-report h2 { font-size: 20px; } .report-stars > span { width: 28px; height: 28px; } .report-actions { flex-direction: column-reverse; } .report-actions .primary-action, .report-actions .secondary-action { flex: none; } }
@media (max-width: 360px) { .flight-stat:nth-of-type(3) { display: none; } .difficulty-switch button { padding: 0 8px; } .flight-label small { display: none; } .expression { font-size: 36px; } .space-scene { min-height: 245px; } }
@media (prefers-reduced-motion: reduce) { .star-field, .rocket-token.boosting, .rocket-token.wobble, .answer-grid button.wrong, .question-body { animation: none; } .rocket-token, .progress-rail i { transition: none; } }
</style>
