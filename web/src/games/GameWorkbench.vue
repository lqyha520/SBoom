<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import FruitSprite from './FruitSprite.vue'
import ShopScene from './ShopScene.vue'
import GameNav from './GameNav.vue'
import {
  addProduct, basketTotal, currentOrder, customers, difficulties, newShop,
  nextCustomer, nextDay, payment, products, removeProduct, restoreShop, submitAmount,
  submitPacking, upgradeShop, type Difficulty,
} from './little-shop'

const props = withDefaults(defineProps<{ embedded?: boolean; storageKey?: string }>(), {
  embedded: false, storageKey: 'lc_game_little_shop_v1_guest',
})
function readSave() {
  try { return restoreShop(localStorage.getItem(props.storageKey)) } catch { return null }
}
const state = ref(readSave() || newShop())
const amount = ref('')
const coins = ref<number[]>([])
const feedback = ref('')
const hint = ref(false)
const paused = ref(false)
const settings = ref(false)
const collection = ref(false)
const resetDifficulty = ref<Difficulty | null>(null)
const sound = ref(false)
const saveError = ref(false)
const order = computed(() => currentOrder(state.value))
const orderItems = computed(() => products.filter(p => order.value[p.id] > 0))
const visitor = computed(() => customers[state.value.customer])
const total = computed(() => basketTotal(order.value))
const given = computed(() => payment(state.value))
const change = computed(() => coins.value.reduce((sum, n) => sum + n, 0))
const completed = computed(() => state.value.customer + (['served', 'closed'].includes(state.value.stage) ? 1 : 0))
const phase = computed(() => ({ packing: 0, total: 1, change: 2, served: 3, closed: 3 })[state.value.stage])
const steps = computed(() => state.value.difficulty === 'count' ? ['装好水果']
  : state.value.difficulty === 'total' ? ['装好水果', '算出总价'] : ['装好水果', '算出总价', '找回零钱'])
const goalTitle = computed(() => ['served', 'closed'].includes(state.value.stage) ? '做得真棒！'
  : state.value.stage === 'packing' ? '先装好顾客要的水果' : state.value.stage === 'total' ? '这些水果一共多少钱？' : '该找给顾客多少零钱？')
const equation = computed(() => orderItems.value.map(p => `${p.price} × ${order.value[p.id]}`).join(' + '))
const badges = computed(() => [
  { name: '开张大吉', icon: 'i-lucide-store', earned: state.value.lifetimeServed >= 4, goal: '接待 4 位顾客' },
  { name: '人气店长', icon: 'i-lucide-heart-handshake', earned: state.value.lifetimeServed >= 8, goal: '接待 8 位顾客' },
  { name: '小小企业家', icon: 'i-lucide-crown', earned: state.value.upgrades >= 2, goal: '完成 2 次店铺升级' },
])
let audio: AudioContext | null = null
function playTone(success = false) {
  if (!sound.value) return
  try {
    audio ||= new AudioContext()
    void audio.resume()
    const oscillator = audio.createOscillator()
    const gain = audio.createGain()
    oscillator.connect(gain); gain.connect(audio.destination)
    oscillator.type = 'sine'
    oscillator.frequency.setValueAtTime(success ? 523 : 440, audio.currentTime)
    oscillator.frequency.setValueAtTime(success ? 784 : 587, audio.currentTime + .08)
    gain.gain.setValueAtTime(.08, audio.currentTime)
    gain.gain.exponentialRampToValueAtTime(.001, audio.currentTime + .22)
    oscillator.start(); oscillator.stop(audio.currentTime + .22)
  } catch { sound.value = false }
}
function clearFeedback() { feedback.value = ''; hint.value = false }
function pick(id: typeof products[number]['id']) {
  if (paused.value || !addProduct(state.value, id)) return
  clearFeedback(); playTone()
}
function unpack(id: typeof products[number]['id']) { removeProduct(state.value, id); clearFeedback() }
function checkBag() {
  if (!submitPacking(state.value)) { feedback.value = '再对照一下购物单，看看水果的种类和数量。'; return }
  clearFeedback(); playTone(true)
}
function digit(value: string) {
  if (amount.value.length >= 3) return
  amount.value = amount.value === '0' ? value : amount.value + value
  feedback.value = ''
}
function addCoin(value: number) {
  if (coins.value.length >= 20) return
  coins.value.push(value); feedback.value = ''; playTone()
}
function checkAmount() {
  if (state.value.stage === 'total' && !amount.value) return
  if (!submitAmount(state.value, state.value.stage === 'total' ? Number(amount.value) : change.value)) {
    feedback.value = state.value.stage === 'total' ? '还差一点点，试着把每种水果的钱加起来。' : '再数一数：总价加上找回的钱，应当等于顾客付的钱。'
    return
  }
  amount.value = ''; coins.value = []; clearFeedback(); playTone(true)
}
function advance() { nextCustomer(state.value); clearFeedback() }
function tomorrow() { nextDay(state.value); clearFeedback() }
function showHint() { if (!hint.value) state.value.hints++; hint.value = !hint.value }
function restart() {
  state.value = newShop(resetDifficulty.value || state.value.difficulty)
  amount.value = ''; coins.value = []; resetDifficulty.value = null; settings.value = false
  clearFeedback()
}
watch(state, value => {
  try { localStorage.setItem(props.storageKey, JSON.stringify(value)); saveError.value = false }
  catch { saveError.value = true }
}, { deep: true, flush: 'post', immediate: true })
watch(() => props.storageKey, () => {
  state.value = readSave() || newShop(); amount.value = ''; coins.value = []; clearFeedback()
})
onBeforeUnmount(() => { void audio?.close() })
</script>

<template>
  <div class="game-module" :class="{ 'game-embedded': embedded }">
    <GameNav v-if="!embedded" active="little-shop" />
    <main class="game-content">
      <header class="shop-heading">
        <div class="shop-title"><span class="game-eyebrow">我的第一家小店</span><h1>小小店长<span class="title-dot">.</span></h1></div>
        <div class="shop-toolbar">
          <div class="difficulty-switch" role="group" aria-label="游戏难度">
            <button v-for="difficulty in difficulties" :key="difficulty.id" :aria-pressed="state.difficulty === difficulty.id" :class="{ selected: state.difficulty === difficulty.id }" :title="difficulty.age" @click="state.difficulty !== difficulty.id && (resetDifficulty = difficulty.id)">{{ difficulty.name }}</button>
          </div>
          <UTooltip :text="sound ? '关闭音效' : '开启音效'"><button class="round-tool" :aria-label="sound ? '关闭音效' : '开启音效'" :aria-pressed="sound" @click="sound = !sound"><UIcon :name="sound ? 'i-lucide-volume-2' : 'i-lucide-volume-x'" /></button></UTooltip>
          <UTooltip text="暂停"><button class="round-tool" aria-label="暂停游戏" @click="paused = true"><UIcon name="i-lucide-pause" /></button></UTooltip>
          <UTooltip text="设置"><button class="round-tool" aria-label="游戏设置" @click="settings = true"><UIcon name="i-lucide-settings-2" /></button></UTooltip>
        </div>
      </header>

      <div class="shop-status">
        <div class="day-label"><span class="sun-icon"><UIcon name="i-lucide-sun" /></span><div><strong>第 {{ state.day }} 天</strong><span>{{ state.stage === 'closed' ? '今日已打烊' : '晴天，适合开张' }}</span></div></div>
        <div class="daily-goal"><span>今日顾客</span><div class="customer-progress" aria-label="今日接待进度"><span v-for="n in 4" :key="n" :class="{ done: n <= completed, current: n === state.customer + 1 && state.stage !== 'closed' && state.stage !== 'served' }"><UIcon :name="n <= completed ? 'i-lucide-check' : 'i-lucide-user-round'" /></span></div><strong>{{ completed }}<small> / 4</small></strong></div>
        <div class="money-stat"><UIcon name="i-lucide-wallet" /><span>小店金库</span><strong>¥ {{ state.cash }}</strong></div>
        <button class="collection-button" aria-label="查看店长徽章" @click="collection = true"><UIcon name="i-lucide-award" /><span>店长徽章</span><strong>{{ badges.filter(b => b.earned).length }} / 3</strong></button>
      </div>

      <div class="play-layout">
        <section class="store-world" aria-label="水果小店">
          <div class="world-label"><span class="open-dot" :class="{ closed: state.stage === 'closed' }" />{{ state.stage === 'closed' ? '明天见' : '正在营业' }}<span class="world-level">Lv. {{ state.upgrades + 1 }}</span></div>
          <div class="world-speech" v-if="state.stage !== 'closed'"><span>{{ visitor.name }}</span><p>{{ state.stage === 'served' ? '谢谢店长，下次还来！' : visitor.message }}</p></div>
          <ShopScene :customer="state.customer" :upgrade="state.upgrades" :closed="state.stage === 'closed'" />
          <div class="scene-fruits" aria-hidden="true"><div v-for="product in products" :key="product.id"><FruitSprite :fruit="product.id" /><FruitSprite :fruit="product.id" /><FruitSprite :fruit="product.id" /></div></div>
          <div class="world-footer"><span><UIcon name="i-lucide-sprout" />{{ state.upgrades === 0 ? '街角的水果小店' : state.upgrades === 1 ? '开满鲜花的水果小店' : '有冰箱的精品水果店' }}</span><span>{{ state.lifetimeServed }} 位顾客光顾过</span></div>
        </section>

        <section class="checkout" aria-label="接待顾客">
          <template v-if="state.stage !== 'closed'">
            <div class="checkout-heading"><span class="receipt-icon"><UIcon name="i-lucide-receipt-text" /></span><div><span class="game-eyebrow">第 {{ state.customer + 1 }} 位顾客</span><h2>{{ visitor.name }}的购物单</h2></div><span class="order-number">NO. {{ String((state.day - 1) * 4 + state.customer + 1).padStart(3, '0') }}</span></div>
            <div class="order-list"><div v-for="product in orderItems" :key="product.id" class="order-row"><FruitSprite :fruit="product.id" /><strong>{{ product.name }}</strong><span>¥ {{ product.price }} / 个</span><b>× {{ order[product.id] }}</b></div></div>
            <div class="step-track" aria-label="订单步骤"><span v-for="(step, index) in steps" :key="step" :class="{ active: phase === index, complete: phase > index }"><i><UIcon v-if="phase > index" name="i-lucide-check" /><template v-else>{{ index + 1 }}</template></i>{{ step }}</span></div>
            <div class="task-area">
              <h3>{{ goalTitle }}</h3>
              <template v-if="state.stage === 'packing'">
                <div class="shopping-bag" :class="{ filled: products.some(p => state.bag[p.id]) }">
                  <div v-if="!products.some(p => state.bag[p.id])" class="empty-bag"><UIcon name="i-lucide-shopping-bag" /><span>购物袋还空着</span></div>
                  <div v-else class="bag-items"><div v-for="product in products.filter(p => state.bag[p.id])" :key="product.id" class="bag-item"><FruitSprite :fruit="product.id" /><strong>× {{ state.bag[product.id] }}</strong><button :aria-label="'从购物袋取出一个' + product.name" @click="unpack(product.id)"><UIcon name="i-lucide-minus" /></button></div></div>
                </div>
                <button class="primary-action" @click="checkBag"><UIcon name="i-lucide-check" />装好了，去结账<UIcon name="i-lucide-arrow-right" /></button>
              </template>
              <template v-else-if="state.stage === 'total'">
                <div class="cash-display"><span>水果总价</span><div><span>¥</span><output aria-label="输入的总价">{{ amount || '?' }}</output></div></div>
                <div class="number-pad" role="group" aria-label="总价数字键盘"><button v-for="n in ['1', '2', '3', '4', '5', '6', '7', '8', '9']" :key="n" :aria-label="'数字' + n" @click="digit(n)">{{ n }}</button><button aria-label="清空总价" @click="amount = ''; feedback = ''"><UIcon name="i-lucide-rotate-ccw" /></button><button aria-label="数字0" @click="digit('0')">0</button><button aria-label="删除上一位" @click="amount = amount.slice(0, -1); feedback = ''"><UIcon name="i-lucide-delete" /></button></div>
                <button class="primary-action" :disabled="!amount" @click="checkAmount"><UIcon name="i-lucide-check" />确认总价<UIcon name="i-lucide-arrow-right" /></button>
              </template>
              <template v-else-if="state.stage === 'change'">
                <div class="payment-info"><div><span>顾客付了</span><strong>¥ {{ given }}</strong></div><UIcon name="i-lucide-arrow-right" /><div><span>水果总价</span><strong>¥ {{ total }}</strong></div></div>
                <div class="change-tray"><span>找回的零钱</span><div class="change-coins"><span v-for="(coin, index) in coins" :key="index" class="small-coin">{{ coin }}</span><span v-if="!coins.length" class="tray-empty">¥ 0</span></div><strong aria-label="找回的零钱金额">¥ {{ change }}</strong><button aria-label="取回最后一枚零钱" :disabled="!coins.length" @click="coins.pop(); feedback = ''"><UIcon name="i-lucide-undo-2" /></button></div>
                <div class="coin-pad" role="group" aria-label="零钱"><button v-for="coin in [1, 2, 5, 10]" :key="coin" :aria-label="'放入' + coin + '元'" @click="addCoin(coin)"><span :class="['coin', { note: coin === 10 }]">{{ coin }}<small>元</small></span></button></div>
                <button class="primary-action" @click="checkAmount"><UIcon name="i-lucide-hand-coins" />找好了，交给顾客<UIcon name="i-lucide-arrow-right" /></button>
              </template>
              <template v-else-if="state.stage === 'served'">
                <div class="sale-success"><span class="success-mark"><UIcon name="i-lucide-party-popper" /></span><p>{{ state.difficulty === 'count' ? '水果种类和数量都装对了！' : '水果和钱都算对了！' }}</p><div><span>收入 <strong>¥ {{ total }}</strong></span><span>赚到 <strong>¥ {{ orderItems.reduce((sum, p) => sum + order[p.id] * (p.price - p.cost), 0) }}</strong></span></div></div>
                <button class="primary-action" @click="advance">{{ state.customer === 3 ? '结束营业，看看收获' : '接待下一位顾客' }}<UIcon name="i-lucide-arrow-right" /></button>
              </template>
              <p v-if="feedback" class="task-feedback" role="status" aria-label="订单反馈"><UIcon name="i-lucide-message-circle" />{{ feedback }}</p>
              <div v-if="hint" class="task-hint" role="status"><template v-if="state.stage === 'packing'">购物单上要：{{ orderItems.map(p => `${p.name} ${order[p.id]} 个`).join('、') }}。多装的水果可以取出来。</template><template v-else-if="state.stage === 'total'">{{ equation }} = {{ total }} 元。先算每种水果的钱，再加在一起。</template><template v-else>顾客付的 {{ given }} 元 − 总价 {{ total }} 元 = {{ given - total }} 元零钱。</template></div>
              <button v-if="!['served', 'closed'].includes(state.stage)" class="hint-button" :aria-expanded="hint" @click="showHint"><UIcon name="i-lucide-lightbulb" />{{ hint ? '收起提示' : '给我一点提示' }}</button>
            </div>
          </template>
          <template v-else>
            <div class="day-summary"><span class="summary-award"><UIcon name="i-lucide-trophy" /></span><span class="game-eyebrow">第 {{ state.day }} 天 · 营业结束</span><h2>今天也是好店长！</h2><div class="summary-stars" aria-label="今日完成四位顾客"><UIcon v-for="n in 4" :key="n" name="i-lucide-star" /></div><div class="summary-stats"><div><span>营业收入</span><strong>¥ {{ state.revenue }}</strong></div><div><span>今日赚到</span><strong>¥ {{ state.profit }}</strong></div><div><span>接待顾客</span><strong>4 <small>位</small></strong></div></div><p>{{ state.mistakes === 0 && state.hints === 0 ? '今天独立完成了所有订单，太棒了！' : `今天尝试调整了 ${state.mistakes} 次，看了 ${state.hints} 次提示，继续进步！` }}</p></div>
            <div v-if="state.upgrades < 2" class="upgrade-offer"><span class="upgrade-art"><UIcon :name="state.upgrades === 0 ? 'i-lucide-flower-2' : 'i-lucide-refrigerator'" /></span><div><strong>{{ state.upgrades === 0 ? '给小店添一盆花' : '添置一台小冰箱' }}</strong><span>货架容量 +2 · ¥ 12</span></div><button :disabled="state.cash < 12" @click="upgradeShop(state); playTone(true)">{{ state.cash >= 12 ? '升级' : '继续攒钱' }}<UIcon name="i-lucide-arrow-up" /></button></div>
            <div v-else class="upgrade-complete"><UIcon name="i-lucide-badge-check" />小店已经焕然一新！</div>
            <button class="primary-action" @click="tomorrow">开始第 {{ state.day + 1 }} 天<UIcon name="i-lucide-sun" /></button>
          </template>
        </section>
      </div>

      <section class="shelf" aria-label="水果货架">
        <div class="shelf-heading"><div><UIcon name="i-lucide-package-open" /><h2>新鲜水果架</h2></div><span>今日收入 <strong>¥ {{ state.revenue }}</strong></span></div>
        <div class="product-grid"><button v-for="product in products" :key="product.id" class="product" :style="{ '--fruit-color': product.color }" :aria-label="'装入一个' + product.name" :disabled="state.stage !== 'packing' || state.bag[product.id] >= state.stock[product.id]" @click="pick(product.id)"><span class="product-art"><FruitSprite :fruit="product.id" /></span><span class="product-copy"><strong>{{ product.name }}</strong><span>剩余 {{ state.stock[product.id] - (state.stage === 'served' || state.stage === 'closed' ? 0 : state.bag[product.id]) }} 个</span></span><span class="product-price">¥ {{ product.price }}<small> / 个</small></span><span class="product-add"><UIcon name="i-lucide-plus" /></span></button></div>
      </section>
      <footer class="game-footer"><span><UIcon name="i-lucide-heart" />每一次尝试，都是成长</span><span v-if="saveError" role="status">本机暂时无法保存进度</span><span v-else><UIcon name="i-lucide-cloud-check" />进度已保存在本机</span></footer>
    </main>

    <UModal :open="paused" title="小店休息一下" description="回来后继续接待顾客。" :ui="{ content: 'game-modal' }" @update:open="paused = $event"><template #body><div class="modal-illustration"><UIcon name="i-lucide-coffee" /></div><button class="primary-action" @click="paused = false">继续营业<UIcon name="i-lucide-play" /></button></template></UModal>
    <UModal :open="settings" title="游戏设置" :ui="{ content: 'game-modal' }" @update:open="settings = $event"><template #body><div class="setting-row"><div><strong>游戏音效</strong><span>{{ sound ? '已开启' : '已关闭' }}</span></div><USwitch v-model="sound" aria-label="游戏音效" /></div><div class="setting-row"><div><strong>当前难度</strong><span>{{ difficulties.find(d => d.id === state.difficulty)?.name }}</span></div><UIcon name="i-lucide-gamepad-2" /></div><button class="reset-button" @click="settings = false; resetDifficulty = state.difficulty"><UIcon name="i-lucide-rotate-ccw" />重新开始</button></template></UModal>
    <UModal :open="resetDifficulty !== null" :title="resetDifficulty === state.difficulty ? '重新开一家小店？' : '切换游戏难度？'" description="小店将从第 1 天开始，当前营业进度和徽章会清空。" :ui="{ content: 'game-modal' }" @update:open="!$event && (resetDifficulty = null)"><template #body><div class="modal-actions"><button class="secondary-action" @click="resetDifficulty = null">继续当前游戏</button><button class="primary-action" @click="restart">{{ resetDifficulty === state.difficulty ? '重新开始' : '切换并开始' }}<UIcon name="i-lucide-arrow-right" /></button></div></template></UModal>
    <UModal :open="collection" title="我的店长徽章" :close="{ 'aria-label': '关闭徽章' }" :ui="{ content: 'game-modal' }" @update:open="collection = $event"><template #body><div class="badge-list"><div v-for="badge in badges" :key="badge.name" :class="{ earned: badge.earned }"><span><UIcon :name="badge.icon" /></span><div><strong>{{ badge.name }}</strong><p>{{ badge.goal }}</p></div><UIcon :name="badge.earned ? 'i-lucide-badge-check' : 'i-lucide-lock-keyhole'" /></div></div></template></UModal>
  </div>
</template>

<style scoped>
.game-module { --game-ink: #344c4b; --game-muted: #84928f; --game-green: #4b8772; --game-border: #e3eae4; min-height: 100dvh; background: #f7faf7; color: var(--game-ink); font-family: var(--font-ui); letter-spacing: 0; }
.game-embedded { flex: 1; min-height: 0; overflow: auto; }
.game-module button, .game-module a { -webkit-tap-highlight-color: transparent; }
.game-module button { cursor: pointer; transition: background .16s, transform .16s, box-shadow .16s; }
.game-module button:disabled { cursor: default; }
.game-module button:focus-visible, .game-module a:focus-visible { outline: 3px solid #679cc2; outline-offset: 3px; }
.game-topbar { min-height: 68px; display: flex; align-items: center; padding: 12px 40px; gap: 64px; border-bottom: 1px solid var(--game-border); background: #fff; }
.module-brand { display: flex; align-items: center; gap: 10px; font-size: 17px; font-weight: 700; text-decoration: none; color: var(--game-ink); }
.module-logo { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 8px; background: #e5f0e9; color: var(--game-green); }
.module-logo > span { width: 23px; height: 23px; }
.game-current { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: var(--game-green); }
.game-current > span { width: 17px; height: 17px; }
.back-workspace { margin-left: auto; display: flex; align-items: center; gap: 7px; font-size: 12px; color: #778985; text-decoration: none; }
.back-workspace > span:first-child { width: 15px; height: 15px; }
.game-content { max-width: 1240px; margin: auto; padding: 30px 36px 16px; }
.shop-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 24px; }
.game-eyebrow { display: block; color: var(--game-muted); font-size: 11px; line-height: 1.5; }
.shop-title h1 { font-size: 32px; font-weight: 750; line-height: 1.4; margin: 3px 0 0; }
.title-dot { color: #e39182; margin-left: 3px; }
.shop-toolbar { display: flex; align-items: center; gap: 9px; }
.difficulty-switch { display: flex; align-items: center; gap: 3px; background: #eaf0eb; padding: 4px; border-radius: 8px; margin-right: 10px; }
.difficulty-switch button { height: 35px; padding: 0 15px; background: transparent; border-radius: 5px; color: #8b9690; font-size: 12px; white-space: nowrap; }
.difficulty-switch button.selected { color: var(--game-green); background: #fff; box-shadow: 0 1px 4px #344c4b12; font-weight: 650; }
.round-tool { width: 36px; height: 36px; display: grid; place-items: center; color: #7f9189; background: transparent; border-radius: 6px; }
.round-tool:hover { background: #eaf0eb; }
.round-tool > span { width: 18px; height: 18px; }
.shop-status { display: flex; align-items: center; gap: 36px; padding: 17px 0; border-top: 1px solid var(--game-border); border-bottom: 1px solid var(--game-border); margin-bottom: 24px; }
.day-label { display: flex; align-items: center; gap: 11px; }
.sun-icon { width: 38px; height: 38px; display: grid; place-items: center; background: #fcf0cf; color: #d4a551; border-radius: 50%; }
.sun-icon > span { width: 22px; height: 22px; }
.day-label > div { display: flex; flex-direction: column; gap: 3px; }
.day-label strong { font-size: 14px; font-weight: 650; }
.day-label div > span { font-size: 10px; color: var(--game-muted); }
.daily-goal { display: flex; align-items: center; gap: 12px; border-left: 1px solid var(--game-border); padding-left: 32px; }
.daily-goal > span, .money-stat > span, .collection-button > span { color: var(--game-muted); font-size: 12px; }
.customer-progress { display: flex; gap: 5px; }
.customer-progress > span { width: 27px; height: 27px; border-radius: 50%; display: grid; place-items: center; background: #e9eee8; color: #b3beb3; }
.customer-progress > span.current { color: #668a76; outline: 1px solid #a6bdac; background: #f6faf5; }
.customer-progress > span.done { color: #fff; background: #8bb19b; }
.customer-progress > span > span { width: 13px; height: 13px; }
.daily-goal > strong { font-size: 13px; font-variant-numeric: tabular-nums; }
.daily-goal small { color: #9aa79e; font-size: 11px; font-weight: 400; }
.money-stat { display: flex; align-items: center; gap: 9px; margin-left: auto; }
.money-stat > span:first-child { color: #94a691; width: 18px; height: 18px; }
.money-stat strong { font-size: 18px; color: var(--game-green); }
.collection-button { display: flex; align-items: center; gap: 7px; background: transparent; }
.collection-button > span:first-child { color: #c7a05b; width: 18px; height: 18px; }
.collection-button strong { font-size: 11px; background: #f1ead8; color: #b49b6b; padding: 3px 5px; border-radius: 4px; font-weight: 500; }
.play-layout { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(340px, 1fr); gap: 28px; align-items: start; }
.store-world { position: relative; overflow: hidden; aspect-ratio: 800 / 590; background: #e9f5f8; border-radius: 8px; }
.world-label { position: absolute; top: 19px; left: 21px; display: flex; align-items: center; gap: 7px; color: #638c80; font-size: 10px; background: #ffffffb8; padding: 7px 10px; border-radius: 5px; z-index: 1; }
.open-dot { width: 5px; height: 5px; border-radius: 50%; background: #6ea588; }
.open-dot.closed { background: #a7b3b0; }
.world-level { border-left: 1px solid #dae7de; padding-left: 8px; color: #96a49a; margin-left: 3px; }
.world-speech { position: absolute; right: 22px; top: 35%; background: #fff; padding: 12px 14px; border-radius: 8px; z-index: 1; box-shadow: 0 3px 10px #6b9b8e0b; max-width: 38%; }
.world-speech::after { content: ''; position: absolute; bottom: -6px; right: 26px; width: 13px; height: 13px; background: #fff; transform: rotate(45deg); }
.world-speech > span { font-size: 10px; color: #a6b1a7; }
.world-speech p { font-size: 11px; margin: 3px 0 0; line-height: 1.6; }
.world-footer { position: absolute; left: 0; bottom: 0; width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 11px 20px; color: #839589; font-size: 10px; background: #ffffff69; }
.world-footer > span:first-child { display: flex; align-items: center; gap: 6px; }
.world-footer span > span { width: 13px; height: 13px; }
.scene-fruits { position: absolute; left: 23.5%; right: 27%; top: 62%; height: 8%; display: flex; gap: 5%; }
.scene-fruits > div { flex: 1; min-width: 0; position: relative; background: #d6b48b; border-radius: 0 0 3px 3px; border-bottom: 4px solid #bb9c78; }
.scene-fruits svg { position: absolute; bottom: 4px; width: 65%; height: auto; }
.scene-fruits svg:nth-child(1) { left: 0; }
.scene-fruits svg:nth-child(2) { right: 0; }
.scene-fruits svg:nth-child(3) { left: 17%; bottom: 13px; }
.checkout { background: #fff; border: 1px solid var(--game-border); border-radius: 8px; padding: 23px 24px 17px; min-width: 0; min-height: 486px; }
.checkout-heading { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.receipt-icon { display: grid; place-items: center; background: #eff4ec; width: 37px; height: 37px; color: #8ba080; border-radius: 8px; }
.receipt-icon > span { width: 21px; height: 21px; }
.checkout h2 { font-size: 17px; font-weight: 700; line-height: 1.5; margin: 1px 0 0; }
.checkout .game-eyebrow { font-size: 10px; }
.order-number { margin-left: auto; color: #b2beb3; font-size: 9px; font-family: monospace; }
.order-list { padding: 7px 0 13px; border-bottom: 1px dashed #dce4d9; }
.order-row { display: flex; align-items: center; gap: 10px; min-height: 38px; }
.order-row svg { width: 32px; height: 32px; flex: none; }
.order-row > strong { font-size: 12px; font-weight: 600; }
.order-row > span { font-size: 10px; color: #a0aa9e; margin-left: auto; }
.order-row > b { font-size: 12px; font-weight: 600; min-width: 36px; text-align: right; }
.step-track { display: flex; justify-content: space-between; margin: 16px 0 19px; gap: 6px; }
.step-track > span { display: flex; align-items: center; gap: 5px; font-size: 10px; color: #b3bdb2; white-space: nowrap; }
.step-track i { width: 17px; height: 17px; border: 1px solid #e0e6dc; border-radius: 50%; display: grid; place-items: center; font-style: normal; font-size: 9px; }
.step-track i > span { width: 11px; height: 11px; }
.step-track > span.active { color: var(--game-green); font-weight: 650; }
.step-track > span.active i { background: var(--game-green); color: #fff; border-color: var(--game-green); }
.step-track > span.complete { color: #749981; }
.step-track > span.complete i { background: #e7f0e7; border-color: #e7f0e7; }
.task-area h3 { font-size: 14px; line-height: 1.5; font-weight: 650; margin: 0 0 14px; }
.shopping-bag { min-height: 111px; display: flex; align-items: center; justify-content: center; border: 1px dashed #d7e1d2; border-radius: 6px; background: #fafcf7; padding: 9px; margin-bottom: 16px; }
.empty-bag { display: flex; flex-direction: column; align-items: center; gap: 10px; color: #a9b7a5; font-size: 11px; }
.empty-bag > span:first-child { width: 28px; height: 28px; }
.bag-items { width: 100%; display: flex; flex-wrap: wrap; justify-content: center; gap: 12px; }
.bag-item { display: flex; align-items: center; gap: 4px; }
.bag-item > svg { width: 38px; height: 46px; }
.bag-item strong { font-size: 12px; font-weight: 600; }
.bag-item button { width: 26px; height: 30px; display: grid; place-items: center; color: #839c85; margin-left: 2px; border-radius: 4px; }
.bag-item button:hover { background: #e6efe3; }
.bag-item button > span { width: 12px; height: 12px; }
.primary-action { width: 100%; min-height: 43px; display: flex; align-items: center; justify-content: center; gap: 8px; background: var(--game-green, #4b8772); color: white; border-radius: 6px; font-size: 12px; font-weight: 600; padding: 10px 14px; border: 1px solid transparent; }
.primary-action:hover { background: #3c765f; }
.primary-action:disabled { opacity: .45; }
.primary-action > span { width: 15px; height: 15px; flex: none; }
.primary-action > span:last-child:not(:first-child) { margin-left: auto; }
.primary-action > span:first-child:not(:last-child) { margin-right: auto; }
.hint-button { display: flex; align-items: center; gap: 5px; margin: 10px auto 0; color: #a5ae94; font-size: 10px; min-height: 30px; background: transparent; }
.hint-button > span { width: 13px; height: 13px; color: #c0ac73; }
.task-feedback, .task-hint { font-size: 11px; line-height: 1.8; padding: 9px 10px; margin: 10px 0 0; border-radius: 4px; overflow-wrap: anywhere; }
.task-feedback { display: flex; align-items: flex-start; gap: 6px; color: #b2815e; background: #fbf1e9; }
.task-feedback > span { width: 14px; height: 14px; flex: none; margin-top: 3px; }
.task-hint { color: #739074; background: #f0f6ed; }
.cash-display { display: flex; align-items: center; justify-content: space-between; min-height: 65px; background: #eef5ed; border: 1px solid #dfebdc; border-radius: 6px; padding: 8px 15px; }
.cash-display > span { font-size: 11px; color: #8c9e87; }
.cash-display > div { display: flex; gap: 7px; align-items: baseline; color: var(--game-green); }
.cash-display output { min-width: 40px; text-align: right; font-size: 28px; font-family: monospace; font-weight: 700; }
.number-pad { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 5px; margin: 10px 0; }
.number-pad button { display: grid; place-items: center; height: 33px; background: #f5f7f3; color: #627b66; border: 1px solid #eef1e9; border-radius: 4px; font-size: 15px; font-weight: 600; }
.number-pad button:hover { background: #e9f0e3; }
.number-pad button > span { width: 15px; height: 15px; }
.payment-info { display: flex; align-items: center; gap: 18px; padding: 10px 13px; background: #f7f9f3; border-radius: 6px; }
.payment-info div { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.payment-info div > span { font-size: 10px; color: #9da994; }
.payment-info strong { font-size: 19px; font-weight: 650; }
.payment-info > span { width: 15px; height: 15px; color: #bbcab5; }
.change-tray { display: flex; align-items: center; flex-wrap: wrap; gap: 5px; padding: 10px 0; min-height: 56px; border-bottom: 1px dashed #e3e9dd; }
.change-tray > span { font-size: 10px; color: #9ca991; }
.change-coins { flex: 1; display: flex; flex-wrap: wrap; gap: 3px; justify-content: center; padding: 0 5px; }
.small-coin { width: 19px; height: 19px; border-radius: 50%; background: #f5e7ba; border: 1px solid #dccc9a; display: grid; place-items: center; color: #a18848; font-size: 10px; }
.tray-empty { color: #c0c9b7; font-size: 14px; }
.change-tray > strong { color: #708b66; font-size: 15px; min-width: 31px; text-align: right; }
.change-tray button { display: grid; place-items: center; width: 25px; height: 28px; color: #9bad92; background: #f3f7ed; border-radius: 4px; }
.change-tray button:disabled { opacity: .3; }
.change-tray button > span { width: 13px; height: 13px; }
.coin-pad { display: flex; justify-content: space-around; gap: 9px; padding: 13px 0; }
.coin-pad button { height: 54px; flex: 1; display: grid; place-items: center; }
.coin { display: flex; align-items: baseline; justify-content: center; gap: 2px; width: 44px; height: 44px; padding-top: 9px; border-radius: 50%; background: #f8e8b8; border: 3px double #ddbf79; color: #b18c45; box-shadow: 0 3px 0 #e0c78e; font-size: 18px; font-weight: 650; }
.coin small { font-size: 8px; font-weight: 400; }
.coin.note { width: 57px; height: 33px; border-radius: 3px; border-color: #a3c5b7; background: #e6f0e6; color: #739e87; box-shadow: 0 3px 0 #c3d8c8; padding-top: 3px; }
.coin-pad button:hover .coin { transform: translateY(-2px); }
.sale-success { text-align: center; padding: 1px 0 16px; }
.success-mark { width: 56px; height: 56px; margin: 0 auto 10px; display: grid; place-items: center; border-radius: 50%; background: #f8edcd; color: #c4a35d; animation: celebrate .4s ease-out; }
.success-mark > span { width: 28px; height: 28px; }
.sale-success p { font-size: 12px; color: #89a07e; margin: 6px 0 15px; }
.sale-success > div { display: flex; justify-content: center; gap: 30px; color: #9aa68e; font-size: 11px; }
.sale-success strong { color: #66885e; font-size: 17px; margin-left: 5px; }
.day-summary { text-align: center; padding: 0 0 15px; }
.summary-award { display: grid; place-items: center; width: 64px; height: 64px; border-radius: 50%; color: #c9a456; background: #fbf1d5; margin: 2px auto 13px; }
.summary-award > span { width: 33px; height: 33px; }
.day-summary h2 { font-size: 21px; margin: 5px 0; }
.summary-stars { display: flex; justify-content: center; gap: 6px; color: #e0bd69; margin: 14px 0 23px; }
.summary-stars > span { width: 22px; height: 22px; }
.summary-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-top: 1px dashed #e3e9dd; border-bottom: 1px dashed #e3e9dd; padding: 15px 0; }
.summary-stats div { display: flex; flex-direction: column; gap: 8px; }
.summary-stats div + div { border-left: 1px solid #e8ede2; }
.summary-stats span { font-size: 10px; color: #9ba992; }
.summary-stats strong { font-size: 21px; color: #6b8a63; }
.summary-stats small { font-size: 11px; font-weight: 400; }
.day-summary > p { font-size: 10px; color: #9aa98f; line-height: 1.8; margin: 15px 0 0; }
.upgrade-offer { display: flex; align-items: center; gap: 10px; background: #f4f6ee; padding: 13px 11px; margin-bottom: 15px; border-radius: 6px; }
.upgrade-art { display: grid; place-items: center; width: 34px; height: 34px; background: #f7e6e0; color: #c99c8e; border-radius: 6px; flex: none; }
.upgrade-art > span { width: 22px; height: 22px; }
.upgrade-offer > div { display: flex; flex-direction: column; gap: 4px; }
.upgrade-offer strong { font-size: 11px; font-weight: 600; }
.upgrade-offer div > span { font-size: 9px; color: #9daa91; }
.upgrade-offer button { display: flex; align-items: center; gap: 4px; margin-left: auto; color: #7e9970; font-size: 11px; flex: none; min-height: 34px; }
.upgrade-offer button:disabled { color: #b7c0ab; }
.upgrade-offer button > span { width: 12px; height: 12px; }
.upgrade-complete { display: flex; align-items: center; justify-content: center; gap: 7px; color: #829b72; font-size: 12px; margin: 15px 0 20px; }
.upgrade-complete > span { width: 18px; height: 18px; }
.shelf { margin-top: 24px; }
.shelf-heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 12px; }
.shelf-heading > div { display: flex; align-items: center; gap: 7px; }
.shelf-heading > div > span { width: 17px; height: 17px; color: #8b9c83; }
.shelf-heading h2 { font-size: 13px; font-weight: 650; }
.shelf-heading > span { color: #9ca992; font-size: 10px; }
.shelf-heading strong { color: #7c9472; font-weight: 600; margin-left: 5px; }
.product-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.product { min-height: 91px; position: relative; display: flex; align-items: center; gap: 9px; background: #fff; border: 1px solid var(--game-border); border-radius: 8px; padding: 12px 13px; text-align: left; }
.product:hover:not(:disabled) { border-color: #adc9b7; box-shadow: 0 4px 13px #6486740b; transform: translateY(-2px); }
.product:disabled { background: #f7faf5; }
.product-art { width: 51px; height: 54px; flex: none; }
.product-art svg { width: 100%; height: 100%; }
.product-copy { display: flex; flex-direction: column; gap: 7px; }
.product-copy strong { font-size: 13px; font-weight: 600; }
.product-copy > span { color: #a0ad97; font-size: 9px; }
.product-price { margin-left: auto; font-size: 16px; font-weight: 650; color: #6a8a5f; padding-bottom: 23px; white-space: nowrap; }
.product-price small { font-size: 9px; color: #adbaa3; font-weight: 400; }
.product-add { position: absolute; right: 14px; bottom: 13px; display: grid; place-items: center; width: 21px; height: 21px; border-radius: 50%; color: #8fa683; background: #edf4e9; }
.product-add > span { width: 13px; height: 13px; }
.product:disabled .product-add { color: #c2cbbb; background: #eff3ea; }
.game-footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-top: 21px; color: #aab5a5; font-size: 10px; padding-bottom: 4px; }
.game-footer > span { display: flex; align-items: center; gap: 5px; }
.game-footer > span > span { width: 12px; height: 12px; }
.setting-row { display: flex; justify-content: space-between; align-items: center; gap: 20px; padding: 13px 0; border-bottom: 1px solid #e7ede5; }
.setting-row > div { display: flex; flex-direction: column; gap: 5px; }
.setting-row strong { font-size: 13px; }
.setting-row div > span { font-size: 11px; color: #9cac95; }
.reset-button { display: flex; align-items: center; justify-content: center; gap: 7px; padding: 13px; width: 100%; border: 1px solid #e3e9df; border-radius: 6px; margin-top: 20px; font-size: 12px; color: #9e8074; }
.reset-button > span { width: 14px; height: 14px; }
.modal-illustration { display: grid; place-items: center; margin: 0 auto 24px; width: 75px; height: 75px; background: #edf4e9; color: #819f78; border-radius: 50%; }
.modal-illustration > span { width: 35px; height: 35px; }
.modal-actions { display: flex; gap: 12px; }
.modal-actions > button { flex: 1; }
.secondary-action { border: 1px solid #e2e8dc; border-radius: 6px; font-size: 12px; color: #8b9e81; padding: 10px; }
.badge-list > div { display: flex; align-items: center; gap: 15px; padding: 15px 0; color: #b9c1b4; }
.badge-list > div + div { border-top: 1px solid #e7ede3; }
.badge-list > div > span { width: 43px; height: 43px; border-radius: 50%; display: grid; place-items: center; background: #f0f2ec; }
.badge-list > div > span > span { width: 23px; height: 23px; }
.badge-list strong { font-size: 13px; font-weight: 600; }
.badge-list p { font-size: 11px; margin: 5px 0 0; }
.badge-list > div > span:last-child { margin-left: auto; background: transparent; width: 20px; height: 20px; }
.badge-list > div.earned { color: #a7a06f; }
.badge-list > div.earned > span:first-child { background: #faf0d4; color: #c3a257; }
@keyframes celebrate { 0% { transform: scale(.7) rotate(-10deg); } 60% { transform: scale(1.1) rotate(5deg); } 100% { transform: scale(1) rotate(0); } }
@media (min-width: 1500px) { .game-content { padding-top: 40px; } }
@media (max-width: 1100px) { .game-content { padding: 25px 24px 15px; } .play-layout { gap: 20px; grid-template-columns: minmax(0, 1.4fr) minmax(310px, 1fr); } .checkout { padding: 20px; } .shop-status { gap: 20px; } .daily-goal { padding-left: 20px; } .product { padding: 10px; gap: 5px; } .product-art { width: 43px; } .product-price { font-size: 14px; } .product-price small { display: none; } .world-speech { right: 15px; max-width: 40%; padding: 9px 11px; } }
@media (max-width: 800px) { .game-topbar { padding: 12px 22px; gap: 30px; } .play-layout { grid-template-columns: minmax(0, 1fr); gap: 18px; } .store-world { aspect-ratio: 800 / 455; } .store-world :deep(.shop-art) { height: auto; position: absolute; bottom: -10%; } .scene-fruits { top: 61%; height: 10%; } .world-speech { top: 28%; right: 6%; max-width: 31%; } .checkout { min-height: 0; padding: 20px 24px; } .checkout-heading { margin-bottom: 7px; } .task-area { max-width: 460px; margin: auto; } .order-list { display: flex; flex-wrap: wrap; gap: 5px 20px; } .order-row { flex: 1; min-width: 180px; } .step-track { justify-content: center; gap: 24px; } .number-pad button { height: 44px; } .product-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; } .product { min-height: 84px; gap: 10px; padding: 10px 16px; } .product-art { width: 52px; } .product-price { font-size: 18px; } .product-price small { display: inline; } .shop-status { flex-wrap: wrap; gap: 18px; } .collection-button { margin-left: auto; } .money-stat { margin-left: 0; } .daily-goal { margin-left: auto; border: 0; padding: 0; } .round-tool { width: 36px; height: 40px; } }
@media (max-width: 540px) { .game-content { padding: 22px 16px 12px; } .game-topbar { min-height: 58px; padding: 10px 16px; gap: 18px; } .module-brand { font-size: 14px; gap: 7px; } .module-logo { width: 30px; height: 30px; } .game-current { font-size: 11px; gap: 5px; } .back-workspace { gap: 3px; font-size: 10px; } .shop-heading { flex-wrap: wrap; gap: 12px; margin-bottom: 18px; } .shop-title { width: 100%; } .shop-title h1 { font-size: 28px; } .shop-toolbar { width: 100%; gap: 6px; } .difficulty-switch { margin-right: auto; padding: 3px; } .difficulty-switch button { padding: 0 13px; min-height: 38px; } .round-tool { width: 32px; height: 40px; } .shop-status { padding: 13px 0; margin-bottom: 18px; gap: 15px 10px; } .sun-icon { width: 32px; height: 32px; } .day-label { gap: 7px; } .day-label strong { font-size: 12px; } .day-label div > span { font-size: 9px; } .daily-goal { gap: 7px; } .daily-goal > span { font-size: 10px; } .customer-progress { gap: 3px; } .customer-progress > span { width: 23px; height: 23px; } .money-stat { flex: 1; } .money-stat strong { font-size: 16px; } .collection-button > span, .money-stat > span { font-size: 10px; } .store-world { aspect-ratio: 800 / 555; } .store-world :deep(.shop-art) { bottom: -2%; } .scene-fruits { top: 64%; height: 8%; } .world-label { top: 12px; left: 12px; font-size: 9px; padding: 6px 8px; } .world-speech { top: 32%; right: 4%; max-width: 39%; padding: 7px 9px; } .world-speech p { font-size: 9px; } .world-footer { padding: 9px 12px; font-size: 8px; } .checkout { padding: 20px 17px 13px; } .checkout h2 { font-size: 16px; } .order-number { font-size: 9px; } .order-list { gap: 0; display: block; } .order-row { min-height: 39px; } .order-row > span { font-size: 11px; } .order-row > strong { font-size: 13px; } .step-track { gap: 10px; justify-content: space-between; } .step-track > span { font-size: 10px; } .shopping-bag { min-height: 100px; } .bag-items { gap: 10px; } .bag-item svg { width: 33px; } .bag-item button { width: 30px; height: 40px; } .primary-action { min-height: 47px; font-size: 12px; } .hint-button { min-height: 36px; font-size: 11px; } .product { min-height: 88px; padding: 9px 10px; gap: 7px; } .product-art { width: 39px; height: 48px; } .product-copy strong { font-size: 12px; } .product-price { font-size: 15px; } .product-price small { display: none; } .product-add { width: 22px; height: 22px; right: 10px; bottom: 12px; } .game-footer { gap: 7px; font-size: 8px; } .game-footer > span > span { width: 10px; height: 10px; } .shelf { margin-top: 20px; } }
@media (max-width: 360px) { .game-current { display: none; } .difficulty-switch button { padding: 0 9px; } .shop-toolbar { gap: 3px; } .round-tool { width: 29px; } .daily-goal > span { display: none; } .product-art { width: 31px; } .product { gap: 4px; } .step-track > span { font-size: 9px; } }
@media (max-width: 800px) {
  .game-content { display: flex; flex-direction: column; }
  .shop-heading { order: 0; }
  .shop-status { order: 1; display: grid; grid-template-columns: minmax(0, 1fr) auto; }
  .daily-goal { margin-left: 0; justify-self: end; }
  .money-stat { margin-left: 0; }
  .money-stat > span, .money-stat strong { white-space: nowrap; }
  .collection-button { justify-self: end; }
  .play-layout { display: contents; }
  .store-world { order: 2; }
  .shelf { order: 3; margin: 18px 0; }
  .checkout { order: 4; }
  .game-footer { order: 5; }
}
@media (prefers-reduced-motion: reduce) { .game-module button { transition: none; } .success-mark { animation: none; } }
</style>
