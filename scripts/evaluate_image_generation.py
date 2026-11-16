"""用生产模型配置在本机一次性库评测图片；示例：python scripts/evaluate_image_generation.py --directory artifacts/image-eval。"""
import argparse
import base64
import hashlib
import html
import json
import os
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'scripts/release')]


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--case', action='append', help='仅运行指定样本；不同轮次使用新目录')
    parser.add_argument('--regressions-only', action='store_true')
    parser.add_argument('--review-samples', type=Path, help='只复核指定评测目录里的已有样图，不重新生图')
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=False)
    os.environ['LC_TEST_PG_ADMIN'] = 'postgresql://postgres:postgres@127.0.0.1:55432/postgres'
    os.environ.pop('DATABASE_URL', None)
    import pg_support
    pg_support.install_module_database({'SECRET_KEY': 'isolated-image-evaluation', 'ADMIN_USERNAME': '', 'ADMIN_PASSWORD': '',
                                        'ENCRYPTION_KEYS': '{}', 'ENCRYPTION_ACTIVE_KEY': ''})
    from existing_host import Host
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app import db, security
    from app.config import get_settings
    from app.deps import SESSION_COOKIE
    from app.models.image_generation import ImageWorksheetRequest
    from app.models.model_profiles import ImageModelProfile, TextModelProfile
    from app.routers import image_generation, me
    from app.services import app_config, image_config, image_review, user_store
    from app.services.generation_control import Usage, current_usage
    from app.services.generation_policy import current_policy, load_policy
    from app.services.image_prompt import PROMPT_VERSION, build_prompt
    from app.services.llm_client import llm_client
    from app.services.provider_http import close_clients

    host = Host('production')
    code = '''import json
from app.services.app_config import get_llm
from app.services.image_config import get_config
print(json.dumps({'text':get_llm(with_key=True,fresh=True),'image':get_config(with_key=True)}))'''
    config = json.loads(host.run('docker', 'exec', host.app, 'python', '-c', code, read_only=True))
    cases = json.loads((ROOT / 'tests/fixtures/image-evaluation.json').read_text(encoding='utf-8'))
    if args.case:
        if set(args.case) - {case['id'] for case in cases}:
            raise ValueError('未知样本')
        cases = [case for case in cases if case['id'] in args.case]
    summary: dict = {'prompt_version': PROMPT_VERSION, 'human_status': 'pending', 'samples': [], 'regressions': [],
               'source_hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (ROOT / 'app').rglob('*.py')}}
    db.init_db()
    configurations: list[tuple[str, type[BaseModel], Callable]] = [
        ('text', TextModelProfile, app_config.save_llm_models), ('image', ImageModelProfile, image_config.save_models)]
    for kind, schema, setter in configurations:
        profiles = config[kind].get('models') or [{**config[kind], 'id': 'legacy'}]
        values = [{**{k: v for k, v in profile.items() if k in schema.model_fields}, 'apiKey': profile['api_key']}
                  for profile in profiles]
        if kind == 'text':
            first = next(value for value in values if value.get('enabled', True))
            first['imageReview'] = True
        setter([schema.model_validate(value) for value in values])
    user = user_store.create_user('image-evaluator', uuid.uuid4().hex)
    app = FastAPI()
    app.include_router(image_generation.router)
    app.include_router(me.router)
    with tempfile.TemporaryDirectory(prefix='lc-image-eval-') as folder, patch.object(get_settings(), 'archive_local_dir', folder), TestClient(app) as client:
        assert client.portal is not None
        client.cookies.set(SESSION_COOKIE, security.create_token(user.id))
        client.headers['X-Workspace-User'] = str(user.id)
        try:
            if args.review_samples:
                originals = json.loads((args.review_samples / 'results.json').read_text(encoding='utf-8'))
                for original in originals['samples']:
                    if original['http'] != 200:
                        continue
                    req = ImageWorksheetRequest.model_validate(original['request'])
                    source = args.review_samples / (original['id'] + '.png')
                    async def inspect_sample(source=source, req=req):
                        token = current_policy.set(load_policy('image'))
                        usage = Usage()
                        usage_token = current_usage.set(usage)
                        try:
                            value = await image_review.review_image({'b64_json': base64.b64encode(source.read_bytes()).decode(),
                                                                     'prompt': build_prompt(req)}, req)
                            return value, usage.model_calls
                        finally:
                            current_policy.reset(token)
                            current_usage.reset(usage_token)
                    value, calls = client.portal.call(inspect_sample)
                    summary['samples'].append({**original, 'quality_review': value, 'review_model_calls': calls})
                    (args.directory / source.name).write_bytes(source.read_bytes())
                    save(args.directory / 'results.json', summary)
                    print(json.dumps({'reviewed': original['id'], 'status': value['status']}, ensure_ascii=False), flush=True)
            for filename in ('primary-workbench.png', 'failover-workbench.png'):
                path = ROOT / 'artifacts/2026-10-16-image-hardening' / filename
                if not path.exists():
                    continue
                req = ImageWorksheetRequest.model_validate({k: v for k, v in cases[0].items() if k != 'id'})
                # 历史两张都是4道口算，与新请求的页次安排无关。
                req = req.model_copy(update={'grade': '小学一年级', 'subject': '数学', 'keyword': '10以内加减法',
                    'items': ImageWorksheetRequest.model_validate({'grade':'小学一年级','subject':'数学','items':[{'game_type':'oral_math','question_count':4}]}).items})
                async def inspect_existing(path=path, req=req, filename=filename):
                    token = current_policy.set(load_policy('image'))
                    usage = Usage()
                    usage_token = current_usage.set(usage)
                    try:
                        result = await image_review.review_image({'b64_json': base64.b64encode(path.read_bytes()).decode(), 'prompt': build_prompt(req)}, req)
                        return {'file': filename, 'review': result, 'model_calls': usage.model_calls}
                    finally:
                        current_policy.reset(token)
                        current_usage.reset(usage_token)
                result = client.portal.call(inspect_existing)
                summary['regressions'].append(result)
                save(args.directory / 'results.json', summary)
                print(json.dumps({'regression': filename, 'status': result['review']['status']}, ensure_ascii=False), flush=True)
            for case in ([] if args.regressions_only or args.review_samples else cases):
                identifier = case['id']
                body = {key: value for key, value in case.items() if key != 'id'}
                rid = 'image-eval-' + uuid.uuid4().hex
                print(json.dumps({'started': identifier}), flush=True)
                started = time.monotonic()
                response = client.post('/api/v1/generate-image', json=body, headers={'X-Request-ID': rid})
                entry = {'id': identifier, 'request': body, 'request_id': rid, 'http': response.status_code,
                         'seconds': round(time.monotonic() - started, 3), 'human_rating': None}
                if response.is_success:
                    value = response.json()
                    raw = client.get(value['url'])
                    raw.raise_for_status()
                    (args.directory / (identifier + '.png')).write_bytes(raw.content)
                    entry.update(quality_review=value['quality_review'], sha256=hashlib.sha256(raw.content).hexdigest())
                    (args.directory / (identifier + '-prompt.txt')).write_text(value['prompt'], encoding='utf-8')
                    status = client.get('/api/v1/me/generations/' + rid).json()
                    assert status['result'] == value
                    entry['usage'] = status['usage']
                    replay = client.post('/api/v1/generate-image', json=body, headers={'X-Request-ID': rid})
                    assert replay.json() == value
                    assert client.get('/api/v1/me/generations/' + rid).json()['usage'] == status['usage']
                    entry['replay_verified'] = True
                else:
                    entry['error'] = response.json()
                summary['samples'].append(entry)
                save(args.directory / 'results.json', summary)
                print(json.dumps({'completed': identifier, 'http': response.status_code,
                                  'status': entry.get('quality_review', {}).get('status'), 'seconds': entry['seconds']}), flush=True)
        finally:
            client.portal.call(close_clients)
            client.portal.call(llm_client.close)
    cards = ''.join('<article><h2>' + html.escape(item['id']) + '</h2><p>待人工评分</p><img src="' + html.escape(item['id'])
                    + '.png"><details><summary>自动检查</summary><pre>' + html.escape(json.dumps(item.get('quality_review'), ensure_ascii=False, indent=2))
                    + '</pre></details></article>' for item in summary['samples'] if item['http'] == 200)
    (args.directory / 'review.html').write_text('<!doctype html><meta charset="utf-8"><title>图片习题验收</title><style>body{max-width:1000px;margin:32px auto;font:16px sans-serif}img{max-width:100%}article{margin-bottom:48px}pre{white-space:pre-wrap}</style><h1>图片习题验收 · 待人工评分</h1><p>逐张核对题量、文字、解题条件、图示和版面；自动检查不等于人工评分。</p>' + cards, encoding='utf-8')
    save(args.directory / 'ratings-pending.json', {'status': 'pending_human_review',
        'items': [{'id': item['id'], 'sha256': item.get('sha256'), 'score': None, 'reviewer': None, 'notes': ''} for item in summary['samples']]})
    db.close_pg_pool()


if __name__ == '__main__':
    main()
