"""审核队列只索引题目位置与状态；原文仍由生成请求保存。"""


def migrate(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS generation_review_queue (
        user_id INTEGER NOT NULL, request_id TEXT NOT NULL,
        section_index INTEGER NOT NULL, question_index INTEGER NOT NULL,
        created_at BIGINT NOT NULL, finished_at BIGINT NOT NULL,
        quality_status TEXT NOT NULL, has_analysis BOOLEAN NOT NULL,
        PRIMARY KEY(user_id, request_id, section_index, question_index),
        FOREIGN KEY(user_id, request_id) REFERENCES generation_requests(user_id, request_id) ON DELETE CASCADE
    )""")
    conn.execute("""CREATE OR REPLACE FUNCTION lc_rebuild_review_queue(owner_id integer, identifier text)
    RETURNS void AS $$
    DECLARE source generation_requests%ROWTYPE; payload jsonb;
    BEGIN
        DELETE FROM generation_review_queue WHERE user_id=owner_id AND request_id=identifier;
        SELECT * INTO source FROM generation_requests WHERE user_id=owner_id AND request_id=identifier;
        IF NOT FOUND OR source.kind NOT IN ('batch','single','analysis')
            OR source.status NOT IN ('succeeded','failed') THEN RETURN; END IF;
        BEGIN
            payload := COALESCE(NULLIF(CASE WHEN source.status='succeeded' THEN source.result_json
                ELSE source.error_json END, ''), '{}')::jsonb;
        EXCEPTION WHEN invalid_text_representation THEN RETURN;
        END;
        INSERT INTO generation_review_queue(user_id,request_id,section_index,question_index,
                                            created_at,finished_at,quality_status,has_analysis)
        SELECT owner_id,identifier,(s.idx-1)::integer,q.idx::integer,source.created_at,source.finished_at,
               COALESCE(r.status,NULLIF(q.data->>'quality_status',''),'unchecked'),
               COALESCE(q.data->>'analysis','')<>''
        FROM jsonb_array_elements(CASE
            WHEN jsonb_typeof(payload->'sections')='array' THEN payload->'sections'
            WHEN jsonb_typeof(payload->'partial_sections')='array' THEN payload->'partial_sections'
            WHEN jsonb_typeof(payload->'questions')='array' THEN jsonb_build_array(payload)
            ELSE '[]'::jsonb END) WITH ORDINALITY s(data,idx)
        CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(s.data->'questions')='array'
            THEN s.data->'questions' ELSE '[]'::jsonb END) WITH ORDINALITY q(data,idx)
        LEFT JOIN generation_review_items r ON r.request_user_id=owner_id AND r.request_id=identifier
            AND r.section_index=s.idx-1 AND r.question_index=q.idx
        WHERE jsonb_typeof(q.data)='object';
    END;
    $$ LANGUAGE plpgsql""")
    conn.execute("""CREATE OR REPLACE FUNCTION lc_generation_review_queue() RETURNS trigger AS $$
    BEGIN
        IF TG_OP='UPDATE' THEN
            IF ROW(OLD.kind,OLD.status,OLD.created_at,OLD.finished_at,OLD.result_json,OLD.error_json)
                IS NOT DISTINCT FROM ROW(NEW.kind,NEW.status,NEW.created_at,NEW.finished_at,NEW.result_json,NEW.error_json)
                THEN RETURN NEW; END IF;
        END IF;
        PERFORM lc_rebuild_review_queue(NEW.user_id,NEW.request_id);
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql""")
    conn.execute('DROP TRIGGER IF EXISTS lc_generation_review_queue ON generation_requests')
    conn.execute("""CREATE TRIGGER lc_generation_review_queue
        AFTER INSERT OR UPDATE OF kind,status,created_at,finished_at,result_json,error_json ON generation_requests
        FOR EACH ROW EXECUTE FUNCTION lc_generation_review_queue()""")
    # 审核状态单独修改时也保持一致；请求写回、历史迁移与旧版本应用均走同一边界。
    conn.execute("""CREATE OR REPLACE FUNCTION lc_generation_review_status() RETURNS trigger AS $$
    BEGIN
        IF TG_OP='DELETE' THEN
            PERFORM lc_rebuild_review_queue(OLD.request_user_id,OLD.request_id);
            RETURN OLD;
        END IF;
        PERFORM lc_rebuild_review_queue(NEW.request_user_id,NEW.request_id);
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql""")
    conn.execute('DROP TRIGGER IF EXISTS lc_generation_review_status ON generation_review_items')
    conn.execute("""CREATE TRIGGER lc_generation_review_status AFTER INSERT OR UPDATE OF status OR DELETE
        ON generation_review_items FOR EACH ROW EXECUTE FUNCTION lc_generation_review_status()""")
    # 迁移在版本锁内回填，失败整笔回滚；再次执行保持相同内容。
    conn.execute("SELECT lc_rebuild_review_queue(user_id,request_id) FROM generation_requests "
                 "WHERE kind IN ('batch','single','analysis') AND status IN ('succeeded','failed')")
    ordering = '((-created_at),user_id,request_id,section_index,question_index)'
    conn.execute('CREATE INDEX IF NOT EXISTS idx_review_queue_order ON generation_review_queue ' + ordering)
    conn.execute('CREATE INDEX IF NOT EXISTS idx_review_queue_pending ON generation_review_queue ' + ordering
                 + " WHERE quality_status<>'passed' OR NOT has_analysis")
    conn.execute('CREATE INDEX IF NOT EXISTS idx_review_queue_status ON generation_review_queue '
                 '(quality_status,(-created_at),user_id,request_id,section_index,question_index)')
