from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from app.deps import require_admin, require_recent_admin
from app.library_deps import no_store
from app.models.finance_ledger import FinanceLedgerEntry, FinanceLedgerInput, FinanceLedgerPage, FinanceLedgerUpdate
from app.services import finance_ledger
from app.services.user_store import CurrentUser

router = APIRouter(prefix='/api/v1/admin/finance-ledger', tags=['经营账本'], dependencies=[Depends(no_store)])


@router.get('', response_model=FinanceLedgerPage)
def listing(page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=200), direction: Literal['', 'income', 'expense'] = '', status: Literal['', 'active', 'void'] = 'active', q: str = Query('', max_length=120), start_date: str = Query('', max_length=10), end_date: str = Query('', max_length=10), user: CurrentUser = Depends(require_admin)):
    return finance_ledger.list_entries(page=page, page_size=page_size, direction=direction, status=status, q=q, start_date=start_date, end_date=end_date)


@router.post('', status_code=201, response_model=FinanceLedgerEntry)
def create(body: FinanceLedgerInput, user: CurrentUser = Depends(require_recent_admin)):
    return finance_ledger.create(user.id, body.model_dump())


@router.put('/{identifier}', response_model=FinanceLedgerEntry)
def update(identifier: str, body: FinanceLedgerUpdate, user: CurrentUser = Depends(require_recent_admin)):
    return finance_ledger.update(user.id, identifier, body.revision, body.model_dump(exclude={'revision'}))


@router.post('/{identifier}/void', response_model=FinanceLedgerEntry)
def void(identifier: str, revision: int = Query(ge=1), user: CurrentUser = Depends(require_recent_admin)):
    return finance_ledger.void(user.id, identifier, revision)


@router.get('/export.csv', response_class=Response, responses={200: {'content': {'text/csv': {'schema': {'type': 'string', 'format': 'binary'}}}}})
def export_csv(direction: Literal['', 'income', 'expense'] = '', status: Literal['', 'active', 'void'] = 'active', q: str = Query('', max_length=120), start_date: str = Query('', max_length=10), end_date: str = Query('', max_length=10), user: CurrentUser = Depends(require_admin)):
    return Response(finance_ledger.export_csv(direction=direction, status=status, q=q, start_date=start_date, end_date=end_date), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="finance-ledger.csv"'})
