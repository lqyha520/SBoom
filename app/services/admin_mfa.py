"""管理员 TOTP：加密密钥、一次性挑战、凭证绑定与重放保护。"""

import base64
import binascii
import hashlib
import hmac
import secrets
import time
from urllib.parse import quote

from fastapi import HTTPException

from app.db import db
from app.security import decrypt_secret, encrypt_secret


def migrate(conn) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS admin_mfa (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            secret_enc TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            last_used_step BIGINT NOT NULL DEFAULT 0,
            created_at BIGINT NOT NULL,
            updated_at BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS admin_mfa_challenges (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at BIGINT NOT NULL,
            created_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_admin_mfa_challenge_expiry ON admin_mfa_challenges(expires_at);
        ALTER TABLE admin_mfa_challenges ADD COLUMN IF NOT EXISTS credential_hash TEXT NOT NULL DEFAULT '';
        ALTER TABLE admin_mfa_challenges ADD COLUMN IF NOT EXISTS valid_after BIGINT NOT NULL DEFAULT 0;
        ALTER TABLE admin_mfa_challenges ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
    """)


def _code(secret: str, step: int) -> str:
    raw = base64.b32decode(secret + '=' * (-len(secret) % 8), casefold=True)
    digest = hmac.new(raw, int(step).to_bytes(8, 'big'), hashlib.sha1).digest()
    offset = digest[-1] & 0x0f
    value = int.from_bytes(digest[offset:offset + 4], 'big') & 0x7fffffff
    return f'{value % 1_000_000:06d}'


def verify_code(secret: str, code: str, now: int | None = None) -> int | None:
    if not secret or not isinstance(code, str) or not code.isascii() or not code.isdigit() or len(code) != 6:
        return None
    step = int((time.time() if now is None else now) // 30)
    try:
        for candidate in range(max(0, step - 1), step + 2):
            if hmac.compare_digest(_code(secret, candidate), code):
                return candidate
    except (ValueError, binascii.Error):
        return None
    return None


def enabled(user_id: int) -> bool:
    with db() as conn:
        return bool(conn.execute('SELECT 1 FROM admin_mfa WHERE user_id = ? AND enabled = 1', (user_id,)).fetchone())


def begin_setup(user_id: int, username: str) -> dict:
    secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')
    now = int(time.time())
    with db(serialized='accounts') as conn:
        current = conn.execute('SELECT enabled FROM admin_mfa WHERE user_id=? FOR UPDATE', (user_id,)).fetchone()
        if current and current['enabled']:
            raise HTTPException(409, detail={'error': 'MFA 已启用，请先用动态验证码关闭后再更换验证器'})
        conn.execute("INSERT INTO admin_mfa(user_id, secret_enc, enabled, created_at, updated_at) VALUES (?, ?, 0, ?, ?) "
                     "ON CONFLICT(user_id) DO UPDATE SET secret_enc=excluded.secret_enc, last_used_step=0, updated_at=excluded.updated_at",
                     (user_id, encrypt_secret(secret), now, now))
    return {'secret': secret, 'otpauth_url': f'otpauth://totp/{quote("LearnCoach:" + username, safe="")}?secret={secret}&issuer=LearnCoach&algorithm=SHA1&digits=6&period=30'}


def confirm(user_id: int, code: str, current_session: str = '') -> dict:
    now = int(time.time())
    with db(serialized='accounts') as conn:
        row = conn.execute('SELECT * FROM admin_mfa WHERE user_id = ? FOR UPDATE', (user_id,)).fetchone()
        if not row or row['enabled'] or now - row['updated_at'] > 600:
            raise HTTPException(409, detail={'error': '请重新初始化 MFA；已启用的密钥不能覆盖'})
        step = verify_code(decrypt_secret(row['secret_enc']), code, now)
        if step is None:
            raise HTTPException(400, detail={'error': '验证码无效或已过期'})
        conn.execute('UPDATE admin_mfa SET enabled=1, last_used_step=?, updated_at=? WHERE user_id=?', (step, now, user_id))
        conn.execute('UPDATE workspace_sessions SET revoked_at=? WHERE user_id=? AND id<>? AND revoked_at=0', (now, user_id, current_session))
        conn.execute('DELETE FROM admin_mfa_challenges WHERE user_id=?', (user_id,))
    return {'enabled': True}


def disable(user_id: int, code: str) -> dict:
    now = int(time.time())
    with db(serialized='accounts') as conn:
        row = conn.execute('SELECT * FROM admin_mfa WHERE user_id = ? FOR UPDATE', (user_id,)).fetchone()
        step = verify_code(decrypt_secret(row['secret_enc']), code, now) if row and row['enabled'] else None
        if step is None or step <= row['last_used_step']:
            raise HTTPException(400, detail={'error': '验证码无效或已使用，请等待下一个验证码'})
        conn.execute('DELETE FROM admin_mfa WHERE user_id=?', (user_id,))
        conn.execute('DELETE FROM admin_mfa_challenges WHERE user_id=?', (user_id,))
    return {'enabled': False}


def challenge(user_id: int, expected_hash: str, expected_after: int) -> str:
    token = 'mfa_' + secrets.token_urlsafe(32)
    now = int(time.time())
    with db(serialized='accounts') as conn:
        row = conn.execute('SELECT * FROM users WHERE id=? FOR UPDATE', (user_id,)).fetchone()
        if not row or not row['is_active'] or row['role'] != 'admin' or row['password_hash'] != expected_hash or row['token_valid_after'] != expected_after:
            raise HTTPException(401, detail={'error': '账号凭证已更新，请重新登录'})
        conn.execute('DELETE FROM admin_mfa_challenges WHERE expires_at < ? OR user_id=?', (now, user_id))
        conn.execute('INSERT INTO admin_mfa_challenges(token_hash, user_id, expires_at, created_at, credential_hash, valid_after) VALUES (?, ?, ?, ?, ?, ?)',
                     (hashlib.sha256(token.encode()).hexdigest(), user_id, now + 300, now, expected_hash, expected_after))
    return token


def consume(token: str, code: str) -> dict:
    now = int(time.time())
    verified = None
    with db(serialized='accounts') as conn:
        digest = hashlib.sha256(token.encode()).hexdigest()
        row = conn.execute('SELECT c.*, m.secret_enc, m.last_used_step, u.password_hash, u.token_valid_after, u.is_active, u.role '
                           'FROM admin_mfa_challenges c JOIN admin_mfa m ON m.user_id=c.user_id JOIN users u ON u.id=c.user_id '
                           'WHERE c.token_hash=? AND c.expires_at>? AND m.enabled=1 FOR UPDATE', (digest, now)).fetchone()
        if not row or row['attempts'] >= 5 or not row['is_active'] or row['role'] != 'admin' or row['credential_hash'] != row['password_hash'] or row['valid_after'] != row['token_valid_after']:
            raise HTTPException(401, detail={'error': 'MFA 验证请求已过期，请重新登录', 'code': 'mfa_challenge_expired'})
        step = verify_code(decrypt_secret(row['secret_enc']), code, now)
        if step is not None and step > row['last_used_step']:
            conn.execute('UPDATE admin_mfa SET last_used_step=?, updated_at=? WHERE user_id=?', (step, now, row['user_id']))
            conn.execute('DELETE FROM admin_mfa_challenges WHERE token_hash=?', (digest,))
            verified = {'user_id': row['user_id'], 'password_hash': row['credential_hash'], 'valid_after': row['valid_after']}
        else:
            # 先提交失败次数，再向客户端返回错误，避免事务回滚重置爆破计数。
            conn.execute('UPDATE admin_mfa_challenges SET attempts=attempts+1 WHERE token_hash=?', (digest,))
    if verified is None:
        raise HTTPException(401, detail={'error': '验证码无效或已使用', 'code': 'mfa_invalid'})
    return verified