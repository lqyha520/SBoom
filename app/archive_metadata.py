"""归档难度和导出模式在写入时派生，公开详情无需解析完整题目快照。"""


def migrate(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS generation_tombstones (user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, request_id TEXT NOT NULL, PRIMARY KEY(user_id, request_id))")
    conn.execute("ALTER TABLE paper_archives ADD COLUMN IF NOT EXISTS difficulty TEXT")
    conn.execute("ALTER TABLE paper_archives ADD COLUMN IF NOT EXISTS export_mode TEXT NOT NULL DEFAULT 'student'")
    conn.execute("""CREATE OR REPLACE FUNCTION lc_archive_metadata() RETURNS trigger AS $$
    DECLARE payload jsonb;
    BEGIN
      BEGIN
        payload := NEW.snapshot_json::jsonb;
        NEW.difficulty := payload->'paper'->>'difficulty';
        NEW.export_mode := COALESCE(payload->'export_options'->>'mode', 'student');
      EXCEPTION WHEN invalid_text_representation THEN
        NEW.difficulty := NULL;
        NEW.export_mode := 'student';
      END;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql""")
    conn.execute("DROP TRIGGER IF EXISTS lc_archive_metadata ON paper_archives")
    conn.execute("CREATE TRIGGER lc_archive_metadata BEFORE INSERT OR UPDATE OF snapshot_json ON paper_archives FOR EACH ROW EXECUTE FUNCTION lc_archive_metadata()")
    conn.execute("UPDATE paper_archives SET snapshot_json = snapshot_json")
