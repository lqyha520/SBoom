import { contentDeck, seededRandom } from './challenge-journey'
export type ProductId = 'apple' | 'banana' | 'pear' | 'orange'
export type Difficulty = 'count' | 'total' | 'change'
export type Stage = 'packing' | 'total' | 'change' | 'served' | 'closed'
export type Basket = Record<ProductId, number>
export const products = [
  { id: 'apple' as const, name: '苹果', price: 3, cost: 1, color: '#ef6c70' },
  { id: 'banana' as const, name: '香蕉', price: 2, cost: 1, color: '#f4c94e' },
  { id: 'pear' as const, name: '梨子', price: 4, cost: 2, color: '#97bd67' },
  { id: 'orange' as const, name: '橙子', price: 5, cost: 2, color: '#f0a350' },
]
export const difficulties = [
  { id: 'count' as const, name: '数一数', age: '4-6 岁' },
  { id: 'total' as const, name: '算总价', age: '6-8 岁' },
  { id: 'change' as const, name: '找零钱', age: '7-10 岁' },
]
export const customers = [
  { name: '小米', color: '#739ecb', hair: '#424d54', message: '今天想带水果去野餐！' },
  { name: '乐乐', color: '#c08ab2', hair: '#675951', message: '我要给家人带点水果。' },
  { name: '朵朵', color: '#e69b7c', hair: '#424d54', message: '放学后来买点好吃的！' },
  { name: '安安', color: '#81b5a2', hair: '#675951', message: '这些水果看起来真新鲜！' },
]
const orderBook: Basket[] = [
  { apple: 2, banana: 1, pear: 0, orange: 0 },
  { apple: 0, banana: 2, pear: 1, orange: 0 },
  { apple: 1, banana: 0, pear: 0, orange: 1 },
  { apple: 0, banana: 0, pear: 2, orange: 1 },
  { apple: 1, banana: 2, pear: 0, orange: 1 },
  { apple: 2, banana: 0, pear: 1, orange: 0 },
  { apple: 0, banana: 1, pear: 1, orange: 2 },
  { apple: 1, banana: 1, pear: 1, orange: 1 },
]
export const emptyBasket = (): Basket => ({ apple: 0, banana: 0, pear: 0, orange: 0 })
export interface ShopState {
  version: 1
  difficulty: Difficulty
  day: number
  customer: number
  stage: Stage
  bag: Basket
  stock: Basket
  cash: number
  revenue: number
  profit: number
  mistakes: number
  hints: number
  upgrades: number
  orders?: Basket[]
  orderHistory?: string[]
  lifetimeServed: number
}
export function newShop(difficulty: Difficulty = 'change'): ShopState {
  return { version: 1, difficulty, day: 1, customer: 0, stage: 'packing', bag: emptyBasket(),
    stock: { apple: 8, banana: 8, pear: 8, orange: 8 }, cash: 0, revenue: 0, profit: 0,
    mistakes: 0, hints: 0, upgrades: 0, lifetimeServed: 0 }
}
export function currentOrder(state: ShopState): Basket {
  return state.orders?.[state.customer] ?? orderBook[((state.day - 1) * 4 + state.customer) % orderBook.length]
}
export function basketTotal(basket: Basket): number {
  return products.reduce((sum, product) => sum + product.price * basket[product.id], 0)
}
export function payment(state: ShopState): number {
  return Math.ceil(basketTotal(currentOrder(state)) / 10) * 10
}
export function addProduct(state: ShopState, id: ProductId): boolean {
  if (state.stage !== 'packing' || state.bag[id] >= state.stock[id]) return false
  state.bag[id]++
  return true
}
export function removeProduct(state: ShopState, id: ProductId): void {
  if (state.stage === 'packing' && state.bag[id] > 0) state.bag[id]--
}
function completeSale(state: ShopState): void {
  const order = currentOrder(state)
  const total = basketTotal(order)
  const profit = products.reduce((sum, p) => sum + order[p.id] * (p.price - p.cost), 0)
  for (const product of products) state.stock[product.id] -= order[product.id]
  state.cash += profit
  state.revenue += total
  state.profit += profit
  state.lifetimeServed++
  state.stage = 'served'
}
export function submitPacking(state: ShopState): boolean {
  if (state.stage !== 'packing') return false
  if (!products.every(p => state.bag[p.id] === currentOrder(state)[p.id])) {
    state.mistakes++
    return false
  }
  if (state.difficulty === 'count') completeSale(state)
  else state.stage = 'total'
  return true
}
export function submitAmount(state: ShopState, value: number): boolean {
  if (state.stage !== 'total' && state.stage !== 'change') return false
  const total = basketTotal(currentOrder(state))
  const expected = state.stage === 'total' ? total : payment(state) - total
  if (!Number.isSafeInteger(value) || value !== expected) { state.mistakes++; return false }
  if (state.stage === 'total' && state.difficulty === 'change') state.stage = 'change'
  else completeSale(state)
  return true
}
export function nextCustomer(state: ShopState): void {
  if (state.stage !== 'served') return
  if (state.customer === 3) { state.stage = 'closed'; return }
  state.customer++
  state.bag = emptyBasket()
  state.stage = 'packing'
}
export function nextDay(state: ShopState): void {
  if (state.stage !== 'closed') return
  state.day++
  state.customer = 0
  state.stage = 'packing'
  state.bag = emptyBasket()
  const pool: Basket[] = []
  const maxQuantity = Math.min(3, 1 + Math.floor(state.day / 3))
  const maxKinds = Math.min(4, 2 + Math.floor(state.day / 4))
  for (let a = 0; a <= maxQuantity; a++) for (let b = 0; b <= maxQuantity; b++)
    for (let c = 0; c <= maxQuantity; c++) for (let d = 0; d <= maxQuantity; d++) {
      const quantities = [a,b,c,d], kinds = quantities.filter(Boolean).length
      if (kinds < 2 || kinds > maxKinds || quantities.reduce((sum,n)=>sum+n,0) > 8) continue
      pool.push({apple:a,banana:b,pear:c,orange:d})
    }
  const key = (basket: Basket) => products.map(product=>basket[product.id]).join(',')
  const history = state.orderHistory || orderBook.slice(0,4).map(key)
  state.orders = contentDeck(pool,4,key,history,seededRandom(state.day*7919 + ['count','total','change'].indexOf(state.difficulty)*65537))
  const ids = state.orders.map(key)
  state.orderHistory = [...history.filter(id=>!ids.includes(id)),...ids].slice(-256)
  const stock = 8 + state.upgrades * 2
  state.stock = { apple: stock, banana: stock, pear: stock, orange: stock }
  for (const product of products) state.stock[product.id] = Math.max(stock,state.orders.reduce((sum,order)=>sum+order[product.id],0))
  state.revenue = 0
  state.profit = 0
  state.mistakes = 0
  state.hints = 0
}
export function upgradeShop(state: ShopState): boolean {
  if (state.stage !== 'closed' || state.upgrades >= 2 || state.cash < 12) return false
  state.cash -= 12
  state.upgrades++
  return true
}
export function restoreShop(raw: string | null): ShopState | null {
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as ShopState
    const nonnegative = (n: unknown) => Number.isSafeInteger(n) && Number(n) >= 0 && Number(n) <= 1_000_000
    if (value.version !== 1 || !difficulties.some(d => d.id === value.difficulty)
      || !['packing', 'total', 'change', 'served', 'closed'].includes(value.stage)
      || !['day', 'customer', 'cash', 'revenue', 'profit', 'mistakes', 'hints', 'upgrades', 'lifetimeServed'].every(k => nonnegative(value[k as keyof ShopState]))
      || value.day < 1 || value.customer > 3 || value.upgrades > 2
      || !products.every(p => nonnegative(value.bag?.[p.id]) && nonnegative(value.stock?.[p.id]) && value.stock[p.id] <= 12 && value.bag[p.id] <= 12)
      || (value.stage === 'closed' && value.customer !== 3)
      || (value.difficulty === 'count' && ['total', 'change'].includes(value.stage))
      || (value.difficulty === 'total' && value.stage === 'change')) return null
    if (value.orders !== undefined && (!Array.isArray(value.orders) || value.orders.length !== 4 || !value.orders.every(order=>products.every(p=>nonnegative(order?.[p.id]) && order[p.id] <= 3) && products.reduce((sum,p)=>sum+order[p.id],0) >= 1))) return null
    if (value.orderHistory !== undefined && (!Array.isArray(value.orderHistory) || value.orderHistory.length > 256 || !value.orderHistory.every(id=>typeof id === 'string' && /^[0-3](,[0-3]){3}$/.test(id)))) return null
    if (value.stage !== 'packing' && !products.every(p => value.bag[p.id] === currentOrder(value)[p.id])) return null
    if (['packing', 'total', 'change'].includes(value.stage) && !products.every(p => value.stock[p.id] >= currentOrder(value)[p.id] && value.bag[p.id] <= value.stock[p.id])) return null
    return value
  } catch { return null }
}
