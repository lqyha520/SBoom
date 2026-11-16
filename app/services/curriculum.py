"""教材关注已下线，仅保留旧任务调用的无操作兼容入口。"""


def digest_tick(now=None):
    """停止生成教材上新消息，旧调用不再读取或修改关注数据。"""
    return None
