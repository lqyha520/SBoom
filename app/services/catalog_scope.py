"""公共习题后台按创建人隔离；超级管理员可管理全部条目。"""

from fastapi import HTTPException


def owner_id(conn, admin_id: int) -> int | None:
    row = conn.execute('SELECT role,is_active,is_super_admin FROM users WHERE id=?', (admin_id,)).fetchone()
    if not row or row['role'] != 'admin' or not row['is_active']:
        raise HTTPException(403, detail={'error': '需要管理员权限', 'code': 'permission_denied'})
    return None if row['is_super_admin'] else admin_id


def condition(conn, admin_id: int) -> tuple[str, list[int]]:
    owner = owner_id(conn, admin_id)
    return ('1=1', []) if owner is None else ('c.publisher_id=?', [owner])


def require_paper(conn, admin_id: int, catalog_id: str) -> None:
    where, args = condition(conn, admin_id)
    if not conn.execute(f'SELECT 1 FROM catalog_papers c WHERE c.id=? AND {where}', [catalog_id, *args]).fetchone():
        raise HTTPException(404, detail={'error': '资料不存在或不在当前账号的管理范围内'})
