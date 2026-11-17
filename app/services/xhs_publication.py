"""发布前的人工复核与启发式提醒；不模拟平台审核或操作小红书账号。"""
import hashlib
import re
from urllib.parse import urlsplit

CHECKS = {
    'rights_checked': '已确认文字、图片、视频和资料的原创或使用授权',
    'truth_checked': '已核对事实与题目答案，删除无法证明的效果承诺',
    'privacy_checked': '已检查个人信息、未成年人信息和图片中的隐私',
    'media_checked': '已逐张检查实际上传的图片或视频及其文字',
    'platform_checked': '已核对平台最新规则及商业合作、AI 内容等所需标识',
}
RULES = (
    ('claims', '核实效果与宣传用语', r'包过|保证.{0,6}(提分|满分|有效)|百分之百|100[%％]|全网第一|绝对有效|稳赚', '删去无法证实的保证、排名和绝对化承诺，说明实际适用范围。'),
    ('contact', '检查站外联系与交易引导', r'加.{0,3}(微信|微[信xX]|[vV][xX])|[vV][xX]\s*[:：]|私信.{0,6}(微信|进群|领取)|扫码|站外|网盘|https?://', '核对链接、二维码、联系方式和交易路径是否符合平台规则；使用平台允许的渠道。'),
    ('engagement', '检查互动换取利益的表述', r'(点赞|关注|收藏|评论|三连).{0,12}(领取|送|解锁|获取|发你)|刷赞|刷粉|互赞|互粉', '提供内容本身的价值，避免刷量和以互动为领取条件。'),
    ('copyright', '核实资料来源与授权', r'盗版|内部试卷|泄题|原版扫描|付费.{0,6}(免费|破解)|搬运', '保留可核实的来源或授权，避免传播盗版资料和未经许可的内容。'),
    ('privacy', '检查可能的个人信息', r'(?<!\d)1[3-9]\d{9}(?!\d)|(?<!\d)\d{17}[\dXx](?!\d)', '检查是否含电话号码、证件号码或其他个人信息，并人工查看图片中的隐私。'),
)


def content(data):
    return data.get('custom_content', {}) if data.get('source') == 'custom' else data.get('draft_snapshot', {})


def content_hash(data):
    value = content(data)
    text = re.sub(r'\s+', '', str(value.get('headline', '')) + '\n' + str(value.get('body', ''))).casefold()
    return hashlib.sha256(text.encode()).hexdigest() if text else ''


def url_key(url):
    if not url:
        return ''
    parts = urlsplit(url)
    match = re.search(r'/(?:explore|discovery/item)/([a-fA-F0-9]{24})(?:/|$)', parts.path)
    if parts.hostname in ('xiaohongshu.com', 'www.xiaohongshu.com') and match:
        return 'note:' + match[1].lower()
    return (parts.hostname or '') + parts.path.rstrip('/')


def report(conn, admin_id, data, record_id=None):
    value = content(data)
    blockers = []
    for missing, label in ((not data['account'], '填写发布账号'), (not value.get('headline'), '填写发布标题'), (not value.get('body'), '填写发布正文')):
        if missing:
            blockers.append(label)
    blockers.extend(label for key, label in CHECKS.items() if not data.get(key))
    text = '\n'.join(str(value.get(k, '')) for k in ('headline', 'body', 'hashtags', 'cover_title', 'cover_subtitle', 'media_notes'))
    text += '\n' + '\n'.join(str(card.get('heading', '')) + '\n' + str(card.get('body', '')) for card in value.get('cards', []))
    findings = []
    for code, title, pattern, suggestion in RULES:
        matches = list(dict.fromkeys(match.group(0) for match in re.finditer(pattern, text, flags=re.IGNORECASE)))
        if matches:
            findings.append({'code': code, 'title': title, 'message': suggestion, 'evidence': [str(m)[:80] for m in matches[:3]]})
    digest = content_hash(data)
    # 仅检查当前管理员的记录；归档内容仍保留历史发布事实。
    duplicates = [dict(row) for row in conn.execute("SELECT id,title FROM xhs_workflow_records WHERE admin_id=? AND kind='publications' AND publication_content_hash=? AND publication_content_hash<>'' AND id<>? ORDER BY updated_at DESC,id LIMIT 10", (admin_id, digest, record_id or '')).fetchall()] if digest else []
    if duplicates:
        findings.append({'code': 'duplicate', 'title': '已有相同标题与正文的发布记录', 'message': '核对是否重复排期或重复发布；不要把相同内容批量铺到多个账号。', 'evidence': [v['title'] for v in duplicates[:3]]})
    if findings and not data.get('review_notes', '').strip():
        blockers.append('填写风险复核说明，记录对上述提醒的修改或核实依据')
    return {'blockers': blockers, 'findings': findings, 'duplicates': duplicates[:10],
            'notice': '这是本地文字规则提醒，不是小红书审核结论；未发现命中也不代表合规。图片、视频、授权及最新规则需要人工检查。'}
