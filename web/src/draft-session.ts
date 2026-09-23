import { randomId } from '../../shared/webcrypto'

export interface DraftSession { previous: string | null; current: string; release?: () => void }
export const draftLockName = (owner: string, id: string) => 'lc-draft:' + owner + ':' + id

/** 刷新复用已关闭页面的草稿；复制标签页必须获得独立写入身份。 */
export async function claimDraftSession(owner: string, session: DraftSession): Promise<DraftSession> {
  if (!navigator.locks) return session
  const take = (id: string) => new Promise<DraftSession | null>((resolve, reject) => {
    let release!: () => void
    const lifetime = new Promise<void>(done => { release = done })
    void navigator.locks.request(draftLockName(owner, id), { ifAvailable: true }, lock => {
      if (!lock) { resolve(null); return }
      resolve({ ...session, current: id, release })
      return lifetime
    }).catch(reject)
  })
  let claimed = session.previous ? await take(session.previous) : null
  claimed ||= await take(session.current)
  while (!claimed) claimed = await take(randomId())
  try { sessionStorage.setItem('lc_draft_session:' + owner, claimed.current) } catch { /* 仍保持独立写入锁。 */ }
  return claimed
}
