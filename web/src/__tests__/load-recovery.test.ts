import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { recoverLoad, setRecoverySave } from '../../../shared/load-recovery'
beforeEach(() => { vi.stubGlobal('confirm', vi.fn()); vi.stubGlobal('alert', vi.fn()) })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); sessionStorage.clear(); setRecoverySave(async () => true) })
it('failed draft persistence blocks reload and explains how to recover', async () => {
  setRecoverySave(async () => false)
  const confirm = vi.spyOn(window, 'confirm'), alert = vi.spyOn(window, 'alert').mockImplementation(() => {})
  await recoverLoad()
  expect(confirm).not.toHaveBeenCalled()
  expect(alert).toHaveBeenCalledWith(expect.stringContaining('草稿尚未保存'))
})
it('concurrent failures prompt once and a previous refresh prevents a reload loop', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  setRecoverySave(async () => true)
  await Promise.all([recoverLoad(), recoverLoad()])
  expect(confirm).toHaveBeenCalledOnce()
  sessionStorage.setItem('lc-load-reloaded', location.href)
  const alert = vi.spyOn(window, 'alert').mockImplementation(() => {})
  await recoverLoad()
  expect(confirm).toHaveBeenCalledOnce()
  expect(alert).toHaveBeenCalledWith(expect.stringContaining('仍未加载成功'))
})
