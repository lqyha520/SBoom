"""分渠道费用与结算汇总，不调用外部支付服务。"""

from typing import Any

CHANNEL_LABELS = {'wechat': '普通微信支付', 'virtual_android': '虚拟支付 · 安卓/鸿蒙/Windows',
                  'virtual_ios': '虚拟支付 · iOS', 'unknown': '渠道或设备待核对'}


def channel_key(channel, platform):
    if channel == 'wechat':
        return 'wechat'
    if channel == 'virtual':
        if platform == 'ios':
            return 'virtual_ios'
        if platform in ('android', 'harmony', 'harmonyos', 'ohos', 'windows'):
            return 'virtual_android'
    return 'unknown'


def channel_rate(policy, channel, platform):
    rates = policy.get('channel_rates')
    return rates.get(channel_key(channel, platform)) if rates is not None else policy.get('channel_rate_bps')


def channel_totals(items, *, reference=False):
    groups: dict[str, Any] = {}
    for item in items:
        key = channel_key(item.get('payment_channel'), item.get('device_platform'))
        group = groups.setdefault(key, {'key': key, 'label': CHANNEL_LABELS[key], 'orders': 0, 'amount_fen': 0,
                                        'channel_fen': 0, 'shared_fen': 0, 'commission_fen': 0, 'unknown_rates': 0})
        group['orders'] += 1
        group['amount_fen'] += item['amount_fen']
        fees = item['reference_fees'] if reference else item['costs']['shared_fees']
        unknown = reference and item['costs'] is None and item.get('reference_channel_rate_bps') is None
        group['unknown_rates'] += int(unknown)
        for field, amount in (
            ('channel_fen', item['reference_channel_fen'] if reference else item['costs']['channel_fee_fen']),
            ('shared_fen', sum(fee.get('amount_fen') or 0 for fee in fees)),
            ('commission_fen', item['reference_commission_fen'] if reference else item['commission_fen']),
        ):
            group[field] = None if unknown or amount is None or group[field] is None else group[field] + amount
    return [groups[key] for key in sorted(groups)]
