<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import GameNav from './GameNav.vue'
import {
  advanceClock, answerClock, CLOCK_QUESTIONS, clockDifficulties, clockExplanation, clockStars,
  formatClock, newClock, restartClock, restoreClock, switchClockDifficulty, type ClockDifficulty,
} from './clock-town'

const props = withDefaults(defineProps<{ storageKey?: string }>(), { storageKey: 'lc_game_clock_town_v1_guest' })
function readSave() {
  try { return restoreClock(localStorage.getItem(props.storageKey)) } catch { return null }
}
const save = ref(readSave() || newClock())
const resetDifficulty = ref<ClockDifficulty | null>(null)
const helpOpen = ref(false)
const saveError = ref(false)
const round = computed(() => save.value.round)
const question = computed(() => round.value.questions[round.value.index])
const difficulty = computed(() => clockDifficulties.find(item => item.id === save.value.difficulty)!)
const answered = computed(() => round.value.answered)
const isCorrect = computed(() => answered.value === question.value.answer)
const finished = computed(() => round.value.finished)
const stars = computed(() => clockStars(round.value))
const answeredCount = computed(() => finished.value ? CLOCK_QUESTIONS : round.value.index + (answered.value === null ? 0 : 1))
const explanation = computed(() => clockExplanation(question.value))
const digital = computed(() => formatClock(question.value.hour, question.value.minute))
const hourAngle = computed(() => (question.value.hour % 12) * 30 + question.value.minute * .5)
const minuteAngle = computed(() => question.value.minute * 6)
const ticks = Array.from({ length: 60 }, (_, index) => index)
const numbers = Array.from({ length: 12 }, (_, index) => {
  const value = index + 1
  const angle = value * Math.PI / 6
  return { value, x: 100 + 62 * Math.sin(angle), y: 100 - 62 * Math.cos(angle) }
})

function choose(value: string) {
  answerClock(save.value, value)
}
function next() {
  advanceClock(save.value)
}
function again() {
  restartClock(save.value)
}
function requestDifficulty(id: ClockDifficulty) {
  if (id !== save.value.difficulty) resetDifficulty.value = id
}
function applyDifficulty() {
  if (!resetDifficulty.value) return
  if (resetDifficulty.value === save.value.difficulty) restartClock(save.value)
  else switchClockDifficulty(save.value, resetDifficulty.value)
  resetDifficulty.value = null
}
watch(save, value => {
  try { localStorage.setItem(props.storageKey, JSON.stringify(value)); saveError.value = false }
  catch { saveError.value = true }
}, { deep: true, immediate: true, flush: 'post' })
watch(() => props.storageKey, () => { save.value = readSave() || newClock() })
</script>

<template>
  <div class="clock-game">
    <GameNav active="clock-town" />
    <main class="clock-content">
      <header class="clock-heading">
        <div class="clock-title"><span class="eyebrow">太阳花小镇 · 数学时间</span><h1>时钟小镇<span>.</span></h1></div>
        <div class="clock-toolbar">
          <div class="difficulty-switch" role="group" aria-label="游戏难度">
            <button v-for="item in clockDifficulties" :key="item.id" :title="item.age" :aria-pressed="save.difficulty === item.id" :class="{ selected: save.difficulty === item.id }" @click="requestDifficulty(item.id)">{{ item.name }}</button>
          </div>
          <UTooltip text="怎么玩"><button class="round-tool" aria-label="怎么玩" @click="helpOpen = true"><UIcon name="i-lucide-circle-help" /></button></UTooltip>
        </div>
      </header>

      <section class="clock-status" aria-label="认时间进度">
        <div class="status-title"><span><UIcon name="i-lucide-clock-3" /></span><div><strong>小镇钟楼</strong><small>{{ difficulty.name }} · {{ difficulty.detail }}</small></div></div>
        <div class="clock-progress">
          <span class="progress-caption">读对的时间<strong>{{ answeredCount }} / {{ CLOCK_QUESTIONS }}</strong></span>
          <div class="progress-rail" aria-hidden="true"><i v-for="n in CLOCK_QUESTIONS" :key="n" :class="{ done: n <= answeredCount, current: !finished && answered === null && n === round.index + 1 }" /></div>
        </div>
        <div class="status-stat"><span><UIcon name="i-lucide-circle-check" />答对</span><strong>{{ round.correct }}</strong></div>
        <div class="status-stat"><span><UIcon name="i-lucide-rotate-ccw" />再看</span><strong>{{ round.mistakes }}</strong></div>
        <div class="status-best"><span><UIcon name="i-lucide-star" />最佳</span><div class="mini-stars" :aria-label="`${difficulty.name}最佳${save.best[save.difficulty]}颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.best[save.difficulty] }" /></div></div>
      </section>

      <section v-if="!finished" class="clock-board">
        <div class="clock-scene" aria-label="小镇钟楼">
          <span class="sun" aria-hidden="true" /><span class="cloud cloud-one" aria-hidden="true" /><span class="cloud cloud-two" aria-hidden="true" />
          <span class="scene-bird bird-one" aria-hidden="true">⌄</span><span class="scene-bird bird-two" aria-hidden="true">⌄</span>
          <div class="clock-frame">
            <div class="clock-plate">
              <svg viewBox="0 0 200 200" role="img" aria-label="一个指针式时钟，请读出显示的时间">
                <circle class="dial-rim" cx="100" cy="100" r="95" />
                <circle class="dial-face" cx="100" cy="100" r="86" />
                <g class="dial-ticks" aria-hidden="true">
                  <line v-for="tick in ticks" :key="tick" x1="100" :y1="tick % 5 === 0 ? 18 : 21" x2="100" y2="26" :transform="`rotate(${tick * 6} 100 100)`" />
                </g>
                <g class="dial-numbers" aria-hidden="true">
                  <text v-for="mark in numbers" :key="mark.value" :x="mark.x" :y="mark.y" text-anchor="middle" dominant-baseline="central">{{ mark.value }}</text>
                </g>
                <line class="hour-hand" x1="100" y1="100" x2="100" y2="56" :transform="`rotate(${hourAngle} 100 100)`" />
                <line class="minute-hand" x1="100" y1="100" x2="100" y2="37" :transform="`rotate(${minuteAngle} 100 100)`" />
                <circle class="hand-cap" cx="100" cy="100" r="6" />
              </svg>
            </div>
            <span class="frame-feet" aria-hidden="true" />
          </div>
          <div class="town-roofs" aria-hidden="true"><span class="roof roof-one" /><span class="roof roof-two" /><span class="roof roof-three" /><span class="roof roof-four" /></div>
          <div class="clock-lcd" :class="{ revealed: answered !== null }"><span>{{ answered === null ? '— — : — —' : digital }}</span><small>{{ answered === null ? '钟面时间' : '正确时间' }}</small></div>
          <div class="scene-footer"><span><i />第 {{ round.index + 1 }} / {{ CLOCK_QUESTIONS }} 个时间</span><span>{{ answered === null ? '看看时针和分针' : isCorrect ? '读对啦！' : '再读一遍钟面' }}</span></div>
        </div>

        <div class="clock-panel">
          <div class="panel-meta"><span class="question-count">第 {{ round.index + 1 }} / {{ CLOCK_QUESTIONS }} 题</span><span class="time-badge"><UIcon name="i-lucide-sun" />{{ difficulty.name }}</span></div>
          <h2>现在是几点？</h2>
          <p class="panel-prompt">{{ difficulty.id === 'starter' ? '分针指向 12 时，看看时针指向几。' : difficulty.id === 'explorer' ? '看看分针走过了一刻、半点还是一刻钟。' : '先看分针指向数字几，再看时针在哪里。' }}</p>
          <div class="time-options" role="group" aria-label="时间选项">
            <button v-for="option in question.options" :key="option" :data-time="option" :class="{ right: answered !== null && option === question.answer, wrong: answered === option && option !== question.answer }" :disabled="answered !== null" :aria-label="`选择时间 ${option}`" @click="choose(option)">
              <UIcon name="i-lucide-clock" />
              <strong>{{ option }}</strong>
              <small>{{ option.endsWith(':00') ? '整点' : option.endsWith(':30') ? '半点' : option.endsWith(':15') || option.endsWith(':45') ? '一刻' : '五分' }}</small>
            </button>
          </div>
          <div v-if="answered !== null" class="clock-feedback" :class="{ good: isCorrect }" role="status" aria-label="答题反馈">
            <span class="feedback-mark"><UIcon :name="isCorrect ? 'i-lucide-circle-check' : 'i-lucide-lightbulb'" /></span>
            <div><strong>{{ isCorrect ? '读对啦，钟楼为你亮灯！' : '再看看时针和分针的位置。' }}</strong><p>{{ explanation }}</p></div>
          </div>
          <p v-else class="clock-tip"><UIcon name="i-lucide-mouse-pointer-2" />读一读钟面，再选出下面的电子时间。</p>
          <button v-if="answered !== null" class="primary-action" @click="next">{{ round.index === CLOCK_QUESTIONS - 1 ? '查看读时成绩' : '下一个时间' }}<UIcon name="i-lucide-arrow-right" /></button>
        </div>
      </section>

      <section v-else class="clock-report">
        <div class="report-stars" :aria-label="`本局获得${stars}颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= stars }" /></div>
        <span class="eyebrow">第 {{ save.rounds }} 次读时 · {{ difficulty.name }}</span>
        <h2>{{ stars === 3 ? '时间读得又快又准，钟楼小主人！' : '时间都认出来啦，再看一遍会更准！' }}</h2>
        <p>{{ round.mistakes === 0 ? '八个时间一次读对，时针和分针都看得很仔细。' : `这次有 ${round.mistakes} 个时间需要再看一看，记住短针是时针、长针是分针。` }}</p>
        <div class="report-stats">
          <div><span>读对时间</span><strong>{{ round.correct }}<small> / {{ CLOCK_QUESTIONS }}</small></strong></div>
          <div><span>再看一次</span><strong>{{ round.mistakes }}<small> 个</small></strong></div>
          <div><span>累计读时</span><strong>{{ save.totalCorrect }}<small> 个</small></strong></div>
        </div>
        <div class="report-best"><span>最佳记录</span><div v-for="item in clockDifficulties" :key="item.id" :class="{ active: item.id === save.difficulty }"><span>{{ item.name }}</span><i><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.best[item.id] }" /></i></div></div>
        <div class="report-actions"><button class="secondary-action" @click="helpOpen = true"><UIcon name="i-lucide-circle-help" />看看玩法</button><button class="primary-action" @click="again"><UIcon name="i-lucide-rotate-ccw" />再读一轮</button></div>
      </section>

      <footer class="clock-footer"><span><UIcon name="i-lucide-heart" />每一次尝试，都是成长</span><span role="status" aria-label="进度保存状态"><UIcon :name="saveError ? 'i-lucide-cloud-off' : 'i-lucide-cloud-check'" />{{ saveError ? '本机暂时无法保存进度' : '进度已保存在本机' }}</span></footer>
    </main>

    <UModal :open="helpOpen" title="看钟面，认时间" description="短针是时针，长针是分针。" :close="{ 'aria-label': '关闭玩法说明' }" :ui="{ content: 'game-modal' }" @update:open="helpOpen = $event"><template #body><ol class="help-list"><li>短而粗的针是时针，长而细的针是分针。</li><li>分针指向 12 是整点，指向 6 是半点，指向 3 是一刻，指向 9 是三刻。</li><li>分针每走一个数字是 5 分钟。先读分针，再读时针。</li><li>在整点时，时针正好指向数字；其他时间，时针会在两个数字之间。</li><li>选出对应的电子时间，答对后还能看到读时的解释。</li></ol><button class="primary-action" @click="helpOpen = false">明白了，去读时间<UIcon name="i-lucide-clock-3" /></button></template></UModal>
    <UModal :open="resetDifficulty !== null" :title="resetDifficulty === save.difficulty ? '重新开始读时间？' : '切换游戏难度？'" description="新的一轮会从第一个时间开始，当前进度会清空，最佳记录会保留。" :close="{ 'aria-label': '关闭难度确认' }" :ui="{ content: 'game-modal' }" @update:open="!$event && (resetDifficulty = null)"><template #body><div class="modal-actions"><button class="secondary-action" @click="resetDifficulty = null">继续当前读时</button><button class="primary-action" @click="applyDifficulty">{{ resetDifficulty === save.difficulty ? '重新开始' : '切换并开始' }}<UIcon name="i-lucide-arrow-right" /></button></div></template></UModal>
  </div>
</template>

<style scoped>
.clock-game { --clock-ink: #314a58; --clock-muted: #879ca7; --clock-blue: #4f83a3; --clock-border: #dce9ee; min-height: 100dvh; background: #f3f9fb; color: var(--clock-ink); font-family: var(--font-ui); letter-spacing: 0; }
.clock-game button { cursor: pointer; transition: background .16s, transform .16s, box-shadow .16s; }
.clock-game button:disabled { cursor: default; }
.clock-game button:focus-visible { outline: 3px solid #7fa9c1; outline-offset: 3px; }
.clock-content { max-width: 1140px; margin: auto; padding: 30px 36px 18px; }
.eyebrow { display: block; color: var(--clock-muted); font-size: 11px; line-height: 1.6; }
.clock-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 22px; }
.clock-title h1 { font-size: 32px; font-weight: 750; line-height: 1.35; margin: 3px 0 0; }
.clock-title h1 > span { color: #e29a6a; margin-left: 3px; }
.clock-toolbar { display: flex; align-items: center; gap: 9px; }
.difficulty-switch { display: flex; align-items: center; gap: 3px; background: #e7f1f5; padding: 4px; border-radius: 8px; margin-right: 6px; }
.difficulty-switch button { height: 35px; padding: 0 15px; background: transparent; border-radius: 5px; color: #8da3ad; font-size: 12px; white-space: nowrap; }
.difficulty-switch button.selected { color: var(--clock-blue); background: #fff; box-shadow: 0 1px 4px #314a5814; font-weight: 650; }
.round-tool { width: 36px; height: 36px; display: grid; place-items: center; color: #8ba1ac; background: transparent; border-radius: 6px; }
.round-tool:hover { background: #e7f1f5; }
.round-tool > span { width: 18px; height: 18px; }
.clock-status { display: flex; align-items: center; gap: 34px; padding: 15px 0; border-top: 1px solid var(--clock-border); border-bottom: 1px solid var(--clock-border); margin-bottom: 22px; }
.status-title { display: flex; align-items: center; gap: 11px; }
.status-title > span { width: 38px; height: 38px; display: grid; place-items: center; background: #e5f1f7; color: #5888a5; border-radius: 50%; }
.status-title > span > span { width: 20px; height: 20px; }
.status-title > div { display: flex; flex-direction: column; gap: 3px; }
.status-title strong { font-size: 13px; font-weight: 650; }
.status-title small { font-size: 10px; color: var(--clock-muted); }
.clock-progress { flex: 1; max-width: 300px; display: flex; flex-direction: column; gap: 7px; }
.progress-caption { display: flex; justify-content: space-between; gap: 10px; color: var(--clock-muted); font-size: 10px; }
.progress-caption strong { color: var(--clock-blue); font-weight: 600; font-variant-numeric: tabular-nums; }
.progress-rail { display: flex; gap: 5px; }
.progress-rail i { flex: 1; height: 5px; border-radius: 4px; background: #e1edf1; transition: background .3s; }
.progress-rail i.done { background: #79a8c0; }
.progress-rail i.current { background: #e4ad63; box-shadow: 0 0 0 3px #e4ad6326; }
.status-stat { display: flex; align-items: center; gap: 7px; color: var(--clock-muted); font-size: 11px; border-left: 1px solid var(--clock-border); padding-left: 22px; }
.status-stat > span { display: flex; align-items: center; gap: 4px; }
.status-stat > span > span { width: 14px; height: 14px; color: #c0a060; }
.status-stat:nth-of-type(4) > span > span { color: #c4957a; }
.status-stat strong { font-size: 17px; color: var(--clock-ink); font-variant-numeric: tabular-nums; }
.status-best { display: flex; flex-direction: column; gap: 5px; margin-left: auto; color: var(--clock-muted); font-size: 10px; }
.status-best > span { display: flex; align-items: center; gap: 4px; }
.status-best > span > span { width: 13px; height: 13px; color: #c8a45c; }
.mini-stars { display: flex; gap: 3px; }
.mini-stars > span { width: 13px; height: 13px; color: #dfeaee; }
.mini-stars > .earned { color: #d5aa5e; }
.clock-board { display: grid; grid-template-columns: minmax(0, 1.02fr) minmax(360px, .98fr); gap: 24px; align-items: stretch; }
.clock-scene { position: relative; overflow: hidden; min-height: 500px; padding: 26px 20px 0; border: 1px solid #d7e7ec; border-radius: 12px; background: linear-gradient(180deg, #d9f0f7 0%, #eaf8fb 52%, #d5ede1 53%, #bfe2d0 100%); }
.sun { position: absolute; top: 26px; right: 34px; width: 47px; height: 47px; border-radius: 50%; background: radial-gradient(circle at 36% 34%, #fff0ba, #f4c568 64%, #eab052); box-shadow: 0 0 0 10px #f7d58b2e, 0 0 28px #f6cf7a4d; }
.cloud { position: absolute; height: 16px; border-radius: 20px; background: #ffffffc7; }
.cloud::before, .cloud::after { content: ''; position: absolute; border-radius: 50%; background: inherit; }
.cloud-one { top: 52px; left: 30px; width: 62px; }.cloud-one::before { width: 24px; height: 24px; left: 10px; top: -11px; }.cloud-one::after { width: 17px; height: 17px; right: 9px; top: -8px; }
.cloud-two { top: 106px; left: 92px; width: 40px; height: 12px; opacity: .8; }.cloud-two::before { width: 17px; height: 17px; left: 8px; top: -8px; }
.scene-bird { position: absolute; color: #8fb7c4; font-size: 15px; transform: rotate(-12deg); }
.bird-one { top: 88px; right: 104px; }.bird-two { top: 70px; right: 80px; font-size: 11px; }
.clock-frame { position: relative; z-index: 2; width: min(78%, 330px); margin: 24px auto 0; padding: 12px; border-radius: 50%; background: linear-gradient(150deg, #fbf4e4, #ecd9b8); box-shadow: 0 18px 34px #6b87773d, inset 0 -5px 0 #d9c29c; }
.clock-plate { aspect-ratio: 1; padding: 8px; border-radius: 50%; background: #fffdf6; box-shadow: inset 0 0 0 1px #e6d7bd, inset 0 4px 12px #d8c6a52e; }
.clock-plate svg { width: 100%; height: 100%; display: block; }
.dial-rim { fill: none; stroke: #d8c7a8; stroke-width: 4; }
.dial-face { fill: #fffdf7; stroke: #ebdfca; stroke-width: 1; }
.dial-ticks line { stroke: #c8b899; stroke-width: 1.3; }
.dial-ticks line:nth-child(5n + 1) { stroke: #7d8f94; stroke-width: 2.6; }
.dial-numbers text { fill: #506872; font-size: 13px; font-weight: 650; font-family: var(--font-ui); }
.hour-hand { stroke: #3e6172; stroke-width: 7; stroke-linecap: round; }
.minute-hand { stroke: #d98767; stroke-width: 4.5; stroke-linecap: round; }
.hand-cap { fill: #3e6172; stroke: #fffdf7; stroke-width: 3; }
.frame-feet { position: absolute; bottom: -7px; left: 50%; width: 46%; height: 9px; transform: translateX(-50%); border-radius: 50%; background: #d9c19b; filter: blur(1px); opacity: .6; }
.town-roofs { position: absolute; left: 0; right: 0; bottom: 0; height: 92px; z-index: 1; }
.roof { position: absolute; bottom: 0; background: #93c2aa; }
.roof-one { left: -4%; width: 28%; height: 62px; clip-path: polygon(0 100%, 0 38%, 50% 0, 100% 38%, 100% 100%); background: #a9cdb8; }
.roof-two { left: 23%; width: 22%; height: 78px; clip-path: polygon(0 100%, 0 32%, 50% 0, 100% 32%, 100% 100%); background: #8fbea5; }
.roof-three { left: 44%; width: 30%; height: 56px; clip-path: polygon(0 100%, 0 40%, 50% 0, 100% 40%, 100% 100%); background: #a4c9b4; }
.roof-four { right: -3%; width: 25%; height: 84px; clip-path: polygon(0 100%, 0 30%, 50% 0, 100% 30%, 100% 100%); background: #86b79d; }
.clock-lcd { position: absolute; z-index: 3; top: 14px; left: 18px; display: flex; flex-direction: column; gap: 1px; padding: 6px 10px; border-radius: 6px; background: #ffffffc4; border: 1px solid #ffffffdb; color: #7d9aa4; backdrop-filter: blur(3px); }
.clock-lcd span { font-size: 14px; font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: .5px; }
.clock-lcd small { font-size: 7px; letter-spacing: .5px; }
.clock-lcd.revealed { color: #4f8874; background: #f1faf4da; }
.scene-footer { position: absolute; z-index: 4; left: 0; right: 0; bottom: 0; display: flex; justify-content: space-between; gap: 8px; padding: 10px 16px; background: #ffffffb8; color: #6d8a83; font-size: 9px; backdrop-filter: blur(3px); }
.scene-footer > span:first-child { display: flex; align-items: center; gap: 6px; }
.scene-footer i { width: 5px; height: 5px; border-radius: 50%; background: #e0a361; box-shadow: 0 0 0 3px #e0a3612b; }
.clock-panel { display: flex; flex-direction: column; min-width: 0; padding: 24px; border: 1px solid var(--clock-border); border-radius: 12px; background: #fff; }
.panel-meta { display: flex; align-items: center; gap: 10px; }
.question-count { color: var(--clock-muted); font-size: 10px; }
.time-badge { margin-left: auto; display: flex; align-items: center; gap: 4px; padding: 4px 8px; border-radius: 20px; background: #fdf3e1; color: #b3874d; font-size: 9px; }
.time-badge > span { width: 12px; height: 12px; }
.clock-panel h2 { margin-top: 14px; font-size: 23px; font-weight: 720; }
.panel-prompt { margin: 6px 0 18px; color: var(--clock-muted); font-size: 10px; line-height: 1.8; }
.time-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.time-options button { position: relative; display: flex; align-items: center; gap: 10px; min-height: 70px; padding: 10px 13px; border: 1px solid #dfeaf0; border-radius: 9px; background: #f9fcfd; color: #4d6d7c; text-align: left; }
.time-options button:not(:disabled):hover { border-color: #a8c8d8; background: #f1f9fc; transform: translateY(-1px); }
.time-options button > span:first-child { width: 19px; height: 19px; color: #91adba; }
.time-options button strong { font-size: 24px; font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: .5px; }
.time-options button small { margin-left: auto; color: #a2b4bd; font-size: 8px; }
.time-options button.right { border-color: #9cc5a5; background: #f0f8f0; color: #518061; }
.time-options button.right > span:first-child { color: #76a17f; }
.time-options button.right small { color: #82a889; }
.time-options button.wrong { border-color: #e3ad91; background: #fdf2e9; color: #b47357; animation: clock-shake .3s ease; }
.time-options button.wrong > span:first-child { color: #c58e73; }
.time-options button.wrong small { color: #c4957d; }
.clock-feedback { display: flex; align-items: flex-start; gap: 9px; margin-top: 15px; padding: 11px 12px; border-radius: 8px; background: #fdf3e8; color: #a77e5d; animation: answer-in .3s ease; }
.clock-feedback.good { background: #edf7f0; color: #6d9078; }
.feedback-mark { flex: none; width: 27px; height: 27px; display: grid; place-items: center; border-radius: 50%; background: #ffffffa8; }
.feedback-mark > span { width: 16px; height: 16px; }
.clock-feedback strong { font-size: 11px; font-weight: 650; }
.clock-feedback p { margin-top: 3px; font-size: 10px; line-height: 1.8; opacity: .9; }
.clock-tip { display: flex; align-items: center; gap: 5px; margin-top: 15px; color: #a8b7be; font-size: 9px; }
.clock-tip > span { width: 12px; height: 12px; }
.primary-action, .secondary-action { min-height: 44px; display: flex; align-items: center; justify-content: center; gap: 7px; border-radius: 7px; font-size: 12px; font-weight: 600; padding: 10px 14px; }
.primary-action { background: var(--clock-blue); color: #fff; border: 1px solid transparent; }
.primary-action:hover { background: #42718d; }
.primary-action > span { width: 15px; height: 15px; }
.clock-panel > .primary-action { width: 100%; margin-top: auto; }
.secondary-action { background: #fff; border: 1px solid var(--clock-border); color: #8da0aa; }
.clock-report { padding: 34px clamp(20px, 6vw, 70px); border: 1px solid var(--clock-border); border-radius: 10px; background: #fff; text-align: center; }
.report-stars { display: flex; justify-content: center; gap: 10px; margin-bottom: 14px; }
.report-stars > span { width: 34px; height: 34px; color: #e1ebef; }
.report-stars > .earned { color: #d8ac61; filter: drop-shadow(0 2px 5px #d8ac612e); }
.clock-report h2 { font-size: 24px; margin: 5px 0 8px; }
.clock-report > p { color: var(--clock-muted); font-size: 11px; line-height: 1.8; }
.report-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); max-width: 480px; margin: 22px auto; padding: 17px 0; border-top: 1px dashed var(--clock-border); border-bottom: 1px dashed var(--clock-border); }
.report-stats div { display: flex; flex-direction: column; gap: 7px; }
.report-stats div + div { border-left: 1px solid #eef4f6; }
.report-stats span { font-size: 10px; color: var(--clock-muted); }
.report-stats strong { font-size: 23px; color: var(--clock-blue); }
.report-stats small { font-size: 11px; font-weight: 400; color: #9caeb7; }
.report-best { display: flex; justify-content: center; flex-wrap: wrap; gap: 8px 20px; color: var(--clock-muted); font-size: 10px; margin-bottom: 22px; }
.report-best > span { font-weight: 600; }
.report-best > div { display: flex; align-items: center; gap: 5px; }
.report-best > div.active { color: var(--clock-blue); font-weight: 600; }
.report-best i { display: flex; gap: 2px; font-style: normal; }
.report-best i > span { width: 12px; height: 12px; color: #e1ebef; }
.report-best i > .earned { color: #d8ac61; }
.report-actions { display: flex; justify-content: center; gap: 10px; max-width: 410px; margin: auto; }
.report-actions .primary-action { flex: 1.3; }
.report-actions .secondary-action { flex: 1; }
.clock-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; color: #a4b6be; font-size: 9px; margin-top: 21px; }
.clock-footer > span { display: flex; align-items: center; gap: 5px; }
.clock-footer > span > span { width: 12px; height: 12px; }
.help-list { color: #748892; font-size: 13px; line-height: 1.9; padding-left: 20px; list-style-type: decimal; margin-bottom: 22px; }
.help-list li + li { margin-top: 12px; }
.modal-actions { display: flex; gap: 10px; }
.modal-actions > button { flex: 1; }
@keyframes clock-shake { 25% { transform: translateX(-3px); } 70% { transform: translateX(3px); } }
@keyframes answer-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
@media (max-width: 960px) { .clock-content { padding: 26px 24px 16px; } .clock-board { grid-template-columns: minmax(0, 1fr) minmax(340px, 1fr); gap: 18px; } .clock-status { gap: 22px; } .status-best { display: none; } .clock-scene { min-height: 450px; } }
@media (max-width: 760px) { .clock-heading { align-items: flex-start; } .clock-title h1 { font-size: 28px; } .clock-board { grid-template-columns: minmax(0, 1fr); } .clock-scene { min-height: 360px; padding-top: 16px; } .clock-frame { width: min(68%, 260px); margin-top: 16px; } .sun { top: 20px; right: 24px; width: 38px; height: 38px; } .town-roofs { height: 62px; } .clock-status { flex-wrap: wrap; gap: 14px 22px; } .clock-progress { order: 5; flex-basis: 100%; max-width: none; } .status-best { display: flex; margin-left: 0; } .status-stat { padding-left: 16px; } }
@media (max-width: 540px) { .clock-content { padding: 21px 16px 14px; } .clock-heading { flex-wrap: wrap; gap: 12px; margin-bottom: 16px; } .clock-title { width: 100%; } .clock-title h1 { font-size: 27px; } .clock-toolbar { width: 100%; gap: 5px; } .difficulty-switch { margin-right: auto; padding: 3px; } .difficulty-switch button { padding: 0 12px; min-height: 38px; font-size: 11px; } .round-tool { width: 32px; height: 40px; } .clock-status { padding: 12px 0; margin-bottom: 16px; gap: 12px 14px; } .status-title > span { width: 32px; height: 32px; } .status-title strong { font-size: 12px; } .status-stat { font-size: 10px; gap: 5px; } .status-stat strong { font-size: 15px; } .status-best { flex-direction: row; align-items: center; gap: 7px; } .clock-scene { min-height: 315px; border-radius: 10px; padding: 12px 13px 0; } .clock-frame { width: min(70%, 220px); margin-top: 10px; padding: 9px; } .clock-plate { padding: 5px; } .clock-lcd { top: 10px; left: 11px; padding: 5px 8px; } .clock-lcd span { font-size: 12px; } .cloud-one { left: 16px; top: 40px; transform: scale(.8); } .cloud-two { left: 66px; top: 82px; transform: scale(.75); } .sun { top: 16px; right: 18px; width: 33px; height: 33px; } .scene-footer { font-size: 8px; padding: 8px 11px; } .clock-panel { padding: 19px 15px; border-radius: 10px; } .clock-panel h2 { font-size: 21px; } .time-options { gap: 7px; } .time-options button { min-height: 60px; padding: 8px 9px; gap: 7px; } .time-options button strong { font-size: 20px; } .time-options button small { font-size: 7px; } .clock-report { padding: 26px 18px; } .clock-report h2 { font-size: 20px; } .report-stars > span { width: 28px; height: 28px; } .report-actions { flex-direction: column-reverse; } .report-actions .primary-action, .report-actions .secondary-action { flex: none; } .clock-footer { font-size: 8px; } }
@media (max-width: 360px) { .status-stat:nth-of-type(4) { display: none; } .difficulty-switch button { padding: 0 9px; } .time-options button { min-height: 55px; gap: 5px; padding: 7px; } .time-options button strong { font-size: 18px; } .time-options button small { display: none; } .clock-frame { width: min(74%, 190px); } .clock-scene { min-height: 285px; } }
@media (prefers-reduced-motion: reduce) { .time-options button.wrong, .clock-feedback { animation: none; } .time-options button:hover { transform: none; } }
</style>
