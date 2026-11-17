"""本机浏览器桥的短期操作凭证；独立签名用途且在线核验最新权限。"""
import hashlib
import hmac
import json
import time

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.admin_permissions import require
from app.deps import SESSION_COOKIE, require_user
from app.library_deps import no_store
from app.models.admin_local_access_api_responses import (
    AdminLocalAccessIssueResponse,
    AdminLocalAccessVerifyResponse,
)
from app.security import _b64url, _b64url_decode, get_secret, parse_token
from app.services.user_store import CurrentUser, get_user_by_id

router = APIRouter(prefix='/api/v1/local-access', tags=['本机后台授权'], dependencies=[Depends(no_store)])


class LocalOperation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    path: str = Field(max_length=500)
    method: str = Field(pattern='^(GET|POST)$')


class LocalVerification(LocalOperation):
    token: str = Field(max_length=4096)
    origin: str = Field(max_length=500)


def check_operation(user, path, method):
    import re
    path = path.split('?')[0]
    rules = {
        ('GET', '/accounts'): ('xhsAccounts', 'view'),
        ('POST', '/accounts/add'): ('xhsAccounts', 'create'),
        ('POST', '/accounts/update'): ('xhsAccounts', 'update'),
        ('POST', '/accounts/open'): ('xhsAccounts', 'run'),
        ('POST', '/accounts/open-note'): ('xhsAccounts', 'run'),
        ('POST', '/accounts/close'): ('xhsAccounts', 'run'),
        ('GET', '/publisher/state'): ('xhsPublishing', 'view'),
        ('GET', '/publisher/preview'): ('xhsPublishing', 'view'),
        ('POST', '/publisher/open'): ('xhsPublishing', 'run'),
        ('POST', '/publisher/prepare'): ('xhsPublishing', 'publish'),
        ('POST', '/jobs'): ('xhsResearch', 'run'),
        ('POST', '/control'): ('xhsResearch', 'run'),
        ('POST', '/open'): ('xhsResearch', 'run'),
        ('POST', '/collect'): ('xhsResearch', 'run'),
    }
    permission = rules.get((method, path))
    if method == 'GET' and re.fullmatch(r'/jobs/[a-zA-Z0-9_-]{8,80}', path):
        permission = ('xhsResearch', 'view')
    if not permission:
        raise HTTPException(403, detail={'error': '本机操作未获授权', 'code': 'permission_denied'})
    require(user, *permission)


def signature(payload: str) -> str:
    return _b64url(hmac.new(get_secret(), b'admin-local-access:' + payload.encode(), hashlib.sha256).digest())


@router.post('/issue', response_model=AdminLocalAccessIssueResponse, response_model_exclude_unset=True)
def issue(body: LocalOperation, request: Request, user: CurrentUser = Depends(require_user), token: str | None = Cookie(None, alias=SESSION_COOKIE)):
    check_operation(user, body.path, body.method)
    session = parse_token(token or '') or {}
    payload = _b64url(json.dumps({'user': user.id, 'revision': user.permissions_revision, 'exp': min(time.time() + 30, session.get('exp', 0)),
        'origin': request.headers.get('origin') or str(request.base_url).rstrip('/'),
        'path': body.path, 'method': body.method, 'session': session}).encode())
    return {'token': payload + '.' + signature(payload)}


@router.post('/verify', response_model=AdminLocalAccessVerifyResponse, response_model_exclude_unset=True)
def verify(body: LocalVerification):
    try:
        payload, sig = body.token.split('.')
        if not hmac.compare_digest(signature(payload), sig):
            raise ValueError
        data = json.loads(_b64url_decode(payload))
        if data['exp'] < time.time() or any(data[key] != getattr(body, key) for key in ('origin', 'path', 'method')):
            raise ValueError
        user = get_user_by_id(data['user'])
        session = data['session']
        if not user or user.permissions_revision != data['revision'] or session.get('iat', 0) < user.token_valid_after:
            raise ValueError
        if session.get('sid'):
            from app.services.workspace_sessions import valid
            if not valid(session['sid'], user.id):
                raise ValueError
    except (ValueError, KeyError, TypeError):
        raise HTTPException(403, detail={'error': '本机操作凭证已失效，请刷新后重试'}) from None
    check_operation(user, body.path, body.method)
    return {'authorized': True}
