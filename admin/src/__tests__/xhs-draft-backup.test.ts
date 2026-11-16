import { defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useXhsDraftBackup, type DraftBackupController } from '../xhs-draft-backup'
import { adminRoute, navigateAdmin, useAdminLeaveGuard } from '../navigation'
let wrapper: ReturnType<typeof mount> | undefined
let backup: DraftBackupController
const data = ref({ headline: '后台标题' }), dirty = ref(false), scope = ref('drafts:one'), revision = ref('1')
function start(adminId = 7) {
  wrapper = mount(defineComponent({ setup() {
    backup = useXhsDraftBackup({ adminId, scope: () => scope.value, enabled: () => true, dirty: () => dirty.value,
      snapshot: () => data.value, restore: value => { data.value = value; dirty.value = true }, revision: () => revision.value })
    useAdminLeaveGuard(() => !dirty.value || window.confirm('未保存'))
    return () => h('div')
  } }))
}
beforeEach(() => { window.confirm = vi.fn(() => true); localStorage.clear(); data.value = { headline: '后台标题' }; dirty.value = false; scope.value = 'drafts:one'; revision.value = '1'; vi.useFakeTimers() })
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.useRealTimers(); vi.unstubAllGlobals() })
it('刷新前立即备份并触发离开提示，重新打开后显式恢复，保存后清除', async () => {
  start(); data.value.headline = '未保存标题'; dirty.value = true; await nextTick()
  const event = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(event)
  expect(event.defaultPrevented).toBe(true)
  expect(JSON.parse(localStorage.getItem('lc-xhs-editor-v1:7:drafts:one')!).data.headline).toBe('未保存标题')
  wrapper!.unmount(); data.value = { headline: '后台标题' }; dirty.value = false; start()
  expect(data.value.headline).toBe('后台标题'); expect(backup.recovery.value).not.toBeNull()
  backup.restore(); expect(data.value.headline).toBe('未保存标题')
  dirty.value = false; backup.clear(); expect(localStorage.getItem('lc-xhs-editor-v1:7:drafts:one')).toBeNull()
})
it('记录和管理员相互隔离；服务器版本改变时禁止覆盖最新内容', async () => {
  start(); data.value.headline = '管理员七的编辑'; dirty.value = true; backup.persist(); wrapper!.unmount()
  dirty.value = false; data.value = { headline: '服务器新版' }; revision.value = '2'; start()
  expect(backup.stale.value).toBe(true); backup.restore(); expect(data.value.headline).toBe('服务器新版')
  wrapper!.unmount(); start(8); expect(backup.recovery.value).toBeNull()
  scope.value = 'drafts:two'; await nextTick(); expect(backup.recovery.value).toBeNull()
})
it('同模块切换记录也检查离开，取消时保留原记录', () => {
  start(); Object.assign(adminRoute, { tab: 'xhsDrafts', query: 'id=one' }); dirty.value = true
  vi.spyOn(window, 'confirm').mockReturnValue(false)
  navigateAdmin('xhsDrafts', { id: 'two' }); expect(adminRoute.query).toBe('id=one')
})
it('存储失败明确提示；后台原记录仍可继续编辑', () => {
  vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => { throw new Error('quota') }, removeItem: vi.fn() })
  start(); dirty.value = true; backup.persist(); expect(backup.storageError.value).toContain('请立即保存到后台')
  expect(data.value.headline).toBe('后台标题')
})
