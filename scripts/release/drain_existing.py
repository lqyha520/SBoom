"""发布守卫独立于应用容器；停止旧应用后释放数据库锁，最终按所有者解除暂停。"""
import time
import uuid
from contextlib import contextmanager


@contextmanager
def drain(command, run, *, timeout=1200, legacy=True):
    owner = uuid.uuid4().hex
    name = 'learncoach-release-drain-' + owner[:12]
    base = [*command, 'run', '--rm', '--no-deps', '--pull', 'never', '-T']
    cli = ['app', 'python', '-m', 'app.services.generation_drain']
    created = False
    released = False
    def release_lock():
        nonlocal released
        if created and not released:
            run('docker', 'stop', '--time', '10', name)
            released = True
    run(*base, *cli, 'set', owner)
    try:
        if legacy:
            run(*base, '-d', '--name', name, *cli, 'hold', owner)
            created = True
            for _ in range(20):
                if b'admission-locked' in run('docker', 'logs', name):
                    break
                time.sleep(1)
            else:
                raise RuntimeError('发布准入锁未就绪')
        deadline = time.monotonic() + timeout
        while int(run(*base, *cli, 'count')):
            if time.monotonic() >= deadline:
                raise RuntimeError('已有生成任务未结束，取消本次切换')
            time.sleep(5)
        yield release_lock
    finally:
        try:
            release_lock()
        finally:
            run(*base, *cli, 'clear', owner)
