"""Disposable local server for the account, avatar and membership UI checks.

Build miniprogram H5, then run: py -3.12 tests/profile_ui_fixture.py --port 8349
Uses temporary SQLite only, with all provider traffic disabled by ui_fixture.
"""

import argparse
import threading
import time
from contextlib import asynccontextmanager

import ui_fixture as base  # Set the disposable environment before app imports.
import uvicorn
from fastapi.staticfiles import StaticFiles
from app.models.commerce import PlanInput
from app.models.experience import SupportSettings
from app.models.mini import MembershipUpdate, MiniProfileUpdate
from app.services import mini_auth, mini_experience, mini_orders


@asynccontextmanager
async def lifespan(app):
    async with base.lifespan(app):
        mini_experience.save_support(SupportSettings(
            wechat="learn_coach_demo", phone="4000000000", email="help@example.test",
            hours="周一至周日 09:00–18:00", benefits="会员权益以资料详情标注为准。"))
        for rank, (name, days, price, description) in enumerate((
            ("月度会员", 30, 1990, "适合短期集中练习"),
            ("季度会员", 90, 4990, "陪伴一整个学习阶段"),
            ("年度会员", 365, 16990, "让练习成为长期习惯"),
        )):
            mini_orders.save_plan(PlanInput(name=name, days=days, price_fen=price,
                                           description=description, is_active=True, sort_order=rank))
        reader = mini_auth.login_password("ui_reader", "reader-pass-123")["user"]
        mini_auth.update_profile(reader["id"], MiniProfileUpdate(nickname="小海豚", avatar="fox"))
        with base.db() as conn:
            admin_id = conn.execute("SELECT id FROM users WHERE username = 'admin_console'").fetchone()[0]
        for name, expiry in (("ui_lifetime", None), ("ui_expired", int(time.time()) - 86400)):
            user = mini_auth.register(name, "reader-pass-123")["user"]
            mini_auth.update_membership(admin_id, user["id"], MembershipUpdate(
                revision=1, membership="vip", vip_expires_at=expiry, is_active=True))
        yield


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8349)
    parser.add_argument("--seconds", type=int, default=1800)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 3600:
        raise ValueError("Fixture lifetime must be between 1 and 3600 seconds")
    app = base.fixture
    app.router.lifespan_context = lifespan
    app.state.demo_library = base.ROOT / "artifacts" / "miniprogram" / "demo"
    app.router.routes[:] = [route for route in app.router.routes if getattr(route, "name", "") != "web"]
    app.mount("/", StaticFiles(directory=base.ROOT / "miniprogram" / "dist" / "build" / "h5", html=True), name="mini")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning"))
    timer = threading.Timer(args.seconds, lambda: setattr(server, "should_exit", True))
    timer.daemon = True
    timer.start()
    try:
        print(f"Profile UI fixture: http://127.0.0.1:{args.port}; auto-stop in {args.seconds}s", flush=True)
        server.run()
    finally:
        timer.cancel()
        base.TEMP.cleanup()
