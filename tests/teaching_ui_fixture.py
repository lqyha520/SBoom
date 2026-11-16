"""只在本机 lc_test_* 一次性库验收习题库和个人中心。"""

import argparse
import threading
from contextlib import asynccontextmanager

import ui_fixture as base
import uvicorn
from fastapi.staticfiles import StaticFiles

from app.db import db
from app.models.catalog import CatalogCreate, CatalogUpdate
from app.models.engagement import PaperLabels, TagInput
from app.services import catalog_discovery, public_catalog


@asynccontextmanager
async def lifespan(app):
    async with base.lifespan(app):
        with db() as conn:
            admin_id = conn.execute("SELECT id FROM users WHERE username='admin_console'").fetchone()[0]
        tag = catalog_discovery.save(TagInput(kind='textbook', name='验收教材'))
        item = public_catalog.create_paper(admin_id, CatalogCreate(title='十以内加法同步资料', grade='小学一年级', subject='数学',
                                           download_mode='external', external_url='https://example.test/library', view_access='free', download_access='vip'))
        catalog_discovery.assign(item['id'], PaperLabels(revision=1, tag_ids=[tag['id']]), admin_id=admin_id)
        public_catalog.update_paper(admin_id, item['id'], CatalogUpdate(title=item['title'], revision=2, status='published',
                                    confirm_publication=True, download_mode='external', external_url='https://example.test/library', view_access='free', download_access='vip'))
        yield


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    app = base.fixture
    app.router.lifespan_context = lifespan
    app.router.routes[:] = [route for route in app.router.routes if getattr(route, 'name', '') != 'web']
    app.mount('/', StaticFiles(directory=base.ROOT / 'miniprogram' / 'dist' / 'build' / 'h5', html=True), name='mini')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=args.port, log_level='warning'))
    timer = threading.Timer(600, lambda: setattr(server, 'should_exit', True))
    timer.daemon = True
    timer.start()
    try:
        server.run()
    finally:
        timer.cancel()
        base.TEMP.cleanup()
