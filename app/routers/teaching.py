"""个人题库、后台资料运营及已下线接口兼容入口。"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.blocking import run_sync
from app.deps import require_admin, require_user
from app.library_deps import no_store, require_mini_user
from app.models.teaching import (
    BankContent,
    BankItem,
    BankMetadata,
    BankPage,
    BankSelection,
    HealthPage,
    LinkCheck,
    ScheduleInput,
    ScheduleItem,
    SchedulePage,
)
from app.services import catalog_operations, question_bank
from app.services.mini_auth import MiniUser
from app.services.rate_limit import allow
from app.services.user_store import CurrentUser

router = APIRouter(prefix='/api/v1', tags=['教学与资料运营'], dependencies=[Depends(no_store)])


# 旧小程序仍可能访问这些路径，明确告知下线，不再读取或保存关注。
@router.api_route('/mini/curriculum', methods=['GET', 'PUT'], status_code=410, include_in_schema=False)
@router.delete('/mini/curriculum/{identifier}', status_code=410, include_in_schema=False)
@router.get('/mini/curriculum/recommendations', status_code=410, include_in_schema=False)
@router.get('/mini/curriculum/textbooks', status_code=410, include_in_schema=False)
def retired_curriculum(user: MiniUser = Depends(require_mini_user)):
    raise HTTPException(410, detail={'error': '教材关注功能已下线，请到习题库按年级和学科查找资料'})


@router.get('/question-bank', response_model=BankPage)
def bank(q: str = Query('', max_length=120), grade: str = Query('', max_length=80), subject: str = Query('', max_length=80),
         section_type: str = Query('', max_length=80), difficulty: Literal['', 'easy', 'medium', 'hard'] = '',
         limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000), user: CurrentUser = Depends(require_user)):
    return question_bank.listing(user.id, q, grade, subject, section_type, difficulty, limit, offset)


@router.post('/question-bank', response_model=BankItem, status_code=201)
def save_question(body: BankContent, user: CurrentUser = Depends(require_user)):
    return question_bank.save(user.id, body)


@router.post('/question-bank/selection', response_model=BankPage)
def select_questions(body: BankSelection, user: CurrentUser = Depends(require_user)):
    return question_bank.select(user.id, body.ids)


@router.patch('/question-bank/{identifier}', response_model=BankItem)
def edit_question(identifier: str, body: BankMetadata, user: CurrentUser = Depends(require_user)):
    return question_bank.update(user.id, identifier, body)


@router.delete('/question-bank/{identifier}', status_code=204)
def delete_question(identifier: str, revision: int = Query(ge=1), user: CurrentUser = Depends(require_user)):
    question_bank.remove(user.id, identifier, revision)
    return Response(status_code=204)


@router.get('/admin/catalog/schedules', response_model=SchedulePage)
def schedules(limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000),
              status: Literal['', 'pending', 'published', 'failed', 'cancelled'] = '', user: CurrentUser = Depends(require_admin)):
    return catalog_operations.schedule_list(user.id, limit, offset, status)


@router.put('/admin/catalog/schedules/{catalog_id}', response_model=ScheduleItem)
def schedule(catalog_id: str, body: ScheduleInput, user: CurrentUser = Depends(require_admin)):
    return catalog_operations.schedule(user.id, catalog_id, body)


@router.get('/admin/catalog/schedules/{catalog_id}', response_model=ScheduleItem | None)
def schedule_detail(catalog_id: str, user: CurrentUser = Depends(require_admin)):
    return catalog_operations.schedule_detail(user.id, catalog_id)


@router.delete('/admin/catalog/schedules/{catalog_id}', status_code=204)
def cancel_schedule(catalog_id: str, revision: int = Query(ge=1), user: CurrentUser = Depends(require_admin)):
    catalog_operations.cancel(user.id, catalog_id, revision)
    return Response(status_code=204)


@router.get('/admin/catalog/health', response_model=HealthPage)
def health(q: str = Query('', max_length=120), limit: int = Query(20, ge=1, le=30), offset: int = Query(0, ge=0, le=100000),
           only_issues: bool = False, category: Literal['', 'file', 'preview', 'textbook', 'review', 'answers', 'link'] = '',
           user: CurrentUser = Depends(require_admin)):
    return catalog_operations.health(user.id, q, limit, offset, only_issues, category)


@router.post('/admin/catalog/health/{catalog_id}/probe', response_model=LinkCheck)
async def probe(catalog_id: str, user: CurrentUser = Depends(require_admin)):
    if not allow(f'catalog-probe:{user.id}', 20, 60):
        raise HTTPException(429, detail={'error': '检测过于频繁，请稍后再试'})
    url = await run_sync(catalog_operations.link_url, user.id, catalog_id)
    status, message = await catalog_operations.probe_url(url)
    return await run_sync(catalog_operations.record_link, user.id, catalog_id, url, status, message)


@router.post('/admin/catalog/health/{catalog_id}/confirm', response_model=LinkCheck)
def confirm_link(catalog_id: str, user: CurrentUser = Depends(require_admin)):
    url = catalog_operations.link_url(user.id, catalog_id)
    return catalog_operations.record_link(user.id, catalog_id, url, 'confirmed', '管理员已人工确认链接与提取码可用')
