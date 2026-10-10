"""内置知识点名称兼容；不改写用户输入的专项或附加限制。"""

import re

LEGACY_TOPIC = "20以内的进位加法（凑十法：9加几、8加几）"
GENERAL_TOPIC = "20以内的进位加法（凑十法）"


def canonical_topic(keyword: str) -> str:
    """保留用户原始知识点，不把旧标签改写成当前教材标签。"""
    return keyword.strip()


def is_make_ten_practice(grade: str, subject: str, keyword: str) -> bool:
    """只对低年级明确的凑十法专项采用基础练习规则，不扩展到综合运算。"""
    if subject != "数学" or not re.fullmatch(r"(?:小学)?[一二]年级", grade):
        return False
    topic = canonical_topic(keyword)
    if any(word in topic for word in ("减法", "退位", "乘法", "除法", "混合", "连加", "100以内")):
        return False
    return bool(re.search(r"凑十法|(?<!\d)20以内的?进位加法|(?<!\d)[2-9]加几", topic))
