import hashlib, secrets, time, uuid
from app.db import db
from app.services.mini_errors import fail
from app.services import membership_ledger, mini_auth

def _hash(code):
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()

def create(admin_id, days, quantity, expires_at=None):
    now = int(time.time()); items=[]
    with db(serialized="accounts") as conn:
        for _ in range(quantity):
            code = 'LC-' + secrets.token_hex(8).upper()
            conn.execute('INSERT INTO mini_membership_cards(id,code_hash,code_hint,days,status,created_by,created_at,expires_at) VALUES (?,?,?,?,?,?,?,?)',
                (uuid.uuid4().hex, _hash(code), code[-4:], days, 'active', admin_id, now, expires_at))
            items.append({'code': code, 'days': days, 'expires_at': expires_at})
    return {'items': items}

def listing(status='', limit=50, offset=0):
    with db() as conn:
        where = 'WHERE status = ?' if status else ''
        args=[status] if status else []
        total=conn.execute(f'SELECT COUNT(*) FROM mini_membership_cards {where}',args).fetchone()[0]
        rows=conn.execute(f'SELECT id,code_hint,days,status,redeemed_by,redeemed_at,created_at,expires_at FROM mini_membership_cards {where} ORDER BY created_at DESC LIMIT ? OFFSET ?', [*args,limit,offset]).fetchall()
    return {'items':[dict(r) for r in rows], 'total':total, 'has_more':offset+len(rows)<total}

def disable(identifier):
    with db(serialized="accounts") as conn:
        row=conn.execute('SELECT status FROM mini_membership_cards WHERE id=?',(identifier,)).fetchone()
        if not row: fail('卡密不存在',404)
        if row['status']=='redeemed': fail('已兑换卡密不能作废',409)
        conn.execute("UPDATE mini_membership_cards SET status='disabled' WHERE id=?",(identifier,))
    return {'status':'disabled'}

def redeem(user_id, code):
    now=int(time.time()); normalized=code.strip().upper()
    with db(serialized="accounts") as conn:
        row=conn.execute('SELECT * FROM mini_membership_cards WHERE code_hash=?',(_hash(normalized),)).fetchone()
        if not row or row['status']!='active': fail('卡密无效或已使用',422)
        if row['expires_at'] and row['expires_at'] < now: fail('卡密已过期',422)
        user=conn.execute('SELECT * FROM mini_users WHERE id=? AND is_active=1',(user_id,)).fetchone()
        if not user: fail('账号不可用',403)
        end=membership_ledger.append(conn,user,row['days'])
        updated_card = conn.execute("UPDATE mini_membership_cards SET status='redeemed',redeemed_by=?,redeemed_at=? WHERE id=? AND status='active' RETURNING id",(user_id,now,row['id'])).fetchone()
        if not updated_card: fail('卡密已被兑换',409)
        updated=conn.execute('SELECT * FROM mini_users WHERE id=?',(user_id,)).fetchone()
    return {'user': mini_auth._row_user(updated).public(), 'days': row['days'], 'vip_expires_at': end}
