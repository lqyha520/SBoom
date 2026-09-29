"""本机 CPU 数不等于临时 PostgreSQL 的容量，自动并发最多使用四个进程。"""

import os

import pytest


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    # 显式 -n N 仍遵循操作者配置；仅约束 auto/logical 的默认值。
    return min(4, os.cpu_count() or 1)
