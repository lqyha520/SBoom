"""宿主定时只读检查；将结果写入日志与状态文件，不发送外部通知。"""

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from ops_check import check
from ops_state import operation_check, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', default='learncoach-app-1')
    parser.add_argument('--output', type=Path, default=Path('/var/lib/learn-coach-monitor/latest.json'))
    parser.add_argument('--backup-status', default='/var/lib/learn-coach/ops-status/backup.json')
    parser.add_argument('--min-free-gib', type=float, default=5)
    args = parser.parse_args()
    # 只提取网络地址；完整容器配置不会写入日志或文件。
    discovery_error = None
    try:
        inspected = json.loads(subprocess.check_output(['docker', 'inspect', args.app], stderr=subprocess.PIPE, timeout=10))[0]
        addresses = [value['IPAddress'] for value in inspected['NetworkSettings']['Networks'].values() if value['IPAddress']]
        if len(addresses) != 1:
            raise RuntimeError('无法确定指标地址')
        metrics_url = f'http://{addresses[0]}:9090/metrics'
    except Exception as error:
        discovery_error = type(error).__name__
        metrics_url = 'http://127.0.0.1:1/metrics'
    options = argparse.Namespace(ready_url='http://127.0.0.1:33403/readyz', metrics_url=metrics_url,
                                 disk_path=Path('/'), backup_status=args.backup_status, max_backup_hours=27,
                                 min_free_gib=args.min_free_gib, min_free_percent=15, tls_host=os.environ.get('OPS_TLS_HOST'),
                                 tls_port=443, min_tls_days=14, state_file=str(args.output.parent / 'maintenance.json'))
    report = check(options)
    if discovery_error:
        report['checks']['container'] = {'ok': False, 'error': discovery_error}
    try:
        usage = shutil.disk_usage('/data/data1')
        report['checks']['data_disk'] = {'ok': usage.free >= args.min_free_gib * 1024**3 and usage.free / usage.total >= .15,
                                        'free_gib': round(usage.free / 1024**3, 2)}
    except Exception as error:
        report['checks']['data_disk'] = {'ok': False, 'error': type(error).__name__}
    status_root = Path(args.backup_status).parent
    for name in ('source-operation', 'offsite-operation', 'restore-operation'):
        try:
            report['checks'][name] = operation_check(status_root / (name + '.json'))
        except Exception as error:
            report['checks'][name] = {'ok': False, 'error': type(error).__name__}
    for name, age_limit in (('restore', 8 * 86400), ('external', 1200)):
        try:
            value = json.loads((status_root / (name + '.json')).read_text())
            age = time.time() - value.get('checked_at', value.get('completed_at', 0))
            healthy = value.get('ok') if name == 'external' else value.get('verified') and value.get('app_started')
            report['checks'][name] = {'ok': bool(healthy) and -300 <= age <= age_limit, 'age_seconds': round(age)}
        except Exception as error:
            report['checks'][name] = {'ok': False, 'error': type(error).__name__}
    report['ok'] = all(item['ok'] for item in report['checks'].values())
    write_json(args.output, report, 0o644)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
