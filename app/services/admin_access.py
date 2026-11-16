"""授权修改与审计同事务提交，权限在下一次请求立即生效。"""

import json

from fastapi import HTTPException

from app.admin_permissions import normalize, require
from app.db import db
from app.services.user_store import from_row


def get_permissions(user_id: int):
    with db() as conn:
        row = conn.execute("SELECT id,username,is_super_admin,admin_permissions,permissions_revision FROM users WHERE id=? AND role='admin'", (user_id,)).fetchone()
    if not row:
        raise HTTPException(404, detail={'error': '管理员账号不存在'})
    return dict(row)


def save_permissions(actor_id: int, user_id: int, revision: int, permissions: dict):
    permissions = normalize(permissions)
    with db(serialized='accounts') as conn:
        actor = conn.execute('SELECT * FROM users WHERE id=?', (actor_id,)).fetchone()
        if not actor:
            raise HTTPException(403, detail={'error': '账号权限已变化', 'code': 'permission_denied'})
        require(from_row(actor), 'adminAccounts', 'update')
        target = conn.execute("SELECT * FROM users WHERE id=? AND role='admin' FOR UPDATE", (user_id,)).fetchone()
        if not target:
            raise HTTPException(404, detail={'error': '管理员账号不存在'})
        if target['is_super_admin']:
            raise HTTPException(400, detail={'error': '超级管理员始终拥有全部权限，不需要单独分配'})
        if target['permissions_revision'] != revision:
            raise HTTPException(409, detail={'error': '权限已被其他页面修改，请重新加载后分配'})
        conn.execute('UPDATE users SET admin_permissions=?::jsonb,permissions_revision=permissions_revision+1 WHERE id=?',
                     (json.dumps(permissions), user_id))
        conn.execute('INSERT INTO admin_permission_audit(actor_id,target_id,permissions,revision) VALUES (?,?,?::jsonb,?)',
                     (actor_id, user_id, json.dumps(permissions), revision + 1))
    return get_permissions(user_id)
