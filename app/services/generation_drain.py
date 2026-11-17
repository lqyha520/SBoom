"""发布期间关闭新任务准入；原请求查询和结果重放保持可用。"""
import argparse
import json
import signal
import time

from fastapi import HTTPException

from app.db import db

KEY = 'generation_deployment_drain'


def require_open(conn) -> None:
    row = conn.execute('SELECT value FROM app_config WHERE key = ?', (KEY,)).fetchone()
    state = json.loads(row['value']) if row else {}
    if state.get('expires_at', 0) > time.time():
        raise HTTPException(503, detail={'code': 'generation_deploying',
                                        'error': '服务正在更新，已有题目不会丢失，请稍后再生成'},
                            headers={'Retry-After': '15'})


def set_drain(owner: str, ttl: int = 3600) -> None:
    if not owner or not 60 <= ttl <= 7200:
        raise ValueError('发布标识或等待期限无效')
    with db(serialized='generation') as conn:
        row = conn.execute('SELECT value FROM app_config WHERE key = ?', (KEY,)).fetchone()
        old = json.loads(row['value']) if row else {}
        if old.get('expires_at', 0) > time.time() and old.get('owner') != owner:
            raise RuntimeError('已有发布正在等待任务完成')
        conn.execute('INSERT INTO app_config(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                     (KEY, json.dumps({'owner': owner, 'expires_at': int(time.time()) + ttl})))


def clear_drain(owner: str) -> None:
    with db(serialized='generation') as conn:
        row = conn.execute('SELECT value FROM app_config WHERE key = ?', (KEY,)).fetchone()
        if row and json.loads(row['value']).get('owner') == owner:
            conn.execute('DELETE FROM app_config WHERE key = ?', (KEY,))


def active_count() -> int:
    with db() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM generation_requests WHERE status='running' "
                                'AND COALESCE(NULLIF(lease_expires_at,0),created_at+90)>=?',
                                (int(time.time()),)).fetchone()[0])


def hold_legacy_admission(owner: str) -> None:
    """旧版本尚不识别暂停标记时，用同一准入锁阻止新任务；心跳与完成写入不受影响。"""
    import psycopg

    from app.config import get_settings
    from app.constants import LOCK_IDS

    stopping = False
    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with psycopg.connect(get_settings().database_url, autocommit=True) as conn:
        conn.execute("SET lock_timeout='10s'")
        conn.execute('SELECT pg_advisory_lock(%s)', (LOCK_IDS['generation'],))
        row = conn.execute('SELECT value FROM app_config WHERE key=%s', (KEY,)).fetchone()
        state = json.loads(row[0]) if row else {}
        if state.get('owner') != owner:
            raise RuntimeError('发布暂停标记不匹配')
        print('admission-locked', flush=True)
        deadline = min(state['expires_at'], time.time() + 1800)
        while not stopping and time.time() < deadline:
            conn.execute('SELECT 1')
            time.sleep(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['set', 'clear', 'hold', 'count'])
    parser.add_argument('owner', nargs='?', default='')
    args = parser.parse_args()
    if args.action == 'count':
        print(active_count())
    elif args.action == 'set':
        set_drain(args.owner)
    elif args.action == 'clear':
        clear_drain(args.owner)
    else:
        hold_legacy_admission(args.owner)
