"""响应字段与状态码也必须进入生成契约，不能只检查请求体。"""

from scripts.generate_api_types import generate


def test_response_only_change_changes_types_and_preserves_status_codes():
    spec = {'paths': {'/sample/{id}': {'get': {
        'parameters': [{'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}],
        'responses': {'200': {'content': {'application/json': {'schema': {
            'type': 'object', 'required': ['value'], 'properties': {'value': {'type': 'integer'}}}}}},
                      '204': {}, '404': {'content': {'application/json': {'schema': {'type': 'string'}}}}},
    }}}}
    before = generate(spec)
    assert '"value": number' in before
    assert '"204": void' in before and '"404": string' in before
    assert 'path: { "id": string }' in before
    spec['paths']['/sample/{id}']['get']['responses']['200']['content']['application/json']['schema']['properties']['value'] = {'type': 'string'}
    after = generate(spec)
    assert after != before and '"value": string' in after


def test_key_read_endpoints_have_declared_response_schemas():
    from app.main import app
    schema = app.openapi()['paths']
    for method, path, status in (
        ('post', '/api/v1/generate-batch', '200'),
        ('get', '/api/v1/library/papers/{paper_id}', '200'),
        ('post', '/api/v1/library/import', '201'),
        ('get', '/api/v1/admin/xhs-workflow/records/{kind}', '200'),
        ('get', '/api/v1/admin/xhs-workspace/assets/{identifier}', '200'),
        ('post', '/api/v1/auth/login', '200'),
        ('post', '/api/v1/auth/mfa/verify', '200'),
        ('get', '/api/v1/admin/sessions', '200'),
        ('get', '/api/v1/admin/finance-ledger', '200'),
        ('get', '/api/v1/mini/me', '200'),
        ('get', '/api/v1/mini/membership/plans', '200'),
        ('get', '/api/v1/mini/orders/{identifier}', '200'),
        ('post', '/api/v1/mini/orders/{identifier}/pay', '200'),
        ('get', '/api/v1/admin/commerce/orders', '200'),
        ('get', '/api/v1/me/generations/{request_id}', '200'),
    ):
        response = schema[path][method]['responses'][status]['content']['application/json']['schema']
        assert '$ref' in response or 'oneOf' in response or 'anyOf' in response, path


def test_asset_binary_responses_include_full_and_partial_downloads():
    generated = generate()
    line = next(line for line in generated.splitlines() if 'GET /api/v1/admin/xhs-workspace/assets/{identifier}/file' in line)
    assert '"200": Blob' in line and '"206": Blob' in line
    for path in ('/api/v1/admin/finance-ledger/export.csv', '/api/v1/admin/commerce/orders/export'):
        line = next(line for line in generated.splitlines() if 'GET ' + path + '"' in line)
        assert '"200": Blob' in line
    line = next(line for line in generated.splitlines() if 'DELETE /api/v1/admin/sessions/{identifier}' in line)
    assert '"204": void' in line


def test_every_success_response_has_an_explicit_json_or_file_contract():
    from app.main import app

    spec = app.openapi()
    missing = []
    for path, methods in spec['paths'].items():
        for method, operation in methods.items():
            for status, response in operation.get('responses', {}).items():
                if not status.startswith('2'):
                    continue
                for media, content in response.get('content', {}).items():
                    schema = content.get('schema', {})
                    if not schema or schema == {'type': 'object'}:
                        missing.append(f'{method.upper()} {path} {status} {media}')
    assert not missing, '\n'.join(missing)
    assert '"200": unknown' not in generate(spec)


def test_files_streams_and_payment_callbacks_keep_their_actual_content_types():
    from app.main import app

    paths = app.openapi()['paths']
    for path in ('/api/v1/library/assets/{asset_id}', '/api/v1/catalog/papers/{catalog_id}/assets/{asset_id}'):
        assert 'application/pdf' in paths[path]['get']['responses']['200']['content']
        assert '206' in paths[path]['get']['responses']
        assert 'application/json' not in paths[path]['get']['responses']['200']['content']
    assert 'text/event-stream' in paths['/api/v1/generate/stream']['post']['responses']['200']['content']
    for path in ('/api/v1/payments/wechat/notify', '/api/v1/payments/wechat/refund-notify'):
        assert '204' in paths[path]['post']['responses']
        assert '200' not in paths[path]['post']['responses']
