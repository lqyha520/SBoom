"""素材、排期、复盘建议与入门示例；全部按后台管理员隔离。"""
import hashlib
import io
import json
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException
from PIL import Image, ImageOps

from app.db import db
from app.models.xhs_workflow import Draft, Idea, Material, Publication
from app.services import xhs_asset_storage
from app.services import xhs_workflow as workflow
from app.services.file_retention import enqueue
from app.sql_utils import escape_like

ASSET_COLUMNS = 'id,media_type,size_bytes,metadata_json,template_json,revision,created_at,updated_at'
QUOTA = 500 * 1024 * 1024


def asset_row(row):
    item = dict(row)
    item['data'] = json.loads(item.pop('metadata_json'))
    item['template'] = json.loads(item.pop('template_json') or 'null')
    return item


def list_assets(admin_id, q='', kind='', archived=False, page=1):
    clauses, args = ['admin_id=?', "(metadata_json::jsonb->>'archived')::boolean=?"], [admin_id, archived]
    if q:
        clauses.append("(metadata_json::jsonb->>'title' ILIKE ? OR metadata_json::jsonb->>'tags' ILIKE ?)")
        args.extend(['%' + escape_like(q) + '%'] * 2)
    if kind == 'media':
        clauses.append("media_type<>'application/x-xhs-template'")
    elif kind:
        clauses.append('media_type LIKE ?')
        args.append({'image': 'image/%', 'video': 'video/%', 'template': 'application/x-xhs-template'}[kind])
    where = ' AND '.join(clauses)
    with db() as conn:
        total = conn.execute('SELECT COUNT(*) FROM xhs_assets WHERE ' + where, args).fetchone()[0]
        rows = conn.execute(f'SELECT {ASSET_COLUMNS} FROM xhs_assets WHERE {where} ORDER BY updated_at DESC,id LIMIT 20 OFFSET ?', (*args, (page - 1) * 20)).fetchall()
        used = conn.execute('SELECT COALESCE(SUM(size_bytes),0) FROM xhs_assets WHERE admin_id=?', (admin_id,)).fetchone()[0]
    return {'items': [asset_row(row) for row in rows], 'total': total, 'used_bytes': used, 'quota_bytes': QUOTA}


def get_asset(admin_id, identifier):
    with db() as conn:
        row = conn.execute(f'SELECT {ASSET_COLUMNS} FROM xhs_assets WHERE id=? AND admin_id=?', (identifier, admin_id)).fetchone()
        if not row:
            raise HTTPException(404, detail={'error': '素材不存在或不属于当前账号'})
        return asset_row(row)


def create_asset(admin_id, metadata, media_type, content=None, template=None):
    thumbnail = None
    if content is not None:
        if media_type == 'video/mp4':
            if len(content) < 16 or content[4:8] != b'ftyp':
                raise HTTPException(422, detail={'error': '文件不是可识别的 MP4'})
        else:
            try:
                with Image.open(io.BytesIO(content)) as image:
                    if Image.MIME.get(image.format or '') != media_type or image.width * image.height > 24_000_000:
                        raise ValueError('图片格式或尺寸无效')
                    image.verify()
                thumbnail = thumbnail_bytes(content)
            except Exception as error:
                raise HTTPException(422, detail={'error': '图片损坏、格式不符或超过 2400 万像素'}) from error
    encoded_template = json.dumps(template, sort_keys=True, ensure_ascii=False) if template is not None else None
    payload = content if content is not None else (encoded_template or '').encode()
    digest = hashlib.sha256(media_type.encode() + b':' + payload).hexdigest()
    key = ''
    try:
        with db(lock_key=('xhs_research', str(admin_id))) as conn:
            previous = conn.execute(f'SELECT {ASSET_COLUMNS} FROM xhs_assets WHERE admin_id=? AND digest=?', (admin_id, digest)).fetchone()
            if previous:
                return {**asset_row(previous), 'duplicate': True}
            usage = conn.execute('SELECT COALESCE(SUM(size_bytes),0),COUNT(*) FROM xhs_assets WHERE admin_id=?', (admin_id,)).fetchone()
            used, count = usage[0], usage[1]
            if used + len(payload) > QUOTA or count >= 1000:
                raise HTTPException(409, detail={'error': '素材库已达到 500 MB 或 1000 项上限，请先导出并整理素材'})
            identifier = str(uuid4())
            if content is not None:
                key = xhs_asset_storage.write_file(admin_id, content, media_type)
            conn.execute('INSERT INTO xhs_assets(id,admin_id,digest,media_type,size_bytes,metadata_json,template_json,storage_key,thumbnail) VALUES (?,?,?,?,?,?,?,?,?)',
                         (identifier, admin_id, digest, media_type, len(payload), json.dumps(metadata, ensure_ascii=False), encoded_template, key, thumbnail))
    except BaseException:
        xhs_asset_storage.discard(key)
        raise
    return {**get_asset(admin_id, identifier), 'duplicate': False}


def update_asset(admin_id, identifier, revision, data):
    with db(lock_key=('xhs_research', str(admin_id))) as conn:
        row = conn.execute('SELECT revision FROM xhs_assets WHERE id=? AND admin_id=?', (identifier, admin_id)).fetchone()
        if not row:
            raise HTTPException(404, detail={'error': '素材不存在或不属于当前账号'})
        if row['revision'] != revision:
            raise HTTPException(409, detail={'error': '素材资料已更新，请刷新后再编辑；当前输入已保留'})
        conn.execute('UPDATE xhs_assets SET metadata_json=?,revision=revision+1,updated_at=now() WHERE id=?', (json.dumps(data, ensure_ascii=False), identifier))
    return get_asset(admin_id, identifier)


def thumbnail_bytes(content):
    """先缩小再处理方向和透明背景；JPEG 可在解码时下采样，避免复制整张原图。"""
    with Image.open(io.BytesIO(content)) as original:
        original.draft('RGB', (640, 640))
        original.thumbnail((320, 320))
        with ImageOps.exif_transpose(original) as image, image.convert('RGBA') as rgba:
            with Image.new('RGB', image.size, 'white') as background, rgba.getchannel('A') as alpha:
                background.paste(rgba, mask=alpha)
                output = io.BytesIO()
                background.save(output, 'JPEG', quality=80)
                return output.getvalue()


def asset_thumbnail(admin_id, identifier):
    # 每次都检查归属；正常路径只取几 KB 缩略图，不读取原文件。
    with db() as conn:
        row = conn.execute('SELECT thumbnail,media_type FROM xhs_assets WHERE id=? AND admin_id=?', (identifier, admin_id)).fetchone()
    if not row or not row['media_type'].startswith('image/'):
        raise HTTPException(404, detail={'error': '此素材不存在或没有图片缩略图'})
    if row['thumbnail'] is not None:
        return bytes(row['thumbnail'])
    path, _ = xhs_asset_storage.owned_file(admin_id, identifier)
    # 历史素材按记录合并首次生成，跨 worker 也只处理一次；不改变元数据版本。
    with db(lock_key=('xhs_research', 'thumbnail:' + identifier)) as conn:
        row = conn.execute('SELECT thumbnail FROM xhs_assets WHERE id=? AND admin_id=?', (identifier, admin_id)).fetchone()
        if not row:
            raise HTTPException(404, detail={'error': '素材不存在或不属于当前账号'})
        if row['thumbnail'] is not None:
            return bytes(row['thumbnail'])
        thumbnail = thumbnail_bytes(path.read_bytes())
        conn.execute('UPDATE xhs_assets SET thumbnail=? WHERE id=? AND admin_id=?', (thumbnail, identifier, admin_id))
    return thumbnail


def today_tasks(admin_id, start, end, category='review', page=1):
    if start.tzinfo is None or end.tzinfo is None or not timedelta(0) < end - start <= timedelta(days=2):
        raise HTTPException(422, detail={'error': '请选择包含时区的本机日期'})
    published = 'r.published_at'
    schedule = 'r.scheduled_at'
    args: tuple = ()
    if category == 'review':
        source = "FROM xhs_workflow_records r WHERE r.admin_id=? AND ((r.kind IN ('materials','drafts') AND r.status IN ('draft','review')) OR (r.kind='publications' AND r.status='planned'))"
        args, extra, order = (admin_id,), '', 'r.updated_at ASC,r.id'
    elif category == 'publish':
        source = f"FROM xhs_workflow_records r WHERE r.admin_id=? AND r.kind='publications' AND r.status IN ('planned','ready') AND {schedule}<?"
        args, extra, order = (admin_id, end), '', schedule + ',r.id'
    elif category == 'analytics':
        due = published + " + c.checkpoint * INTERVAL '1 day'"
        source = f"FROM xhs_workflow_records r CROSS JOIN (VALUES (1),(3),(7)) c(checkpoint) LEFT JOIN xhs_workflow_metrics m ON m.publication_id=r.id AND m.checkpoint=c.checkpoint WHERE r.admin_id=? AND r.kind='publications' AND r.status='published' AND m.publication_id IS NULL AND {due}<=?"
        args, extra, order = (admin_id, datetime.now(UTC)), f',c.checkpoint,{due} AS due_at', due + ',r.id,c.checkpoint'
    else:
        raise HTTPException(422, detail={'error': '未知的待办类型'})
    with db() as conn:
        total = conn.execute('SELECT COUNT(*) ' + source, args).fetchone()[0]
        rows = conn.execute('SELECT r.*' + extra + ' ' + source + ' ORDER BY ' + order + ' LIMIT 20 OFFSET ?', (*args, (page - 1) * 20)).fetchall()
    return {'items': [workflow._row(row) for row in rows], 'total': total, 'page': page, 'page_size': 20, 'day_start': start.isoformat()}


def delete_asset(admin_id, identifier, revision):
    with db(lock_key=('xhs_research', str(admin_id))) as conn:
        row = conn.execute('SELECT revision,metadata_json,storage,storage_key FROM xhs_assets WHERE id=? AND admin_id=?', (identifier, admin_id)).fetchone()
        if not row:
            raise HTTPException(404, detail={'error': '素材不存在或不属于当前账号'})
        if row['revision'] != revision or not json.loads(row['metadata_json']).get('archived'):
            raise HTTPException(409, detail={'error': '请先归档素材，并重新读取后再删除'})
        if row['storage_key']:
            enqueue(conn, [(row['storage'], row['storage_key'])])
        conn.execute('DELETE FROM xhs_assets WHERE id=? AND admin_id=?', (identifier, admin_id))


def account_key(data):
    return data.get('account_id') or data.get('account', '').strip().casefold() or '(未指定账号)'


def calendar(admin_id, start, end, account='', unscheduled_page=1):
    if start.tzinfo is None or end.tzinfo is None or not timedelta(0) < end - start <= timedelta(days=32):
        raise HTTPException(422, detail={'error': '请选择包含时区、最长 31 天的有效日期区间'})
    # 账号概要只聚合昵称、编号和时间，不拉取所有历史文案或配图快照。
    with db() as conn:
        summaries = conn.execute("""SELECT COALESCE(data_json::jsonb->>'account_id','') AS account_id,
            COALESCE(data_json::jsonb->>'account','') AS account,MAX(published_at) AS last_published_at,
            MAX(updated_at) AS latest FROM xhs_workflow_records WHERE admin_id=? AND kind='publications'
            GROUP BY 1,2 ORDER BY latest DESC,account_id,account""", (admin_id,)).fetchall()
    accounts: dict[str, dict] = {}
    aliases: dict[str, set[str]] = {}
    for row in summaries:
        if row['account_id'] and row['account'].strip():
            aliases.setdefault(row['account'].strip().casefold(), set()).add(row['account_id'])

    def resolved_key(data):
        key = account_key(data)
        return next(iter(aliases[key])) if not data.get('account_id') and len(aliases.get(key, set())) == 1 else key

    for row in summaries:
        key = resolved_key(row)
        summary = accounts.setdefault(key, {'id': key, 'name': row['account'] or '未指定账号', 'last_published_at': None})
        published = row['last_published_at']
        if published and (summary['last_published_at'] is None or published > datetime.fromisoformat(summary['last_published_at'])):
            summary['last_published_at'] = published.isoformat()

    source = " FROM xhs_workflow_records r WHERE r.admin_id=? AND r.kind='publications'"
    args: tuple = (admin_id,)
    if account:
        names = [row['account'].strip().lower() for row in summaries if not row['account_id'] and resolved_key(row) == account]
        source += " AND (r.data_json::jsonb->>'account_id'=? OR (COALESCE(r.data_json::jsonb->>'account_id','')='' AND lower(trim(COALESCE(r.data_json::jsonb->>'account','')))=ANY(?)))"
        args += (account, names)
    before, after = start - timedelta(hours=1), end + timedelta(hours=1)
    unplanned = source + " AND r.status NOT IN ('published','archived') AND r.scheduled_at IS NULL"
    with db() as conn:
        rows = conn.execute(
            'SELECT r.*' + source + " AND r.status='published' AND r.published_at>=? AND r.published_at<? UNION ALL " +
            'SELECT r.*' + source + " AND r.status NOT IN ('published','archived') AND r.scheduled_at>=? AND r.scheduled_at<?",
            (*args, before, after, *args, before, after),
        ).fetchall()
        unscheduled_total = conn.execute('SELECT COUNT(*)' + unplanned, args).fetchone()[0]
        unscheduled_page = min(unscheduled_page, max(1, (unscheduled_total + 19) // 20))
        unplanned_rows = conn.execute('SELECT r.*' + unplanned + ' ORDER BY r.updated_at DESC,r.id LIMIT 20 OFFSET ?',
                                     (*args, (unscheduled_page - 1) * 20)).fetchall()
    entries, unscheduled = [], []
    scheduled: dict[str, list[tuple[datetime, dict]]] = {}
    for row in [*rows, *unplanned_rows]:
        timestamp = row['published_at'] if row['status'] == 'published' else row['scheduled_at']
        item = workflow._row(row)
        key = resolved_key(item['data'])
        timestamp = timestamp.isoformat() if timestamp else None
        item.update(account_key=key, calendar_at=timestamp, conflicts=[])
        if timestamp:
            when = datetime.fromisoformat(timestamp)
            if key != '(未指定账号)':
                scheduled.setdefault(key, []).append((when, item))
            if start <= when < end:
                entries.append(item)
        else:
            unscheduled.append(item)
    # 同账号排序后用双指针扫描一小时窗口；密集排期只返回十个关联编号及完整数量。
    for group in scheduled.values():
        group.sort(key=lambda pair: (pair[0], pair[1]['id']))
        left = right = 0
        for when, item in group:
            while when - group[left][0] >= timedelta(hours=1):
                left += 1
            while right < len(group) and group[right][0] - when < timedelta(hours=1):
                right += 1
            item['conflict_count'] = right - left - 1
            item['conflicts'] = [other['id'] for _, other in group[left:min(right, left + 11)] if other['id'] != item['id']][:10]
    return {'items': sorted(entries, key=lambda item: (item['calendar_at'], item['id'])), 'unscheduled': unscheduled,
            'accounts': list(accounts.values()), 'unscheduled_total': unscheduled_total,
            'unscheduled_page': unscheduled_page, 'page_size': 20}


def idea_preview(admin_id, identifier, checkpoint):
    record = workflow.get_record(admin_id, 'publications', identifier)
    values = workflow.metrics(admin_id, identifier)
    metric = next((item for item in values if item['checkpoint'] == checkpoint), None)
    if record['status'] != 'published' or not metric:
        raise HTTPException(409, detail={'error': '请先登记实际发布，并保存所选阶段的复盘数据'})
    views = metric['views']
    save_rate = metric['saves'] / views * 100 if views else None
    interaction = (metric['likes'] + metric['saves'] + metric['comments']) / views * 100 if views else None
    with db() as conn:
        summary = conn.execute(f"""SELECT COUNT(*) AS samples,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY (m.data_json::jsonb->>'saves')::double precision / (m.data_json::jsonb->>'views')::double precision * 100) AS benchmark
            FROM xhs_workflow_records r JOIN xhs_workflow_metrics m ON m.publication_id=r.id
            WHERE r.admin_id=? AND r.kind='publications' AND r.status='published' AND m.checkpoint=? AND r.id<>?
            AND {workflow.ACCOUNT_SQL}=? AND (m.data_json::jsonb->>'views')::bigint>=100""",
                               (admin_id, checkpoint, identifier, account_key(record['data']))).fetchone()
    benchmark = summary['benchmark'] if summary['samples'] >= 3 else None
    reasons = [f'依据：发布后第 {checkpoint} 天，浏览 {views}，收藏 {metric["saves"]}，评论 {metric["comments"]}。']
    if save_rate is not None:
        reasons.append(f'收藏率 {save_rate:.2f}%，互动率 {interaction:.2f}%。')
    if views < 100:
        reasons.append('浏览样本不足 100，先作为待验证方向，不能据此判断内容有效。')
    elif benchmark is not None:
        reasons.append(f'同账号同阶段 {summary["samples"]} 篇其他内容的收藏率中位数为 {benchmark:.2f}%。')
    else:
        reasons.append('同账号同阶段的对比样本不足 3 篇，暂不判断优于历史表现。')
    series = '进阶练习' if views >= 100 and benchmark is not None and save_rate >= benchmark else '问题答疑' if metric['comments'] else '方法验证'
    source = None
    if record['parent_id']:
        draft = workflow.get_record(admin_id, 'drafts', record['parent_id'])
        material = workflow.get_record(admin_id, 'materials', draft['parent_id'])
        source = material['data']
    title = (record['title'] + ' · ' + series)[:120]
    idea = Idea(title=title, source_publication_id=identifier, grade=source['grade'] if source else '一年级', subject=source['subject'] if source else '数学', keyword=source['keyword'] if source else '',
                problem=record['data']['conclusion'][:2000], angle=(record['data']['next_action'] or f'围绕原内容制作一篇{series}，保留相同观察阶段验证反馈。')[:2000],
                notes=('\n'.join(reasons) + '\n原发布：' + record['data']['url'] + '\n本阶段观察：' + metric.get('notes', ''))[:4000])
    return {'data': idea.model_dump(mode='json'), 'reasons': reasons, 'series': series, 'checkpoint': checkpoint}


def tutorial(admin_id, create=False):
    identifiers = {kind: str(uuid5(NAMESPACE_URL, f'learn-coach:xhs-guide-v1:{admin_id}:{kind}')) for kind in ('ideas', 'materials', 'drafts', 'publications')}
    if create:
        idea = Idea(title='示例 · 一年级找规律', keyword='找规律', audience='一年级家长', problem='帮助孩子说出相邻数字如何变化', angle='先示范，再练习，最后说出理由', notes='入门示例，可修改；请不要未经检查直接发布。')
        material = Material(title='示例 · 找规律练习', keyword='找规律', questions=[{'stem': '1，2，3，__', 'answer': '4', 'analysis': '每次增加 1，所以下一个数是 4。'}])
        draft = Draft(title='示例 · 找规律笔记', headline='和孩子一起发现数字规律', body='先读一读 1、2、3，观察相邻的数怎样变化。再想一想：下一个数是什么？最后请孩子说出理由。', hashtags='#一年级数学 #找规律', cover_title='一起找规律', cover_subtitle='观察 · 练习 · 讲理由', cards=[{'heading': '试一试', 'body': '1，2，3，__\n每次增加 1，下一个数是 4。'}])
        publication = Publication(title='示例 · 首次发布计划', notes='此记录未实际发布。请按步骤复核并手动发布，成功后登记真实链接。')
        parent = None
        for kind, model in zip(identifiers, (idea, material, draft, publication), strict=True):
            workflow.create_record(admin_id, kind, identifiers[kind], parent, model.model_dump(mode='json'))
            parent = identifiers[kind]
    with db() as conn:
        found = conn.execute('SELECT id,kind FROM xhs_workflow_records WHERE admin_id=? AND id IN (?,?,?,?)', (admin_id, *identifiers.values())).fetchall()
    return {'records': {row['kind']: row['id'] for row in found}}
