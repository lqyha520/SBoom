"""续费状态和预计有效期由服务端统一计算。"""
import time


def renewal_state(membership: str, expires_at: int | None, now: int | None = None) -> dict:
    now = int(time.time()) if now is None else now
    state = 'regular'
    if membership == 'vip':
        state = 'lifetime' if expires_at is None else 'expired' if expires_at <= now else 'expiring' if expires_at <= now + 7 * 86400 else 'active'
    return {'status': state, 'expires_at': expires_at, 'renewal_due': state in ('expired', 'expiring'),
            'automatic_renewal': False, 'starts_at': max(now, expires_at or now) if state != 'lifetime' else None}
