"""个人题库保存不可变题目内容，元数据可编辑，选题复用无需模型调用。"""

import hashlib
import json
import time
import uuid

from fastapi import HTTPException

from app.db import db


def item(row):
    data = json.loads(row['content_json'])
    return {key: row[key] for key in ('id', 'title', 'grade', 'subject', 'topic', 'difficulty', 'section_type', 'revision', 'created_at', 'updated_at')} | data


def save(user_id, body):
    questions = []
    for question in body.questions:
        value = question.model_dump(exclude_none=True)
        value.pop('id', None)
        # 复用资料仍须在新试卷核对，客户端提交的模型复核状态不能成为可信证明。
        value.update(quality_status='unchecked', quality_issues=[])
        questions.append(value)
    content = json.dumps({'passage': body.passage, 'questions': questions}, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(json.dumps([body.grade, body.subject, body.section_type, content], ensure_ascii=False).encode()).hexdigest()
    now = int(time.time())
    with db(serialized=True) as conn:
        row = conn.execute('SELECT * FROM question_bank WHERE user_id=? AND content_hash=?', (user_id, digest)).fetchone()
        if row:
            return item(row)
        if conn.execute('SELECT COUNT(*) FROM question_bank WHERE user_id=?', (user_id,)).fetchone()[0] >= 5000:
            raise HTTPException(422, detail={'error': '题库已达 5000 条，请先整理旧题'})
        identifier = uuid.uuid4().hex
        conn.execute('INSERT INTO question_bank(id,user_id,title,grade,subject,topic,difficulty,section_type,content_json,content_hash,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                     (identifier, user_id, body.title, body.grade, body.subject, body.topic, body.difficulty, body.section_type, content, digest, now, now))
        return item(conn.execute('SELECT * FROM question_bank WHERE id=?', (identifier,)).fetchone())


def listing(user_id, q='', grade='', subject='', section_type='', difficulty='', limit=20, offset=0):
    conditions, args = ['user_id=?'], [user_id]
    for field, value in (('grade', grade), ('subject', subject), ('section_type', section_type), ('difficulty', difficulty)):
        if value:
            conditions.append(f'{field}=?')
            args.append(value)
    if q.strip():
        pattern = '%' + q.strip().lower().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        conditions.append("(LOWER(title) LIKE ? ESCAPE '\\' OR LOWER(topic) LIKE ? ESCAPE '\\' OR LOWER(content_json) LIKE ? ESCAPE '\\')")
        args.extend([pattern] * 3)
    where = ' AND '.join(conditions)
    with db() as conn:
        scopes = conn.execute('SELECT grade,subject,COUNT(*) AS count FROM question_bank WHERE user_id=? GROUP BY grade,subject ORDER BY grade,subject', (user_id,)).fetchall()
        total = conn.execute(f'SELECT COUNT(*) FROM question_bank WHERE {where}', args).fetchone()[0]
        rows = conn.execute(f'SELECT * FROM question_bank WHERE {where} ORDER BY updated_at DESC,id DESC LIMIT ? OFFSET ?', [*args, limit, offset]).fetchall()
    available: dict[str, list[str]] = {}
    for scope in scopes:
        available.setdefault(scope['grade'], []).append(scope['subject'])
    return {'items': [item(r) for r in rows], 'total': total, 'has_more': offset + len(rows) < total,
            'bank_total': sum(scope['count'] for scope in scopes), 'available': available}


def select(user_id, ids):
    with db() as conn:
        rows = {r['id']: r for r in conn.execute('SELECT * FROM question_bank WHERE user_id=? AND id=ANY(?)', (user_id, ids)).fetchall()}
    if any(identifier not in rows for identifier in ids):
        raise HTTPException(404, detail={'error': '部分题目已删除或不属于当前账号，请刷新'})
    items = [item(rows[identifier]) for identifier in ids]
    if len({(r['grade'], r['subject']) for r in items}) != 1:
        raise HTTPException(422, detail={'error': '请选择同一年级、同一学科的题目组卷'})
    if sum(len(r['questions']) for r in items) > 300:
        raise HTTPException(422, detail={'error': '一次组卷最多 300 道题'})
    return {'items': items, 'total': len(items), 'has_more': False}


def update(user_id, identifier, body):
    with db() as conn:
        row = conn.execute('SELECT * FROM question_bank WHERE id=? AND user_id=? FOR UPDATE', (identifier, user_id)).fetchone()
        if not row:
            raise HTTPException(404, detail={'error': '题目不存在'})
        if row['revision'] != body.revision:
            raise HTTPException(409, detail={'error': '题目已更新，请刷新后重试'})
        conn.execute('UPDATE question_bank SET title=?,topic=?,difficulty=?,revision=revision+1,updated_at=? WHERE id=?',
                     (body.title, body.topic, body.difficulty, int(time.time()), identifier))
        return item(conn.execute('SELECT * FROM question_bank WHERE id=?', (identifier,)).fetchone())


def remove(user_id, identifier, revision):
    with db() as conn:
        row = conn.execute('SELECT revision FROM question_bank WHERE id=? AND user_id=? FOR UPDATE', (identifier, user_id)).fetchone()
        if not row:
            raise HTTPException(404, detail={'error': '题目不存在'})
        if row['revision'] != revision:
            raise HTTPException(409, detail={'error': '题目已更新，请刷新后重试'})
        conn.execute('DELETE FROM question_bank WHERE id=?', (identifier,))
