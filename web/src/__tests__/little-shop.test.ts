import { describe, expect, it } from 'vitest'
import {
  addProduct, basketTotal, currentOrder, newShop, nextCustomer, nextDay,
  payment, products, removeProduct, restoreShop, submitAmount, submitPacking, upgradeShop,
  type ShopState,
} from '../games/little-shop'

function pack(state: ShopState) {
  for (const product of products) {
    for (let n = 0; n < currentOrder(state)[product.id]; n++) addProduct(state, product.id)
  }
}
function serve(state: ShopState) {
  pack(state)
  expect(submitPacking(state)).toBe(true)
  if (state.stage === 'total') expect(submitAmount(state, basketTotal(currentOrder(state)))).toBe(true)
  if (state.stage === 'change') expect(submitAmount(state, payment(state) - basketTotal(currentOrder(state)))).toBe(true)
  expect(state.stage).toBe('served')
}

describe('小小店长', () => {
  it('数量错误不会扣库存、收钱或推进；多装的商品可以取出', () => {
    const state = newShop()
    pack(state); addProduct(state, 'orange')
    expect(submitPacking(state)).toBe(false)
    expect(state.mistakes).toBe(1)
    expect(state.cash).toBe(0)
    expect(state.stock.orange).toBe(8)
    removeProduct(state, 'orange')
    expect(submitPacking(state)).toBe(true)
    expect(state.stage).toBe('total')
    expect(addProduct(state, 'apple')).toBe(false)
  })

  it('总价和找零分别校验，销售仅结算一次', () => {
    const state = newShop()
    pack(state); submitPacking(state)
    expect(submitAmount(state, 9)).toBe(false)
    expect(submitAmount(state, 8)).toBe(true)
    expect(state.stage).toBe('change')
    expect(state.cash).toBe(0)
    expect(submitAmount(state, 1)).toBe(false)
    expect(submitAmount(state, 2)).toBe(true)
    expect(state.revenue).toBe(8)
    expect(state.profit).toBe(5)
    expect(state.stock.apple).toBe(6)
    expect(state.stock.banana).toBe(7)
    expect(submitAmount(state, 2)).toBe(false)
    expect(submitPacking(state)).toBe(false)
    expect(state.revenue).toBe(8)
    expect(state.lifetimeServed).toBe(1)
  })

  it.each(['count', 'total', 'change'] as const)('%s 模式完成四单、升级和次日补货', difficulty => {
    const state = newShop(difficulty)
    for (let n = 0; n < 4; n++) { serve(state); nextCustomer(state) }
    expect(state.stage).toBe('closed')
    expect(state.revenue).toBe(37)
    expect(state.profit).toBe(21)
    expect(upgradeShop(state)).toBe(true)
    expect(state.cash).toBe(9)
    expect(upgradeShop(state)).toBe(false)
    nextDay(state)
    expect(state.stage).toBe('packing')
    expect(state.day).toBe(2)
    expect(state.stock.apple).toBe(10)
    expect(state.revenue).toBe(0)
    expect(state.lifetimeServed).toBe(4)
    for (let n = 0; n < 4; n++) { serve(state); nextCustomer(state) }
    expect(upgradeShop(state)).toBe(true)
    expect(upgradeShop(state)).toBe(false)
    expect(state.upgrades).toBe(2)
  })

  it('限制库存；进度可在每一个阶段恢复，损坏数据会被忽略', () => {
    const state = newShop()
    for (let n = 0; n < 8; n++) expect(addProduct(state, 'apple')).toBe(true)
    expect(addProduct(state, 'apple')).toBe(false)
    expect(restoreShop(JSON.stringify(state))).toEqual(state)
    const clean = newShop()
    pack(clean)
    for (const move of [() => {}, () => submitPacking(clean), () => submitAmount(clean, 8), () => submitAmount(clean, 2), () => nextCustomer(clean)]) {
      move()
      expect(restoreShop(JSON.stringify(clean))).toEqual(clean)
    }
    expect(restoreShop('invalid')).toBeNull()
    expect(restoreShop(JSON.stringify({ ...state, cash: -1 }))).toBeNull()
    expect(restoreShop(JSON.stringify({ ...state, stock: { ...state.stock, apple: 999 } }))).toBeNull()
    expect(restoreShop(JSON.stringify({ ...state, stage: 'total' }))).toBeNull()
    expect(restoreShop(JSON.stringify({ ...state, stage: 'closed' }))).toBeNull()
  })
})
