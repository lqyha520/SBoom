"""公共资料排期与体检；后台归属、发布权限和执行时版本均重新校验。"""

import asyncio
import hashlib
import ipaddress
import json
import socket
import time
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from app.admin_permissions import require
from app.blocking import run_sync
from app.db import db
from app.services import catalog_access, catalog_review, catalog_scope, public_catalog
from app.services.paper_storage import storage_for
from app.services.user_store import from_row


def file_issues(conn, row, assets=None):
    issues = []
    if row['download_mode'] == 'external':
        if not row['external_url']:
            issues.append({'code': 'external_missing', 'severity': 'error', 'message': '未填写网盘链接'})
        return issues
    if assets is None:
        assets = conn.execute('SELECT * FROM paper_assets WHERE paper_id=? OR paper_id IN (SELECT paper_id FROM catalog_print_editions WHERE catalog_id=?)',
                              (row['paper_id'], row['id'])).fetchall()
    primary = [a for a in assets if a['paper_id'] == row['paper_id']]
    if row['file_status'] != 'ready' or not any(a['kind'] == 'pdf' for a in primary):
        issues.append({'code': 'pdf_missing', 'severity': 'error', 'message': '主 PDF 未就绪'})
    if not any(a['kind'] == 'page' for a in primary):
        issues.append({'code': 'preview_missing', 'severity': 'error', 'message': '缺少预览图片'})
    for asset in assets:
        try:
            path = storage_for(asset['storage']).path(asset['storage_key'])
            if not path.is_file() or path.stat().st_size != asset['byte_size']:
                raise ValueError('missing or changed')
        except (ValueError, OSError):
            issues.append({'code': 'asset_unavailable', 'severity': 'error', 'message': '文件缺失或大小异常，请补传原稿或打印版本'})
            break
    return issues


def schedule_list(admin_id, limit=20, offset=0, status=''):
    with db() as conn:
        where, args = catalog_scope.condition(conn, admin_id)
        groups = conn.execute(f'SELECT s.status,COUNT(*) AS count FROM catalog_schedules s JOIN catalog_papers c ON c.id=s.catalog_id WHERE {where} GROUP BY s.status', args).fetchall()
        counts = {key: 0 for key in ('pending', 'failed', 'published', 'cancelled')}
        counts.update({row['status']: row['count'] for row in groups})
        counts['all'] = sum(counts.values())
        total = counts[status or 'all']
        if status:
            where += ' AND s.status=?'
            args.append(status)
        rows = conn.execute(f'SELECT s.*,c.title FROM catalog_schedules s JOIN catalog_papers c ON c.id=s.catalog_id WHERE {where} '
                            "ORDER BY CASE s.status WHEN 'failed' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,s.scheduled_at,s.catalog_id LIMIT ? OFFSET ?", [*args, limit, offset]).fetchall()
    return {'items': [dict(r) for r in rows], 'total': total, 'has_more': offset + len(rows) < total, 'counts': counts}


def policy_hash(conn, catalog_id):
    policy = catalog_access.access_map(conn, [catalog_id], None)[catalog_id]
    return hashlib.sha256(json.dumps([policy['required_view'], policy['required_download']]).encode()).hexdigest()


def schedule(admin_id, catalog_id, body):
    now = int(time.time())
    if not now + 60 <= body.scheduled_at <= now + 180 * 86400:
        raise HTTPException(422, detail={'error': '发布时间须在 1 分钟后至 180 天内'})
    with db(serialized=True) as conn:
        catalog_scope.require_paper(conn, admin_id, catalog_id)
        actor = conn.execute('SELECT * FROM users WHERE id=? FOR SHARE', (admin_id,)).fetchone()
        require(from_row(actor), 'papers', 'publish')
        row = conn.execute(f'SELECT c.*,a.file_status FROM {public_catalog.JOIN} WHERE c.id=?', (catalog_id,)).fetchone()
        if row['revision'] != body.catalog_revision:
            raise HTTPException(409, detail={'error': '资料已更新，请刷新并核对后重新排期'})
        if row['status'] == 'published':
            raise HTTPException(422, detail={'error': '该资料已经发布，无需排期'})
        current = conn.execute('SELECT revision FROM catalog_schedules WHERE catalog_id=?', (catalog_id,)).fetchone()
        if (current['revision'] if current else 0) != body.schedule_revision:
            raise HTTPException(409, detail={'error': '排期已被其他操作更新，请刷新并重新核对'})
        errors = file_issues(conn, row)
        if errors:
            raise HTTPException(422, detail={'error': errors[0]['message']})
        conn.execute("INSERT INTO catalog_schedules(catalog_id,admin_id,scheduled_at,catalog_revision,created_at,updated_at,policy_hash) VALUES (?,?,?,?,?,?,?) "
                     "ON CONFLICT(catalog_id) DO UPDATE SET admin_id=excluded.admin_id,scheduled_at=excluded.scheduled_at,catalog_revision=excluded.catalog_revision,"
                     "revision=catalog_schedules.revision+1,status='pending',message='',updated_at=excluded.updated_at,policy_hash=excluded.policy_hash",
                     (catalog_id, admin_id, body.scheduled_at, body.catalog_revision, now, now, policy_hash(conn, catalog_id)))
        return dict(conn.execute('SELECT s.*,c.title FROM catalog_schedules s JOIN catalog_papers c ON c.id=s.catalog_id WHERE s.catalog_id=?', (catalog_id,)).fetchone())


def schedule_detail(admin_id, catalog_id):
    with db() as conn:
        catalog_scope.require_paper(conn, admin_id, catalog_id)
        row = conn.execute('SELECT s.*,c.title FROM catalog_schedules s JOIN catalog_papers c ON c.id=s.catalog_id WHERE s.catalog_id=?', (catalog_id,)).fetchone()
    return dict(row) if row else None


def cancel(admin_id, catalog_id, revision):
    with db(serialized=True) as conn:
        catalog_scope.require_paper(conn, admin_id, catalog_id)
        row = conn.execute('SELECT * FROM catalog_schedules WHERE catalog_id=? FOR UPDATE', (catalog_id,)).fetchone()
        if not row:
            raise HTTPException(404, detail={'error': '排期不存在'})
        if row['revision'] != revision or row['status'] != 'pending':
            raise HTTPException(409, detail={'error': '排期已变化，请刷新'})
        conn.execute("UPDATE catalog_schedules SET status='cancelled',revision=revision+1,updated_at=?,message='已取消排期' WHERE catalog_id=?", (int(time.time()), catalog_id))


def schedule_tick(now=None):
    now = int(time.time()) if now is None else now
    with db() as conn:
        due = conn.execute("SELECT catalog_id,revision FROM catalog_schedules WHERE status='pending' AND scheduled_at<=? ORDER BY scheduled_at,catalog_id LIMIT 20", (now,)).fetchall()
    for due_row in due:
        try:
            with db(serialized=True, invalidate_public=True) as conn:
                s = conn.execute("SELECT * FROM catalog_schedules WHERE catalog_id=? AND status='pending' AND revision=? FOR UPDATE", (due_row['catalog_id'], due_row['revision'])).fetchone()
                if not s:
                    raise HTTPException(409, detail={'error': '排期已变化'})
                actor = conn.execute('SELECT * FROM users WHERE id=? FOR SHARE', (s['admin_id'],)).fetchone()
                if not actor:
                    raise HTTPException(403, detail={'error': '排期管理员已删除，请重新核对排期'})
                require(from_row(actor), 'papers', 'publish')
                catalog_scope.require_paper(conn, s['admin_id'], s['catalog_id'])
                row = conn.execute(f'SELECT c.*,a.file_status FROM {public_catalog.JOIN} WHERE c.id=?', (s['catalog_id'],)).fetchone()
                if row['revision'] != s['catalog_revision'] or row['status'] == 'published':
                    raise HTTPException(409, detail={'error': '资料版本或发布状态已变化，请重新核对并排期'})
                if policy_hash(conn, row['id']) != s['policy_hash']:
                    raise HTTPException(409, detail={'error': '资料实际观看或下载权限已变化，请重新核对并排期'})
                errors = file_issues(conn, row)
                if errors:
                    raise HTTPException(422, detail={'error': errors[0]['message']})
                conn.execute("UPDATE catalog_papers SET status='published',revision=revision+1,published_at=?,updated_at=? WHERE id=?", (now, now, row['id']))
                catalog_review.confirm(conn, row['id'], s['admin_id'])
                conn.execute("UPDATE catalog_schedules SET status='published',message='已按排期发布',revision=revision+1,updated_at=? WHERE catalog_id=?", (now, row['id']))
        except HTTPException as exc:
            message = exc.detail.get('error', '排期校验未通过') if isinstance(exc.detail, dict) else str(exc.detail)
            with db() as conn:
                conn.execute("UPDATE catalog_schedules SET status='failed',message=?,revision=revision+1,updated_at=? WHERE catalog_id=? AND status='pending' AND revision=?",
                             (message, now, due_row['catalog_id'], due_row['revision']))


HEALTH_CATEGORIES = {
    'file': {'external_missing', 'pdf_missing', 'asset_unavailable'},
    'preview': {'preview_missing'},
    'textbook': {'textbook_missing'},
    'review': {'unreviewed'},
    'answers': {'answers_missing', 'answers_unverified'},
    'link': {'link_check'},
}


def health(admin_id, q='', limit=20, offset=0, only_issues=False, category=''):
    now = int(time.time())
    counts = {key: 0 for key in ('all', 'issues', *HEALTH_CATEGORIES)}
    total, scanned, results = 0, 0, []
    with db() as conn:
        where, args = catalog_scope.condition(conn, admin_id)
        if q.strip():
            where += " AND LOWER(c.title) LIKE ? ESCAPE '\\'"
            args.append(public_catalog._match(q))
        # 全部资料先体检、分类再分页；每批合并查询文件、教材与链接记录，避免逐条查库。
        while True:
            rows = conn.execute(f'SELECT c.*,a.file_status FROM {public_catalog.JOIN} WHERE {where} ORDER BY c.updated_at DESC,c.id DESC LIMIT 200 OFFSET ?', [*args, scanned]).fetchall()
            if not rows:
                break
            scanned += len(rows)
            ids = [row['id'] for row in rows]
            assets: dict[str, list[dict]] = {identifier: [] for identifier in ids}
            for asset in conn.execute('SELECT c.id AS catalog_id,p.* FROM catalog_papers c JOIN paper_assets p ON p.paper_id=c.paper_id '
                                      'WHERE c.id=ANY(?) UNION SELECT e.catalog_id,p.* FROM catalog_print_editions e JOIN paper_assets p ON p.paper_id=e.paper_id WHERE e.catalog_id=ANY(?)', (ids, ids)).fetchall():
                assets[asset['catalog_id']].append(asset)
            tagged = {row['catalog_id'] for row in conn.execute("SELECT DISTINCT p.catalog_id FROM catalog_paper_tags p JOIN catalog_tags t ON t.id=p.tag_id WHERE p.catalog_id=ANY(?) AND t.kind='textbook' AND t.is_visible=1", (ids,)).fetchall()}
            links = {row['catalog_id']: row for row in conn.execute('SELECT * FROM catalog_link_checks WHERE catalog_id=ANY(?)', (ids,)).fetchall()}
            for row in rows:
                issues = file_issues(conn, row, assets[row['id']])
                if row['id'] not in tagged:
                    issues.append({'code': 'textbook_missing', 'severity': 'warning', 'message': '未关联可见教材标签，无法参与教材精准推荐'})
                if not row['reviewed_at']:
                    issues.append({'code': 'unreviewed', 'severity': 'warning', 'message': '尚无人工内容核对记录'})
                if row['answer_readiness'] in ('missing', 'unknown'):
                    issues.append({'code': 'answers_missing' if row['answer_readiness'] == 'missing' else 'answers_unverified', 'severity': 'info',
                                   'message': '未提供配套答案，可按资料用途补充' if row['answer_readiness'] == 'missing' else '答案状态待核对，请确认文件内答案或配套答案'})
                link = links.get(row['id']) if row['download_mode'] == 'external' else None
                if link and link['url_hash'] != hashlib.sha256(row['external_url'].encode()).hexdigest():
                    link = None
                if row['download_mode'] == 'external' and (not link or link['status'] in ('suspect', 'unverified') or link['checked_at'] < now - 7 * 86400):
                    issues.append({'code': 'link_check', 'severity': 'warning', 'message': link['message'] if link and link['checked_at'] >= now - 7 * 86400 else '网盘链接尚未核验或核验超过 7 天'})
                codes = {issue['code'] for issue in issues}
                categories = {key for key, values in HEALTH_CATEGORIES.items() if codes & values}
                counts['all'] += 1
                counts['issues'] += bool(issues)
                for key in categories:
                    counts[key] += 1
                if (only_issues and not issues) or (category and category not in categories):
                    continue
                if offset <= total < offset + limit:
                    results.append({'catalog_id': row['id'], 'title': row['title'], 'revision': row['revision'], 'status': row['status'],
                                    'external': row['download_mode'] == 'external', 'issues': issues,
                                    'link_check': {key: link[key] for key in ('catalog_id', 'status', 'message', 'checked_at')} if link else None})
                total += 1
    return {'items': results, 'total': total, 'has_more': offset + len(results) < total, 'checked_at': now, 'counts': counts}


async def _pin_link(request):
    url = str(request.url)
    parts = urlsplit(url)
    if (parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password
            or parts.port not in (None, 80, 443) or '\\' in url):
        raise ValueError('不支持的网盘链接地址')
    addresses = await asyncio.wait_for(run_sync(socket.getaddrinfo, parts.hostname, parts.port or (443 if parts.scheme == 'https' else 80), type=socket.SOCK_STREAM), 3)
    ips = sorted({a[4][0] for a in addresses})
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ValueError('网盘链接未解析到公网地址')
    request.headers['Host'] = request.url.netloc.decode('ascii')
    request.extensions['sni_hostname'] = parts.hostname
    request.url = request.url.copy_with(host=ips[0])


async def probe_url(url):
    # 独立无凭据连接，固定公网 IP，关闭代理和自动跳转；读取最多 8 KiB。
    try:
        async with asyncio.timeout(12):
            async with httpx.AsyncClient(timeout=4, trust_env=False, follow_redirects=False, event_hooks={'request': [_pin_link]}) as client:
                for _ in range(4):
                    async with client.stream('GET', url, headers={'Range': 'bytes=0-8191', 'Accept-Encoding': 'identity'}) as response:
                        if response.is_redirect:
                            url = str(httpx.URL(url).join(response.headers.get('location', '')))
                            continue
                        if response.status_code in (404, 410):
                            return 'suspect', '链接疑似失效，请在网盘中人工确认'
                        if response.status_code not in (200, 206):
                            return 'unverified', '网盘限制自动访问，请人工确认链接与提取码'
                        raw = bytearray()
                        async for chunk in response.aiter_raw(chunk_size=8192):
                            raw.extend(chunk[:8192 - len(raw)])
                            if len(raw) >= 8192:
                                break
                        text = raw.decode('utf-8', errors='ignore')
                        if any(word in text for word in ('分享已取消', '分享已过期', '链接不存在', '分享不存在')):
                            return 'suspect', '页面提示分享失效，请人工确认'
                        return 'reachable', '链接可以访问，文件与提取码仍需人工核对'
        return 'unverified', '跳转次数过多，请人工确认'
    except (ValueError, OSError, TimeoutError, httpx.HTTPError):
        return 'unverified', '自动检测未能确认，请人工检查链接与提取码'


def link_url(admin_id, catalog_id):
    with db() as conn:
        catalog_scope.require_paper(conn, admin_id, catalog_id)
        row = conn.execute('SELECT download_mode,external_url FROM catalog_papers WHERE id=?', (catalog_id,)).fetchone()
    if row['download_mode'] != 'external' or not row['external_url']:
        raise HTTPException(422, detail={'error': '此资料未配置网盘下载'})
    return row['external_url']


def record_link(admin_id, catalog_id, url, status, message):
    now = int(time.time())
    with db(serialized=True) as conn:
        catalog_scope.require_paper(conn, admin_id, catalog_id)
        row = conn.execute('SELECT external_url FROM catalog_papers WHERE id=?', (catalog_id,)).fetchone()
        if row['external_url'] != url:
            raise HTTPException(409, detail={'error': '检测期间链接已修改，请重新检查'})
        conn.execute('INSERT INTO catalog_link_checks(catalog_id,url_hash,status,message,checked_at) VALUES (?,?,?,?,?) '
                     'ON CONFLICT(catalog_id) DO UPDATE SET url_hash=excluded.url_hash,status=excluded.status,message=excluded.message,checked_at=excluded.checked_at',
                     (catalog_id, hashlib.sha256(url.encode()).hexdigest(), status, message, now))
    return {'catalog_id': catalog_id, 'status': status, 'message': message, 'checked_at': now}
