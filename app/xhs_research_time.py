"""采集快照与历史迁移共用的时间比较规则。"""

from datetime import UTC, datetime


def capture_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
