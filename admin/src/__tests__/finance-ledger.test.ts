import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import FinanceLedger from '../components/FinanceLedger.vue'
import * as ledger from '../finance-ledger'
import { setAdminIdentity } from '../permissions'
import { uiStubs } from '../../../shared/test/ui-stubs'
import { canLeaveAdmin } from '../navigation'

afterEach(() => { vi.restoreAllMocks(); setAdminIdentity(null) })
it('保存期间锁定全部账本字段并阻止离开，完成后解锁', async () => {
  vi.spyOn(ledger, 'financeLedger').mockResolvedValue({ items: [], total: 0, page: 1, page_size: 30, summary: { income_fen: 0, expense_fen: 0, net_fen: 0, tax_fen: 0 } })
  let complete!: (value: ledger.FinanceLedgerEntry) => void
  const create = vi.spyOn(ledger, 'createFinanceLedger').mockImplementation(() => new Promise(resolve => { complete = resolve }))
  const wrapper = mount(FinanceLedger, { global: { stubs: uiStubs } })
  const button = (label: string) => wrapper.findAll('button').find(value => value.text() === label)!
  try {
    await flushPromises(); await button('新增收支').trigger('click')
    await wrapper.find('input[placeholder="如会员收入、报销、服务费"]').setValue('服务费')
    await wrapper.findAll('input[inputmode="decimal"]')[0]!.setValue('12.34')
    await wrapper.findAll('form')[1]!.trigger('submit'); await flushPromises()
    const fields = wrapper.findAll('form')[1]!.findAll('input,select,textarea')
    expect(fields).toHaveLength(9)
    expect(fields.every(field => (field.element as HTMLInputElement).disabled)).toBe(true)
    expect(canLeaveAdmin()).toBe(false)
    await button('取消').trigger('click')
    expect(wrapper.findAll('form')).toHaveLength(2)
    await wrapper.findAll('form')[1]!.trigger('submit')
    expect(create).toHaveBeenCalledTimes(1)
    complete({} as ledger.FinanceLedgerEntry); await flushPromises()
    expect(wrapper.findAll('form')).toHaveLength(1)
    expect(canLeaveAdmin()).toBe(true)
    expect(create.mock.calls[0]![0].amount_fen).toBe(1234)
  } finally { wrapper.unmount() }
})

it('金额按分转换，拒绝负数、超额和多余小数', () => {
  expect(ledger.moneyFen('0.29')).toBe(29)
  expect(ledger.moneyFen('100.01')).toBe(10001)
  for (const input of ['-1', '1.001', 'Infinity', '1000000000', '']) expect(() => ledger.moneyFen(input)).toThrow()
})

it('保存失败保留草稿与幂等标识，成功后刷新账本', async () => {
  setAdminIdentity({ id: 1, username: 'admin', role: 'admin', is_super_admin: true })
  vi.spyOn(ledger, 'financeLedger').mockResolvedValue({ items: [], total: 0, page: 1, page_size: 30, summary: { income_fen: 0, expense_fen: 0, net_fen: 0, tax_fen: 0 } })
  const create = vi.spyOn(ledger, 'createFinanceLedger').mockRejectedValueOnce(new Error('网络中断')).mockResolvedValue({} as ledger.FinanceLedgerEntry)
  const wrapper = mount(FinanceLedger, { global: { stubs: uiStubs } })
  const button = (label: string) => wrapper.findAll('button').find(value => value.text() === label)!
  try {
    await flushPromises(); await button('新增收支').trigger('click')
    await wrapper.find('input[placeholder="如会员收入、报销、服务费"]').setValue('服务费')
    await wrapper.findAll('input[inputmode="decimal"]')[0]!.setValue('12.34')
    const form = () => wrapper.findAll('form')[1]!
    await form().trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('网络中断')
    expect((wrapper.findAll('input[inputmode="decimal"]')[0]!.element as HTMLInputElement).value).toBe('12.34')
    await form().trigger('submit'); await flushPromises()
    expect(create.mock.calls[1]![0].identifier).toBe(create.mock.calls[0]![0].identifier)
    expect(create.mock.calls[1]![0].amount_fen).toBe(1234)
    expect(wrapper.text()).toContain('账本记录已保存')
  } finally { wrapper.unmount() }
})
