# -*- coding: utf-8 -*-
"""后台管理系统全链路验证：角色/权限/用户管理/缓存/日志"""
import os

import httpx

BASE = os.environ.get("LC_TEST_BASE", "http://127.0.0.1:8000")
passed, failed = 0, 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def register_or_login(c, username, password):
    r = c.post("/api/v1/auth/register", json={"username": username, "password": password})
    if r.status_code == 409:
        r = c.post("/api/v1/auth/login", json={"username": username, "password": password})
    return r


admin = httpx.Client(base_url=BASE, timeout=60)  # 生成请求含 LLM 重试退避（~7s），需放宽超时
r = admin.post("/api/v1/auth/login", json={"username": "admin_root", "password": "admin-pass-123"})
if r.status_code != 200:
    print(f"无法准备管理员账号: {r.status_code} {r.text[:200]}")
    print("请仅在可丢弃测试环境中显式配置 ADMIN_USERNAME=admin_root 和对应密码，不要使用真实数据库。")
    exit(1)
admin_id = r.json()["id"]
role = r.json().get("role")

if role != "admin":
    print("SKIP: admin_root 不是管理员。公开注册始终只创建普通用户。")
    print("      推荐运行 python tests/run_ui_contracts.py，使用自动隔离的测试服务。")
    exit(0)

print("== 1. 普通用户访问管理端应被拒 403 ==")
norm = httpx.Client(base_url=BASE)
r = register_or_login(norm, "norm_user", "norm-pass-123")
check("norm_user 注册为普通用户", r.status_code == 200 and r.json().get("role") == "user", r.text[:200])
r = norm.get("/api/v1/admin/stats")
check("stats 普通用户 403", r.status_code == 403, f"got {r.status_code}")
r = norm.get("/api/v1/admin/users")
check("users 普通用户 403", r.status_code == 403, f"got {r.status_code}")
r = norm.put("/api/v1/admin/llm-config")
check("llm-config PUT 普通用户 403", r.status_code == 403, f"got {r.status_code}")
r = norm.delete("/api/v1/admin/users/999")
check("delete 普通用户 403", r.status_code == 403, f"got {r.status_code}")

print("== 2. 未登录访问管理端应被拒 401 ==")
anon = httpx.Client(base_url=BASE)
r = anon.get("/api/v1/admin/stats")
check("stats 未登录 401", r.status_code == 401, f"got {r.status_code}")

print("== 3. 概览数据 ==")
r = admin.get("/api/v1/admin/stats")
d = r.json()
check("stats 200", r.status_code == 200, r.text[:200])
check("stats 字段齐全", all(k in d for k in ("users", "activeUsers", "admins", "templates", "llmConfigured", "server")), str(d)[:200])
check("至少 2 用户 / 1 管理员", d["users"] >= 2 and d["admins"] >= 1, str(d)[:150])

print("== 4. 创建用户（含参数校验） ==")
r = admin.post("/api/v1/admin/users", json={"username": "managed_user", "password": "pass-123456", "role": "user"})
check("创建 managed_user", r.status_code == 200, r.text[:200])
mid = r.json()["id"]
r = admin.post("/api/v1/admin/users", json={"username": "x", "password": "pass-123456"})
check("非法用户名 400", r.status_code == 400, f"got {r.status_code}")
r = admin.post("/api/v1/admin/users", json={"username": "managed_user", "password": "pass-123456"})
check("重复用户名 409", r.status_code == 409, f"got {r.status_code}")
r = admin.post("/api/v1/admin/users", json={"username": "bad_role", "password": "pass-123456", "role": "super"})
check("非法角色 400", r.status_code == 400, f"got {r.status_code}")

print("== 5. 用户列表与搜索 ==")
r = admin.get("/api/v1/admin/users")
names = [u["username"] for u in r.json()["users"]]
check("列表包含全部测试用户", all(n in names for n in ("admin_root", "norm_user", "managed_user")), str(names))
r = admin.get("/api/v1/admin/users", params={"query": "managed"})
check("搜索只返回匹配用户", [u["username"] for u in r.json()["users"]] == ["managed_user"], r.text[:200])
u_row = [u for u in r.json()["users"] if u["username"] == "managed_user"][0]
check("列表附带模板数字段", "template_count" in u_row, str(u_row))

print("== 6. 重置密码 ==")
r = admin.put(f"/api/v1/admin/users/{mid}", json={"password": "newpass-456"})
check("重置密码 200", r.status_code == 200, r.text[:200])
r = httpx.post(f"{BASE}/api/v1/auth/login", json={"username": "managed_user", "password": "pass-123456"})
check("旧密码登录失败 401", r.status_code == 401, f"got {r.status_code}")
r = httpx.post(f"{BASE}/api/v1/auth/login", json={"username": "managed_user", "password": "newpass-456"})
check("新密码登录成功", r.status_code == 200, r.text[:200])
r = admin.put(f"/api/v1/admin/users/{mid}", json={"password": "123"})
check("弱密码 400", r.status_code == 400, f"got {r.status_code}")

print("== 7. 禁用/启用：被禁用户会话立即失效 ==")
managed = httpx.Client(base_url=BASE)
managed.post("/api/v1/auth/login", json={"username": "managed_user", "password": "newpass-456"})
r = managed.get("/api/v1/auth/me")
check("禁用前会话正常", r.status_code == 200, f"got {r.status_code}")
r = admin.put(f"/api/v1/admin/users/{mid}", json={"is_active": False})
check("禁用用户 200", r.status_code == 200, r.text[:200])
r = managed.get("/api/v1/auth/me")
check("被禁用户现有会话立即 403", r.status_code == 403, f"got {r.status_code}")
r = httpx.post(f"{BASE}/api/v1/auth/login", json={"username": "managed_user", "password": "newpass-456"})
check("被禁用户登录 403", r.status_code == 403, f"got {r.status_code}")
r = admin.put(f"/api/v1/admin/users/{mid}", json={"is_active": True})
check("重新启用 200", r.status_code == 200, r.text[:200])
r = httpx.post(f"{BASE}/api/v1/auth/login", json={"username": "managed_user", "password": "newpass-456"})
check("启用后可登录", r.status_code == 200, r.text[:200])

print("== 8. 自我保护护栏 ==")
r = admin.put(f"/api/v1/admin/users/{admin_id}", json={"role": "user"})
check("不能自降级 400", r.status_code == 400, f"got {r.status_code} {r.text[:100]}")
r = admin.put(f"/api/v1/admin/users/{admin_id}", json={"is_active": False})
check("不能自禁用 400", r.status_code == 400, f"got {r.status_code}")
r = admin.delete(f"/api/v1/admin/users/{admin_id}")
check("不能自删除 400", r.status_code == 400, f"got {r.status_code}")
r = admin.get("/api/v1/auth/me")
check("管理员身份未被破坏", r.status_code == 200 and r.json()["role"] == "admin", r.text[:100])

print("== 9. 角色提升/降级 ==")
r = admin.put(f"/api/v1/admin/users/{mid}", json={"role": "admin"})
check("提升为管理员 200", r.status_code == 200, r.text[:200])
r = admin.get("/api/v1/admin/users")
u_row = [u for u in r.json()["users"] if u["id"] == mid][0]
check("列表反映新角色", u_row["role"] == "admin", str(u_row))
r = admin.put(f"/api/v1/admin/users/{mid}", json={"role": "user"})
check("降级回普通用户 200", r.status_code == 200, r.text[:200])

print("== 10. 删除用户（级联） ==")
# 给 managed_user 存一个模板，验证级联删除
managed.post("/api/v1/auth/login", json={"username": "managed_user", "password": "newpass-456"})
managed.put("/api/v1/me/templates", json={"template": {"name": "将被级联删除", "cards": []}})
r = admin.get("/api/v1/admin/stats")
tpl_before = r.json()["templates"]

# 10b. 管理端查看用户模板
r = admin.get(f"/api/v1/admin/users/{mid}/templates")
tpls = r.json()["templates"]
check("管理端列出用户模板", r.status_code == 200 and len(tpls) == 1 and tpls[0]["name"] == "将被级联删除", r.text[:200])
tpl_row_id = tpls[0]["id"] if tpls else 0
r = admin.get(f"/api/v1/admin/users/{mid}/templates/{tpl_row_id}")
check("管理端读取模板内容", r.status_code == 200 and r.json()["template"]["name"] == "将被级联删除", r.text[:200])
# 越权防御：用别的 user_id 访问同一 tpl_id → 404
r = admin.get(f"/api/v1/admin/users/{admin_id}/templates/{tpl_row_id}")
check("tpl_id 与 user_id 不匹配返回 404", r.status_code == 404, f"got {r.status_code}")
r = admin.get(f"/api/v1/admin/users/99999/templates")
check("不存在的用户返回 404", r.status_code == 404, f"got {r.status_code}")
r = norm.get(f"/api/v1/admin/users/{mid}/templates")
check("普通用户查看模板 403", r.status_code == 403, f"got {r.status_code}")

r = admin.delete(f"/api/v1/admin/users/{mid}")
check("删除用户 200", r.status_code == 200, r.text[:200])
r = admin.get("/api/v1/admin/users", params={"query": "managed"})
check("用户已从列表消失", not r.json()["users"], r.text[:200])
r = admin.get("/api/v1/admin/stats")
check("模板被级联删除", r.json()["templates"] == tpl_before - 1, f"{tpl_before} -> {r.json()['templates']}")
r = admin.delete(f"/api/v1/admin/users/{mid}")
check("重复删除 404", r.status_code == 404, f"got {r.status_code}")

print("== 11. 全局模型配置 ==")
# 备份当前模型配置（可能是真实生产配置），测试完在 finally 里走 API 恢复——
# 绝不弄丢用户数据；也绝不直写数据库文件（绕过加密、无视 LC_DB_PATH/PG）。


def _read_llm_row():
    """从运行时实际使用的数据库读 app_config.llm 原始值（兼容 PG 与 SQLite）。"""
    import sys as _sys
    import pathlib as _pl
    _sys.path.insert(0, str(_pl.Path(__file__).parent))
    from app.config import get_settings as _gs
    _url = _gs().database_url
    if _url.startswith(("postgresql://", "postgres://")):
        import psycopg
        with psycopg.connect(_url) as _c:
            _row = _c.execute("SELECT value FROM app_config WHERE key='llm'").fetchone()
            return _row[0] if _row else None
    import sqlite3
    _db_file = os.environ.get("LC_DB_PATH") or str(_pl.Path(__file__).parent / "data" / "users.db")
    try:
        _row = sqlite3.connect(_db_file).execute(
            "SELECT value FROM app_config WHERE key='llm'").fetchone()
        return _row[0] if _row else None
    except sqlite3.OperationalError:
        return None


r = admin.get("/api/v1/admin/llm-config")
_saved = r.json()  # {baseUrl, model, timeout, hasKey}（不含明文密钥）
_saved_has_key = bool(_saved.get("hasKey"))
# 普通用户 403
r = norm.get("/api/v1/admin/llm-config")
check("普通用户读模型配置 403", r.status_code == 403, f"got {r.status_code}")
try:
    # 管理员保存（含密钥）
    r = admin.put("/api/v1/admin/llm-config", json={
        "baseUrl": "https://llm.example.com/v1", "model": "global-model", "apiKey": "sk-global-secret", "timeout": 90})
    check("管理员保存全局配置", r.status_code == 200 and r.json().get("hasKey") is True, r.text[:200])
    # 读回：明文密钥绝不出现
    r = admin.get("/api/v1/admin/llm-config")
    d = r.json()
    check("配置可读且字段正确", d.get("baseUrl") == "https://llm.example.com/v1" and d.get("model") == "global-model" and d.get("timeout") == 90, str(d))
    check("密钥明文绝不回传", "sk-global-secret" not in r.text, r.text[:200])
    # 数据库中加密存储（按运行时实际 DB：PG 或 SQLite）
    row = _read_llm_row()
    check("数据库中密钥已加密", row and "enc:" in row and "sk-global-secret" not in row, str(row)[:120])
    # 空密钥保存 = 保留原密钥
    r = admin.put("/api/v1/admin/llm-config", json={
        "baseUrl": "https://llm.example.com/v1", "model": "global-model-v2", "apiKey": "", "timeout": 90})
    check("空密钥保存保留原密钥", r.status_code == 200 and r.json().get("hasKey") is True, r.text[:200])
    # 生成请求走全局配置（本机关闭端口 → 502 连接失败，证明全局配置已生效）
    r = admin.put("/api/v1/admin/llm-config", json={
        "baseUrl": "http://127.0.0.1:9", "model": "global-model", "apiKey": "sk-global-secret", "timeout": 10})
    r = admin.post("/api/v1/generate-batch", json={
        "grade": "小学三年级", "subject": "数学", "keyword": "分数", "difficulty": "medium",
        "items": [{"game_type": "oral_math", "question_count": 2}]})
    check("生成请求使用全局配置（连接被拒 → 502）", r.status_code == 502, f"got {r.status_code} {r.text[:150]}")
    # stats 反映模型已配置
    r = admin.get("/api/v1/admin/stats")
    check("stats 显示模型已配置", r.json().get("llmConfigured") in (1, True), str(r.json())[:150])
    # 清除配置（含密钥）：DELETE 后回到未配置状态
    r = admin.delete("/api/v1/admin/llm-config")
    check("清除配置 200", r.status_code == 200, r.text[:150])
    r = admin.get("/api/v1/admin/llm-config")
    check("清除后 hasKey=False", not r.json().get("hasKey"), str(r.json()))
finally:
    # 恢复测试前的真实配置：一律走管理 API（后端负责加密），PG/自定义 DB 路径天然正确。
    if _saved_has_key:
        # API 拿不到明文密钥，无法原样回填——恢复非密钥字段并提示重新保存
        admin.put("/api/v1/admin/llm-config", json={
            "baseUrl": _saved.get("baseUrl", ""), "model": _saved.get("model", ""),
            "apiKey": "", "timeout": _saved.get("timeout", 120)})
        print("  [!!] 测试前已有真实模型密钥：密钥无法自动回填（明文不可知）。")
        print("       请管理员到后台「模型配置」重新保存真实密钥！")
    else:
        # 原本无密钥：DELETE 清除 + 按需恢复非密钥字段（无密钥时空 apiKey 不会写入密钥）
        admin.delete("/api/v1/admin/llm-config")
        if _saved.get("baseUrl") or _saved.get("model"):
            r = admin.put("/api/v1/admin/llm-config", json={
                "baseUrl": _saved.get("baseUrl", ""), "model": _saved.get("model", ""),
                "apiKey": "", "timeout": _saved.get("timeout", 120)})
            if r.status_code != 200:
                print(f"  [!!] 配置恢复失败: {r.status_code} {r.text[:150]}")
                failed += 1
        print("  [OK] 已恢复测试前的模型配置状态")

print("== 12. 日志查看 ==")
r = admin.get("/api/v1/admin/logs", params={"lines": 300})
check("日志 200 且非空", r.status_code == 200 and len(r.json().get("logs", "")) > 0, r.text[:150])
check("日志含管理员操作记录", "admin_root" in r.json()["logs"], "")

print(f"\n===== 结果: {passed} passed, {failed} failed =====")
exit(1 if failed else 0)
