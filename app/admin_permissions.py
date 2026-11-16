"""后台菜单与操作的统一权限目录；未登记的管理接口默认拒绝。"""

import re
from typing import Literal

from fastapi import HTTPException

Action = Literal['view', 'create', 'update', 'delete', 'export', 'publish', 'run']
ACTION_LABELS = {'view': '查看', 'create': '新增', 'update': '修改', 'delete': '删除',
                 'export': '导出/下载', 'publish': '发布/撤回', 'run': '执行/生成'}
MENUS = [
    ('overview', '待办与概览', '工作台', 'view'),
    ('miniAnalytics', '内容数据看板', '工作台', 'view'),
    ('papers', '公共习题', '内容资料', 'view create update delete export publish'),
    ('topics', '专题合集', '内容资料', 'view create update delete'),
    ('categories', '分类管理', '内容资料', 'view create update delete'),
    ('catalogTags', '教材与知识点', '内容资料', 'view create update delete'),
    ('xhsResearch', '选题调研', '小红书工作台', 'view create update delete export run'),
    ('xhsIdeas', '选题库', '小红书工作台', 'view create update'),
    ('xhsMaterials', '资料制作', '小红书工作台', 'view create update export run'),
    ('xhsDrafts', '笔记制作', '小红书工作台', 'view create update export run'),
    ('xhsPublishing', '发布管理', '小红书工作台', 'view create update export publish run'),
    ('xhsAnalytics', '效果复盘', '小红书工作台', 'view update export'),
    ('xhsAssets', '素材库', '小红书工作台', 'view create update delete export'),
    ('xhsAccounts', '账号管理', '小红书工作台', 'view create update run'),
    ('miniUsers', '小程序用户', '用户服务', 'view create update delete'),
    ('users', '出题用户', '用户服务', 'view create update delete'),
    ('resourceRequests', '资料需求', '用户服务', 'view update'),
    ('supportCenter', '小程序反馈', '用户服务', 'view update'),
    ('feedback', '出题质量反馈', '用户服务', 'view'),
    ('accountClosures', '注销申请', '用户服务', 'view update'),
    ('orders', '会员订单', '会员交易', 'view update export run'),
    ('referrals', '推广管理与奖励规则', '推广运营', 'view create export'),
    ('settlements', '个人收益与结算明细', '推广运营', 'view create export'),
    ('settlementCosts', '费用核对、制单与成本台账', '财务中心', 'view run export'),
    ('settlementReview', '结算审核与异议处理', '财务中心', 'view run'),
    ('settlementPayout', '付款登记与批次', '财务中心', 'view run export'),
    ('financeLedger', '经营账本', '财务中心', 'view create update export'),
    ('membershipPlans', '会员套餐', '会员交易', 'view create update'),
    ('membershipCards', '会员卡密', '会员交易', 'view create update export'),
    ('reconciliations', '微信账单核对', '财务中心', 'view run'),
    ('membershipContact', '会员与联系设置', '运营配置', 'view update'),
    ('banners', '首页推荐图', '运营配置', 'view create update delete'),
    ('notices', '公告与弹窗', '运营配置', 'view create update delete'),
    ('delivery', '订阅提醒', '运营配置', 'view'),
    ('documents', '协议与隐私页', '运营配置', 'view update'),
    ('adminAccounts', '管理员账号与授权', '系统设置', ''),
    ('accountSecurity', '我的账号安全', '系统设置', 'view delete'),
    ('llm', '模型配置', '系统设置', 'view update delete run'),
    ('typeAccess', '题型权限', '系统设置', 'view update'),
    ('dictionary', '年级科目字典', '系统设置', 'view create update delete'),
    ('logs', '系统日志', '系统设置', 'view'),
]
MENU_ACTIONS = {key: actions.split() for key, _, _, actions in MENUS}
LOOKUPS = {
    'papers': {'categories', 'dictionary', 'tags'},
    'banners': {'categories', 'dictionary', 'papers'},
    'topics': {'papers'}, 'resourceRequests': {'papers'}, 'supportCenter': {'papers'},
    'orders': {'payment'}, 'reconciliations': {'payment'}, 'membershipCards': {'payment'},
}


def catalog():
    return [{'id': key, 'label': label, 'group': group, 'actions': actions.split(),
             'super_only': key == 'adminAccounts'} for key, label, group, actions in MENUS]


def normalize(value: dict) -> dict[str, list[str]]:
    result = {}
    for menu, actions in value.items():
        # 旧页面或历史授权可能仍携带已下线的菜单，保存时自动移除。
        if menu == 'generationReview':
            continue
        if menu not in MENU_ACTIONS or menu == 'adminAccounts' or not isinstance(actions, list):
            raise HTTPException(422, detail={'error': '权限菜单无效或仅限超级管理员'})
        if any(action not in MENU_ACTIONS[menu] for action in actions):
            raise HTTPException(422, detail={'error': '菜单不支持所选操作'})
        if actions:
            result[menu] = [action for action in MENU_ACTIONS[menu] if action == 'view' or action in actions]
    if any(key in result for key in ('settlementCosts', 'settlementReview', 'settlementPayout')):
        result['settlements'] = list(dict.fromkeys(['view', *result.get('settlements', [])]))
    return result


def allowed(user, menu: str, action: str = 'view') -> bool:
    return user.role == 'admin' and user.is_active and (user.is_super_admin or menu == 'accountSecurity' and action in ('view', 'delete') or
        menu != 'adminAccounts' and 'view' in user.admin_permissions.get(menu, []) and action in user.admin_permissions.get(menu, []))


def require(user, menu: str, action: str = 'view') -> None:
    if not allowed(user, menu, action):
        raise HTTPException(403, detail={'error': '未获授权执行此操作，请联系超级管理员',
                                        'code': 'permission_denied', 'menu': menu, 'action': action})


# 顺序由具体到通用。GET 导出及 POST 查询也按实际效果单独归类。
RULES = [
    (r'/catalog/schedules/[^/]+', 'papers', 'publish'),
    (r'/catalog/(?:schedules|health)', 'papers', 'view'),
    (r'/catalog/health/[^/]+/probe', 'papers', 'view'),
    (r'/catalog/health/[^/]+/confirm', 'papers', 'update'),
    (r'/settlements/month-end', 'settlementCosts', 'view'),
    (r'/settlements/(?:cost-vouchers(?:/[^/]+(?:/files)?)?|cost-voucher-files/[^/]+)', 'settlementCosts', 'view'),
    (r'/referrals/comparison', 'referrals', 'view'),
    (r'/settlements/payout-candidates(?:/preview)?', 'settlementPayout', 'run'),
    (r'/settlements/expenses/export\.xlsx', 'settlementCosts', 'export'),
    (r'/settlements/expenses', 'settlementCosts', 'view'),
    (r'/settlements/finance-controls', 'settlements', 'view'),
    (r'/settlements/monthly(?:/archive)?', 'settlements', 'view'),
    (r'/settlements/monthly/export.xlsx', 'settlements', 'export'),
    (r'/settlements/batches(?:/[^/]+(?:/(?:preview|import|cancel|export.csv))?)?', 'settlementPayout', 'view'),
    (r'/settlements/disputes(?:/[^/]+(?:/(?:reply|files))?)?', 'settlements', 'view'),
    (r'/settlements/dispute-files/[^/]+', 'settlements', 'view'),
    (r'/settlements/rewards/[^/]+/costs', 'settlementCosts', 'run'),
    (r'/settlements/requests/[^/]+/(?:start|reject|costs)', 'settlementCosts', 'run'),
    (r'/settlements/statements/[^/]+/approve', 'settlementReview', 'run'),
    (r'/settlements/statements/[^/]+/(?:paid|payee(?:/reveal)?)', 'settlementPayout', 'run'),
    (r'/settlements/statements', 'settlementCosts', 'run'),
    (r'/settlements/statements/[^/]+/void', 'settlementReview', 'run'),
    (r'/settlements/bills(?:/[^/]+)?', 'settlementCosts', 'view'),
    (r'/settlements/statements/[^/]+/attachments', 'settlements', 'view'),
    (r'/referrals/campaigns/[^/]+/expenses(?:/[^/]+)?', 'referrals', 'view'),
    (r'/referrals/quality', 'referrals', 'view'),
    (r'/settlements/(?:summary|rules|admins|notices|notices/read|statements/[^/]+|attachments/[^/]+)', 'settlements', 'view'),
    (r'/settlements/payee', 'settlements', 'create'),
    (r'/settlements/requests/[^/]+/recover', 'settlements', 'create'),
    (r'/settlements/(?:bills(?:/[^/]+)?|statements/[^/]+/(?:attachments|payee(?:/reveal)?))', 'adminAccounts', None),
    (r'/referrals/campaigns(?:/[^/]+(?:/performance)?)?', 'referrals', None),
    (r'/referrals/budget/[^/]+', 'referrals', 'view'),
    (r'/settlements/export(?:\.xlsx)?', 'settlements', 'export'),
    (r'/finance-ledger/export\.csv', 'financeLedger', 'export'),
    (r'/finance-ledger/[^/]+/void', 'financeLedger', 'update'),
    (r'/finance-ledger(?:/[^/]+)?', 'financeLedger', None),
    (r'/settlements/list/(?:rewards|statements|adjustments|requests)', 'settlements', 'view'),
    (r'/settlements/requests/[^/]+/(?:start|reject|costs)', 'adminAccounts', None),
    (r'/settlements/requests/preview', 'settlements', 'create'),
    (r'/settlements/requests/[^/]+/cancel', 'settlements', 'create'),
    (r'/settlements/requests/[^/]+', 'settlements', 'view'),
    (r'/settlements/requests', 'settlements', 'create'),
    (r'/settlements/(?:policy|adjustments|rewards/[^/]+/costs|statements(?:/[^/]+/(?:approve|paid|void))?)', 'adminAccounts', None),
    (r'/referrals/(?:qrcode|poster|export/(?:users|orders))', 'referrals', 'export'),
    (r'/referrals/users/[^/]+(?:/audit)?', 'adminAccounts', None),
    (r'/referrals/(?:code|admins|users|orders|summary|conversion|acquisition|rules)', 'referrals', None),
    (r'/access(?:/catalog|/users/[^/]+)?', 'adminAccounts', None),
    (r'/users(?:/[^/]+(?:/templates(?:/[^/]+)?)?)?', 'users', None),
    (r'/stats', 'overview', None), (r'/feedbacks', 'feedback', None),
    (r'/logs', 'logs', None), (r'/generation-traces', 'logs', None),
    (r'/sessions(?:/[^/]+)?', 'accountSecurity', None),
    (r'/(?:llm-config|image-config)', 'llm', None),
    (r'/model-health', 'llm', 'view'), (r'/(?:llm-models|test-llm|test-llm-generation)', 'llm', 'run'),
    (r'/catalog/type-rules(?:/[^/]+)?', 'typeAccess', None),
    (r'/catalog/tags(?:/[^/]+)?', 'catalogTags', None),
    (r'/catalog/papers/[^/]+/assets/[^/]+', 'papers', 'view'),
    (r'/catalog/import', 'papers', 'create'),
    (r'/catalog/papers/[^/]+/editions/import', 'papers', 'update'),
    (r'/catalog/papers/[^/]+/revision', 'papers', 'update'),
    (r'/catalog/batch', 'papers', 'update'),
    (r'/catalog/(?:summary|sources|papers(?:/[^/]+(?:/(?:labels|editions|edition-sources|preview))?)?)', 'papers', None),
    (r'/mini-users(?:/[^/]+(?:/avatar/[^/]+|/events|/renew)?)?', 'miniUsers', None),
    (r'/experience/support', 'membershipContact', None),
    (r'/experience/feedback(?:/[^/]+)?', 'supportCenter', None),
    (r'/(?:experience/analytics|site/analytics)', 'miniAnalytics', None),
    (r'/experience/topics(?:/[^/]+)?', 'topics', None),
    (r'/engagement/delivery-status', 'delivery', None),
    (r'/engagement/requests(?:/[^/]+)?', 'resourceRequests', None),
    (r'/engagement/closures(?:/[^/]+)?', 'accountClosures', None),
    (r'/commerce/plans(?:/[^/]+)?', 'membershipPlans', None),
    (r'/commerce/cards/[^/]+/disable', 'membershipCards', 'update'),
    (r'/commerce/cards', 'membershipCards', None),
    (r'/commerce/orders/export', 'orders', 'export'),
    (r'/commerce/(?:orders|refunds)/[^/]+/sync', 'orders', 'run'),
    (r'/commerce/orders/[^/]+/cancel', 'orders', 'update'),
    (r'/commerce/(?:orders|refunds)(?:/[^/]+)?', 'orders', None),
    (r'/commerce/reconciliations(?:/[^/]+)?', 'reconciliations', None),
    (r'/site/categories/order', 'categories', 'update'),
    (r'/site/categories(?:/[^/]+)?', 'categories', None),
    (r'/site/home-settings', 'banners', None),
    (r'/site/banners(?:/[^/]+(?:/image)?)?', 'banners', None),
    (r'/site/notices(?:/[^/]+)?', 'notices', None),
    (r'/site/documents(?:/[^/]+)?', 'documents', None),
    (r'/site/dictionary/(?:adopt|reorder)', 'dictionary', 'update'),
    (r'/site/dictionary(?:/[^/]+(?:/[^/]+)?)?', 'dictionary', None),
    (r'/xhs-research/notes/export', 'xhsResearch', 'export'),
    (r'/xhs-research/tasks/[^/]+/(?:start|results|failure)', 'xhsResearch', 'run'),
    (r'/xhs-research/(?:batches|notes|tasks)(?:/[^/]+(?:/(?:mark|history))?)?', 'xhsResearch', None),
    (r'/xhs-workflow/generate-copy', 'xhsDrafts', 'run'),
    (r'/xhs-workflow/publication-check', 'xhsPublishing', 'view'),
    (r'/xhs-workflow/publications/[^/]+/refresh-draft', 'xhsPublishing', 'update'),
    (r'/xhs-workflow/(?:analytics|metrics/[^/]+|reviews/[^/]+)', 'xhsAnalytics', None),
    (r'/xhs-workspace/assets/[^/]+/file', 'xhsAssets', 'export'),
    (r'/xhs-workspace/assets(?:/[^/]+(?:/(?:thumbnail|preview))?)?', 'xhsAssets', None),
    (r'/xhs-workspace/calendar', 'xhsPublishing', 'view'),
    (r'/xhs-workspace/(?:today|tutorial)', 'xhsPublishing', 'view'),
    (r'/xhs-workspace/analytics/[^/]+/idea-preview', 'xhsAnalytics', 'view'),
]


def route_permission(path: str, method: str) -> tuple[str, str] | None:
    path = path.removeprefix('/api/v1/admin')
    if re.fullmatch(r'/catalog/schedules/[^/]+', path) and method == 'GET':
        return 'papers', 'view'
    if path == '/settlements/finance-controls' and method == 'PUT':
        return 'adminAccounts', 'update'
    if path == '/settlements/monthly/archive':
        return 'settlementReview', 'run'
    if path.startswith('/settlements/batches'):
        return 'settlementPayout', 'export' if path.endswith('/export.csv') else 'run' if method == 'POST' else 'view'
    if re.fullmatch(r'/referrals/campaigns/[^/]+/expenses(?:/[^/]+)?', path):
        return 'referrals', 'view' if method == 'GET' else 'create'
    if path == '/settlements/bills' and method == 'POST':
        return 'settlementCosts', 'run'
    lookup = re.fullmatch(r'/options/([^/]+)/([^/]+)', path)
    if lookup and method == 'GET' and lookup[2] in LOOKUPS.get(lookup[1], set()):
        return lookup[1], 'view'
    action = {'GET': 'view', 'HEAD': 'view', 'POST': 'create', 'PUT': 'update', 'PATCH': 'update', 'DELETE': 'delete'}.get(method, '')
    match = re.fullmatch(r'/xhs-workflow/records/(ideas|materials|drafts|publications)(?:/[^/]+(?:/versions)?)?', path)
    if match:
        return {'ideas': 'xhsIdeas', 'materials': 'xhsMaterials', 'drafts': 'xhsDrafts', 'publications': 'xhsPublishing'}[match[1]], action
    for pattern, menu, override in RULES:
        if re.fullmatch(pattern, path):
            if method == 'PUT' and path.startswith('/referrals/campaigns/'):
                return 'referrals', 'create'
            if method == 'POST' and menu == 'reconciliations':
                return menu, 'run'
            if method == 'POST' and path.endswith('/renew'):
                return menu, 'update'
            return menu, override or action
    return None


async def authorize_request(request, user) -> None:
    from app.blocking import run_sync
    from app.services.user_store import get_user_by_id

    path, method = request.url.path, request.method
    if path == '/api/v1/admin/settlements/month-end' and method == 'GET':
        if any(allowed(user, menu) for menu in ('settlementCosts', 'settlementReview', 'settlementPayout', 'reconciliations')):
            return
        require(user, 'settlementCosts')
        return
    if re.fullmatch(r'/api/v1/admin/settlements/(?:cost-vouchers(?:/[^/]+(?:/files)?)?|cost-voucher-files/[^/]+)', path):
        write = method not in ('GET', 'HEAD')
        if allowed(user, 'referrals', 'create' if write else 'view') or allowed(user, 'settlementCosts', 'run' if write else 'view') or (not write and any(allowed(user, key) for key in ('settlementReview', 'settlementPayout'))):
            return  # 具体凭据仍在服务层校验归属。
        require(user, 'settlementCosts', 'run' if write else 'view')
        return
    if method == 'POST' and path.startswith('/api/v1/admin/settlements/disputes'):
        if re.fullmatch(r'/api/v1/admin/settlements/disputes/[^/]+/(reply|files)', path) and allowed(user, 'settlementReview', 'run'):
            require(user, 'settlementReview', 'run')
        else:
            require(user, 'settlements', 'create')
        return
    permission = route_permission(path, method)
    if permission is None:
        raise HTTPException(403, detail={'error': '接口尚未配置管理权限', 'code': 'permission_denied'})
    menu, action = permission
    if path.endswith('/xhs-workspace/tutorial'):
        for stage in ('xhsIdeas', 'xhsMaterials', 'xhsDrafts', 'xhsPublishing'):
            require(user, stage, 'create' if method == 'POST' else 'view')
        return
    if path.endswith('/xhs-workspace/today'):
        # 待办汇总包含三个阶段的数据；只授予单一阶段时使用该阶段自己的列表。
        for stage in ('xhsMaterials', 'xhsDrafts', 'xhsPublishing', 'xhsAnalytics'):
            require(user, stage)
        return
    if menu == 'users':
        target_id = request.path_params.get('user_id')
        if target_id is not None:
            try:
                identifier = int(target_id)
            except (ValueError, TypeError):
                raise HTTPException(422, detail={'error': '用户编号无效'}) from None
            target = await run_sync(get_user_by_id, identifier)
            if target and target.role == 'admin':
                menu = 'adminAccounts'
        elif request.query_params.get('role') == 'admin':
            menu = 'adminAccounts'
        # 创建/更新角色还会在账号事务中重新校验目标和操作者。
        if method in ('POST', 'PUT'):
            try:
                body = await request.json()
            except ValueError:
                body = {}
            if isinstance(body, dict) and body.get('role') == 'admin':
                menu = 'adminAccounts'
    require(user, menu, action)
