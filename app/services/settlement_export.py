"""金额用元的财务工作表及筛选口径；文本只写字符串单元格，不执行公式。"""

import io
import re
import zipfile
from datetime import datetime
from decimal import Decimal
from xml.sax.saxutils import escape

from app.models.settlements import SettlementFilters
from app.services import settlements
from app.services.mini_errors import fail
from app.services.settlement_channels import CHANNEL_LABELS, channel_key
from app.services.settlement_queries import ZONE


def money(value):
    return Decimal(value) / 100 if value is not None else ''


def date_time(value):
    return datetime.fromtimestamp(value, ZONE).strftime('%Y-%m-%d %H:%M:%S') if value else ''


def column(number):
    result = ''
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def workbook(sheets):
    output = io.BytesIO()
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        overrides = ''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, len(sheets) + 1))
        archive.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' + overrides + '</Types>')
        archive.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml', f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + ''.join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i, name in enumerate(sheets, 1)) + '</sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1)) + '<Relationship Id="styles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        archive.writestr('xl/styles.xml', f'<styleSheet xmlns="{ns}"><fonts count="2"><font><sz val="11"/><name val="Microsoft YaHei"/></font><font><b/><sz val="11"/><name val="Microsoft YaHei"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="3"><xf fontId="0"/><xf fontId="1" applyFont="1"/><xf numFmtId="2" applyNumberFormat="1"/></cellXfs></styleSheet>')
        for index, rows in enumerate(sheets.values(), 1):
            cells = []
            for number, row in enumerate(rows, 1):
                parts = []
                for n, value in enumerate(row, 1):
                    cell = column(n) + str(number)
                    if isinstance(value, (int, Decimal)):
                        parts.append(f'<c r="{cell}" s="{2 if isinstance(value, Decimal) else 0}"><v>{value}</v></c>')
                    else:
                        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value or ''))[:32767]
                        parts.append(f'<c r="{cell}" t="inlineStr" s="{1 if number == 1 else 0}"><is><t xml:space="preserve">{escape(text)}</t></is></c>')
                cells.append(f'<row r="{number}">' + ''.join(parts) + '</row>')
            width = len(rows[0]) if rows else 1
            archive.writestr(f'xl/worksheets/sheet{index}.xml', f'<worksheet xmlns="{ns}"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="{width}" width="22" customWidth="1"/></cols><sheetData>' + ''.join(cells) + f'</sheetData><autoFilter ref="A1:{column(width)}{max(1,len(rows))}"/></worksheet>')
    return output.getvalue()


def export(actor, kind, filters):
    filters = filters or SettlementFilters()
    data = settlements.listing(actor, kind, limit=5000, filters=filters)
    if data['total'] > 5000:
        fail('超过 5000 条，请按管理员、日期或状态筛选后导出', 422)
    summary = [['记录编号', '管理员', '状态', '税前奖励（元）', '历史调整（元）', '个人费用（元）', '代扣个税（元）', '最终应付（元）', '创建时间（北京时间）', '实际付款时间（北京时间）', '付款凭证', '金额口径']]
    orders = [['记录编号', '订单号', '管理员', '支付渠道', '实收（元）', '渠道费率（%）', '渠道费（元）', '奖励比例（%）', '奖励封顶（元）', '税前奖励（元）', '费用状态']]
    fees = [['记录编号', '订单号', '费用类别', '费用名称', '模式', '计算基数', '比例（%）', '基数金额（元）', '扣费金额（元）', '核对依据', '凭据关联编号']]
    states = {'pending': '待处理', 'reviewing': '对账中', 'draft': '待审核', 'approved': '待付款', 'paid': '已付款', 'void': '已作废', 'invalidated': '已失效', 'rejected': '已退回', 'cancelled': '已撤回'}
    bases = {'order_gross': '订单实收', 'after_channel': '扣渠道费后', 'reward_gross': '税前奖励合计', 'after_adjustment': '历史调整后可用奖励'}
    for row in data['items']:
        key = row.get('id', row.get('order_id'))
        if kind == 'statements':
            summary.append([key, row['beneficiary_name'], states[row['status']], money(row['gross_fen']), money(row['adjustment_fen']), money(row['personal_fen']) if row['review'] else '', money(row['tax_fen']), money(max(0, row['net_fen'])) if row['net_fen'] is not None else '', date_time(row['created_at']), date_time(row['payout'].get('transferred_at')), row['receipt'], '核定金额；空白为待核定'])
            items = row['snapshot']['items']
            if row['review']:
                for fee in row['review']['personal_fees']:
                    fees.append([key, '', '个人费用', fee['name'], fee.get('mode', 'fixed'), bases.get(fee.get('basis'), ''), money(fee.get('rate_bps')), money(fee.get('base_fen')), money(fee['amount_fen']), row['review']['evidence'], fee.get('source_ref', '')])
                fees.append([key, '', '个税', '实际代扣个税', '实际金额', '', '', '', money(row['tax_fen']), row['review']['evidence'], ''])
        elif kind == 'requests':
            snapshot = row['snapshot']
            summary.append([key, row['beneficiary_name'], states[row['status']], money(snapshot['reference_gross_fen']), money(snapshot['adjustment_fen']), '', '', '', date_time(row['created_at']), '', '', '申请时参考；最终以结算单为准'])
            items = snapshot['items']
        elif kind == 'rewards':
            items = [row]
        else:
            summary.append([key, row['beneficiary_name'], '已入结算单' if row['statement_id'] else '待抵扣或补付', '', money(row['amount_fen']), '', '', '', date_time(row['created_at']), '', row['evidence'], row['reason']])
            items = []
        for item in items:
            if len(orders) > 20000:
                fail('明细超过 20000 笔，请缩小筛选范围', 422)
            costs, policy = item.get('costs'), item['policy']
            channel = costs['channel_fee_fen'] if costs else item.get('reference_channel_fen')
            rate = costs.get('channel_rate_bps') if costs else policy.get('channel_rate_bps')
            commission = item.get('commission_fen') if costs else item.get('reference_commission_fen')
            shared = costs['shared_fees'] if costs else item.get('reference_fees', [])
            orders.append([key, item['order_id'], row['beneficiary_name'], CHANNEL_LABELS[channel_key(item.get('payment_channel'), item.get('device_platform'))], money(item['amount_fen']), money(rate), money(channel), money(policy['rate_bps']), money(policy.get('max_reward_fen')), money(commission), '已核对' if costs else '参考或待核对'])
            fees.append([key, item['order_id'], '渠道费用', '渠道手续费', '按账单' if costs and costs.get('bill_row_id') else '比例', '订单实收', money(rate), money(item['amount_fen']), money(channel), costs['evidence'] if costs else '未核对', ''])
            for fee in shared:
                fees.append([key, item['order_id'], '共同费用', fee['name'], fee.get('mode', 'fixed'), bases.get(fee.get('basis'), ''), money(fee.get('rate_bps')), money(fee.get('base_fen')), money(fee.get('amount_fen')), costs['evidence'] if costs else '参考', fee.get('source_ref', '')])
    scope = [['筛选项目', '筛选值'], ['日期口径', '实际付款日期（仅包含已留存实际付款时间的付款）' if filters.date_basis == 'paid' else '记录创建日期'],
             ['起始日期', filters.start_date], ['截止日期', filters.end_date], ['管理员编号', filters.admin_id],
             ['关键词', filters.q], ['支付渠道', filters.channel], ['状态', filters.status],
             ['处理时效', {'': '全部', 'stalled': '超过三天未更新', 'review_overdue': '超过审核目标', 'payout_overdue': '超过付款目标'}[filters.timing]]]
    return workbook({'结算汇总': summary, '逐单明细': orders, '扣费明细': fees, '筛选口径': scope})
