"""小红书素材的私有文件存储与逐条迁移；缩略图仍留在数据库。"""

import hashlib
import logging
import os
from uuid import uuid4

from fastapi import HTTPException

from app.db import db
from app.services.file_retention import enqueue
from app.services.paper_storage import storage_for

logger = logging.getLogger(__name__)
EXTENSIONS = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp', 'video/mp4': 'mp4'}


def write_file(admin_id: int, content: bytes, media_type: str) -> str:
    key = f'xhs/{admin_id}/{uuid4().hex}.{EXTENSIONS[media_type]}'
    try:
        storage_for().put(key, content, media_type)
        path = storage_for().path(key)
        with path.open('r+b') as stream:
            os.fsync(stream.fileno())
        if os.name != 'nt':
            # 同步目录项（包括首次创建的父目录），然后才允许清空数据库原件。
            parent = path.parent
            for _ in range(len(key.split('/')) + 1):
                descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                parent = parent.parent
    except BaseException:
        discard(key)
        raise
    return key


def discard(key: str) -> None:
    if not key:
        return
    try:
        with db() as conn:
            enqueue(conn, [('local', key)])
    except Exception:
        # 数据库不可用时由登记过的键格式进行孤儿扫描，保留原始异常。
        logger.warning('素材清理登记失败，将由孤儿文件扫描重试')


def migrate_one(admin_id: int, identifier: str) -> bool:
    key = ''
    try:
        with db(lock_key=('xhs_research', str(admin_id))) as conn:
            row = conn.execute('SELECT content,media_type,digest,size_bytes,storage_key FROM xhs_assets WHERE id=? AND admin_id=? FOR UPDATE',
                               (identifier, admin_id)).fetchone()
            if not row or row['storage_key'] or row['content'] is None:
                return False
            content = bytes(row['content'])
            if len(content) != row['size_bytes'] or hashlib.sha256(row['media_type'].encode() + b':' + content).hexdigest() != row['digest']:
                raise ValueError('历史素材摘要与文件不一致，保留数据库原件')
            key = write_file(admin_id, content, row['media_type'])
            # 文件写入并校验成功后，同一事务切换引用；失败会保留原 BYTEA。
            if hashlib.sha256(storage_for().path(key).read_bytes()).digest() != hashlib.sha256(content).digest():
                raise OSError('素材文件校验失败')
            conn.execute("UPDATE xhs_assets SET storage='local',storage_key=?,content=NULL WHERE id=? AND admin_id=?",
                         (key, identifier, admin_id))
        return True
    except BaseException:
        discard(key)
        raise


def migrate_batch(limit: int = 5) -> int:
    with db() as conn:
        cursor = conn.execute("SELECT value FROM app_config WHERE key='xhs_asset_migration_cursor'").fetchone()
        rows = conn.execute("SELECT id,admin_id FROM xhs_assets WHERE storage_key='' AND content IS NOT NULL AND id>? ORDER BY id LIMIT ?",
                            (cursor[0] if cursor else '', limit)).fetchall()
        conn.execute("INSERT INTO app_config(key,value) VALUES ('xhs_asset_migration_cursor',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (rows[-1]['id'] if len(rows) == limit else '',))
    migrated = 0
    for row in rows:
        try:
            migrated += migrate_one(row['admin_id'], row['id'])
        except Exception:
            from app.metrics import maintenance_failures
            maintenance_failures.inc()
            logger.warning('素材 %s 迁移失败，保留数据库原件，后续轮次重试', row['id'])
    return migrated


def owned_file(admin_id: int, identifier: str):
    with db() as conn:
        row = conn.execute('SELECT storage,storage_key,media_type FROM xhs_assets WHERE id=? AND admin_id=?', (identifier, admin_id)).fetchone()
    if not row or row['media_type'] not in EXTENSIONS:
        raise HTTPException(404, detail={'error': '没有可下载的素材文件'})
    if not row['storage_key']:
        migrate_one(admin_id, identifier)
        with db() as conn:
            row = conn.execute('SELECT storage,storage_key,media_type FROM xhs_assets WHERE id=? AND admin_id=?', (identifier, admin_id)).fetchone()
    if not row or not row['storage_key']:
        raise HTTPException(404, detail={'error': '没有可下载的素材文件'})
    path = storage_for(row['storage']).path(row['storage_key'])
    if not path.is_file():
        raise HTTPException(404, detail={'error': '素材文件暂不可用，请联系管理员检查存储或备份'})
    return path, row['media_type']
