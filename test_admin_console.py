# -*- coding: utf-8 -*-
"""独立后台系统验证：/admin 页面可达 + 资源加载 + 登录流程 + 权限隔离"""
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


print("== 1. /admin 静态页面 ==")
with httpx.Client(base_url=BASE, follow_redirects=True) as c:
    r = c.get("/admin")
    check("GET /admin 返回 200（307 → /admin/）", r.status_code == 200, f"got {r.status_code}")
    check("返回后台 HTML（含 #app 与 /admin/assets）", 'id="app"' in r.text and "/admin/assets/" in r.text, r.text[:200])
    check("页面标题为后台管理", "后台管理" in r.text, "")
    # 提取资源路径并验证可加载
    import re
    assets = re.findall(r'(?:src|href)="(/admin/assets/[^"]+)"', r.text)
    ok_assets = all(c.get(a).status_code == 200 for a in assets) if assets else False
    check(f"全部 {len(assets)} 个静态资源可加载", ok_assets, str(assets))
    r = c.get("/admin/")
    check("GET /admin/（带斜杠）也 200", r.status_code == 200, f"got {r.status_code}")

print("== 2. 工作台不受影响 ==")
with httpx.Client(base_url=BASE) as c:
    r = c.get("/")
    check("工作台首页 200", r.status_code == 200, f"got {r.status_code}")
    check("工作台标题为出题工作台（非后台）", "后台管理" not in r.text and ("app" in r.text), r.text[:150])
    r = c.get("/health")
    check("健康检查 200", r.status_code == 200, "")

print("== 3. 后台登录流程（非管理员被拒） ==")
# 准备一个管理员 + 一个普通用户
admin = httpx.Client(base_url=BASE)
r = register_or_login(admin, "admin_console", "admin-pass-123")
if r.status_code != 200:
    print(f"准备管理员失败: {r.text[:200]}")
    exit(1)
if r.json().get("role") != "admin":
    print("SKIP: admin_console 不是管理员（库中已有别的管理员）。删除 data/users.db 后重跑可完整验证。")
    exit(0)

norm = httpx.Client(base_url=BASE)
register_or_login(norm, "console_user", "norm-pass-123")

# 普通用户调管理 API → 403（后台前端会展示无权限提示）
r = norm.get("/api/v1/admin/stats")
check("普通用户调管理 API 403", r.status_code == 403, f"got {r.status_code}")

# 管理员会话调管理 API 正常
r = admin.get("/api/v1/admin/stats")
check("管理员会话调管理 API 200", r.status_code == 200, f"got {r.status_code} {r.text[:150]}")
r = admin.get("/api/v1/admin/users")
check("管理员用户列表 200", r.status_code == 200, f"got {r.status_code}")

print("== 4. 会话互认（同源 Cookie，工作台登录后可直接进后台） ==")
r = admin.get("/api/v1/auth/me")
check("管理员 me 返回 role", r.status_code == 200 and r.json().get("role") == "admin", r.text[:100])

print(f"\n===== 结果: {passed} passed, {failed} failed =====")
exit(1 if failed else 0)
