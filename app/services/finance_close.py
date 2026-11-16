"""月末办理清单是当前待办的只读汇总，不替代已留档账本。"""

import time
from datetime import datetime

from app.admin_permissions import allowed
from app.db import db
from app.services import settlement_access
from app.services.mini_errors import fail
from app.services.referral_metrics import real_order
from app.services.settlement_ledger import month_range
from app.services.settlement_queries import ZONE


def checklist(actor, month, page=1, cost_page=1, dispute_page=1):
    start, end = month_range(month)
    now = int(time.time())
    if start > now:
        fail('不能查看未来月份的核对清单', 422)
    with db(read_only_snapshot=True) as conn:
        user = settlement_access.identity(conn, actor)
        financial = any(allowed(user, key) for key in settlement_access.MENUS)
        if not financial and not allowed(user, 'reconciliations'):
            fail('需要财务查看权限', 403)
        result = {'month': month, 'ended': end <= now, 'as_of': now, 'archives': None, 'bills': None, 'costs': None, 'disputes': None}
        if financial:
            scope = """WITH balances AS (
                SELECT beneficiary,SUM(amount_fen) AS closing_fen FROM referral_ledger_events WHERE occurred_at<? GROUP BY beneficiary
                HAVING SUM(amount_fen)<>0 OR COUNT(*) FILTER(WHERE occurred_at>=?)>0)
                SELECT b.*,u.username AS admin_name,split_part(b.beneficiary,':',2)::integer AS admin_id
                FROM balances b LEFT JOIN users u ON u.id=split_part(b.beneficiary,':',2)::integer
                WHERE NOT EXISTS(SELECT 1 FROM referral_monthly_reports r WHERE r.beneficiary=b.beneficiary AND r.month=?)"""
            args = [end, start, month]
            count = conn.execute(f'SELECT COUNT(*) FROM ({scope}) pending', args).fetchone()[0]
            current = min(page, max(1, (count + 19) // 20))
            rows = [dict(row) for row in conn.execute(scope + ' ORDER BY b.beneficiary LIMIT 20 OFFSET ?', [*args, (current - 1) * 20])]
            result['archives'] = {'items': rows, 'total': count, 'page': current}
            where = "status IN ('open','processing') AND created_at<?"
            total = conn.execute('SELECT COUNT(*) FROM referral_disputes WHERE ' + where, (end,)).fetchone()[0]
            current = min(dispute_page, max(1, (total + 19) // 20))
            result['disputes'] = {'total': total, 'page': current,
                                  'items': [dict(row) for row in conn.execute('SELECT id,title,status,target_id FROM referral_disputes WHERE ' + where + ' ORDER BY created_at,id LIMIT 20 OFFSET ?', (end, (current - 1) * 20))]}
        if allowed(user, 'reconciliations'):
            rows = conn.execute(f"""WITH events AS (
                SELECT o.paid_at AS stamp FROM mini_orders o WHERE o.payment_channel='wechat' AND o.paid_at>=? AND o.paid_at<? AND {real_order()}
                UNION ALL SELECT f.completed_at FROM mini_refunds f JOIN mini_orders o ON o.id=f.order_id
                    WHERE o.payment_channel='wechat' AND f.status='success' AND f.completed_at>=? AND f.completed_at<?),
                days AS (SELECT DISTINCT TO_CHAR(TO_TIMESTAMP(stamp) AT TIME ZONE 'Asia/Shanghai','YYYY-MM-DD') AS day FROM events),
                latest AS (SELECT DISTINCT ON(bill_date) bill_date,status,summary_json,differences_json FROM mini_reconciliations ORDER BY bill_date,created_at DESC,id DESC)
                SELECT days.day,latest.status,latest.summary_json,latest.differences_json FROM days LEFT JOIN latest ON latest.bill_date=days.day ORDER BY days.day""", (start, min(end, now), start, min(end, now)))
            bills = []
            import json
            for row in rows:
                summary = json.loads(row['summary_json'] or '{}') if isinstance(row['summary_json'], str) else row['summary_json'] or {}
                differences = json.loads(row['differences_json'] or '[]') if isinstance(row['differences_json'], str) else row['differences_json'] or []
                count = summary.get('differences', 0)
                reason = '未核对' if row['status'] is None else '核对未完成' if row['status'] != 'complete' else '差异未完整留存' if count != len(differences) else '存在账单差异' if count else ''
                if reason:
                    bills.append({'day': row['day'], 'reason': reason, 'differences': count})
            result['bills'] = bills
        if allowed(user, 'settlementCosts'):
            query = """SELECT c.id,c.name,c.admin_id,c.spend_fen,
                (SELECT COUNT(*) FROM referral_campaign_expenses e WHERE e.campaign_id=c.id AND e.active AND NOT EXISTS(
                    SELECT 1 FROM referral_cost_vouchers v JOIN referral_cost_voucher_files f ON f.voucher_id=v.id
                    WHERE v.reference=split_part(e.source_ref,'/',1))) AS missing_evidence
                FROM referral_campaigns c WHERE c.created_at<?"""
            scope = f'SELECT * FROM ({query}) costs WHERE spend_fen IS NULL OR missing_evidence>0'
            count = conn.execute(f'SELECT COUNT(*) FROM ({scope}) missing', (end,)).fetchone()[0]
            current = min(cost_page, max(1, (count + 19) // 20))
            rows = [dict(row) for row in conn.execute(scope + ' ORDER BY admin_id,id LIMIT 20 OFFSET ?', (end, (current - 1) * 20))]
            result['costs'] = {'total': count, 'page': current, 'items': rows}
        result['month_end'] = datetime.fromtimestamp(end - 1, ZONE).strftime('%Y-%m-%d')
        return result
