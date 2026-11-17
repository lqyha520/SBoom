import { afterEach, expect, it } from 'vitest'
import { allowedAdminGroups, searchAdminNavigation } from '../admin-navigation'
import { parseAdminRoute } from '../navigation'
import { setAdminIdentity } from '../permissions'

afterEach(() => setAdminIdentity(null))

it('旧的生成审核书签回到有效页面，侧栏和搜索不再出现审核入口', () => {
  setAdminIdentity({ id: 1, username: 'admin', role: 'admin', is_super_admin: true })
  expect(parseAdminRoute('#generationReview').tab).toBe('overview')
  expect(allowedAdminGroups().flatMap(group => group.items).some(item => String(item.id) === 'generationReview')).toBe(false)
  expect(searchAdminNavigation('生成结果审核', true)).toEqual([])
})
