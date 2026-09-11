"""题型质检 —— 对 LLM 生成的题目做内容级校验，不合格的剔除或重生成

当前规则（用户明确要求）：
1. 禁止「加法转乘法」题：a + a + a + ... = n × ____ 这种同数连加配乘法的填空题
2. 禁止长连加：任何算式里同数连加/连减超过 3 项
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# 「同数连加」核心模式：a + a（两项即成，为 3 项检测打基础）
# 「加法转乘法」题：4 + 4 + 4 + 4 + 4 = 5 × ____（同数连加 ≥2 项 + 乘号）
_CHAIN_ADD_TO_MUL = re.compile(
    r"(\d+)\s*\+\s*\1(?:\s*\+\s*\1)*\s*=\s*\d*\s*[×x*]"
)
# 同数连加 ≥ 3 项（无论是否配乘法）——乘法意义题，题目必然冗长
_SAME_NUM_CHAIN3 = re.compile(
    r"(\d+)\s*\+\s*\1\s*\+\s*\1"
)


def reject_reason(stem: Optional[str]) -> Optional[str]:
    """检查题干，返回拒绝原因；None = 合格。

    只检查算式类特征，纯文字题干（应用题等）不受影响。
    """
    if not stem or not isinstance(stem, str):
        return None
    s = stem.strip()
    if not s:
        return None

    # 1. 加法转乘法题：4+4+4+4+4 = 5 × ____（同数连加配乘号，两项以上即拦）
    if _CHAIN_ADD_TO_MUL.search(s):
        return "同数连加配乘法（加法转乘法题）"

    # 2. 同数连加 3 项及以上（不配乘法也算——乘法意义题型，题目必然冗长）
    if _SAME_NUM_CHAIN3.search(s):
        return "同数连加 3 项及以上"

    return None


def filter_questions(questions: list, context: str = "") -> tuple:
    """拦截不合格题目。返回 (保留列表, 被拦截题目列表)。

    注意：被拦截的题【不删除】——由调用方决定替换重出或提示用户，
    保证试卷题数不被悄悄减少。
    """
    ok, blocked = [], []
    for q in (questions or []):
        stem = q.get("stem") or ""
        reason = reject_reason(stem)
        if reason:
            blocked.append(q)
            logger.info(f"题型质检拦截{f'（{context}）' if context else ''}: {stem[:50]!r} → {reason}")
            continue
        ok.append(q)
    return ok, blocked
