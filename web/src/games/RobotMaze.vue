<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import GameNav from './GameNav.vue'
import {
  chapters, commandInfo, compileProgram, levels, MAX_BODY, MAX_CARDS, moveRobot,
  newMaze, pointKey, restoreMaze, resultOf, starsFor, startRobot,
  type Command, type CompiledStep,
} from './robot-maze'

const props = withDefaults(defineProps<{ storageKey?: string }>(), { storageKey: 'lc_game_robot_maze_v1_guest' })
function readSave() {
  try { return restoreMaze(localStorage.getItem(props.storageKey)) } catch { return null }
}
const save = ref(readSave() || newMaze())
const level = computed(() => levels[save.value.level])
const robot = ref(startRobot(level.value))
const journeyEl = ref<HTMLElement | null>(null)
const status = ref<'idle' | 'running' | 'paused' | 'success' | 'failed'>('idle')
const message = ref('先安排指令，再让小布出发。')
const steps = ref<CompiledStep[]>([])
const cursor = ref(0)
const activeStep = ref<CompiledStep | null>(null)
const selectedLoop = ref<number | null>(null)
const hintOpen = ref(false)
const resetOpen = ref(false)
const helpOpen = ref(false)
const saveError = ref(false)
const quick = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
const busy = computed(() => status.value === 'running' || status.value === 'paused')
const stars = computed(() => save.value.stars.reduce((sum, n) => sum + n, 0))
const cleared = computed(() => save.value.stars.filter(n => n > 0).length)
const expanded = computed(() => compileProgram(save.value.program))
const loop = computed(() => {
  const value = selectedLoop.value === null ? null : save.value.program[selectedLoop.value]
  return value?.type === 'repeat' ? value : null
})
const tiles = computed(() => level.value.rows.flatMap((row, y) => [...row].map((terrain, x) => ({
  x, y, key: `${x},${y}`, terrain,
  goal: pointKey(level.value.goal) === `${x},${y}`,
  start: pointKey(level.value.start) === `${x},${y}`,
  gear: level.value.gears.some(p => pointKey(p) === `${x},${y}`),
}))))
const directionNames = ['上', '右', '下', '左']
const unlocked = (index: number) => index === 0 || save.value.stars[index - 1] > 0
function centerCurrentLevel() {
  const journey = journeyEl.value
  if (!journey || !window.matchMedia('(max-width: 980px)').matches) return
  const current = journey.querySelector<HTMLElement>('.level-button.current')
  if (!current) return
  const view = journey.getBoundingClientRect()
  const card = current.getBoundingClientRect()
  journey.scrollBy({
    left: card.left - view.left - (view.width - card.width) / 2,
    behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
  })
}
function cancelTimer() { if (timer !== undefined) clearTimeout(timer); timer = undefined }
function rewind() {
  cancelTimer(); robot.value = startRobot(level.value); status.value = 'idle'
  cursor.value = 0; steps.value = []; activeStep.value = null
  message.value = '先安排指令，再让小布出发。'
}
function retryAttempt() {
  rewind(); save.value.hints[save.value.level] = 0; hintOpen.value = false
}
function chooseLevel(index: number) {
  if (!unlocked(index) || index === save.value.level) return
  cancelTimer(); save.value.level = index; save.value.program = []
  selectedLoop.value = null; hintOpen.value = false; rewind()
}
function addCommand(command: Command) {
  if (busy.value) return
  if (loop.value) {
    if (loop.value.body.length >= MAX_BODY) { message.value = '一块重复积木里最多放 6 个动作。'; return }
    rewind(); loop.value.body.push(command)
  } else {
    if (save.value.program.length >= MAX_CARDS) { message.value = '程序最多放 12 块积木，可以试试整理顺序。'; return }
    rewind(); save.value.program.push({ type: command })
  }
}
function addLoop() {
  if (busy.value || !level.value.repeat || save.value.program.length >= MAX_CARDS) return
  rewind(); save.value.program.push({ type: 'repeat', count: 2, body: [] })
  selectedLoop.value = save.value.program.length - 1
}
function removeCard(index: number) {
  if (busy.value) return
  rewind(); save.value.program.splice(index, 1); selectedLoop.value = null
}
function moveCard(index: number, delta: number) {
  if (busy.value || index + delta < 0 || index + delta >= save.value.program.length) return
  rewind()
  const [card] = save.value.program.splice(index, 1)
  save.value.program.splice(index + delta, 0, card); selectedLoop.value = null
}
function removeInner(card: number, inner: number) {
  if (busy.value) return
  rewind(); const instruction = save.value.program[card]
  if (instruction.type === 'repeat') instruction.body.splice(inner, 1)
}
function setRepeat(index: number, count: number) {
  if (busy.value) return
  rewind(); const instruction = save.value.program[index]
  if (instruction.type === 'repeat') instruction.count = count
}
function clearProgram() {
  if (busy.value) return
  rewind(); save.value.program = []; selectedLoop.value = null
}
function prepare(): boolean {
  if (!save.value.program.length) { message.value = '先点击「前进」等积木，安排小布的路线。'; return false }
  if (save.value.program.some(i => i.type === 'repeat' && !i.body.length)) {
    message.value = '重复积木还是空的。选中它，再点击动作放进去。'; return false
  }
  robot.value = startRobot(level.value); steps.value = expanded.value; cursor.value = 0
  activeStep.value = null; selectedLoop.value = null
  return true
}
function finish() {
  const result = resultOf(level.value, robot.value)
  if (result === 'success') {
    status.value = 'success'
    const earned = starsFor(level.value, save.value.program, save.value.hints[save.value.level])
    save.value.stars[save.value.level] = Math.max(save.value.stars[save.value.level], earned)
    message.value = '零件收齐，成功抵达充电站！'
  } else {
    status.value = 'failed'
    message.value = result === 'missing' ? '已经到了充电站，不过还有零件没拿到。调整路线再试试。' : '指令执行完了，小布还没到充电站。看看还需要走几步。'
  }
}
function tick() {
  const step = steps.value[cursor.value]
  if (!step) { finish(); return }
  activeStep.value = step
  const result = moveRobot(level.value, robot.value, step.command)
  cursor.value++
  if (result.blocked) {
    status.value = 'failed'; message.value = '前面没有小路，小布停下来了。检查这一块指令，转个方向试试。'; return
  }
  robot.value = result.robot
  message.value = `第 ${cursor.value} 步：${commandInfo[step.command].name}${step.inner === null ? '' : ` · 重复第 ${step.iteration} 次`}。小布现在朝${directionNames[robot.value.direction]}。`
  if (cursor.value === steps.value.length) finish()
}
function schedule() {
  cancelTimer()
  timer = setTimeout(() => {
    if (status.value !== 'running') return
    tick(); if (status.value === 'running') schedule()
  }, quick.value ? 220 : 600)
}
function run() {
  if (status.value === 'running') return
  if (status.value !== 'paused' && !prepare()) return
  status.value = 'running'; message.value = '小布出发啦！观察正在执行的积木。'; schedule()
}
function pause() { cancelTimer(); status.value = 'paused'; message.value = '已暂停，可以单步观察或继续运行。' }
function singleStep() {
  if (status.value === 'running') return
  if (status.value !== 'paused' && !prepare()) return
  status.value = 'paused'; tick()
}
function showHint() {
  if (!hintOpen.value) save.value.hints[save.value.level]++
  hintOpen.value = !hintOpen.value
}
function restart() {
  cancelTimer(); save.value = newMaze(); selectedLoop.value = null
  hintOpen.value = false; resetOpen.value = false; rewind()
}
watch(save, value => {
  try { localStorage.setItem(props.storageKey, JSON.stringify(value)); saveError.value = false }
  catch { saveError.value = true }
}, { deep: true, immediate: true, flush: 'post' })
watch(() => props.storageKey, () => {
  cancelTimer(); save.value = readSave() || newMaze(); selectedLoop.value = null; hintOpen.value = false; rewind()
})
watch(() => save.value.level, () => { void nextTick(centerCurrentLevel) })
onMounted(() => { void nextTick(centerCurrentLevel) })
onBeforeUnmount(cancelTimer)
</script>

<template>
  <div class="maze-game">
    <GameNav active="robot-maze" />
    <main class="maze-content">
      <div class="maze-heading">
        <div><span class="eyebrow">小布的探索日记 · 逻辑与编程</span><h1>机器人闯迷宫<span>.</span></h1><p>用小小的指令，走出大大的冒险。</p></div>
        <button class="text-button" @click="helpOpen = true"><UIcon name="i-lucide-circle-help" />怎么玩</button>
      </div>
      <div class="maze-layout">
        <aside ref="journeyEl" class="journey" aria-label="关卡地图">
          <div class="journey-title"><span>探索路线</span><strong>{{ cleared }} / {{ levels.length }}</strong></div>
          <div class="journey-progress"><span :style="{ width: `${cleared / levels.length * 100}%` }" /></div>
          <section v-for="(chapter, chapterIndex) in chapters" :key="chapter.name" class="chapter">
            <div class="chapter-title"><span><UIcon :name="chapter.icon" /></span><div><h2>{{ chapter.name }}</h2><p>{{ chapter.subtitle }}</p></div></div>
            <template v-for="(item, index) in levels" :key="item.name">
              <button v-if="item.chapter === chapterIndex" class="level-button" :class="{ current: index === save.level, cleared: save.stars[index] }" :disabled="!unlocked(index)" :aria-current="index === save.level ? 'step' : undefined" :aria-label="`第${index + 1}关 ${item.name}`" @click="chooseLevel(index)">
                <span class="level-number"><UIcon v-if="!unlocked(index)" name="i-lucide-lock-keyhole" /><template v-else>{{ String(index + 1).padStart(2, '0') }}</template></span><span class="level-name">{{ item.name }}<span v-if="save.stars[index]" class="mini-stars" :aria-label="`${save.stars[index]}颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.stars[index] }" /></span></span><UIcon v-if="index === save.level" name="i-lucide-chevron-right" class="level-arrow" />
              </button>
            </template>
          </section>
          <div class="collection-note"><span><UIcon name="i-lucide-sparkles" /></span><div><strong>{{ stars }} 颗探索星</strong><p>每次尝试，都在发现新办法</p></div></div>
        </aside>

        <div class="mission">
          <header class="mission-heading"><div><span class="eyebrow">第 {{ String(save.level + 1).padStart(2, '0') }} 关 / {{ String(levels.length).padStart(2, '0') }}</span><h2>{{ level.name }}</h2></div><span class="concept-tag"><UIcon name="i-lucide-lightbulb" />{{ level.concept }}</span></header>
          <p class="mission-description">{{ level.description }}</p>
          <div class="play-area">
            <section class="scene-panel" aria-label="迷宫场景">
              <div class="scene-meta"><span class="scene-label"><i />小布的森林基地</span><span class="gear-count"><UIcon name="i-lucide-cog" />零件 {{ robot.collected.length }} / {{ level.gears.length }}</span></div>
              <div class="map-scene">
                <span class="decor-cloud cloud-one" /><span class="decor-cloud cloud-two" /><span class="scene-sun" />
                <div class="maze-board" :style="{ '--columns': level.rows[0].length }" role="img" :aria-label="`迷宫地图：小布位于第${robot.y + 1}行、第${robot.x + 1}列，朝${directionNames[robot.direction]}，已收集${robot.collected.length}枚零件`">
                  <div v-for="tile in tiles" :key="tile.key" class="tile" :class="{ path: tile.terrain === '.', water: tile.terrain === '~', rock: tile.terrain === '#', station: tile.goal, origin: tile.start }">
                    <span v-if="tile.terrain === '~'" class="water-ripple" />
                    <span v-if="tile.terrain === '#'" class="stone"><i /></span>
                    <span v-if="tile.goal" class="charging-station"><UIcon name="i-lucide-zap" /></span>
                    <span v-if="tile.gear && !robot.collected.includes(tile.key)" class="map-gear"><UIcon name="i-lucide-cog" /></span>
                    <span v-if="tile.start && !tile.goal" class="start-dot" />
                    <div v-if="robot.x === tile.x && robot.y === tile.y" class="robot-token" :class="{ celebrating: status === 'success' }">
                      <span class="robot-direction" :style="{ transform: `rotate(${robot.direction * 90}deg)` }"><UIcon name="i-lucide-arrow-up" /></span>
                      <svg viewBox="0 0 70 78" aria-hidden="true"><ellipse cx="35" cy="71" rx="21" ry="5" fill="#263e5820" /><path d="M24 57v12m22-12v12" stroke="#47667f" stroke-width="9" stroke-linecap="round" /><rect x="19" y="43" width="33" height="20" rx="8" fill="#eef6f7" stroke="#42647b" stroke-width="2" /><path d="m14 46-5 10m47-10 5 10" stroke="#54728b" stroke-width="7" stroke-linecap="round" /><rect x="28" y="48" width="14" height="7" rx="3" fill="#f1c15d" /><path d="M35 17V9" stroke="#42647b" stroke-width="3" /><circle cx="35" cy="7" r="4" fill="#f1c15d" /><rect x="10" y="17" width="50" height="33" rx="12" fill="#f9fcfd" stroke="#42647b" stroke-width="2.5" /><rect x="16" y="24" width="38" height="18" rx="7" fill="#345269" /><circle cx="26" cy="32" r="3.3" fill="#99e6d5" /><circle cx="44" cy="32" r="3.3" fill="#99e6d5" /><path d="M30 38q5 3 10 0" fill="none" stroke="#99e6d5" stroke-width="1.5" stroke-linecap="round" /></svg>
                    </div>
                  </div>
                </div>
                <div class="scene-caption"><span>森林探索区</span><span>跟着箭头，观察小布的朝向</span></div>
              </div>
              <div class="map-legend"><span><i class="legend-start" />起点</span><span><UIcon name="i-lucide-cog" class="legend-gear" />零件</span><span><UIcon name="i-lucide-zap" class="legend-goal" />充电站</span><span class="facing">朝向 <strong>{{ directionNames[robot.direction] }}</strong></span></div>
              <div class="feedback" :class="status" role="status" aria-label="机器人反馈"><span class="feedback-icon"><UIcon :name="status === 'success' ? 'i-lucide-circle-check' : status === 'failed' ? 'i-lucide-search' : 'i-lucide-bot'" /></span><div><strong>{{ status === 'success' ? '任务完成，干得漂亮！' : status === 'failed' ? '发现了一个需要调整的地方' : status === 'running' ? '小布正在执行指令' : status === 'paused' ? '停下来，想一想' : '你好，我是小布！' }}</strong><p>{{ message }}</p></div></div>
              <div v-if="status === 'success'" class="success-panel">
                <div class="result-stars" :aria-label="`本关最佳${save.stars[save.level]}颗星`"><UIcon v-for="n in 3" :key="n" name="i-lucide-star" :class="{ earned: n <= save.stars[save.level] }" /></div>
                <p>{{ save.level === levels.length - 1 ? '探索路线全部完成！你已经会用顺序、转向和循环了。' : save.stars[save.level] === 3 ? '路线规划得真好，下一段冒险等着你！' : `独立使用不超过 ${level.budget} 块积木，可以挑战 3 颗星。` }}</p>
                <button v-if="save.level < levels.length - 1" class="primary-button next-level" @click="chooseLevel(save.level + 1)">前往下一关<UIcon name="i-lucide-arrow-right" /></button>
                <button v-else class="secondary-button" @click="chooseLevel(0)">再去第一关看看<UIcon name="i-lucide-flag" /></button>
              </div>
              <button class="hint-button" :aria-expanded="hintOpen" @click="showHint"><UIcon name="i-lucide-lightbulb" />{{ hintOpen ? '收起提示' : '给我一点提示' }}<UIcon name="i-lucide-chevron-down" /></button>
              <p v-if="hintOpen" class="hint-text">{{ level.hint }}</p>
            </section>

            <section class="program-panel" aria-label="指令编排">
              <header class="program-heading"><div><UIcon name="i-lucide-blocks" /><h3>我的指令</h3></div><span>{{ save.program.length }} / {{ MAX_CARDS }} 块</span></header>
              <p class="program-intro">{{ level.repeat ? '相同的动作，试着放进重复积木。' : '点击积木加入程序，从上到下依次执行。' }}</p>
              <div class="command-palette">
                <button v-for="command in level.commands" :key="command" class="command-button" :class="command" :disabled="busy || (loop ? loop.body.length >= MAX_BODY : save.program.length >= MAX_CARDS)" :aria-label="`添加${commandInfo[command].name}指令`" @click="addCommand(command)"><UIcon :name="commandInfo[command].icon" /><strong>{{ commandInfo[command].name }}</strong><span>{{ commandInfo[command].description }}</span></button>
              </div>
              <button v-if="level.repeat" class="add-loop" aria-label="重复积木" :disabled="busy || save.program.length >= MAX_CARDS" @click="addLoop"><UIcon name="i-lucide-repeat-2" /><strong>重复积木</strong><span>让一组动作执行多次</span><UIcon name="i-lucide-plus" /></button>
              <div v-if="loop" class="loop-notice"><span>正在给第 {{ (selectedLoop ?? 0) + 1 }} 块重复积木添加动作</span><button :disabled="busy" @click="selectedLoop = null">完成</button></div>
              <div class="sequence" aria-label="程序列表">
                <div v-if="!save.program.length" class="empty-program"><span><UIcon name="i-lucide-mouse-pointer-2" /></span><strong>第一步，从一块积木开始</strong><p>点一下上面的「前进」<br>把你的想法交给小布</p><span class="empty-dots"><i /><i /><i /></span></div>
                <div v-for="(instruction, index) in save.program" :key="index" class="instruction-card" :class="[instruction.type, { executing: activeStep?.card === index, editing: selectedLoop === index }]">
                  <div class="instruction-main"><span class="step-number">{{ index + 1 }}</span><UIcon :name="instruction.type === 'repeat' ? 'i-lucide-repeat-2' : commandInfo[instruction.type].icon" /><strong>{{ instruction.type === 'repeat' ? '重复' : commandInfo[instruction.type].name }}</strong>
                    <select v-if="instruction.type === 'repeat'" :value="instruction.count" :disabled="busy" :aria-label="`第${index + 1}块重复次数`" @change="setRepeat(index, Number(($event.target as HTMLSelectElement).value))"><option v-for="n in [2, 3, 4]" :key="n" :value="n">{{ n }} 次</option></select>
                    <div class="card-tools"><button :disabled="busy || index === 0" :aria-label="`上移第${index + 1}块指令`" @click="moveCard(index, -1)"><UIcon name="i-lucide-chevron-up" /></button><button :disabled="busy || index === save.program.length - 1" :aria-label="`下移第${index + 1}块指令`" @click="moveCard(index, 1)"><UIcon name="i-lucide-chevron-down" /></button><button :disabled="busy" :aria-label="`删除第${index + 1}块指令`" @click="removeCard(index)"><UIcon name="i-lucide-x" /></button></div>
                  </div>
                  <div v-if="instruction.type === 'repeat'" class="repeat-body">
                    <div v-for="(command, inner) in instruction.body" :key="inner" class="inner-command" :class="[command, { active: activeStep?.card === index && activeStep?.inner === inner }]">
                      <UIcon :name="commandInfo[command].icon" /><span>{{ commandInfo[command].name }}</span><button :disabled="busy" :aria-label="`删除第${index + 1}块重复里的第${inner + 1}个动作`" @click="removeInner(index, inner)"><UIcon name="i-lucide-x" /></button>
                    </div>
                    <button class="edit-loop" :disabled="busy" :aria-label="`编辑第${index + 1}块重复动作`" @click="selectedLoop = selectedLoop === index ? null : index">{{ instruction.body.length ? '添加动作' : '点击这里，再选上面的动作' }}<UIcon name="i-lucide-plus" /></button>
                    <span v-if="activeStep?.card === index && busy" class="iteration-label">正在重复第 {{ activeStep.iteration }} / {{ instruction.count }} 次</span>
                  </div>
                </div>
              </div>
              <div class="program-meta"><span><UIcon name="i-lucide-list-ordered" />{{ busy || status === 'success' || status === 'failed' ? `${cursor} / ${steps.length}` : expanded.length }} 步动作</span><button :disabled="busy || !save.program.length" @click="clearProgram"><UIcon name="i-lucide-trash-2" />清空</button></div>
              <div class="run-controls"><button v-if="status === 'running'" class="primary-button" @click="pause"><UIcon name="i-lucide-pause" />暂停运行</button><button v-else class="primary-button" @click="run"><UIcon name="i-lucide-play" />{{ status === 'paused' ? '继续运行' : '运行程序' }}</button><button class="step-button" :disabled="status === 'running'" @click="singleStep"><UIcon name="i-lucide-step-forward" />单步</button><button class="rewind-button" aria-label="回到起点" title="重新尝试，本次提示记录清零" @click="retryAttempt"><UIcon name="i-lucide-rotate-ccw" /></button></div>
              <div class="program-bottom"><span>3 星挑战：独立使用 ≤ {{ level.budget }} 块</span><label><input v-model="quick" type="checkbox">快速运行</label></div>
            </section>
          </div>
        </div>
      </div>
      <footer class="maze-footer"><span><UIcon name="i-lucide-heart" />每一次尝试，都是成长</span><button @click="resetOpen = true">重新开始探索</button><span role="status" aria-label="进度保存状态"><UIcon :name="saveError ? 'i-lucide-cloud-off' : 'i-lucide-cloud-check'" />{{ saveError ? '本机暂时无法保存进度' : '进度已保存在本机' }}</span></footer>
    </main>
    <UModal :open="helpOpen" title="和小布一起探索" description="先想路线，再用积木写出你的办法。" :close="{ 'aria-label': '关闭玩法说明' }" @update:open="helpOpen = $event"><template #body><ol class="help-list"><li>观察小布头上的箭头。「前进」沿箭头方向走一格，「左转」「右转」只改变朝向。</li><li>点击动作积木加入程序，用上下按钮调整顺序。收齐所有零件，并在指令结束时停在充电站。</li><li>按「运行程序」看完整过程，或用「单步」一次看一个动作。遇到障碍会停下，可以回到起点重新调整。</li><li>后面的关卡会解锁重复积木：选中它，加入动作，设置重复次数。完成关卡后自动解锁下一关。</li></ol><button class="primary-button" @click="helpOpen = false">明白了，开始探索<UIcon name="i-lucide-arrow-right" /></button></template></UModal>
    <UModal :open="resetOpen" title="重新开始探索？" description="本游戏的关卡、指令和探索星会清空，从第 1 关重新开始。" @update:open="resetOpen = $event"><template #body><div class="reset-actions"><button class="secondary-button" @click="resetOpen = false">保留当前进度</button><button class="primary-button" @click="restart">重新开始</button></div></template></UModal>
  </div>
</template>

<style scoped>
.maze-game { --maze-ink: #344c5f; --maze-muted: #83919c; --maze-blue: #527b96; --maze-border: #e1e8ec; min-height: 100dvh; background: #f7f9fa; color: var(--maze-ink); font-family: var(--font-ui); letter-spacing: 0; }
.maze-game button { cursor: pointer; transition: background .16s, box-shadow .16s; }
.maze-game button:disabled { cursor: default; opacity: .42; }
.maze-game button:focus-visible, .maze-game select:focus-visible, .maze-game input:focus-visible { outline: 3px solid #86b9d8; outline-offset: 3px; }
.maze-content { max-width: 1400px; margin: auto; padding: 30px 36px 18px; }
.maze-heading { display: flex; align-items: center; justify-content: space-between; margin-bottom: 29px; gap: 12px; }
.eyebrow { color: var(--maze-muted); font-size: 11px; line-height: 1.6; }
.maze-heading h1 { font-size: 29px; font-weight: 750; letter-spacing: -1px; line-height: 1.5; margin-top: 3px; }
.maze-heading h1 > span { color: #e5b95b; margin-left: 3px; }
.maze-heading p { color: var(--maze-muted); font-size: 12px; margin-top: 5px; }
.text-button { display: flex; align-items: center; gap: 7px; font-size: 12px; color: #718795; border: 1px solid var(--maze-border); border-radius: 6px; background: #fff; padding: 9px 12px; white-space: nowrap; }
.maze-layout { display: grid; grid-template-columns: 208px minmax(0, 1fr); gap: 32px; }
.journey { padding-right: 24px; border-right: 1px solid var(--maze-border); }
.journey-title { display: flex; justify-content: space-between; align-items: center; font-size: 12px; margin-bottom: 12px; }
.journey-title > span { font-weight: 650; }
.journey-title strong { color: var(--maze-muted); font-size: 11px; font-weight: 500; }
.journey-progress { height: 4px; background: #e6ecef; border-radius: 3px; overflow: hidden; }
.journey-progress > span { display: block; height: 100%; background: #81a79c; transition: width .3s; }
.chapter { margin-top: 27px; }
.chapter-title { display: flex; gap: 9px; align-items: center; margin-bottom: 12px; }
.chapter-title > span { width: 28px; height: 28px; background: #edf1f3; color: #7d96a6; display: grid; place-items: center; border-radius: 7px; }
.chapter-title h2 { font-size: 12px; font-weight: 650; }
.chapter-title p { font-size: 9px; color: var(--maze-muted); margin-top: 3px; }
.level-button { display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px 9px; min-height: 43px; border-radius: 6px; text-align: left; margin: 3px 0; }
.level-button:not(:disabled):hover { background: #edf2f5; }
.level-button.current { background: #e8f0f5; color: #527b96; }
.level-button:disabled { opacity: .52; }
.level-number { font-size: 10px; color: #97a6ae; flex: none; width: 18px; text-align: center; }
.level-number > span { width: 13px; height: 13px; }
.current .level-number { color: #527b96; font-weight: 700; }
.level-name { font-size: 11px; flex: 1; }
.current .level-name { font-weight: 650; }
.level-arrow { width: 13px; }
.mini-stars { display: flex; gap: 2px; margin-top: 3px; }
.mini-stars > span { width: 9px; height: 9px; color: #dbe1e5; }
.mini-stars > .earned { color: #d8ad55; }
.collection-note { margin-top: 27px; padding-top: 20px; border-top: 1px solid var(--maze-border); display: flex; align-items: center; gap: 10px; }
.collection-note > span { width: 30px; height: 30px; border-radius: 50%; background: #fcf3dc; color: #c8a051; display: grid; place-items: center; }
.collection-note strong { font-size: 11px; }
.collection-note p { font-size: 9px; color: var(--maze-muted); margin-top: 4px; }
.mission { min-width: 0; }
.mission-heading { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.mission-heading h2 { font-size: 21px; font-weight: 700; margin-top: 3px; }
.concept-tag { display: flex; align-items: center; gap: 5px; padding: 6px 10px; border-radius: 5px; background: #f0f1eb; color: #9a965f; font-size: 10px; white-space: nowrap; }
.concept-tag > span { width: 13px; height: 13px; }
.mission-description { color: var(--maze-muted); font-size: 12px; margin: 9px 0 22px; }
.play-area { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(310px, 1fr); gap: 24px; align-items: start; }
.scene-panel { min-width: 0; }
.scene-meta { padding: 12px 16px; border: 1px solid var(--maze-border); border-bottom: 0; border-radius: 9px 9px 0 0; background: #fff; display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.scene-label { font-size: 10px; color: #7e949d; display: flex; align-items: center; gap: 6px; }
.scene-label i { width: 5px; height: 5px; background: #82aa94; border-radius: 50%; }
.gear-count { display: flex; align-items: center; gap: 5px; color: #a99159; font-size: 10px; }
.gear-count > span { width: 13px; height: 13px; }
.map-scene { position: relative; overflow: hidden; background: linear-gradient(150deg, #e9f2f3, #dcebea 65%, #d7e5d8); padding: 44px 26px 37px; border: 1px solid #dce6e7; }
.map-scene::before, .map-scene::after { content: ''; position: absolute; border-radius: 45% 50% 0 0; width: 330px; height: 160px; background: #c4d9c342; bottom: -115px; left: -80px; transform: rotate(12deg); }
.map-scene::after { left: auto; right: -100px; bottom: -100px; background: #adcba13b; }
.decor-cloud { position: absolute; height: 8px; width: 40px; border-radius: 30px; background: #ffffff87; }
.decor-cloud::before { content: ''; position: absolute; width: 18px; height: 12px; border-radius: 20px; top: -6px; left: 9px; background: #ffffffaa; }
.cloud-one { left: 26px; top: 28px; }
.cloud-two { right: 30px; top: 50px; transform: scale(.8); }
.scene-sun { position: absolute; right: 66px; top: 18px; width: 22px; height: 22px; background: #eed7a4; border-radius: 50%; box-shadow: 0 0 0 7px #eed7a421; }
.maze-board { position: relative; z-index: 1; display: grid; grid-template-columns: repeat(var(--columns), minmax(0, 1fr)); gap: 5px; width: 100%; max-width: 390px; margin: 0 auto; padding: 11px; border-radius: 15px; background: #b6cfd275; border: 1px solid #ffffff90; box-shadow: 0 10px 0 -3px #acc6c673, 0 18px 20px -12px #3a5d6338; }
.tile { aspect-ratio: 1; border-radius: 7px; position: relative; display: grid; place-items: center; }
.tile.path { background: #f3f0df; box-shadow: 0 3px 0 #d9d8bd; border: 1px solid #ffffffc0; }
.tile.path::before { content: ''; position: absolute; bottom: 13%; left: 17%; width: 3px; height: 3px; background: #dbd6bc; border-radius: 50%; box-shadow: 22px -20px #ded7bd; }
.tile.water { background: #9fcbd34f; }
.water-ripple { width: 28%; height: 5px; border-bottom: 2px solid #e5f4f06e; border-radius: 50%; }
.water-ripple::after { content: ''; display: block; width: 80%; margin: 7px 0 0 12px; height: 3px; border-bottom: 1px solid #e5f4f054; border-radius: 50%; }
.tile.rock { background: #cad8ba9c; }
.stone { width: 63%; height: 48%; border-radius: 45% 45% 25% 30%; background: #93a69c; box-shadow: inset -7px -6px #7c928973, 0 4px 0 #81978a40; transform: rotate(-6deg); }
.stone i { display: block; width: 30%; height: 3px; border-radius: 3px; background: #bccbc1; position: relative; top: 20%; left: 20%; }
.charging-station { position: absolute; width: 68%; height: 68%; border-radius: 9px; background: #9fbba566; border: 2px solid #8aad97; display: grid; place-items: center; color: #6a9a7e; }
.charging-station > span { width: 52%; height: 52%; }
.map-gear { color: #cda04d; display: grid; place-items: center; width: 57%; height: 57%; background: #f8e5a9; border-radius: 50%; box-shadow: 0 3px 0 #cfb56b, 0 0 0 5px #e9c75c16; z-index: 2; }
.map-gear > span { width: 80%; height: 80%; }
.start-dot { width: 20%; height: 20%; background: #9fbdcd; border-radius: 50%; border: 2px solid #7395ab; }
.robot-token { position: absolute; width: 95%; height: 105%; bottom: 0; z-index: 4; }
.robot-token svg { width: 100%; height: 100%; filter: drop-shadow(0 3px 2px #34526919); }
.robot-direction { position: absolute; top: -17%; left: 36%; width: 28%; height: 28%; color: #517b98; display: grid; place-items: center; background: #fff; border-radius: 50%; box-shadow: 0 2px 4px #34526918; z-index: 5; }
.robot-direction > span { width: 85%; height: 85%; }
.robot-token.celebrating { animation: robot-bounce .6s ease 2; }
@keyframes robot-bounce { 50% { transform: translateY(-6px); } }
.scene-caption { position: relative; z-index: 1; display: flex; justify-content: space-between; gap: 5px; font-size: 8px; color: #869d9c; margin-top: 24px; }
.map-legend { display: flex; align-items: center; gap: 18px; padding: 13px 16px; border: 1px solid var(--maze-border); border-top: 0; border-radius: 0 0 9px 9px; background: #fff; font-size: 9px; color: #8c999f; }
.map-legend > span { display: flex; align-items: center; gap: 5px; }
.map-legend > span > span { width: 12px; height: 12px; }
.legend-start { width: 8px; height: 8px; border: 2px solid #87a7bb; border-radius: 50%; }
.legend-gear { color: #cda04d; }
.legend-goal { color: #81a68d; }
.map-legend .facing { margin-left: auto; }
.facing strong { font-weight: 600; color: #63869c; }
.feedback { padding: 18px 1px 14px; display: flex; align-items: flex-start; gap: 10px; min-height: 88px; }
.feedback-icon { width: 32px; height: 32px; flex: none; display: grid; place-items: center; background: #eaf0f5; color: #708fa6; border-radius: 9px; }
.feedback-icon > span { width: 19px; height: 19px; }
.feedback strong { font-size: 12px; font-weight: 650; }
.feedback p { font-size: 11px; color: #8a969c; line-height: 1.8; margin-top: 4px; }
.feedback.failed .feedback-icon { background: #fbf0db; color: #b39a62; }
.feedback.success .feedback-icon { background: #e7f2e9; color: #6a9476; }
.hint-button { width: 100%; display: flex; align-items: center; gap: 7px; border-top: 1px solid var(--maze-border); padding: 12px 0; color: #9a9b7e; font-size: 11px; }
.hint-button > span { width: 14px; height: 14px; }
.hint-button > span:last-child { margin-left: auto; }
.hint-text { font-size: 11px; line-height: 1.9; color: #91876e; background: #fbf6e9; border-radius: 6px; padding: 12px; }
.program-panel { border: 1px solid var(--maze-border); border-radius: 9px; padding: 20px; background: #fff; min-width: 0; }
.program-heading { display: flex; justify-content: space-between; align-items: center; }
.program-heading > div { display: flex; align-items: center; gap: 7px; }
.program-heading > div > span { width: 17px; height: 17px; color: #7b99ab; }
.program-heading h3 { font-size: 14px; font-weight: 650; }
.program-heading > span { font-size: 10px; color: #a0acb3; }
.program-intro { font-size: 10px; color: var(--maze-muted); line-height: 1.7; margin: 8px 0 16px; }
.command-palette { display: flex; gap: 8px; }
.command-button { flex: 1; display: flex; align-items: center; flex-direction: column; padding: 12px 4px 9px; border: 1px solid #dbe7ef; background: #eef5fa; border-radius: 7px; color: #63869c; min-width: 0; }
.command-button > span:first-child { width: 20px; height: 20px; margin-bottom: 7px; }
.command-button strong { font-size: 11px; font-weight: 650; }
.command-button > span:last-child { font-size: 8px; margin-top: 4px; opacity: .75; white-space: nowrap; }
.command-button.left { background: #eef4ed; border-color: #dce7d8; color: #7d9974; }
.command-button.right { background: #faf2e7; border-color: #efe3cd; color: #b0996b; }
.command-button:not(:disabled):hover { box-shadow: inset 0 0 0 1px currentColor; }
.add-loop { display: flex; align-items: center; gap: 6px; width: 100%; margin-top: 9px; padding: 10px; border-radius: 6px; background: #f1edf8; color: #9781b5; border: 1px solid #e4dbef; }
.add-loop > span:first-child, .add-loop > span:last-child { width: 15px; height: 15px; flex: none; }
.add-loop strong { font-size: 10px; white-space: nowrap; }
.add-loop > span:nth-last-child(2) { font-size: 9px; color: #a395b7; flex: 1; text-align: right; }
.loop-notice { display: flex; align-items: center; gap: 5px; color: #9a83b1; font-size: 9px; padding: 10px 0 0; }
.loop-notice > span { flex: 1; }
.loop-notice button { border: 1px solid #e4dbef; border-radius: 4px; padding: 4px 8px; white-space: nowrap; }
.sequence { display: flex; flex-direction: column; gap: 7px; min-height: 190px; max-height: 390px; overflow-y: auto; margin-top: 18px; padding: 2px 3px 3px; scrollbar-width: thin; }
.empty-program { display: flex; align-items: center; justify-content: center; flex-direction: column; border: 1px dashed #dce5eb; border-radius: 7px; background: #fafcfd; flex: 1; text-align: center; min-height: 185px; padding: 20px 5px; }
.empty-program > span:first-child { width: 33px; height: 33px; display: grid; place-items: center; border-radius: 50%; background: #edf3f6; color: #aac0cc; margin-bottom: 12px; }
.empty-program strong { font-size: 11px; color: #91a1ab; font-weight: 500; }
.empty-program p { font-size: 10px; line-height: 1.9; color: #a5b1b8; margin: 8px 0 14px; }
.empty-dots { display: flex; gap: 4px; }
.empty-dots i { width: 4px; height: 4px; border-radius: 50%; background: #dbe5eb; }
.instruction-card { border: 1px solid #dce7ee; background: #f1f6fa; color: #6b899e; border-radius: 6px; flex-shrink: 0; }
.instruction-card.left { background: #f1f6ef; border-color: #dfe8db; color: #809778; }
.instruction-card.right { background: #faf4e9; border-color: #ece1cd; color: #ac956d; }
.instruction-card.repeat { background: #f5f1f9; border-color: #e5dcee; color: #9780ad; }
.instruction-card.executing { outline: 2px solid #e2bc62; outline-offset: 0; box-shadow: 0 0 0 3px #e2bc6218; }
.instruction-card.editing { border-color: #ad92c8; }
.instruction-main { display: flex; align-items: center; gap: 8px; padding: 6px 8px; min-height: 40px; }
.step-number { font-size: 9px; opacity: .6; width: 14px; flex: none; }
.instruction-main > span:nth-child(2) { width: 15px; height: 15px; flex: none; }
.instruction-main strong { font-size: 11px; font-weight: 600; }
.instruction-main select { background: #fff9; border: 1px solid #e2d7ed; border-radius: 4px; padding: 2px; font-size: 10px; color: #9780ad; }
.card-tools { display: flex; margin-left: auto; gap: 1px; }
.card-tools button { display: grid; place-items: center; width: 25px; height: 26px; border-radius: 4px; }
.card-tools button:hover { background: #fff9; }
.card-tools button > span { width: 12px; height: 12px; }
.repeat-body { margin: 0 10px 10px 30px; border-left: 2px solid #d8c9e7; padding-left: 9px; display: flex; flex-direction: column; gap: 5px; }
.inner-command { display: flex; align-items: center; gap: 6px; background: #fff9; padding: 4px 8px; border-radius: 4px; font-size: 10px; }
.inner-command > span:first-child { width: 12px; height: 12px; }
.inner-command button { margin-left: auto; width: 24px; height: 24px; display: grid; place-items: center; }
.inner-command button > span { width: 12px; height: 12px; }
.inner-command.active { background: #f9eccb; }
.edit-loop { display: flex; align-items: center; justify-content: space-between; min-height: 30px; font-size: 9px; color: #ab99bc; }
.edit-loop > span { width: 12px; height: 12px; }
.iteration-label { font-size: 9px; color: #af945d; }
.program-meta { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #eaf0f3; padding: 13px 0; color: #9aaab3; font-size: 9px; }
.program-meta > span, .program-meta button { display: flex; align-items: center; gap: 4px; }
.program-meta button { padding: 3px 0 3px 8px; }
.program-meta > span > span, .program-meta button > span { width: 12px; height: 12px; }
.run-controls { display: flex; gap: 7px; margin-top: 16px; }
.primary-button { display: flex; align-items: center; justify-content: center; gap: 7px; background: #527b96; color: #fff; min-height: 43px; padding: 10px 12px; border-radius: 6px; font-size: 11px; font-weight: 600; flex: 1; }
.primary-button:hover { background: #426a84; }
.primary-button > span { width: 14px; height: 14px; }
.step-button, .rewind-button, .secondary-button { display: flex; align-items: center; justify-content: center; gap: 5px; border: 1px solid var(--maze-border, #e1e8ec); border-radius: 6px; color: #7c94a2; font-size: 10px; min-height: 43px; background: #fff; }
.step-button { padding: 8px 10px; }
.rewind-button { width: 39px; flex: none; }
.step-button > span, .rewind-button > span { width: 15px; height: 15px; }
.program-bottom { display: flex; justify-content: space-between; align-items: center; gap: 7px; margin-top: 13px; font-size: 8px; color: #9ca8af; }
.program-bottom label { display: flex; align-items: center; gap: 4px; white-space: nowrap; cursor: pointer; }
.program-bottom input { width: 11px; height: 11px; accent-color: #527b96; }
.success-panel { text-align: center; background: #f0f6ef; border: 1px solid #e0ebdc; border-radius: 8px; padding: 15px; margin-bottom: 12px; }
.result-stars { display: flex; justify-content: center; gap: 7px; }
.result-stars > span { width: 22px; height: 22px; color: #dce3d6; }
.result-stars > .earned { color: #d7b057; }
.success-panel p { font-size: 10px; color: #85957c; line-height: 1.8; margin: 9px 0 12px; }
.next-level { width: 100%; background: #74977d; }
.next-level:hover { background: #66876e; }
.secondary-button { padding: 10px 16px; width: 100%; }
.maze-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: #a7b3b6; font-size: 9px; margin-top: 27px; }
.maze-footer > span { display: flex; align-items: center; gap: 5px; }
.maze-footer > span > span { width: 12px; height: 12px; }
.maze-footer button { color: #a4b0b5; text-decoration: underline; text-underline-offset: 3px; }
.help-list { color: #71828e; font-size: 13px; line-height: 1.9; padding-left: 20px; list-style-type: decimal; margin-bottom: 22px; }
.help-list li + li { margin-top: 12px; }
.reset-actions { display: flex; gap: 10px; }
.reset-actions .secondary-button { flex: 1; width: auto; }
@media (min-width: 1500px) { .maze-content { padding-top: 38px; } .map-scene { padding-top: 50px; padding-bottom: 42px; } .sequence { min-height: 220px; } }
@media (max-width: 1150px) { .maze-content { padding: 26px 24px 18px; } .maze-layout { grid-template-columns: 178px minmax(0, 1fr); gap: 22px; } .journey { padding-right: 17px; } .play-area { grid-template-columns: minmax(0, 1fr) minmax(290px, 1fr); gap: 16px; } .map-scene { padding: 35px 15px 28px; } .program-panel { padding: 16px; } .map-legend { gap: 10px; padding: 13px 10px; } .scene-meta { padding: 12px 10px; } .card-tools button { width: 23px; } }
@media (max-width: 980px) { .maze-layout { grid-template-columns: minmax(0, 1fr); gap: 22px; } .journey { border: 0; padding: 0; display: flex; gap: 8px; overflow-x: auto; padding-bottom: 8px; scroll-snap-type: x proximity; scroll-behavior: smooth; scrollbar-width: none; -webkit-overflow-scrolling: touch; } .journey::-webkit-scrollbar { display: none; } .journey-title, .journey-progress, .collection-note { display: none; } .chapter { margin: 0; display: flex; gap: 8px; flex: none; } .chapter-title { display: none; } .level-button { width: 144px; padding: 9px; margin: 0; border: 1px solid var(--maze-border); min-height: 44px; scroll-snap-align: center; } .level-name { font-size: 10px; } .play-area { grid-template-columns: minmax(0, 1.2fr) minmax(300px, 1fr); gap: 22px; } .map-scene { padding: 43px 24px 32px; } .maze-heading { margin-bottom: 20px; } }
@media (max-width: 680px) { .maze-content { padding: 21px 18px 16px; } .maze-heading h1 { font-size: 24px; } .maze-heading p { font-size: 11px; } .maze-heading .eyebrow { font-size: 10px; } .text-button { padding: 8px; font-size: 10px; } .maze-layout { gap: 18px; } .level-name { font-size: 11px; } .play-area { grid-template-columns: minmax(0, 1fr); gap: 18px; } .mission-heading h2 { font-size: 19px; } .mission-description { margin-bottom: 16px; font-size: 11px; } .map-scene { padding: 35px 25px 25px; } .maze-board { max-width: 350px; gap: 4px; padding: 10px; } .scene-meta { padding: 12px 14px; } .map-legend { padding: 13px 14px; gap: 18px; } .feedback { min-height: 78px; padding-top: 15px; } .program-panel { padding: 18px; } .program-intro { font-size: 11px; } .command-button { padding-top: 13px; } .command-button strong { font-size: 12px; } .command-button > span:last-child { font-size: 9px; } .sequence { min-height: 160px; max-height: 350px; } .empty-program { min-height: 155px; } .instruction-main { min-height: 43px; } .instruction-main strong { font-size: 12px; } .card-tools { gap: 4px; } .card-tools button { width: 30px; height: 30px; } .repeat-body { margin-left: 33px; } .inner-command { font-size: 11px; } .inner-command button { width: 30px; height: 28px; } .run-controls .primary-button, .step-button, .rewind-button { min-height: 46px; } .primary-button { font-size: 12px; } .program-bottom { font-size: 10px; } .maze-footer { flex-wrap: wrap; font-size: 8px; gap: 9px; margin-top: 22px; } .maze-footer button { order: 3; width: 100%; text-align: left; } }
@media (max-width: 360px) { .maze-content { padding-left: 14px; padding-right: 14px; } .maze-heading h1 { font-size: 21px; } .maze-heading p { font-size: 10px; } .map-scene { padding-left: 14px; padding-right: 14px; } .map-legend { gap: 11px; } .program-panel { padding: 14px; } .command-button > span:last-child { font-size: 8px; } }
@media (prefers-reduced-motion: reduce) { .robot-token.celebrating { animation: none; } .maze-game button, .journey-progress > span { transition: none; } .journey { scroll-behavior: auto; } }
</style>
