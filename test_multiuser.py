# -*- coding: utf-8 -*-
"""方案B 全链路验证脚本：注册/登录/配置/模板/用户隔离"""
import httpx

BASE = "http://127.0.0.1:8000"
passed, failed = 0, 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")

print("== 1. 未登录访问业务 API 应被拒 ==")
with httpx.Client(base_url=BASE) as c:
    r = c.get("/api/v1/scope/available")
    check("scope/available 未登录返回 401", r.status_code == 401, f"got {r.status_code}")
    r = c.post("/api/v1/generate-batch", json={})
    check("generate-batch 未登录返回 401", r.status_code == 401, f"got {r.status_code}")
    r = c.get("/api/v1/me/templates")
    check("me/templates 未登录返回 401", r.status_code == 401, f"got {r.status_code}")

print("== 2. 注册 alice / bob（已存在则登录，脚本可重复运行） ==")
def register_or_login(c, username, password):
    r = c.post("/api/v1/auth/register", json={"username": username, "password": password})
    if r.status_code == 409:
        r = c.post("/api/v1/auth/login", json={"username": username, "password": password})
    return r

alice = httpx.Client(base_url=BASE)
bob = httpx.Client(base_url=BASE)
r = register_or_login(alice, "alice_test", "secret123")
check("alice 就绪（注册或登录）", r.status_code == 200, r.text[:200])
r = register_or_login(bob, "bob_test", "secret456")
check("bob 就绪（注册或登录）", r.status_code == 200, r.text[:200])

r = alice.post("/api/v1/auth/register", json={"username": "alice_test", "password": "another789"})
check("重复用户名被拒 409", r.status_code == 409, f"got {r.status_code}")
r = alice.post("/api/v1/auth/register", json={"username": "x", "password": "short"})
check("弱参数被拒 422", r.status_code == 422, f"got {r.status_code}")

print("== 3. 会话/me ==")
r = alice.get("/api/v1/auth/me")
check("alice me 正确", r.status_code == 200 and r.json()["username"] == "alice_test", r.text[:200])
r = bob.get("/api/v1/auth/me")
check("bob me 正确", r.status_code == 200 and r.json()["username"] == "bob_test", r.text[:200])

print("== 4. 登出后 401，再登录恢复 ==")
tmp = httpx.Client(base_url=BASE)
tmp.cookies.update(alice.cookies)
tmp.post("/api/v1/auth/logout")
r = tmp.get("/api/v1/auth/me")
check("登出后 me 401", r.status_code == 401, f"got {r.status_code}")
r = tmp.post("/api/v1/auth/login", json={"username": "alice_test", "password": "wrongpass"})
check("错误密码 401", r.status_code == 401, f"got {r.status_code}")
r = tmp.post("/api/v1/auth/login", json={"username": "alice_test", "password": "secret123"})
check("正确密码登录成功", r.status_code == 200, r.text[:200])
tmp.close()

print("== 5. 模型配置已收归后台 ==")
# 旧的每用户配置端点已移除
r = alice.get("/api/v1/me/llm-config")
check("me/llm-config 端点已移除（404）", r.status_code == 404, f"got {r.status_code}")
# 普通用户不能访问管理端的全局模型配置
r = alice.get("/api/v1/admin/llm-config")
check("普通用户访问管理端模型配置 403", r.status_code == 403, f"got {r.status_code}")
r = alice.post("/api/v1/admin/test-llm", json={})
check("普通用户测试连接 403", r.status_code == 403, f"got {r.status_code}")

print("== 6. 模板 CRUD + 用户隔离 ==")
tpl_a = {"name": "三年级期中", "grade": "三年级", "cards": [{"type": "oral_math", "count": 4}]}
tpl_b = {"name": "bob专属", "grade": "五年级", "cards": []}
r = alice.put("/api/v1/me/templates", json={"template": tpl_a})
check("alice 存模板", r.status_code == 200, r.text[:200])
r = bob.put("/api/v1/me/templates", json={"template": tpl_b})
check("bob 存模板", r.status_code == 200, r.text[:200])
r = alice.get("/api/v1/me/templates")
names_a = [t["name"] for t in r.json()["templates"]]
check("alice 看到自己的模板且看不到 bob 的", "三年级期中" in names_a and "bob专属" not in names_a, str(names_a))
r = bob.get("/api/v1/me/templates")
names_b = [t["name"] for t in r.json()["templates"]]
check("bob 只看到自己的模板", names_b == ["bob专属"], str(names_b))
r = alice.delete("/api/v1/me/templates?name=" + "bob专属")
check("alice 删不掉 bob 的模板 404", r.status_code == 404, f"got {r.status_code}")
r = bob.get("/api/v1/me/templates")
check("bob 模板仍在", any(t["name"] == "bob专属" for t in r.json()["templates"]), "")

# bulk 迁移
r = alice.post("/api/v1/me/templates/bulk", json={"templates": [
    {"name": "迁移模板1", "cards": []}, {"name": "迁移模板2", "cards": []}, {"bad": "no name"}]})
check("bulk 导入 2 条（跳过无效）", r.status_code == 200 and r.json()["imported"] == 2, r.text[:200])

print("== 7. 不支持的年级/科目组合在调 LLM 前被 400 拦截 ==")
r = bob.post("/api/v1/generate-batch", json={
    "grade": "小学三年级", "subject": "物理", "keyword": "浮力", "difficulty": "medium",
    "items": [{"game_type": "oral_math", "question_count": 2}]})
# 知识范围库未定义 → 400，不会消耗 LLM 调用
check("不支持科目得到 400", r.status_code == 400 and "暂不支持" in r.text, f"{r.status_code} {r.text[:150]}")

print("== 8. 生成接口无缓存：use_cache 字段被忽略 ==")
r = bob.post("/api/v1/generate", json={
    "grade": "小学三年级", "subject": "物理", "keyword": "浮力", "difficulty": "medium",
    "game_type": "quiz", "question_count": 2, "use_cache": True})
# use_cache 已从请求模型移除（pydantic 忽略多余字段，不报 422）；照常在知识范围校验处 400
check("use_cache 字段被忽略，不报 422", r.status_code == 400 and "暂不支持" in r.text, f"{r.status_code} {r.text[:150]}")

print(f"\n===== 结果: {passed} passed, {failed} failed =====")
exit(1 if failed else 0)
