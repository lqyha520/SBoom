"""从 WSL 检查公网入口、页面资源和 TLS；结果只写日志及运维回执。"""
import json
import os
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from offsite_ops import Offsite
from ops_check import fetch, tls_days
from ops_state import operation_check, write_json


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        value = dict(attrs)
        if tag == 'script' and value.get('src'):
            self.urls.append(value['src'])
        if tag == 'link' and value.get('rel') in ('stylesheet', 'modulepreload'):
            self.urls.append(value['href'])


def check_public(base: str) -> dict:
    parsed = urlsplit(base)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query:
        raise ValueError('公网地址必须是无凭证的 HTTPS 入口')
    checks: dict[str, dict] = {}
    retries = 0
    def read(url, **kwargs):
        nonlocal retries
        for attempt in range(2):
            try:
                return fetch(url, **kwargs)
            except OSError:
                if attempt:
                    raise
                retries += 1
    for path, label in (('/', 'workbench'), ('/admin/', 'admin')):
        before_retries = retries
        try:
            parser = Assets()
            parser.feed(read(base.rstrip('/') + path).decode())
            if not parser.urls:
                raise ValueError('页面没有应用资源')
            for asset in parser.urls:
                url = urljoin(base.rstrip('/') + path, asset)
                if urlsplit(url).netloc != parsed.netloc:
                    raise ValueError('应用资源不属于当前站点')
                content = read(url, limit=8 * 1024 * 1024)
                if not content:
                    raise ValueError('空资源')
                if content.lstrip().lower().startswith((b'<!doctype html', b'<html')):
                    raise ValueError('应用资源错误地返回了HTML页面')
            checks[label] = {'ok': True, 'assets_checked': len(parser.urls), 'network_retries': retries - before_retries}
        except Exception as error:
            checks[label] = {'ok': False, 'error': type(error).__name__}
    try:
        days = tls_days(parsed.hostname, parsed.port or 443, time.time())
        checks['tls'] = {'ok': days >= 14, 'days_left': round(days, 1)}
    except Exception as error:
        checks['tls'] = {'ok': False, 'error': type(error).__name__}
    return {'ok': all(item['ok'] for item in checks.values()), 'checked_at': int(time.time()), 'checks': checks}


def main():
    target = Offsite()
    report = check_public(os.environ['OPS_PUBLIC_URL'])
    for name in ('operation', 'restore-operation'):
        try:
            report['checks'][name] = operation_check(target.root / 'status' / (name + '.json'))
        except Exception as error:
            report['checks'][name] = {'ok': False, 'error': type(error).__name__}
    report['ok'] = all(item['ok'] for item in report['checks'].values())
    write_json(target.root / 'status/external.json', report)
    try:
        target.remote('external', json.dumps(report).encode())
    except Exception:
        report['receipt_delivered'] = False
        report['ok'] = False
        write_json(target.root / 'status/external.json', report)
    print(json.dumps(report), flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
