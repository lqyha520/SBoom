"""未处理异常在最外层响应中保留追踪编号，不依赖数据库。"""

import logging
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Route

from app.main import app as main_app
from app.main import unhandled_error
from app.request_context import RequestContext, RequestIdFilter, request_id


def test_unhandled_error_preserves_validated_id_in_response_and_log():
    app = FastAPI()
    app.add_middleware(RequestContext)
    app.add_exception_handler(Exception, unhandled_error)

    @app.get('/failure')
    async def failure():
        raise RuntimeError('测试内部异常，不能暴露给客户端')

    with patch('app.main.logger.error') as log:
        client = TestClient(app, raise_server_exceptions=False)
        first = client.get('/failure', headers={'X-Correlation-ID': 'fixture-request-123'})
        assert first.status_code == 500
        assert first.headers['X-Correlation-ID'] == first.json()['request_id'] == 'fixture-request-123'
        assert first.headers['Cache-Control'] == 'no-store'
        assert '测试内部异常' not in first.text
        assert log.call_args.kwargs['extra']['request_id'] == 'fixture-request-123'
        assert isinstance(log.call_args.kwargs['exc_info'][1], RuntimeError)
        for supplied in ('', 'invalid/id'):
            response = client.get('/failure', headers={'X-Correlation-ID': supplied})
            identifier = response.headers['X-Correlation-ID']
            assert len(identifier) == 32 and identifier == response.json()['request_id']
            assert log.call_args.kwargs['extra']['request_id'] == identifier
    assert request_id.get() == '-'


def test_logging_filter_retains_explicit_id_after_request_context_is_reset():
    record = logging.LogRecord('app', logging.ERROR, __file__, 1, 'failure', (), None)
    record.request_id = 'fixture-explicit-123'
    assert RequestIdFilter().filter(record)
    assert record.request_id == 'fixture-explicit-123'


def test_main_application_middleware_keeps_error_response_traceable(monkeypatch):
    async def failure(request):
        raise RuntimeError('内部异常详情')

    path = '/api/v1/__test_unhandled_error'
    monkeypatch.setattr(main_app.router, 'routes', [Route(path, failure), *main_app.router.routes])
    # 走主应用实际中间件；不进入 lifespan，不启动数据库或后台任务。
    client = TestClient(main_app, raise_server_exceptions=False)
    with patch('app.main.logger.error') as log:
        for headers in ({'X-Correlation-ID': 'main-request-123'}, {}):
            response = client.get(path, headers=headers)
            assert response.status_code == 500
            identifier = response.json()['request_id']
            assert identifier and response.headers['X-Correlation-ID'] == identifier
            assert identifier == headers.get('X-Correlation-ID', identifier)
            assert log.call_args.kwargs['extra']['request_id'] == identifier
            assert response.headers['Cache-Control'] == 'no-store'
            assert response.headers['Vary'] == 'Cookie, Authorization'
            assert '内部异常详情' not in response.text
    assert request_id.get() == '-'
