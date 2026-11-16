"""独立创作模块的持久化、关联、版本与发布复盘。"""
import hashlib
import json
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from pydantic import ValidationError

from app.db import db
from app.models.xhs_workflow import MODELS
from app.services import xhs_publication as publication
from app.sql_utils import escape_like

PARENTS = {'ideas': None, 'materials': 'ideas', 'drafts': 'materials', 'publications': 'drafts'}


def validated(kind, data):
    try:
        return MODELS[kind].model_validate(data).model_dump(mode='json')
    except ValidationError as error:
        raise HTTPException(422, detail={'error': '; '.join(e['msg'] for e in error.errors())}) from error


def _row(row):
    value = dict(row)
    value['data'] = json.loads(value.pop('data_json'))
    if value.get('kind') in MODELS:
        value['data'] = {**MODELS[value['kind']](title=value['title']).model_dump(mode='json'), **value['data']}
    value.pop('create_hash', None)
    value.pop('scheduled_at', None)
    value.pop('published_at', None)
    value.pop('publication_url_key', None)
    value.pop('publication_content_hash', None)
    return value


def _owned(conn, admin_id, kind, record_id):
    row = conn.execute('SELECT * FROM xhs_workflow_records WHERE id=? AND kind=? AND admin_id=?', (record_id, kind, admin_id)).fetchone()
    if not row:
        raise HTTPException(404, detail={'error': '内容不存在或不属于当前账号'})
    return row


def get_record(admin_id, kind, record_id):
    with db() as conn:
        row = _row(_owned(conn, admin_id, kind, record_id))
        row['children'] = [dict(r) for r in conn.execute('SELECT id,kind,title,status FROM xhs_workflow_records WHERE parent_id=? AND admin_id=? ORDER BY updated_at DESC', (record_id, admin_id)).fetchall()]
        row['parent'] = None
        if row['parent_id']:
            parent = conn.execute('SELECT id,kind,title,revision FROM xhs_workflow_records WHERE id=? AND admin_id=?', (row['parent_id'], admin_id)).fetchone()
            row['parent'] = dict(parent) if parent else None
    return row


def list_records(admin_id, kind, q='', status='', parent_id='', page=1):
    clauses, values = ['admin_id=?', 'kind=?'], [admin_id, kind]
    if q.strip():
        clauses.append('title ILIKE ?')
        values.append('%' + escape_like(q.strip()) + '%')
    if status:
        clauses.append('status=?')
        values.append(status)
    else:
        clauses.append("status<>'archived'")
    if parent_id:
        clauses.append('parent_id=?')
        values.append(parent_id)
    where = ' AND '.join(clauses)
    with db() as conn:
        total = conn.execute('SELECT COUNT(*) FROM xhs_workflow_records WHERE ' + where, values).fetchone()[0]
        rows = conn.execute('SELECT * FROM xhs_workflow_records WHERE ' + where + ' ORDER BY updated_at DESC,id LIMIT 20 OFFSET ?', (*values, (page - 1) * 20)).fetchall()
    return {'items': [_row(row) for row in rows], 'total': total, 'page': page, 'page_size': 20}


def create_record(admin_id, kind, record_id, parent_id, data):
    data = validated(kind, data)
    fingerprint = hashlib.sha256(json.dumps([kind, parent_id, data], sort_keys=True).encode()).hexdigest()
    with db(lock_key=('xhs_research', str(admin_id))) as conn:
        existing = conn.execute('SELECT * FROM xhs_workflow_records WHERE id=?', (record_id,)).fetchone()
        if existing:
            if existing['admin_id'] != admin_id or existing['create_hash'] != fingerprint:
                raise HTTPException(409, detail={'error': '创建请求已用于其他内容，请刷新后重试'})
            return _row(existing)
        expected = PARENTS[kind]
        if kind == 'publications' and data['source'] == 'custom':
            if parent_id:
                raise HTTPException(422, detail={'error': '自定义发布不需要关联笔记'})
        elif expected:
            if not parent_id:
                message = {'materials': '请先选择关联选题', 'drafts': '请先选择关联资料',
                           'publications': '请选择关联笔记，或切换为自定义发布'}[kind]
                raise HTTPException(422, detail={'error': message})
            parent = _owned(conn, admin_id, expected, parent_id)
            if parent['status'] == 'archived':
                raise HTTPException(409, detail={'error': '请先恢复关联的上一步内容'})
        elif parent_id:
            raise HTTPException(422, detail={'error': '选题不需要上级内容'})
        if kind == 'ideas' and data['source_note_id']:
            note = conn.execute('SELECT note_id FROM xhs_research_notes WHERE note_id=?', (data['source_note_id'],)).fetchone()
            if not note:
                raise HTTPException(404, detail={'error': '参考笔记不存在'})
        if kind == 'ideas' and data['source_publication_id']:
            _owned(conn, admin_id, 'publications', data['source_publication_id'])
        if kind == 'publications':
            # 发布记录绑定所选文案版本，后续草稿修改不会改写已发布的内容。
            if data['source'] == 'linked':
                data['draft_snapshot'] = json.loads(parent['data_json'])
                data['draft_revision'] = parent['revision']
            validate_publication(conn, admin_id, data, record_id)
        encoded = json.dumps(data, ensure_ascii=False)
        conn.execute('INSERT INTO xhs_workflow_records(id,admin_id,kind,parent_id,title,status,data_json,create_hash,scheduled_at,published_at,publication_url_key,publication_content_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                     (record_id, admin_id, kind, parent_id, data['title'], data['status'], encoded, fingerprint, data.get('scheduled_at'), data.get('published_at'),
                      publication.url_key(data.get('url', '')) if kind == 'publications' else None, publication.content_hash(data) if kind == 'publications' else None))
        conn.execute('INSERT INTO xhs_workflow_versions(record_id,revision,data_json) VALUES (?,1,?)', (record_id, encoded))
    return get_record(admin_id, kind, record_id)


def update_record(admin_id, kind, record_id, revision, data):
    data = validated(kind, data)
    with db(lock_key=('xhs_research', str(admin_id))) as conn:
        old = _owned(conn, admin_id, kind, record_id)
        if old['revision'] != revision:
            raise HTTPException(409, detail={'error': '内容已在其他页面更新，当前输入已保留，请重新读取最新版本'})
        previous = _row(old)['data']
        if kind == 'ideas' and data['source_publication_id']:
            _owned(conn, admin_id, 'publications', data['source_publication_id'])
        if kind == 'materials' and any(previous.get(k) != data.get(k) for k in (
                'grade', 'subject', 'keyword', 'game_type', 'difficulty', 'question_count', 'questions', 'instructions')):
            data.update(status='draft', accuracy_checked=False, scope_checked=False, layout_checked=False)
        if kind == 'publications':
            if data['source'] != previous.get('source', 'linked'):
                raise HTTPException(409, detail={'error': '已保存的发布记录不能切换内容来源，请新建发布记录'})
            if data['source'] == 'linked':
                data.update(draft_snapshot=previous['draft_snapshot'], draft_revision=previous['draft_revision'])
            changed = any(previous.get(k, '') != data.get(k, '') for k in ('account', 'account_id', 'custom_content', 'media'))
            if changed:
                for key in publication.CHECKS:
                    data[key] = False
                data['review_notes'] = ''
                if data['status'] == 'ready':
                    data['status'] = 'planned'
            was_published = previous['status'] == 'published' or bool(previous.get('published_at') and previous.get('url'))
            if was_published and data['status'] not in ('published', 'archived'):
                raise HTTPException(409, detail={'error': '已发布记录保留发布事实，可归档；再次发布请新建记录'})
            if was_published and not (data['published_at'] and data['url']):
                raise HTTPException(422, detail={'error': '请保留实际发布时间和链接，归档不会删除发布事实'})
            metric = conn.execute('SELECT data_json FROM xhs_workflow_metrics WHERE publication_id=?', (record_id,)).fetchall()
            if metric and data['published_at'] and any(datetime.fromisoformat(data['published_at']) > datetime.fromisoformat(json.loads(row['data_json'])['measured_at']) for row in metric):
                raise HTTPException(409, detail={'error': '实际发布时间不能晚于已有复盘数据的统计时间'})
            validate_publication(conn, admin_id, data, record_id, previous)
        if data != previous:
            encoded = json.dumps(data, ensure_ascii=False)
            conn.execute('UPDATE xhs_workflow_records SET title=?,status=?,data_json=?,scheduled_at=?,published_at=?,publication_url_key=?,publication_content_hash=?,revision=revision+1,updated_at=now() WHERE id=?',
                         (data['title'], data['status'], encoded, data.get('scheduled_at'), data.get('published_at'),
                          publication.url_key(data.get('url', '')) if kind == 'publications' else None, publication.content_hash(data) if kind == 'publications' else None, record_id))
            conn.execute('INSERT INTO xhs_workflow_versions(record_id,revision,data_json) VALUES (?,?,?)', (record_id, revision + 1, encoded))
    return get_record(admin_id, kind, record_id)


def validate_publication(conn, admin_id, data, record_id, previous=None):
    # 历史发布保留已删除素材的引用；新选用或准备发布时核对归属及来源。
    if not previous or data.get('media', []) != previous.get('media', []) or data['status'] == 'ready':
        for item in data.get('media', []):
            if not item['asset_id']:
                continue
            asset = conn.execute('SELECT media_type,size_bytes,metadata_json FROM xhs_assets WHERE id=? AND admin_id=?',
                                 (item['asset_id'], admin_id)).fetchone()
            if not asset:
                raise HTTPException(422, detail={'error': '发布素材不存在或不属于当前账号，请重新选择'})
            metadata = json.loads(asset['metadata_json'])
            if metadata['archived'] or metadata['rights'] == 'unknown':
                raise HTTPException(422, detail={'error': '请先恢复素材并核实来源，再用于发布'})
            if asset['media_type'] != item['media_type'] or asset['size_bytes'] != item['size_bytes']:
                raise HTTPException(422, detail={'error': '素材文件信息已变化，请重新选择'})
    key = publication.url_key(data['url'])
    if key:
        if conn.execute("SELECT 1 FROM xhs_workflow_records WHERE admin_id=? AND kind='publications' AND publication_url_key=? AND publication_url_key<>'' AND id<>? LIMIT 1", (admin_id, key, record_id)).fetchone():
            raise HTTPException(409, detail={'error': '这篇笔记已登记过发布记录，请修改原记录，避免重复统计'})
    if data['status'] == 'ready' or (data['status'] == 'published' and (not previous or previous['status'] != 'published')):
        checks = publication.report(conn, admin_id, data, record_id)
        if checks['blockers']:
            raise HTTPException(422, detail={'error': '请先完成发布前检查：' + '；'.join(checks['blockers'])})


def check_publication(admin_id, data, record_id=None, parent_id=None):
    data = validated('publications', data)
    with db() as conn:
        if record_id:
            old = _owned(conn, admin_id, 'publications', record_id)
            previous = json.loads(old['data_json'])
            if data['source'] != previous.get('source', 'linked'):
                raise HTTPException(409, detail={'error': '内容来源与已保存的记录不一致'})
            if data['source'] == 'linked':
                data['draft_snapshot'] = previous['draft_snapshot']
        elif data['source'] == 'linked':
            parent = _owned(conn, admin_id, 'drafts', parent_id)
            data['draft_snapshot'] = json.loads(parent['data_json'])
        return publication.report(conn, admin_id, data, record_id)


def refresh_publication_draft(admin_id, record_id, revision):
    with db(lock_key=('xhs_research', str(admin_id))) as conn:
        old = _owned(conn, admin_id, 'publications', record_id)
        if old['revision'] != revision:
            raise HTTPException(409, detail={'error': '发布记录已更新，请重新读取后操作'})
        data = json.loads(old['data_json'])
        if data.get('source', 'linked') != 'linked' or data['status'] == 'archived' or data.get('published_at') or data.get('url'):
            raise HTTPException(409, detail={'error': '仅未发布、未归档的关联记录可以更新笔记版本'})
        parent = _owned(conn, admin_id, 'drafts', old['parent_id'])
        if parent['status'] == 'archived':
            raise HTTPException(409, detail={'error': '请先恢复关联笔记'})
        data.update(draft_snapshot=json.loads(parent['data_json']), draft_revision=parent['revision'], status='planned', review_notes='')
        for key in publication.CHECKS:
            data[key] = False
        encoded = json.dumps(data, ensure_ascii=False)
        conn.execute('UPDATE xhs_workflow_records SET status=?,data_json=?,publication_content_hash=?,revision=revision+1,updated_at=now() WHERE id=?', ('planned', encoded, publication.content_hash(data), record_id))
        conn.execute('INSERT INTO xhs_workflow_versions(record_id,revision,data_json) VALUES (?,?,?)', (record_id, revision + 1, encoded))
    return get_record(admin_id, 'publications', record_id)


def versions(admin_id, kind, record_id, page=1):
    with db() as conn:
        _owned(conn, admin_id, kind, record_id)
        rows = conn.execute('SELECT revision,data_json,created_at FROM xhs_workflow_versions WHERE record_id=? ORDER BY revision DESC LIMIT 20 OFFSET ?', (record_id, (page - 1) * 20)).fetchall()
        total = conn.execute('SELECT COUNT(*) FROM xhs_workflow_versions WHERE record_id=?', (record_id,)).fetchone()[0]
    return {'items': [_row(row) for row in rows], 'total': total}


def metrics(admin_id, publication_id):
    with db() as conn:
        _owned(conn, admin_id, 'publications', publication_id)
        return _metrics(conn, publication_id)


def _metrics(conn, publication_id):
    rows = conn.execute('SELECT data_json,revision FROM xhs_workflow_metrics WHERE publication_id=? ORDER BY checkpoint', (publication_id,)).fetchall()
    return [dict(json.loads(row['data_json']), revision=row['revision']) for row in rows]


def save_metric(admin_id, publication_id, data):
    with db(lock_key=('xhs_research', str(admin_id))) as conn:
        _save_metric(conn, _owned(conn, admin_id, 'publications', publication_id), data)
        return _metrics(conn, publication_id)


def _save_metric(conn, record, data):
    if record['status'] != 'published':
        raise HTTPException(409, detail={'error': '实际发布后再录入效果数据'})
    published_at = datetime.fromisoformat(json.loads(record['data_json'])['published_at'])
    measured = datetime.fromisoformat(data['measured_at'])
    if measured < published_at or measured > datetime.now(UTC) + timedelta(minutes=5):
        raise HTTPException(422, detail={'error': '统计时间应在发布后，且不能晚于当前时间'})
    existing = conn.execute('SELECT revision FROM xhs_workflow_metrics WHERE publication_id=? AND checkpoint=?', (record['id'], data['checkpoint'])).fetchone()
    if (existing['revision'] if existing else 0) != data['revision']:
        raise HTTPException(409, detail={'error': '该阶段的数据已更新，请重新读取后修改'})
    conn.execute('INSERT INTO xhs_workflow_metrics(publication_id,checkpoint,data_json) VALUES (?,?,?) '
                 'ON CONFLICT(publication_id,checkpoint) DO UPDATE SET data_json=excluded.data_json,revision=xhs_workflow_metrics.revision+1,updated_at=now()',
                 (record['id'], data['checkpoint'], json.dumps(data, ensure_ascii=False)))


def save_review(admin_id, publication_id, data):
    # 两处版本检查与写入共用事务和账号锁，任何失败都不会留下半份复盘。
    with db(lock_key=('xhs_research', str(admin_id))) as conn:
        record = _owned(conn, admin_id, 'publications', publication_id)
        if record['revision'] != data['revision']:
            raise HTTPException(409, detail={'error': '发布记录已在其他页面更新，复盘尚未保存，当前输入已保留'})
        _save_metric(conn, record, data['metric'])
        previous = json.loads(record['data_json'])
        current = {**previous, 'conclusion': data['conclusion'], 'next_action': data['next_action']}
        if current != previous:
            encoded = json.dumps(current, ensure_ascii=False)
            conn.execute('UPDATE xhs_workflow_records SET data_json=?,revision=revision+1,updated_at=now() WHERE id=?', (encoded, publication_id))
            conn.execute('INSERT INTO xhs_workflow_versions(record_id,revision,data_json) VALUES (?,?,?)', (publication_id, record['revision'] + 1, encoded))
        return {'record': _row(_owned(conn, admin_id, 'publications', publication_id)), 'items': _metrics(conn, publication_id)}


ACCOUNT_SQL = "COALESCE(NULLIF(r.data_json::jsonb->>'account_id',''),NULLIF(lower(trim(r.data_json::jsonb->>'account')),''),'(未指定账号)')"
PUBLISHED_SQL = 'r.published_at'


def analytics(admin_id, checkpoint=7, q='', page=1, account='', start=None, end=None, sort='published_at'):
    if any(value is not None and value.tzinfo is None for value in (start, end)) or (start and end and start >= end):
        raise HTTPException(422, detail={'error': '请选择包含时区、开始早于结束的日期范围'})
    clauses, args = ["r.admin_id=?", "r.kind='publications'", "r.status='published'"], [admin_id]
    if q.strip():
        clauses.append('r.title ILIKE ?')
        args.append('%' + escape_like(q.strip()) + '%')
    if account:
        clauses.append(ACCOUNT_SQL + '=?')
        args.append(account)
    for operator, value in (('>=', start), ('<', end)):
        if value:
            clauses.append(PUBLISHED_SQL + operator + '?')
            args.append(value)
    views = "(m.data_json::jsonb->>'views')::numeric"
    rate = f"CASE WHEN {views}>0 THEN (m.data_json::jsonb->>'saves')::numeric/{views} END"
    interaction = f"CASE WHEN {views}>0 THEN ((m.data_json::jsonb->>'likes')::numeric+(m.data_json::jsonb->>'saves')::numeric+(m.data_json::jsonb->>'comments')::numeric)/{views} END"
    orders = {'published_at': PUBLISHED_SQL, 'save_rate': rate, 'interaction_rate': interaction, 'views': views}
    if sort not in orders:
        raise HTTPException(422, detail={'error': '不支持的复盘排序方式'})
    source = ' FROM xhs_workflow_records r LEFT JOIN xhs_workflow_metrics m ON m.publication_id=r.id AND m.checkpoint=? WHERE ' + ' AND '.join(clauses)
    now = datetime.now(UTC)
    with db() as conn:
        total = conn.execute('SELECT COUNT(*)' + source, (checkpoint, *args)).fetchone()[0]
        rows = conn.execute('SELECT r.*,m.data_json AS metric_json,m.revision AS metric_revision' + source + f' ORDER BY {orders[sort]} DESC NULLS LAST,{PUBLISHED_SQL} DESC,r.id LIMIT 20 OFFSET ?', (checkpoint, *args, (page - 1) * 20)).fetchall()
        accounts = conn.execute(f"SELECT {ACCOUNT_SQL} AS id,MAX(COALESCE(NULLIF(r.data_json::jsonb->>'account',''),'未指定账号')) AS name FROM xhs_workflow_records r WHERE r.admin_id=? AND r.kind='publications' AND r.status='published' GROUP BY {ACCOUNT_SQL} ORDER BY name,id", (admin_id,)).fetchall()
    items = []
    for row in rows:
        values = dict(row)
        metric_json, revision = values.pop('metric_json'), values.pop('metric_revision')
        item = _row(values)
        metric = dict(json.loads(metric_json), revision=revision) if metric_json else None
        item['metric'] = metric
        due = datetime.fromisoformat(item['data']['published_at']) + timedelta(days=checkpoint)
        item['due_at'], item['needs_recording'] = due.isoformat(), metric is None and due <= now
        item['save_rate'] = round(metric['saves'] / metric['views'] * 100, 2) if metric and metric['views'] else None
        item['interaction_rate'] = round((metric['likes'] + metric['saves'] + metric['comments']) / metric['views'] * 100, 2) if metric and metric['views'] else None
        items.append(item)
    return {'items': items, 'total': total, 'page': page, 'page_size': 20, 'accounts': [dict(row) for row in accounts]}
