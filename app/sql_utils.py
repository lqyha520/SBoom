"""参数化 LIKE 查询的字面值转义；调用方决定大小写和匹配范围。"""


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
