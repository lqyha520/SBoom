"""申请参考金额的展示口径；不改写历史申请快照或核定结果。"""

from copy import deepcopy

from app.services.settlement_channels import channel_totals


def unknown_reference(item):
    return item.get('costs') is None and item.get('reference_channel_rate_bps') is None


def reference_snapshot(snapshot):
    value = deepcopy(snapshot)
    unknown = 0
    for item in value['items']:
        if not unknown_reference(item):
            continue
        unknown += 1
        item['reference_channel_fen'] = None
        item['reference_commission_fen'] = None
        # 老快照曾按零渠道费推算共同费用，展示时还原规则，不能当作已知金额。
        item['reference_fees'] = [{key: field for key, field in fee.items() if field is not None}
                                  for fee in item['policy']['shared_fees']]
    known = sum(item['reference_commission_fen'] or 0 for item in value['items'])
    value.update(unknown_orders=unknown, known_reference_gross_fen=known,
                 reference_gross_fen=None if unknown else known,
                 reference_after_adjustment_fen=None if unknown else max(0, known + value['adjustment_fen']),
                 channels=channel_totals(value['items'], reference=True))
    return value
