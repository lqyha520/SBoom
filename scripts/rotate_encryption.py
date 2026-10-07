"""使用配置的密钥环重新加密数据库字段；默认仅校验，--apply 写入，任何解密失败整批回滚。

先备份并将旧密钥和新密钥同时放入 ENCRYPTION_KEYS，再设置 ENCRYPTION_ACTIVE_KEY。
全体旧进程退出、新进程加载密钥环后运行；保留旧密钥直到备份保留期结束。
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.db import close_pg_pool, db, init_db
from app.security import decrypt_secret, encrypt_secret


def rotate(*, apply: bool = False) -> dict[str, int | bool]:
    settings = get_settings()
    settings.validate_startup()
    if not settings.encryption_active_key:
        raise ValueError("请先配置 ENCRYPTION_ACTIVE_KEY 与包含新旧密钥的 ENCRYPTION_KEYS")
    prefix = "enc2:" + settings.encryption_active_key + ":"
    checked = changed = 0

    def reencrypt(value: str) -> str:
        nonlocal checked, changed
        if not value:
            return value
        checked += 1
        plain = decrypt_secret(value)
        if not plain:
            raise ValueError("历史字段解密失败；本批次未写入，请恢复旧密钥后重试")
        if value.startswith(prefix):
            return value
        changed += 1
        return encrypt_secret(plain)

    with db(serialized="accounts") as conn:
        for row in conn.execute("SELECT key, value FROM app_config WHERE key IN ('llm', 'image_generation') FOR UPDATE").fetchall():
            value = json.loads(row["value"])
            old = value.get("apiKeyEnc", "")
            value["apiKeyEnc"] = reencrypt(old)
            if apply and old != value["apiKeyEnc"]:
                conn.execute("UPDATE app_config SET value = ? WHERE key = ?", (json.dumps(value, ensure_ascii=False), row["key"]))
        # 固定字段白名单，标识符不能由命令行输入。
        for table, key, column in (("mini_users", "id", "wechat_openid_enc"), ("mini_orders", "id", "payer_enc"),
                                   ("user_llm_configs", "user_id", "api_key_enc")):
            if not conn.execute("SELECT to_regclass(?)", (table,)).fetchone()[0]:
                continue
            rows = conn.execute(f"SELECT {key}, {column} FROM {table} WHERE {column} <> '' FOR UPDATE").fetchall()
            for row in rows:
                value = reencrypt(row[column])
                if apply and value != row[column]:
                    conn.execute(f"UPDATE {table} SET {column} = ? WHERE {key} = ?", (value, row[key]))
    if apply:
        from app.services.app_config import _invalidate_cache
        _invalidate_cache()
    return {"checked": checked, "changed" if apply else "would_change": changed, "applied": apply}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        init_db(migrate=False)
        print(json.dumps(rotate(apply=args.apply)))
    finally:
        close_pg_pool()


if __name__ == "__main__":
    main()
