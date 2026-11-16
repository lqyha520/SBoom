from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response

from app.db import db
from app.deps import require_admin, require_recent_admin
from app.http_contracts import binary_responses
from app.models.promotion_finance import (
    CostVoucherInput,
    DisputeInput,
    DisputeReply,
    FinanceControls,
    MonthlyArchive,
    PayoutBatchInput,
    PayoutImportInput,
    PayoutPreview,
    PayoutSelection,
)
from app.models.promotion_finance_api_responses import (
    PromotionFinanceArchiveResponse,
    PromotionFinanceControlsResponse,
    PromotionFinanceCostVouchersResponse,
    PromotionFinanceCreateDisputeResponse,
    PromotionFinanceCreateVoucherResponse,
    PromotionFinanceDisputeDetailResponse,
    PromotionFinanceDisputesResponse,
    PromotionFinanceFinanceExpensesResponse,
    PromotionFinanceMonthEndResponse,
    PromotionFinanceMonthlyResponse,
    PromotionFinanceReplyResponse,
    PromotionFinanceSaveControlsResponse,
    PromotionFinanceUpdateVoucherResponse,
    PromotionFinanceUploadResponse,
    PromotionFinanceUploadVoucherResponse,
)
from app.models.responses import (
    PayoutBatchPageResponse,
    PayoutBatchResponse,
    PayoutCandidatePageResponse,
    PayoutImportResponse,
    PayoutPreviewResponse,
    PayoutSelectionResponse,
)
from app.models.settlements import Revision
from app.services import settlement_access, settlement_batches, settlement_disputes, settlement_ledger, settlements
from app.services.mini_errors import fail
from app.services.user_store import CurrentUser

router = APIRouter()


@router.get('/month-end', response_model=PromotionFinanceMonthEndResponse, response_model_exclude_unset=True)
def month_end(month: str = Query(pattern=r'^\d{4}-\d{2}$'), page: int = Query(1, ge=1, le=5000), cost_page: int = Query(1, ge=1, le=5000), dispute_page: int = Query(1, ge=1, le=5000), user: CurrentUser = Depends(require_admin)):
    from app.services.finance_close import checklist
    return checklist(user.id, month, page, cost_page, dispute_page)


@router.get('/cost-vouchers', response_model=PromotionFinanceCostVouchersResponse, response_model_exclude_unset=True)
def cost_vouchers(admin_id: int | None = Query(None, gt=0), q: str = Query('', max_length=80), page: int = Query(1, ge=1, le=5000), user: CurrentUser = Depends(require_admin)):
    from app.services.cost_vouchers import listing
    return listing(user.id, admin_id, q, page)


@router.post('/cost-vouchers', response_model=PromotionFinanceCreateVoucherResponse, response_model_exclude_unset=True)
def create_voucher(body: CostVoucherInput, user: CurrentUser = Depends(require_recent_admin)):
    from app.services.cost_vouchers import save
    return save(user.id, body)


@router.put('/cost-vouchers/{identifier}', response_model=PromotionFinanceUpdateVoucherResponse, response_model_exclude_unset=True)
def update_voucher(identifier: str, body: CostVoucherInput, user: CurrentUser = Depends(require_recent_admin)):
    from app.services.cost_vouchers import save
    return save(user.id, body, identifier)


@router.post('/cost-vouchers/{identifier}/files', response_model=PromotionFinanceUploadVoucherResponse, response_model_exclude_unset=True)
async def upload_voucher(identifier: str, request: Request, name: str = Query(min_length=1, max_length=120), user: CurrentUser = Depends(require_recent_admin)):
    from app.blocking import run_sync
    from app.services.cost_vouchers import upload
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 2 * 1024 * 1024:
            fail('凭据附件限 2MB', 413)
        chunks.append(chunk)
    return await run_sync(upload, user.id, identifier, name, b''.join(chunks))


@router.get('/cost-voucher-files/{identifier}', response_class=Response, responses=binary_responses('application/pdf', 'image/jpeg', 'image/png', 'application/octet-stream'))
def voucher_file(identifier: str, user: CurrentUser = Depends(require_admin)):
    from app.services.cost_vouchers import file
    row = file(user.id, identifier)
    return Response(bytes(row['content']), media_type=row['media_type'], headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(row['name']), 'X-Content-Type-Options': 'nosniff'})


@router.get('/payout-candidates', response_model=PayoutCandidatePageResponse, response_model_exclude_unset=True)
def payout_candidates(page: int = Query(1, ge=1, le=5000), user: CurrentUser = Depends(require_admin)):
    return settlement_batches.candidates(user.id, page)


@router.post('/payout-candidates/preview', response_model=PayoutSelectionResponse, response_model_exclude_unset=True)
def payout_selection(body: PayoutSelection, user: CurrentUser = Depends(require_admin)):
    return settlement_batches.selection(user.id, body.statement_ids)


@router.get('/expenses', response_model=PromotionFinanceFinanceExpensesResponse, response_model_exclude_unset=True)
def finance_expenses(admin_id: int | None = Query(None, gt=0), campaign_id: str = Query('', max_length=80),
                     q: str = Query('', max_length=80), start_date: str = Query('', max_length=10),
                     end_date: str = Query('', max_length=10), state: Literal['all', 'active', 'void'] = 'all',
                     page: int = Query(1, ge=1, le=5000), user: CurrentUser = Depends(require_admin)):
    from app.services.referral_expenses import finance_listing
    return finance_listing(user.id, admin_id, campaign_id, q, start_date, end_date, state, page)


@router.get('/expenses/export.xlsx', response_class=Response, responses=binary_responses('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))
def export_finance_expenses(admin_id: int | None = Query(None, gt=0), campaign_id: str = Query('', max_length=80),
                            q: str = Query('', max_length=80), start_date: str = Query('', max_length=10),
                            end_date: str = Query('', max_length=10), state: Literal['all', 'active', 'void'] = 'all',
                            user: CurrentUser = Depends(require_admin)):
    from app.services.referral_expenses import finance_export
    return Response(finance_export(user.id, admin_id, campaign_id, q, start_date, end_date, state), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename="finance-expenses.xlsx"'})


@router.get('/finance-controls', response_model=PromotionFinanceControlsResponse, response_model_exclude_unset=True)
def controls(user: CurrentUser = Depends(require_admin)):
    with db() as conn:
        settlement_access.identity(conn, user.id)
        return settlement_access.controls(conn)


@router.put('/finance-controls', response_model=PromotionFinanceSaveControlsResponse, response_model_exclude_unset=True)
def save_controls(body: FinanceControls, user: CurrentUser = Depends(require_recent_admin)):
    with db(serialized='accounts') as conn:
        settlements.require_super(conn, user.id)
        if settlement_access.controls(conn)['revision'] != body.revision:
            fail('复核设置已变化，请刷新', 409)
        conn.execute('UPDATE referral_finance_controls SET separate_review=?,separate_payment=?,revision=revision+1 WHERE id=1', (body.separate_review, body.separate_payment))
        settlements.audit(conn, user.id, 'finance_controls', '1', body.model_dump())
        return settlement_access.controls(conn)


@router.get('/monthly', response_model=PromotionFinanceMonthlyResponse, response_model_exclude_unset=True)
def monthly(admin_id: int = Query(gt=0), month: str = Query(pattern=r'^\d{4}-\d{2}$'), user: CurrentUser = Depends(require_admin)):
    return settlement_ledger.monthly(user.id, admin_id, month)


@router.post('/monthly/archive', response_model=PromotionFinanceArchiveResponse, response_model_exclude_unset=True)
def archive(body: MonthlyArchive, user: CurrentUser = Depends(require_recent_admin)):
    return settlement_ledger.archive(user.id, body)


@router.get('/monthly/export.xlsx', response_class=Response, responses=binary_responses('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))
def export_month(admin_id: int = Query(gt=0), month: str = Query(pattern=r'^\d{4}-\d{2}$'), user: CurrentUser = Depends(require_admin)):
    return Response(settlement_ledger.export(user.id, admin_id, month), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename="monthly.xlsx"'})


@router.get('/batches', response_model=PayoutBatchPageResponse, response_model_exclude_unset=True)
def batches(page: int = Query(1, ge=1, le=5000), q: str = Query('', max_length=80), status: Literal['', 'active', 'completed', 'cancelled'] = '', user: CurrentUser = Depends(require_admin)):
    return settlement_batches.listing(user.id, page, q, status)


@router.get('/batches/{identifier}', response_model=PayoutBatchResponse, response_model_exclude_unset=True)
def batch_detail(identifier: str, user: CurrentUser = Depends(require_admin)):
    with db(read_only_snapshot=True) as conn:
        return settlement_batches.detail(conn, user.id, identifier)


@router.post('/batches', response_model=PayoutBatchResponse, response_model_exclude_unset=True)
def create_batch(body: PayoutBatchInput, user: CurrentUser = Depends(require_recent_admin)):
    return settlement_batches.create(user.id, body)


@router.get('/batches/{identifier}/export.csv', response_class=Response, responses=binary_responses('text/csv'))
def export_batch(identifier: str, user: CurrentUser = Depends(require_recent_admin)):
    return Response(settlement_batches.export(user.id, identifier), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="payout.csv"'})


@router.post('/batches/{identifier}/preview', response_model=PayoutPreviewResponse, response_model_exclude_unset=True)
def preview_batch(identifier: str, body: PayoutPreview, user: CurrentUser = Depends(require_admin)):
    return settlement_batches.preview(user.id, identifier, body.content)


@router.post('/batches/{identifier}/import', response_model=PayoutImportResponse, response_model_exclude_unset=True)
def import_batch(identifier: str, body: PayoutImportInput, user: CurrentUser = Depends(require_recent_admin)):
    return settlement_batches.import_receipts(user.id, identifier, body)


@router.post('/batches/{identifier}/cancel', response_model=PayoutBatchResponse, response_model_exclude_unset=True)
def cancel_batch(identifier: str, body: Revision, user: CurrentUser = Depends(require_recent_admin)):
    return settlement_batches.cancel(user.id, identifier, body.revision)


@router.get('/disputes', response_model=PromotionFinanceDisputesResponse, response_model_exclude_unset=True)
def disputes(status: Literal['', 'open', 'processing', 'resolved', 'rejected'] = '', page: int = Query(1, ge=1, le=5000), personal: bool = False, user: CurrentUser = Depends(require_admin)):
    return settlement_disputes.listing(user.id, status, page, personal)


@router.post('/disputes', response_model=PromotionFinanceCreateDisputeResponse, response_model_exclude_unset=True)
def create_dispute(body: DisputeInput, user: CurrentUser = Depends(require_recent_admin)):
    return settlement_disputes.create(user.id, body)


@router.post('/disputes/{identifier}/reply', response_model=PromotionFinanceReplyResponse, response_model_exclude_unset=True)
def reply(identifier: str, body: DisputeReply, user: CurrentUser = Depends(require_recent_admin)):
    return settlement_disputes.reply(user.id, identifier, body)


@router.get('/disputes/{identifier}', response_model=PromotionFinanceDisputeDetailResponse, response_model_exclude_unset=True)
def dispute_detail(identifier: str, personal: bool = False, user: CurrentUser = Depends(require_admin)):
    with db(read_only_snapshot=True) as conn:
        return settlement_disputes.detail(conn, user.id, identifier, personal)


@router.post('/disputes/{identifier}/files', response_model=PromotionFinanceUploadResponse, response_model_exclude_unset=True)
async def upload(identifier: str, request: Request, name: str = Query(max_length=120), user: CurrentUser = Depends(require_recent_admin)):
    from app.blocking import run_sync
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 2 * 1024 * 1024:
            fail('凭证限 2MB', 413)
        chunks.append(chunk)
    return await run_sync(settlement_disputes.upload, user.id, identifier, name, b''.join(chunks))


@router.get('/dispute-files/{identifier}', response_class=Response, responses=binary_responses('application/pdf', 'image/jpeg', 'image/png', 'application/octet-stream'))
def download(identifier: str, user: CurrentUser = Depends(require_admin)):
    row = settlement_disputes.file(user.id, identifier)
    return Response(bytes(row['content']), media_type=row['media_type'], headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(row['name']), 'X-Content-Type-Options': 'nosniff'})
