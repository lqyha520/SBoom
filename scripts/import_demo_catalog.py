"""One-time, explicit import of a local demo catalog into the configured database.

Back up the destination first, initialize its schema, and pass --apply to write.
Workbench accounts, private-only archives, model settings and secrets are excluded.
"""

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: F401  导入期触发 .env 加载（db 连接串等）
from app.db import db
from app.services.paper_storage import LocalStorage, _key

MARKER = "local_demo_catalog_import_v1"
CHILD_TABLES = (
    "catalog_access", "catalog_question_types", "catalog_type_rules",
    "mini_catalog_favorites", "mini_catalog_downloads", "mini_membership_events",
)
TABLES = ("mini_users", "mini_user_sessions", "paper_archives", "paper_assets", "catalog_papers", *CHILD_TABLES)


def read_snapshot(source_db, source_files):
    source_db = Path(source_db).resolve(strict=True)
    source_files = Path(source_files).resolve(strict=True)
    with closing(sqlite3.connect(source_db.as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or conn.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("The source database failed its integrity check")
        source_users = {row["username"] for row in conn.execute("SELECT username FROM users")}
        if source_users != {"admin_console", "ui_teacher"}:
            raise ValueError("This importer accepts the isolated UI demo only")
        rows = {}
        for table in TABLES:
            query = f"SELECT * FROM {table}"
            if table == "paper_archives":
                query += " WHERE id IN (SELECT paper_id FROM catalog_papers)"
            elif table == "paper_assets":
                query += " WHERE paper_id IN (SELECT paper_id FROM catalog_papers)"
            rows[table] = [dict(row) for row in conn.execute(query)]
        if not rows["catalog_papers"] or not rows["mini_users"]:
            raise ValueError("The source does not contain a consumer catalog")

    assets = []
    for asset in rows["paper_assets"]:
        if asset["storage"] != "local":
            raise ValueError("Remote demo files are not supported")
        path = (source_files / _key(asset["storage_key"])).resolve(strict=True)
        if not path.is_relative_to(source_files):
            raise ValueError("A demo file escapes its storage directory")
        with path.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        if path.stat().st_size != asset["byte_size"] or checksum != asset["sha256"]:
            raise ValueError("A demo file is missing or damaged")
        assets.append((asset, path))
    for archive in rows["paper_archives"]:
        files = [asset for asset, _ in assets if asset["paper_id"] == archive["id"]]
        if archive["file_status"] == "uploading":
            raise ValueError("Finish or cancel in-flight uploads before importing")
        if archive["file_status"] == "ready" and (
            sum(asset["kind"] == "pdf" for asset in files) != 1
            or {asset["page_number"] for asset in files if asset["kind"] == "page"}
            != set(range(1, archive["page_count"] + 1))
        ):
            raise ValueError("A ready exercise has an incomplete file manifest")
    return rows, assets


def insert_rows(conn, table, rows):
    if table not in (*TABLES, "paper_series"):
        raise ValueError("Unsupported import table")
    for row in rows:
        columns = list(row)
        if not all(re.fullmatch(r"[a-z_][a-z0-9_]*", column) for column in columns):
            raise ValueError("Invalid source columns")
        conn.execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                     [row[column] for column in columns])


def import_catalog(source_db, source_files, publisher_id, *, apply=False):
    rows, assets = read_snapshot(source_db, source_files)
    fingerprint = hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    report = {"source_fingerprint": fingerprint, "publisher_id": publisher_id,
              "counts": {table: len(items) for table, items in rows.items()},
              "file_bytes": sum(asset["byte_size"] for asset, _ in assets)}
    storage = LocalStorage()
    with db(serialized=True) as conn:
        previous = conn.execute("SELECT value FROM app_config WHERE key = ?", (MARKER,)).fetchone()
        if previous:
            saved = json.loads(previous["value"])
            if saved["source_fingerprint"] != fingerprint or saved["publisher_id"] != publisher_id:
                raise ValueError("Another demo import has already been recorded; nothing was overwritten")
            return {**saved, "status": "already_imported"}
        publisher = conn.execute("SELECT role, is_active FROM users WHERE id = ?", (publisher_id,)).fetchone()
        if not publisher or publisher["role"] != "admin" or not publisher["is_active"]:
            raise ValueError("Select an existing, active workbench administrator as publisher")
        for table in ("mini_users", "catalog_papers", "catalog_type_rules"):
            if conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]:
                raise ValueError("The destination already contains consumer data; no automatic merge is allowed")
        if not apply:
            return {**report, "status": "dry_run"}

        # Verify the complete source first. Never overwrite a destination file.
        for asset, source in assets:
            asset["storage_key"] = f"imports/{fingerprint[:24]}/{asset['id']}"
            destination = storage.path(asset["storage_key"])
            if destination.exists():
                with destination.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != asset["sha256"]:
                        raise ValueError("An existing destination file does not match the source")
            else:
                storage.put(asset["storage_key"], source.read_bytes(), asset["mime_type"])
        series: dict[str, int] = {}
        for archive in rows["paper_archives"]:
            archive.update(user_id=publisher_id, folder_id=None, favorite=0,
                           upload_token="", upload_started_at=0, upload_reserved_bytes=0)
            series[archive["source_id"]] = max(series.get(archive["source_id"], 0), archive["version"])
        for paper in rows["catalog_papers"]:
            paper["publisher_id"] = publisher_id
        for event in rows["mini_membership_events"]:
            # The fixture administrator is not a real production administrator.
            event["admin_id"] = None
        insert_rows(conn, "paper_series", [
            {"user_id": publisher_id, "source_id": source_id, "version": version}
            for source_id, version in series.items()
        ])
        for table in TABLES:
            insert_rows(conn, table, rows[table])
        report.update(imported_at=int(time.time()))
        conn.execute("INSERT INTO app_config(key, value) VALUES (?, ?)", (MARKER, json.dumps(report)))
    return {**report, "status": "imported"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", required=True, type=Path)
    parser.add_argument("--source-files", required=True, type=Path)
    parser.add_argument("--publisher-id", required=True, type=int)
    parser.add_argument("--apply", action="store_true", help="Write after backing up and initializing the destination")
    args = parser.parse_args()
    result = import_catalog(args.source_db, args.source_files, args.publisher_id, apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
