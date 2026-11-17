"""小红书教育选题调研任务与公开笔记快照。"""

from app.xhs_research_time import capture_time


def migrate(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS xhs_research_tasks (
        id TEXT PRIMARY KEY,
        created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
        grade TEXT NOT NULL,
        subject TEXT NOT NULL,
        keyword TEXT NOT NULL DEFAULT '',
        period TEXT NOT NULL,
        sort_by TEXT NOT NULL,
        note_limit INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued',
        note_count INTEGER NOT NULL DEFAULT 0,
        error TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS')),
        finished_at TEXT NOT NULL DEFAULT ''
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS xhs_research_items (
        id BIGSERIAL PRIMARY KEY,
        task_id TEXT NOT NULL REFERENCES xhs_research_tasks(id) ON DELETE CASCADE,
        note_id TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        author TEXT NOT NULL DEFAULT '',
        published_text TEXT NOT NULL DEFAULT '',
        likes_text TEXT NOT NULL DEFAULT '',
        likes_count BIGINT,
        url TEXT NOT NULL DEFAULT '',
        sort_rank INTEGER NOT NULL DEFAULT 0,
        captured_at TEXT NOT NULL DEFAULT '',
        UNIQUE(task_id, note_id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_xhs_research_tasks_created ON xhs_research_tasks(created_at DESC, id DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_xhs_tasks_owner_created ON xhs_research_tasks(created_by,created_at DESC,id DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_xhs_research_items_task_likes ON xhs_research_items(task_id, likes_count DESC NULLS LAST)")
    conn.execute("ALTER TABLE xhs_research_tasks ADD COLUMN IF NOT EXISTS batch_id TEXT NOT NULL DEFAULT ''")
    conn.execute("ALTER TABLE xhs_research_tasks ADD COLUMN IF NOT EXISTS batch_position INTEGER NOT NULL DEFAULT 0")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_xhs_tasks_batch ON xhs_research_tasks(created_by, batch_id, batch_position)")
    fields = """
        note_id TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '', author TEXT NOT NULL DEFAULT '',
        published_text TEXT NOT NULL DEFAULT '', likes_text TEXT NOT NULL DEFAULT '', likes_count BIGINT,
        url TEXT NOT NULL, captured_at TEXT NOT NULL DEFAULT '',
        grade TEXT NOT NULL, subject TEXT NOT NULL, keyword TEXT NOT NULL DEFAULT '',
        period TEXT NOT NULL, sort_by TEXT NOT NULL
    """
    conn.execute(f"CREATE TABLE IF NOT EXISTS xhs_research_notes ({fields}, PRIMARY KEY(note_id))")
    conn.execute("ALTER TABLE xhs_research_notes ADD COLUMN IF NOT EXISTS captured_epoch DOUBLE PRECISION")
    conn.execute(f"""CREATE TABLE IF NOT EXISTS xhs_research_observations (
        id BIGSERIAL PRIMARY KEY, {fields}, task_id TEXT NOT NULL,
        FOREIGN KEY(note_id) REFERENCES xhs_research_notes(note_id), UNIQUE(task_id, note_id)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_xhs_observations_note ON xhs_research_observations(note_id, id DESC)")
    conn.execute("""CREATE TABLE IF NOT EXISTS xhs_research_marks (
        admin_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        note_id TEXT NOT NULL REFERENCES xhs_research_notes(note_id),
        favorite BOOLEAN NOT NULL DEFAULT FALSE,
        status TEXT NOT NULL DEFAULT '' CHECK(status IN ('', 'reference', 'planned', 'done', 'irrelevant')),
        remark TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY(admin_id, note_id)
    )""")
    columns = "note_id,title,author,published_text,likes_text,likes_count,url,captured_at,grade,subject,keyword,period,sort_by"
    selection = "i.note_id,i.title,i.author,i.published_text,i.likes_text,i.likes_count,i.url,i.captured_at,t.grade,t.subject,t.keyword,t.period,t.sort_by"
    conn.execute(f"""INSERT INTO xhs_research_notes({columns})
        SELECT DISTINCT ON (i.note_id) {selection} FROM xhs_research_items i
        JOIN xhs_research_tasks t ON t.id=i.task_id ORDER BY i.note_id, i.id DESC
        ON CONFLICT(note_id) DO NOTHING""")
    # 独立保留采集记录，删除任务不再丢失收藏和历史点赞快照。
    conn.execute(f"""INSERT INTO xhs_research_observations({columns},task_id)
        SELECT {selection},i.task_id FROM xhs_research_items i JOIN xhs_research_tasks t ON t.id=i.task_id
        ORDER BY i.id ON CONFLICT(task_id,note_id) DO NOTHING""")
    # 与运行时共用 ISO 解析；PG 接受的 now 等相对时间不能变成较新快照。
    # 按主键分批回填，避免将全部历史笔记拉入迁移进程内存。
    last_note = ''
    while rows := conn.execute("""SELECT note_id,captured_at FROM xhs_research_notes
        WHERE note_id>? AND (captured_epoch IS NULL OR captured_epoch='-Infinity'::double precision)
        ORDER BY note_id LIMIT 1000""", (last_note,)).fetchall():
        conn.executemany('UPDATE xhs_research_notes SET captured_epoch=? WHERE note_id=?',
                         [(capture_time(row['captured_at']).timestamp(), row['note_id']) for row in rows])
        last_note = rows[-1]['note_id']
    conn.execute("ALTER TABLE xhs_research_notes ALTER COLUMN captured_epoch SET DEFAULT '-Infinity'")
    conn.execute("ALTER TABLE xhs_research_notes ALTER COLUMN captured_epoch SET NOT NULL")
