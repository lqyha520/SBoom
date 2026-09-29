"""宿主机 systemd 入口；只操作备份和隔离恢复服务。"""
import argparse
import os
import subprocess


def compose():
    return ['docker', 'compose',
            '--env-file', os.environ.get('RELEASE_ENV_FILE', '/etc/learn-coach/release.env'),
            '-f', 'deploy/docker-compose.server.yml', '-f', 'deploy/docker-compose.prod.yml',
            '-f', 'deploy/docker-compose.ops.yml']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup', 'restore-check'])
    args = parser.parse_args()
    command = compose()
    if args.action == 'backup':
        subprocess.run([*command, 'run', '--rm', '--no-deps', 'backup'], check=True)
    else:
        # rm 仅针对本工具创建的临时 restore-db，不触碰生产 db/app 或其卷。
        try:
            subprocess.run([*command, 'up', '-d', '--wait', 'restore-db'], check=True)
            subprocess.run([*command, 'run', '--rm', '--no-deps', 'restore-check'], check=True)
        finally:
            subprocess.run([*command, 'rm', '-sf', 'restore-db'], check=True)


if __name__ == '__main__':
    main()
