"""小红书公开搜索卡片采集任务与快照存储。"""

import re
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from app.db import db
from app.xhs_research_time import capture_time as _capture_time


def _task(row) -> dict:
    item = dict(row)
    likes = item.get("median_likes")
    average = item.get("average_likes")
    return {
        "id": item["id"], "grade": item["grade"], "subject": item["subject"],
        "keyword": item["keyword"], "period": item["period"], "sort_by": item["sort_by"],
        "note_limit": item["note_limit"], "status": item["status"], "note_count": item["note_count"],
        "error": item["error"], "created_at": item["created_at"], "finished_at": item["finished_at"],
        "batch_id": item.get("batch_id", ""), "batch_position": item.get("batch_position", 0),
        "median_likes": round(float(likes)) if likes is not None else None,
        "average_likes": round(float(average)) if average is not None else None,
    }


def create_task(admin_id: int, grade: str, subject: str, keyword: str, period: str,
                sort_by: str, note_limit: int) -> dict:
    task_id = str(uuid4())
    with db() as conn:
        conn.execute(
            "INSERT INTO xhs_research_tasks(id, created_by, grade, subject, keyword, period, sort_by, note_limit) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, admin_id, grade, subject, keyword, period, sort_by, note_limit),
        )
    return get_task(admin_id, task_id)


def list_tasks(admin_id: int, limit: int = 10, offset: int = 0) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "WITH page AS (SELECT * FROM xhs_research_tasks WHERE created_by=? "
            "ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?) "
            "SELECT t.*,s.median_likes,s.average_likes FROM page t LEFT JOIN LATERAL "
            "(SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY likes_count) AS median_likes, "
            "AVG(likes_count) AS average_likes FROM xhs_research_items "
            "WHERE task_id=t.id AND likes_count IS NOT NULL) s ON TRUE ORDER BY t.created_at DESC,t.id DESC",
            (admin_id, limit, offset)
        ).fetchall()
    return [_task(row) for row in rows]


def count_tasks(admin_id: int) -> int:
    with db() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM xhs_research_tasks WHERE created_by=?", (admin_id,)).fetchone()
    return int(row["total"])


def _owned_task(conn, admin_id: int, task_id: str):
    row = conn.execute("SELECT * FROM xhs_research_tasks WHERE id=? AND created_by=?", (task_id, admin_id)).fetchone()
    if not row:
        raise HTTPException(404, detail={"error": "采集任务不存在或不属于当前账号"})
    return row


def get_task(admin_id: int, task_id: str) -> dict:
    with db() as conn:
        row = _owned_task(conn, admin_id, task_id)
        notes = conn.execute(
            "SELECT note_id, title, author, published_text, likes_text, likes_count, url, sort_rank, captured_at "
            "FROM xhs_research_items WHERE task_id = ? ORDER BY likes_count DESC NULLS LAST, sort_rank, id",
            (task_id,),
        ).fetchall()
        stats = conn.execute(
            "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY likes_count) AS median_likes, "
            "AVG(likes_count) AS average_likes FROM xhs_research_items WHERE task_id = ? AND likes_count IS NOT NULL",
            (task_id,),
        ).fetchone()
    result = _task(row)
    result["median_likes"] = round(float(stats["median_likes"])) if stats["median_likes"] is not None else None
    result["average_likes"] = round(float(stats["average_likes"])) if stats["average_likes"] is not None else None
    result["items"] = [dict(note) for note in notes]
    return result


def start_task(admin_id: int, task_id: str) -> dict:
    with db(lock_key=("xhs_research", str(admin_id))) as conn:
        row = _owned_task(conn, admin_id, task_id)
        if row["status"] not in ("queued", "failed", "running"):
            raise HTTPException(409, detail={"error": "当前任务状态不能启动，请刷新列表"})
        conn.execute("UPDATE xhs_research_tasks SET status = 'running', error = '', finished_at = '' WHERE id = ?", (task_id,))
    return get_task(admin_id, task_id)


def fail_task(admin_id: int, task_id: str, error: str) -> dict:
    with db(lock_key=("xhs_research", str(admin_id))) as conn:
        row = _owned_task(conn, admin_id, task_id)
        if row["status"] != "running":
            raise HTTPException(409, detail={"error": "任务已结束，不能覆盖当前状态"})
        conn.execute("UPDATE xhs_research_tasks SET status = 'failed', error = ?, finished_at = datetime('now','localtime') WHERE id = ?",
                     (error[:500], task_id))
    return get_task(admin_id, task_id)


def save_items(admin_id: int, task_id: str, rows: list[dict]) -> dict:
    # IDs are derived from note URLs after strict host/path validation in the router.
    seen: set[str] = set()
    normalized: list[dict] = []
    for item in rows:
        match = re.search(r"/(?:search_result|explore)/([A-Za-z0-9_-]{8,80})", item["url"])
        note_id = match.group(1) if match else ""
        if not note_id or note_id in seen:
            continue
        seen.add(note_id)
        normalized.append({**item, "note_id": note_id})

    with db(lock_key=("xhs_research", str(admin_id))) as conn:
        task = _owned_task(conn, admin_id, task_id)
        if task["status"] == "completed":
            # 页面重开后可以重交本机缓存，已保存的任务不重复写入。
            return _completed_task(conn, task)
        if task["status"] != "running":
            raise HTTPException(409, detail={"error": "请先启动任务再提交采集结果"})
        if len(normalized) > task["note_limit"]:
            normalized = normalized[:task["note_limit"]]
        _save_observations(conn, task, normalized)
        conn.execute("DELETE FROM xhs_research_items WHERE task_id = ?", (task_id,))
        if normalized:
            conn.executemany(
                "INSERT INTO xhs_research_items(task_id, note_id, title, author, published_text, likes_text, "
                "likes_count, url, sort_rank, captured_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(task_id, item["note_id"], item["title"], item["author"], item["published_text"],
                  item["likes_text"], item["likes_count"], item["url"], item["sort_rank"], item["captured_at"])
                 for item in normalized],
            )
        conn.execute(
            "UPDATE xhs_research_tasks SET status = 'completed', note_count = ?, "
            "finished_at = datetime('now','localtime') WHERE id = ?",
            (len(normalized), task_id),
        )
    return get_task(admin_id, task_id)


def _completed_task(conn, task) -> dict:
    result = _task(task)
    result["items"] = [dict(row) for row in conn.execute(
        "SELECT note_id,title,author,published_text,likes_text,likes_count,url,sort_rank,captured_at "
        "FROM xhs_research_items WHERE task_id=? ORDER BY likes_count DESC NULLS LAST,id", (task["id"],)
    ).fetchall()]
    stats = conn.execute('SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY likes_count) AS median_likes, '
                         'AVG(likes_count) AS average_likes FROM xhs_research_items WHERE task_id=? AND likes_count IS NOT NULL',
                         (task['id'],)).fetchone()
    for name in ('median_likes', 'average_likes'):
        result[name] = round(float(stats[name])) if stats[name] is not None else None
    return result


def _save_observations(conn, task, notes: list[dict]) -> None:
    columns = "note_id,title,author,published_text,likes_text,likes_count,url,captured_at,grade,subject,keyword,period,sort_by"
    for note in sorted(notes, key=lambda item: item['note_id']):
        values = tuple(note[name] for name in columns.split(',')[:8]) + tuple(task[name] for name in columns.split(',')[8:])
        # 条件在 upsert 行锁内检查，跨管理员并发或恢复旧任务都不能覆盖较新的快照。
        conn.execute(
            f"INSERT INTO xhs_research_notes({columns},captured_epoch) VALUES ({','.join('?' for _ in range(len(values) + 1))}) "
            "ON CONFLICT(note_id) DO UPDATE SET " + ','.join(f"{name}=excluded.{name}" for name in columns.split(',')[1:]) +
            ",captured_epoch=excluded.captured_epoch WHERE excluded.captured_epoch>=xhs_research_notes.captured_epoch",
            (*values, _capture_time(note['captured_at']).timestamp()),
        )
        conn.execute(f"INSERT INTO xhs_research_observations({columns},task_id) "
                     f"VALUES ({','.join('?' for _ in range(len(values) + 1))}) ON CONFLICT(task_id,note_id) DO NOTHING",
                     (*values, task["id"]))


def create_batch(admin_id: int, common: dict, keywords: list[str]) -> dict:
    batch_id = str(uuid4())
    with db() as conn:
        for position, keyword in enumerate(dict.fromkeys(word.strip() for word in keywords)):
            conn.execute("INSERT INTO xhs_research_tasks(id,created_by,grade,subject,keyword,period,sort_by,note_limit,batch_id,batch_position) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?)", (str(uuid4()), admin_id, common['grade'], common['subject'], keyword,
                         common['period'], common['sort_by'], common['note_limit'], batch_id, position))
    return get_batch(admin_id, batch_id)


def get_batch(admin_id: int, batch_id: str) -> dict:
    with db() as conn:
        rows = conn.execute("SELECT * FROM xhs_research_tasks WHERE batch_id=? AND created_by=? ORDER BY batch_position",
                            (batch_id, admin_id)).fetchall()
    if not rows:
        raise HTTPException(404, detail={"error": "队列不存在"})
    return {"id": batch_id, "items": [_task(row) for row in rows]}


def list_batches(admin_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute("SELECT batch_id AS id, MAX(created_at) AS created_at, COUNT(*) AS total, "
                            "COUNT(*) FILTER (WHERE status='completed') AS completed FROM xhs_research_tasks "
                            "WHERE created_by=? AND batch_id<>'' GROUP BY batch_id ORDER BY MAX(created_at) DESC,batch_id DESC LIMIT 20",
                            (admin_id,)).fetchall()
    return [dict(row) for row in rows]


def _like(value: str) -> str:
    return '%' + value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


def list_notes(admin_id: int, *, task_id: str = '', q: str = '', author: str = '', exclude: str = '',
               min_likes: int | None = None, favorite_only: bool = False, status: str = 'all',
               hide_seen: bool = False, sort: str = 'likes_desc', page: int = 1, page_size: int = 20,
               note_ids: list[str] | None = None) -> dict:
    source = 'xhs_research_observations' if task_id else 'xhs_research_notes'
    clauses: list[str] = []
    params: list[Any] = [admin_id]
    if task_id:
        clauses.append('n.task_id=?')
        params.append(task_id)
    for value, column in ((q.strip(), 'n.title'), (author.strip(), 'n.author')):
        if value:
            clauses.append(f'{column} ILIKE ?')
            params.append(_like(value))
    for word in (word.strip() for word in re.split(r'[,，、;；\n]+', exclude) if word.strip()):
        clauses.append("(n.title || ' ' || n.author) NOT ILIKE ?")
        params.append(_like(word))
    if min_likes is not None:
        clauses.append('n.likes_count>=?')
        params.append(min_likes)
    if favorite_only:
        clauses.append('m.favorite=TRUE')
    if status != 'all':
        clauses.append("COALESCE(m.status,'')=?")
        params.append(status)
    seen = ('EXISTS(SELECT 1 FROM xhs_research_observations prev WHERE prev.note_id=n.note_id AND prev.id<n.id)'
            if task_id else 'EXISTS(SELECT 1 FROM xhs_research_observations prev WHERE prev.note_id=n.note_id OFFSET 1 LIMIT 1)')
    if hide_seen:
        clauses.append(f'NOT ({seen})')
    if note_ids is not None:
        clauses.append('n.note_id=ANY(?)')
        params.append(note_ids)
    joined = f"FROM {source} n LEFT JOIN xhs_research_marks m ON m.note_id=n.note_id AND m.admin_id=? "
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    ordering = {'likes_desc': 'n.likes_count DESC NULLS LAST', 'likes_asc': 'n.likes_count ASC NULLS LAST',
                'latest': 'n.captured_at DESC', 'earliest': 'n.captured_at ASC'}[sort]
    with db() as conn:
        if task_id:
            _owned_task(conn, admin_id, task_id)
        total = conn.execute('SELECT COUNT(*) ' + joined + where, tuple(params)).fetchone()[0]
        rows = conn.execute("SELECT n.*,COALESCE(m.favorite,FALSE) AS favorite,COALESCE(m.status,'') AS mark_status, "
                            "COALESCE(m.remark,'') AS remark,COALESCE(m.revision,0) AS revision, "
                            "(SELECT COUNT(*) FROM xhs_research_observations o WHERE o.note_id=n.note_id) AS seen_count, "
                            f"({seen}) AS seen_before " + joined + where + f' ORDER BY {ordering},n.note_id LIMIT ? OFFSET ?',
                            (*params, page_size, (page - 1) * page_size)).fetchall()
    return {'items': [dict(row) for row in rows], 'total': total, 'page': page, 'page_size': page_size}


def get_note(admin_id: int, note_id: str) -> dict:
    result = list_notes(admin_id, note_ids=[note_id], page_size=1)
    if not result['items']:
        raise HTTPException(404, detail={'error': '参考笔记不存在'})
    return dict(result['items'][0])


def save_mark(admin_id: int, note_id: str, favorite: bool, status: str, remark: str, revision: int) -> dict:
    with db(lock_key=('xhs_research', str(admin_id))) as conn:
        if not conn.execute('SELECT 1 FROM xhs_research_notes WHERE note_id=?', (note_id,)).fetchone():
            raise HTTPException(404, detail={'error': '笔记不存在'})
        current = conn.execute('SELECT revision FROM xhs_research_marks WHERE admin_id=? AND note_id=?',
                               (admin_id, note_id)).fetchone()
        if (current['revision'] if current else 0) != revision:
            raise HTTPException(409, detail={'error': '该笔记标记已在其他页面更新，请刷新后重试'})
        row = conn.execute('INSERT INTO xhs_research_marks(admin_id,note_id,favorite,status,remark,revision) VALUES (?,?,?,?,?,?) '
                           'ON CONFLICT(admin_id,note_id) DO UPDATE SET favorite=excluded.favorite,status=excluded.status, '
                           'remark=excluded.remark,revision=excluded.revision RETURNING favorite,status AS mark_status,remark,revision',
                           (admin_id, note_id, favorite, status, remark, revision + 1)).fetchone()
    return dict(row)


def note_history(note_id: str, page: int = 1) -> dict:
    with db() as conn:
        rows = conn.execute('SELECT task_id,grade,subject,keyword,period,sort_by,likes_text,likes_count,captured_at '
                            'FROM xhs_research_observations WHERE note_id=? ORDER BY id DESC LIMIT 20 OFFSET ?',
                            (note_id, (page - 1) * 20)).fetchall()
        total = conn.execute('SELECT COUNT(*) FROM xhs_research_observations WHERE note_id=?', (note_id,)).fetchone()[0]
    return {'items': [dict(row) for row in rows], 'total': total, 'page': page, 'page_size': 20}


def delete_task(admin_id: int, task_id: str) -> None:
    with db(lock_key=('xhs_research', str(admin_id))) as conn:
        _owned_task(conn, admin_id, task_id)
        conn.execute("DELETE FROM xhs_research_tasks WHERE id=? AND created_by=?", (task_id, admin_id))
