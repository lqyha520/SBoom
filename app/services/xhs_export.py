"""用 OOXML 导出固定笔记表；所有用户文本均为字符串单元格，避免执行公式。"""
import io
import re
from xml.sax.saxutils import escape, quoteattr
from zipfile import ZIP_DEFLATED, ZipFile

STATUSES = {'': '未标记', 'reference': '值得参考', 'planned': '准备做', 'done': '已做过', 'irrelevant': '不相关'}
HEADERS = ['笔记标题', '作者', '发布时间', '点赞数', '笔记链接', '收藏', '选题状态', '备注', '采集次数',
           '年级', '科目', '关键词', '采集时间']


def export_workbook(notes: list[dict]) -> bytes:
    rows = [HEADERS]
    for note in notes:
        rows.append([note['title'], note['author'], note['published_text'], note['likes_count'], note['url'],
                     '是' if note['favorite'] else '否', STATUSES[note['mark_status']], note['remark'], note['seen_count'],
                     note['grade'], note['subject'], note['keyword'], note['captured_at']])
    content = []
    for index, row in enumerate(rows, 1):
        cells = []
        for col, value in enumerate(row):
            ref = f'{chr(65 + col)}{index}'
            if isinstance(value, int):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value or ''))
                cells.append(f'<c r="{ref}" t="inlineStr" s="{1 if index == 1 else 0}"><is><t xml:space="preserve">{escape(text)}</t></is></c>')
        content.append(f'<row r="{index}">{"".join(cells)}</row>')
    main = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel = 'http://schemas.openxmlformats.org/package/2006/relationships'
    office = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    buffer = io.BytesIO()
    hyperlinks = ''.join(f'<hyperlink ref="E{index}" r:id="rId{index}"/>' for index in range(2, len(rows) + 1))
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                         '<Default Extension="xml" ContentType="application/xml"/>'
                         '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                         '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                         '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
        archive.writestr('_rels/.rels', f'<Relationships xmlns="{rel}"><Relationship Id="rId1" Type="{office}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml', f'<workbook xmlns="{main}" xmlns:r="{office}"><sheets><sheet name="小红书选题" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', f'<Relationships xmlns="{rel}"><Relationship Id="rId1" Type="{office}/worksheet" Target="worksheets/sheet1.xml"/>'
                         f'<Relationship Id="rId2" Type="{office}/styles" Target="styles.xml"/></Relationships>')
        archive.writestr('xl/styles.xml', f'<styleSheet xmlns="{main}"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
                         '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
                         '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                         '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
                         '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        archive.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="{main}" xmlns:r="{office}"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
                         f'<cols><col min="1" max="13" width="22" customWidth="1"/></cols><sheetData>{"".join(content)}</sheetData><autoFilter ref="A1:M{len(rows)}"/>'
                         f'{"<hyperlinks>" + hyperlinks + "</hyperlinks>" if hyperlinks else ""}</worksheet>')
        relationships = ''.join(f'<Relationship Id="rId{index}" Type="{office}/hyperlink" Target={quoteattr(note["url"])} TargetMode="External"/>'
                                for index, note in enumerate(notes, 2))
        archive.writestr('xl/worksheets/_rels/sheet1.xml.rels', f'<Relationships xmlns="{rel}">{relationships}</Relationships>')
    return buffer.getvalue()
