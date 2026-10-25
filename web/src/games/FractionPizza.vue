<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import GameNav from './GameNav.vue'
import {
  advanceFraction, answerFraction, fractionDifficulties, fractionPrompt, fractionReading,
  fractionStars, FRACTION_QUESTIONS, gcd, newFraction, restartFraction, restoreFraction,
  switchFractionDifficulty, type FractionDifficulty,
} from './fraction-pizza'

const props = withDefaults(defineProps<{ storageKey?: string }>(), { storageKey: 'lc_game_fraction_pizza_v1_guest' })
function readSave() {
  try { return restoreFraction(localStorage.getItem(props.storageKey)) } catch { return null }
}
const save = ref(readSave() || newFraction())
const resetDifficulty = ref<FractionDifficulty | null>(null)
const helpOpen = ref(false)
const saveError = ref(false)
const flight = computed(() => save.value.flight)
const question = computed(() => flight.value.questions[flight.value.index])
const answered = computed(() => flight.value.answered)
const isCorrect = computed(() => answered.value === question.value.answer)
const finished = computed(() => flight.value.finished)
const stars = computed(() => fractionStars(flight.value))
const answeredCount = computed(() => finished.value ? FRACTION_QUESTIONS : flight.value.index + (answered.value === null ? 0 : 1))
const difficulty = computed(() => fractionDifficulties.find(item => item.id === save.value.difficulty)!)
const pizza = computed(() => {
  const total = question.value.total
  const step = (Math.PI * 2) / total
  const slices = Array.from({ length: total }, (_, index) => {
    const start = -Math.PI / 2 + index * step
    const end = start + step
    const x1 = 120 + 96 * Math.cos(start)
    const y1 = 120 + 96 * Math.sin(start)
    const x2 = 120 + 96 * Math.cos(end)
    const y2 = 120 + 96 * Math.sin(end)
    return {
      index,
      step,
      mid: start + step / 2,
      shaded: index < question.value.shaded,
      path: `M120 120 L${x1.toFixed(2)} ${y1.toFixed(2)} A96 96 0 0 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z`,
    }
  })
  const toppings = slices.filter(slice => slice.shaded).flatMap((slice, sliceIndex) => {
    const radius = total <= 4 ? 9.5 : total <= 6 ? 7.5 : 6
    return [0, 1].map(offset => {
      const distance = offset === 0 ? .5 : .73
      const angle = slice.mid + slice.step * (offset === 0 ? -.16 : .14)
      return {
        key: `${sliceIndex}-${offset}`,
        cx: 120 + 96 * distance * Math.cos(angle),
        cy: 120 + 96 * distance * Math.sin(angle),
        r: radius,
      }
    })
  })
  return { slices, toppings }
})
const explanation = computed(() => {
  const value = question.value
  if (value.mode === 'identify') {
    return `这张披萨平均分成 ${value.total} 份，涂色 ${value.shaded} 份，所以是 ${value.answer}，读作「${fractionReading(value.answer)}」。`
  }
  const divisor = gcd(value.shaded, value.total)
  return `涂色部分是 ${value.shaded}/${value.total}，分子和分母同时除以 ${divisor}，得到最简分数 ${value.answer}。`
})
function choose(value: string) { answerFraction(save.value, value) }
function next() { advanceFraction(save.value) }
function again() { restartFraction(save.value) }
function requestDifficulty(id: FractionDifficulty) {
  if (id !== save.value.difficulty) resetDifficulty.value = id
}
function applyDifficulty() {
  if (!resetDifficulty.value) return
  if (resetDifficulty.value === save.value.difficulty) restartFraction(save.value)
  else switchFractionDifficulty(save.value, resetDifficulty.value)
  resetDifficulty.value = null
}
watch(save, value => {
  try { localStorage.setItem(props.storageKey, JSON.stringify(value)); saveError.value = false }
  catch { saveError.value = true }
}, { deep: true, immediate: true, flush: 'post' })
watch(() => props.storageKey, () => { save.value = readSave() || newFraction() })
</script>

<template>
  <div class="fraction-game">
    <GameNav active="fraction-pizza" />
    <main class="fraction-content">
      <header class="fraction-heading">
        <div class="fraction-title"><span class="eyebrow">小小披萨店 · 分数启蒙</span><h1>披萨分数<span>.</span></h1></div>
        <div class="fraction-toolbar">
          <div class="difficulty-switch" role="group" aria-label="游戏难度">
            <button v-for="item in fractionDifficulties" :key="item.id" :title="item.age" :aria-pressed="save.difficulty === item.id" :class="{ selected: save.difficulty === item.id }" @click="requestDifficulty(item.id)">{{ item.name }}</button>
          </div>
          <UTooltip text="怎么玩"><button class="round-tool" aria-label="怎么玩" @click="helpOpen = true"><UIcon name="i-lucide-circle-help" /></button></UTooltip>
        </div>
      </header>

      <section class="fraction-status" aria-label="答题进度">
        <div class="status-title"><span><UIcon name="i-lucide-pizza" /></span><div><strong>第 {{ save.flights + (finished ? 0 : 1) }} 盘披萨</strong><small>{{ difficulty.name }} · {{ difficulty.detail }}</small></div></div>
        <div class="fraction-progress">
          <span class="progress-caption">本盘进度<strong>{{ answeredCount }} / {{ FRACTION_QUESTIONS }}</strong></span>
          <div class="progress-rail" aria-hidden="true"><i v-for="n in FRACTION_QUESTIONS" :key="n" :class="{ done: n <= answeredCount, current: !finished && answered === null && n === flight.index + 1 }" /></div>
        </div>
        <div class="status-stat"><span><UIcon name="i-lucide-circle-check" />答对</span><strong>{{ flight.correct }}</strong></div>
        <div class="status-stat"><span><UIcon name="i-lucide-scaling" />尝试</span><strong>{{ flight.mistakes }}</strong></div>
        <div class="status-best"><span><UIcon name="i-lucide-star" />最佳</span><div class="mini-stars" :aria-label="`${difficulty.name}最佳${save.best[save.difficulty]}颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.best[save.difficulty] }" /></div></div>
      </section>

      <section v-if="!finished" class="fraction-layout">
        <div class="pizza-scene">
          <span class="kitchen-ticket"><UIcon name="i-lucide-chef-hat" />今日点单 · 分数披萨</span>
          <span class="steam steam-one" aria-hidden="true" /><span class="steam steam-two" aria-hidden="true" />
          <div class="pizza-art" :class="{ celebrate: answered !== null && isCorrect }" role="img" :aria-label="`披萨平均分成 ${question.total} 块，其中 ${question.shaded} 块涂色`">
            <svg viewBox="0 0 240 250" aria-hidden="true">
              <defs>
                <linearGradient id="fraction-cheese" x1="0" y1="0" x2="1" y2="1">
                  <stop offset="0" stop-color="#f6c768" /><stop offset="1" stop-color="#e9a94d" />
                </linearGradient>
                <radialGradient id="fraction-board" cx=".4" cy=".3" r=".8">
                  <stop offset="0" stop-color="#dcaa78" /><stop offset="1" stop-color="#bd8857" />
                </radialGradient>
              </defs>
              <ellipse cx="120" cy="234" rx="89" ry="9" fill="#4d35221a" />
              <circle cx="120" cy="120" r="112" fill="url(#fraction-board)" />
              <circle cx="120" cy="120" r="105" fill="none" stroke="#a97645" stroke-width="1.5" opacity=".55" />
              <circle cx="120" cy="120" r="100" fill="#dca467" />
              <circle cx="120" cy="120" r="100" fill="none" stroke="#c48b4f" stroke-width="1.6" stroke-dasharray="2 7" opacity=".8" />
              <path v-for="slice in pizza.slices" :key="slice.index" :d="slice.path" :fill="slice.shaded ? 'url(#fraction-cheese)' : '#f8e9cf'" stroke="#fff8ea" stroke-width="2.6" stroke-linejoin="round" />
              <g v-for="slice in pizza.slices.filter(item => !item.shaded)" :key="'dim-' + slice.index">
                <circle :cx="120 + 96 * .56 * Math.cos(slice.mid)" :cy="120 + 96 * .56 * Math.sin(slice.mid)" r="3" fill="#e8d3af" opacity=".8" />
              </g>
              <g v-for="topping in pizza.toppings" :key="topping.key">
                <circle :cx="topping.cx" :cy="topping.cy" :r="topping.r" fill="#cd6045" stroke="#af4e36" stroke-width="1.2" />
                <circle :cx="topping.cx - topping.r * .26" :cy="topping.cy - topping.r * .3" :r="topping.r * .22" fill="#f2a08b" opacity=".85" />
              </g>
              <circle cx="120" cy="120" r="3.4" fill="#e9b159" />
            </svg>
          </div>
          <div class="scene-legend"><span><i class="legend-shaded" />涂色部分</span><span><i class="legend-plain" />没涂色</span><span class="slice-count">一共 {{ question.total }} 块</span></div>
          <div class="scene-note"><UIcon name="i-lucide-info" />每一块都一样大，才可以用分数表示。</div>
        </div>

        <div class="pizza-panel">
          <div :key="flight.index" class="question-body">
            <div class="question-meta"><span>第 {{ flight.index + 1 }} / {{ FRACTION_QUESTIONS }} 题</span><span v-if="question.mode === 'simplify'" class="simplify-pill"><UIcon name="i-lucide-scaling" />最简分数</span></div>
            <h2 class="pizza-prompt">{{ fractionPrompt(question.mode) }}</h2>
            <p class="prompt-hint"><UIcon name="i-lucide-eye" />{{ question.mode === 'simplify' ? '先看涂色部分占几分之几，再把分子和分母化成最简。' : '先数一数涂色的块数，再数一数一共分成几块。' }}</p>
            <div class="fraction-options" role="group" aria-label="分数选项">
              <button v-for="option in question.options" :key="option" :data-fraction="option" :class="{ right: answered !== null && option === question.answer, wrong: answered === option && option !== question.answer }" :disabled="answered !== null" :aria-label="`选择 ${option}，读作${fractionReading(option)}`" @click="choose(option)"><strong>{{ option }}</strong><small>{{ fractionReading(option) }}</small></button>
            </div>
            <div v-if="answered !== null" class="answer-feedback" :class="{ good: isCorrect }" role="status" aria-label="答题反馈">
              <span class="feedback-icon"><UIcon :name="isCorrect ? 'i-lucide-circle-check' : 'i-lucide-chef-hat'" /></span>
              <div><strong>{{ isCorrect ? '答对了，这盘披萨归你啦！' : '再看看涂色的块数。' }}</strong><p>{{ explanation }}</p></div>
            </div>
            <p v-else class="answer-tip"><UIcon name="i-lucide-mouse-pointer-2" />想好了，就点选一个分数。</p>
            <button v-if="answered !== null" class="primary-action" @click="next">{{ flight.index === FRACTION_QUESTIONS - 1 ? '查看披萨成绩单' : '下一盘披萨' }}<UIcon name="i-lucide-arrow-right" /></button>
          </div>
        </div>
      </section>

      <section v-else class="fraction-report">
        <div class="report-stars" :aria-label="`本次获得${stars}颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= stars }" /></div>
        <span class="eyebrow">本盘成绩单 · {{ difficulty.name }}</span>
        <h2>{{ stars === 3 ? '满分披萨师傅，出炉！' : '披萨出炉，再试一次会更香！' }}</h2>
        <p>{{ flight.mistakes === 0 ? '八盘披萨的分数都认对了，一块也没有切错。' : `有 ${flight.mistakes} 道题需要再想想，看看分数是怎么数出来的吧。` }}</p>
        <div class="report-stats">
          <div><span>答对题数</span><strong>{{ flight.correct }}<small> / {{ FRACTION_QUESTIONS }}</small></strong></div>
          <div><span>本盘星星</span><strong>{{ stars }}<small> 颗</small></strong></div>
          <div><span>累计完成</span><strong>{{ save.flights }}<small> 盘</small></strong></div>
        </div>
        <div class="report-best"><span>最佳记录</span><div v-for="item in fractionDifficulties" :key="item.id" :class="{ active: item.id === save.difficulty }"><span>{{ item.name }}</span><i><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.best[item.id] }" /></i></div></div>
        <div class="report-actions"><button class="secondary-action" @click="helpOpen = true"><UIcon name="i-lucide-circle-help" />看看玩法</button><button class="primary-action" @click="again"><UIcon name="i-lucide-pizza" />再烤一盘</button></div>
      </section>

      <footer class="fraction-footer"><span><UIcon name="i-lucide-heart" />每一次尝试，都是成长</span><span role="status" aria-label="进度保存状态"><UIcon :name="saveError ? 'i-lucide-cloud-off' : 'i-lucide-cloud-check'" />{{ saveError ? '本机暂时无法保存进度' : '进度已保存在本机' }}</span></footer>
    </main>

    <UModal :open="helpOpen" title="切披萨，认识分数" description="平均分的每一块，都藏着分数的秘密。" :close="{ 'aria-label': '关闭玩法说明' }" :ui="{ content: 'game-modal' }" @update:open="helpOpen = $event"><template #body><ol class="help-list"><li>先看披萨平均分成了几块，这就是分母；再看涂色的有几块，这就是分子。</li><li>例如分成 4 块、涂色 3 块，就是 3/4，读作「四分之三」。</li><li>挑战难度里，涂色部分可能不是最简分数。把分子和分母同时除以相同的数，就得到最简分数。</li><li>八道题完成后可以查看成绩单。全部答对就能烤出三颗星的满分披萨。</li></ol><button class="primary-action" @click="helpOpen = false">明白了，开始切披萨<UIcon name="i-lucide-pizza" /></button></template></UModal>
    <UModal :open="resetDifficulty !== null" :title="resetDifficulty === save.difficulty ? '重新烤一盘？' : '切换游戏难度？'" description="新的披萨会从第一题开始，当前这盘题的进度会清空，最佳记录会保留。" :close="{ 'aria-label': '关闭难度确认' }" :ui="{ content: 'game-modal' }" @update:open="!$event && (resetDifficulty = null)"><template #body><div class="modal-actions"><button class="secondary-action" @click="resetDifficulty = null">继续这一盘</button><button class="primary-action" @click="applyDifficulty">{{ resetDifficulty === save.difficulty ? '重新开始' : '切换并开始' }}<UIcon name="i-lucide-arrow-right" /></button></div></template></UModal>
  </div>
</template>

<style scoped>
.fraction-game { --fraction-ink: #4a3c34; --fraction-muted: #9b8d82; --fraction-red: #c4674f; --fraction-border: #efe3d8; min-height: 100dvh; background: #fdf9f4; color: var(--fraction-ink); font-family: var(--font-ui); letter-spacing: 0; }
.fraction-game button { cursor: pointer; transition: background .16s, transform .16s, box-shadow .16s; }
.fraction-game button:disabled { cursor: default; }
.fraction-game button:focus-visible { outline: 3px solid #d49a86; outline-offset: 3px; }
.fraction-content { max-width: 1180px; margin: auto; padding: 30px 36px 18px; }
.eyebrow { display: block; color: var(--fraction-muted); font-size: 11px; line-height: 1.6; }
.fraction-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 22px; }
.fraction-title h1 { font-size: 32px; font-weight: 750; line-height: 1.35; margin: 3px 0 0; }
.fraction-title h1 > span { color: #7da86d; margin-left: 3px; }
.fraction-toolbar { display: flex; align-items: center; gap: 9px; }
.difficulty-switch { display: flex; align-items: center; gap: 3px; background: #f4ebe3; padding: 4px; border-radius: 8px; margin-right: 6px; }
.difficulty-switch button { height: 35px; padding: 0 15px; background: transparent; border-radius: 5px; color: #a29388; font-size: 12px; white-space: nowrap; }
.difficulty-switch button.selected { color: var(--fraction-red); background: #fff; box-shadow: 0 1px 4px #4a3c3412; font-weight: 650; }
.round-tool { width: 36px; height: 36px; display: grid; place-items: center; color: #9e8f83; background: transparent; border-radius: 6px; }
.round-tool:hover { background: #f4ebe3; }
.round-tool > span { width: 18px; height: 18px; }
.fraction-status { display: flex; align-items: center; gap: 34px; padding: 15px 0; border-top: 1px solid var(--fraction-border); border-bottom: 1px solid var(--fraction-border); margin-bottom: 22px; }
.status-title { display: flex; align-items: center; gap: 11px; }
.status-title > span { width: 38px; height: 38px; display: grid; place-items: center; background: #fbeade; color: #c77b58; border-radius: 50%; }
.status-title > span > span { width: 20px; height: 20px; }
.status-title > div { display: flex; flex-direction: column; gap: 3px; }
.status-title strong { font-size: 13px; font-weight: 650; }
.status-title small { font-size: 10px; color: var(--fraction-muted); }
.fraction-progress { flex: 1; max-width: 300px; display: flex; flex-direction: column; gap: 7px; }
.progress-caption { display: flex; justify-content: space-between; gap: 10px; color: var(--fraction-muted); font-size: 10px; }
.progress-caption strong { color: var(--fraction-red); font-weight: 600; font-variant-numeric: tabular-nums; }
.progress-rail { display: flex; gap: 5px; }
.progress-rail i { flex: 1; height: 5px; border-radius: 4px; background: #f1e7dd; transition: background .3s; }
.progress-rail i.done { background: #dfa184; }
.progress-rail i.current { background: #7da86d; box-shadow: 0 0 0 3px #7da86d1f; }
.status-stat { display: flex; align-items: center; gap: 7px; color: var(--fraction-muted); font-size: 11px; border-left: 1px solid var(--fraction-border); padding-left: 22px; }
.status-stat > span { display: flex; align-items: center; gap: 4px; }
.status-stat > span > span { width: 14px; height: 14px; color: #b9a06d; }
.status-stat strong { font-size: 17px; color: var(--fraction-ink); font-variant-numeric: tabular-nums; }
.status-best { display: flex; flex-direction: column; gap: 5px; margin-left: auto; color: var(--fraction-muted); font-size: 10px; }
.status-best > span { display: flex; align-items: center; gap: 4px; }
.status-best > span > span { width: 13px; height: 13px; color: #c9a55f; }
.mini-stars { display: flex; gap: 3px; }
.mini-stars > span { width: 13px; height: 13px; color: #ece0d5; }
.mini-stars > .earned { color: #d9b263; }
.fraction-layout { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(360px, .95fr); gap: 26px; align-items: stretch; }
.pizza-scene { position: relative; min-height: 490px; border-radius: 10px; overflow: hidden; background-color: #fbf0df; background-image: linear-gradient(#f3e2cb66 1px, transparent 1px), linear-gradient(90deg, #f3e2cb66 1px, transparent 1px); background-size: 26px 26px; border: 1px solid #f0e2d0; display: flex; align-items: center; justify-content: center; padding: 58px 24px 74px; }
.pizza-scene::before { content: ''; position: absolute; width: 340px; height: 340px; border-radius: 50%; background: #ffffff7d; box-shadow: 0 0 0 22px #ffffff38; }
.kitchen-ticket { position: absolute; top: 18px; left: 20px; display: flex; align-items: center; gap: 6px; padding: 7px 10px; background: #fffaf2; border: 1px solid #ecdbc4; border-radius: 5px; color: #a0836b; font-size: 10px; z-index: 2; box-shadow: 0 2px 6px #8c6a4a0a; }
.kitchen-ticket > span { width: 14px; height: 14px; color: #c58b64; }
.steam { position: absolute; width: 12px; height: 54px; border-radius: 50%; border-left: 3px solid #ffffffb8; filter: blur(1px); top: 21%; z-index: 1; }
.steam-one { left: 34%; animation: steam-rise 3.6s ease-in-out infinite; }
.steam-two { right: 33%; top: 25%; height: 40px; animation: steam-rise 3.6s ease-in-out 1.4s infinite; }
.pizza-art { position: relative; z-index: 2; width: min(86%, 420px); animation: pizza-in .5s ease-out; }
.pizza-art svg { width: 100%; height: auto; filter: drop-shadow(0 14px 15px #a06d3b26); }
.pizza-art.celebrate { animation: pizza-pop .6s ease; }
.scene-legend { position: absolute; left: 20px; right: 20px; bottom: 41px; display: flex; align-items: center; gap: 16px; color: #9c8874; font-size: 9px; z-index: 2; }
.scene-legend > span { display: flex; align-items: center; gap: 5px; }
.scene-legend i { width: 9px; height: 9px; border-radius: 2px; }
.legend-shaded { background: #eeb85e; border: 1px solid #dba24a; }
.legend-plain { background: #f8e9cf; border: 1px solid #e2cda7; }
.scene-legend .slice-count { margin-left: auto; color: #b09070; font-weight: 600; }
.scene-note { position: absolute; left: 0; bottom: 0; width: 100%; display: flex; align-items: center; gap: 5px; padding: 10px 20px; background: #fffaf2b8; color: #a79583; font-size: 9px; z-index: 2; }
.scene-note > span { width: 12px; height: 12px; }
.pizza-panel { background: #fff; border: 1px solid var(--fraction-border); border-radius: 10px; padding: 24px; display: flex; min-width: 0; }
.question-body { width: 100%; display: flex; flex-direction: column; animation: question-in .32s ease-out; }
.question-meta { display: flex; align-items: center; gap: 10px; color: var(--fraction-muted); font-size: 11px; }
.simplify-pill { margin-left: auto; display: flex; align-items: center; gap: 4px; background: #eef5e9; color: #7b9a69; font-size: 10px; padding: 4px 8px; border-radius: 20px; }
.simplify-pill > span { width: 12px; height: 12px; }
.pizza-prompt { font-size: 19px; font-weight: 700; line-height: 1.55; margin: 14px 0 6px; }
.prompt-hint { display: flex; align-items: flex-start; gap: 5px; color: #b1a294; font-size: 10px; line-height: 1.7; }
.prompt-hint > span { width: 13px; height: 13px; flex: none; margin-top: 1px; color: #c0a883; }
.fraction-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; margin: 19px 0 4px; }
.fraction-options button { min-height: 68px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px; border: 1px solid #eadfd2; border-radius: 8px; background: #fdfaf5; color: #6c564a; }
.fraction-options button:not(:disabled):hover { border-color: #d3ad95; background: #fdf4ea; transform: translateY(-1px); }
.fraction-options strong { font-size: 25px; font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: .5px; }
.fraction-options small { font-size: 9px; color: #b3a190; }
.fraction-options button.right { background: #eef7ef; border-color: #9fc8a8; color: #4f8a65; }
.fraction-options button.right small { color: #86a98e; }
.fraction-options button.wrong { background: #fdf0e8; border-color: #e5ae95; color: #b66c4d; animation: option-shake .3s ease; }
.answer-tip { display: flex; align-items: center; gap: 5px; color: #b4a79b; font-size: 10px; margin-top: 10px; }
.answer-tip > span { width: 13px; height: 13px; }
.answer-feedback { display: flex; align-items: flex-start; gap: 9px; margin-top: 13px; padding: 11px 12px; background: #fcf3e7; color: #a57a55; border-radius: 7px; }
.answer-feedback.good { background: #eef7ef; color: #719079; }
.feedback-icon { width: 27px; height: 27px; flex: none; display: grid; place-items: center; background: #ffffff9e; border-radius: 50%; }
.feedback-icon > span { width: 16px; height: 16px; }
.answer-feedback strong { font-size: 11px; font-weight: 650; }
.answer-feedback p { font-size: 10px; line-height: 1.8; margin: 3px 0 0; opacity: .88; }
.primary-action, .secondary-action { min-height: 44px; display: flex; align-items: center; justify-content: center; gap: 7px; border-radius: 7px; font-size: 12px; font-weight: 600; padding: 10px 14px; }
.primary-action { background: var(--fraction-red); color: #fff; border: 1px solid transparent; }
.primary-action:hover { background: #b25a43; }
.primary-action > span { width: 15px; height: 15px; }
.question-body .primary-action { width: 100%; margin-top: auto; }
.secondary-action { background: #fff; border: 1px solid var(--fraction-border); color: #96857a; }
.secondary-action:hover { background: #fdfaf6; }
.secondary-action > span { width: 14px; height: 14px; }
.fraction-report { background: #fff; border: 1px solid var(--fraction-border); border-radius: 10px; padding: 34px clamp(20px, 6vw, 70px); text-align: center; }
.report-stars { display: flex; justify-content: center; gap: 10px; margin-bottom: 14px; }
.report-stars > span { width: 34px; height: 34px; color: #f0e4d8; }
.report-stars > .earned { color: #dfb164; filter: drop-shadow(0 2px 5px #dfb1642e); }
.fraction-report h2 { font-size: 24px; margin: 5px 0 8px; }
.fraction-report > p { color: var(--fraction-muted); font-size: 11px; line-height: 1.8; }
.report-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); max-width: 480px; margin: 22px auto; border-top: 1px dashed var(--fraction-border); border-bottom: 1px dashed var(--fraction-border); padding: 17px 0; }
.report-stats div { display: flex; flex-direction: column; gap: 7px; }
.report-stats div + div { border-left: 1px solid #f3eae1; }
.report-stats span { font-size: 10px; color: var(--fraction-muted); }
.report-stats strong { font-size: 23px; color: var(--fraction-red); }
.report-stats small { font-size: 11px; font-weight: 400; color: #b5a79b; }
.report-best { display: flex; justify-content: center; flex-wrap: wrap; gap: 8px 20px; color: var(--fraction-muted); font-size: 10px; margin-bottom: 22px; }
.report-best > span { font-weight: 600; }
.report-best > div { display: flex; align-items: center; gap: 5px; }
.report-best > div.active { color: var(--fraction-red); font-weight: 600; }
.report-best i { display: flex; gap: 2px; font-style: normal; }
.report-best i > span { width: 12px; height: 12px; color: #eee3d9; }
.report-best i > .earned { color: #ddb264; }
.report-actions { display: flex; justify-content: center; gap: 10px; max-width: 400px; margin: auto; }
.report-actions .primary-action { flex: 1.4; }
.report-actions .secondary-action { flex: 1; }
.fraction-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; color: #b3a79c; font-size: 9px; margin-top: 21px; }
.fraction-footer > span { display: flex; align-items: center; gap: 5px; }
.fraction-footer > span > span { width: 12px; height: 12px; }
.help-list { color: #7e6f64; font-size: 13px; line-height: 1.9; padding-left: 20px; list-style-type: decimal; margin-bottom: 22px; }
.help-list li + li { margin-top: 12px; }
.modal-actions { display: flex; gap: 10px; }
.modal-actions > button { flex: 1; }
@keyframes question-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
@keyframes pizza-in { from { opacity: 0; transform: scale(.94) rotate(-2deg); } to { opacity: 1; transform: none; } }
@keyframes pizza-pop { 40% { transform: scale(1.03) rotate(1deg); } }
@keyframes option-shake { 25% { transform: translateX(-3px); } 70% { transform: translateX(3px); } }
@keyframes steam-rise { 0% { opacity: 0; transform: translateY(8px) scaleX(.9); } 35% { opacity: .7; } 100% { opacity: 0; transform: translateY(-26px) scaleX(1.2); } }
@media (max-width: 1000px) { .fraction-content { padding: 26px 24px 16px; } .fraction-layout { grid-template-columns: minmax(0, 1fr) minmax(330px, 1fr); gap: 18px; } .pizza-scene { min-height: 450px; padding-left: 16px; padding-right: 16px; } .status-best { display: none; } .fraction-status { gap: 22px; } }
@media (max-width: 760px) { .fraction-heading { align-items: flex-start; } .fraction-title h1 { font-size: 28px; } .fraction-layout { grid-template-columns: minmax(0, 1fr); } .pizza-scene { min-height: 0; padding: 48px 20px 70px; } .pizza-art { width: min(82%, 330px); } .pizza-panel { padding: 20px; } .fraction-status { flex-wrap: wrap; gap: 14px 22px; } .fraction-progress { order: 5; flex-basis: 100%; max-width: none; } .status-best { display: flex; margin-left: 0; } .status-stat + .status-stat { padding-left: 16px; } }
@media (max-width: 540px) { .fraction-content { padding: 21px 16px 14px; } .fraction-heading { flex-wrap: wrap; gap: 12px; margin-bottom: 16px; } .fraction-title { width: 100%; } .fraction-title h1 { font-size: 27px; } .fraction-toolbar { width: 100%; gap: 5px; } .difficulty-switch { margin-right: auto; padding: 3px; } .difficulty-switch button { padding: 0 11px; min-height: 38px; font-size: 11px; } .round-tool { width: 32px; height: 40px; } .fraction-status { padding: 12px 0; margin-bottom: 16px; gap: 12px 14px; } .status-title > span { width: 32px; height: 32px; } .status-title strong { font-size: 12px; } .status-stat { font-size: 10px; gap: 5px; } .status-stat strong { font-size: 15px; } .status-best { flex-direction: row; align-items: center; gap: 7px; } .pizza-scene { padding: 44px 12px 68px; } .pizza-art { width: 88%; } .kitchen-ticket { top: 12px; left: 12px; font-size: 9px; } .scene-legend { left: 14px; right: 14px; bottom: 37px; gap: 10px; } .scene-note { padding: 9px 14px; font-size: 8px; } .pizza-panel { padding: 18px 16px; } .pizza-prompt { font-size: 17px; margin-top: 12px; } .fraction-options { gap: 8px; margin-top: 16px; } .fraction-options button { min-height: 62px; } .fraction-options strong { font-size: 23px; } .fraction-footer { font-size: 8px; } .fraction-report { padding: 26px 18px; } .fraction-report h2 { font-size: 20px; } .report-stars > span { width: 28px; height: 28px; } .report-actions { flex-direction: column-reverse; } .report-actions .primary-action, .report-actions .secondary-action { flex: none; } }
@media (max-width: 360px) { .status-stat:nth-of-type(4) { display: none; } .difficulty-switch button { padding: 0 8px; } .pizza-art { width: 94%; } .kitchen-ticket span:not(:first-child) { display: none; } .fraction-options button { min-height: 58px; } .fraction-options strong { font-size: 21px; } }
@media (prefers-reduced-motion: reduce) { .pizza-art, .pizza-art.celebrate, .steam, .question-body, .fraction-options button.wrong { animation: none; } .progress-rail i { transition: none; } }
</style>
