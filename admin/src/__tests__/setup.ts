import { beforeEach } from 'vitest'
import { setAdminIdentity } from '../permissions'

// 原有功能用例使用全权限测试账号；权限用例显式切换为受限账号。
beforeEach(() => setAdminIdentity({ id: 1, username: 'test-admin', role: 'admin', is_super_admin: true }))
