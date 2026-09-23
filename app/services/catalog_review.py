"""Record explicit human confirmation; file mode is not content verification."""
import json
import time


def confirm(conn, catalog_id, admin_id):
    row = conn.execute("SELECT c.paper_id, c.revision, a.snapshot_json FROM catalog_papers c JOIN paper_archives a ON a.id = c.paper_id WHERE c.id = ?", (catalog_id,)).fetchone()
    mode = json.loads(row["snapshot_json"])["export_options"].get("mode")
    answers = "included" if mode in ("answersOnly", "withAnswers") else "missing"
    if conn.execute("SELECT 1 FROM catalog_print_editions WHERE catalog_id = ? AND kind = 'answers'", (catalog_id,)).fetchone():
        answers = "separate"
    now = int(time.time())
    conn.execute("UPDATE catalog_papers SET reviewed_at = ?, reviewed_by = ?, answer_readiness = ? WHERE id = ?", (now, admin_id, answers, catalog_id))
    conn.execute("INSERT INTO catalog_reviews(catalog_id, paper_id, admin_id, revision, reviewed_at, answer_readiness) VALUES (?, ?, ?, ?, ?, ?)",
                 (catalog_id, row["paper_id"], admin_id, row["revision"], now, answers))
