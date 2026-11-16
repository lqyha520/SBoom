"""推广结算：推广人申请本人奖励，授权财务分别核对、审核和登记付款。"""

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response

from app.deps import require_admin, require_recent_admin
from app.http_contracts import binary_responses
from app.library_deps import no_store
from app.models.responses import SettlementListResponse, SettlementSummaryResponse
from app.models.settlements import (
    AdjustmentInput,
    BatchCostsInput,
    BillImportInput,
    CostsInput,
    PayeeInput,
    PolicyInput,
    ReceiptInput,
    RecoveryInput,
    ReviewInput,
    Revision,
    SettlementApplyInput,
    SettlementFilters,
    SettlementPreviewInput,
    StatementInput,
    VoidInput,
)
from app.models.settlements_api_responses import (
    SettlementsAdjustmentResponse,
    SettlementsAdminsResponse,
    SettlementsApplyRequestResponse,
    SettlementsApproveResponse,
    SettlementsAttachPayeeResponse,
    SettlementsBatchCostsResponse,
    SettlementsBillDetailResponse,
    SettlementsBillsResponse,
    SettlementsCancelRequestResponse,
    SettlementsCostsResponse,
    SettlementsCreateResponse,
    SettlementsImportBillResponse,
    SettlementsNoticesResponse,
    SettlementsPaidResponse,
    SettlementsPayeeResponse,
    SettlementsPolicyResponse,
    SettlementsPreviewRecoveryResponse,
    SettlementsPreviewRequestResponse,
    SettlementsReadNoticesResponse,
    SettlementsRecoverResponse,
    SettlementsRejectRequestResponse,
    SettlementsRequestDetailResponse,
    SettlementsRevealPayeeResponse,
    SettlementsRulesResponse,
    SettlementsSavePayeeResponse,
    SettlementsSavePolicyResponse,
    SettlementsStartRequestResponse,
    SettlementsStatementDetailResponse,
    SettlementsUploadAttachmentResponse,
    SettlementsVoidResponse,
)
from app.routers.promotion_finance import router as finance_router
from app.services import settlement_bills, settlement_operations, settlement_queries, settlements
from app.services.mini_errors import fail
from app.services.user_store import CurrentUser

router = APIRouter(prefix='/api/v1/admin/settlements', tags=['推广结算'], dependencies=[Depends(no_store)])


@router.get('/rules', response_model=SettlementsRulesResponse, response_model_exclude_unset=True)
def rules(user: CurrentUser = Depends(require_admin)):
    return settlements.public_rules(user.id)


@router.get('/policy', response_model=SettlementsPolicyResponse, response_model_exclude_unset=True)
def policy(user: CurrentUser = Depends(require_admin)):
    return settlements.get_policy(user.id)


@router.put('/policy', response_model=SettlementsSavePolicyResponse, response_model_exclude_unset=True)
def save_policy(body: PolicyInput, user: CurrentUser = Depends(require_recent_admin)):
    return settlements.save_policy(user.id, body)


@router.get('/export', response_class=Response, responses=binary_responses('text/csv'))
def export(user: CurrentUser = Depends(require_admin)):
    return Response(settlements.export_statements(user.id), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="settlements.csv"'})


@router.get('/export.xlsx', response_class=Response, responses=binary_responses('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))
def export_excel(kind: Literal['rewards', 'statements', 'adjustments', 'requests'] = 'statements', filters: SettlementFilters = Depends(), user: CurrentUser = Depends(require_admin)):
    from app.services.settlement_export import export
    return Response(export(user.id, kind, filters), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename="settlements.xlsx"'})


@router.get('/list/{kind}', response_model=SettlementListResponse, response_model_exclude_unset=True)
def listing(kind: Literal['rewards', 'statements', 'adjustments', 'requests'], filters: SettlementFilters = Depends(), offset: int = Query(0, ge=0, le=100000), limit: int = Query(20, ge=1, le=50), user: CurrentUser = Depends(require_admin)):
    return settlements.listing(user.id, kind, offset, limit, filters)


@router.get('/summary', response_model=SettlementSummaryResponse, response_model_exclude_unset=True)
def summary(filters: SettlementFilters = Depends(), user: CurrentUser = Depends(require_admin)):
    return settlement_queries.summary(user.id, filters)


@router.get('/admins', response_model=SettlementsAdminsResponse, response_model_exclude_unset=True)
def admins(user: CurrentUser = Depends(require_admin)):
    from app.db import db
    from app.services.settlement_access import owner_id
    with db() as conn:
        owner = owner_id(conn, user.id)
        rows = conn.execute("SELECT id,username FROM users WHERE role='admin'" + (' AND id=?' if owner is not None else '') + ' ORDER BY username,id', [owner] if owner is not None else []).fetchall()
        return {'items': [dict(row) for row in rows]}


@router.get('/payee', response_model=SettlementsPayeeResponse, response_model_exclude_unset=True)
def payee(user: CurrentUser = Depends(require_admin)):
    return settlement_operations.payee(user.id)


@router.put('/payee', response_model=SettlementsSavePayeeResponse, response_model_exclude_unset=True)
def save_payee(body: PayeeInput, user: CurrentUser = Depends(require_recent_admin)):
    return settlement_operations.save_payee(user.id, body)


@router.get('/statements/{identifier}', response_model=SettlementsStatementDetailResponse, response_model_exclude_unset=True)
def statement_detail(identifier: str, user: CurrentUser = Depends(require_admin)):
    return settlement_operations.statement_detail(user.id, identifier)


@router.post('/statements/{identifier}/payee/reveal', response_model=SettlementsRevealPayeeResponse, response_model_exclude_unset=True)
def reveal_payee(identifier: str, user: CurrentUser = Depends(require_recent_admin)):
    return settlement_operations.reveal_payee(user.id, identifier)


@router.post('/statements/{identifier}/payee', response_model=SettlementsAttachPayeeResponse, response_model_exclude_unset=True)
def attach_payee(identifier: str, body: Revision, user: CurrentUser = Depends(require_recent_admin)):
    return settlement_operations.attach_payee(user.id, identifier, body.revision)


@router.post('/statements/{identifier}/attachments', response_model=SettlementsUploadAttachmentResponse, response_model_exclude_unset=True)
async def upload_attachment(identifier: str, request: Request, name: str = Query(max_length=120), user: CurrentUser = Depends(require_recent_admin)):
    from app.blocking import run_sync
    await run_sync(settlement_operations.attachment_access, user.id, identifier, write=True)
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 2 * 1024 * 1024:
            fail('凭证限 2MB', 413)
        chunks.append(chunk)
    return await run_sync(settlement_operations.upload_attachment, user.id, identifier, name, b''.join(chunks))


@router.get('/attachments/{identifier}', response_class=Response, responses=binary_responses('application/pdf', 'image/jpeg', 'image/png', 'application/octet-stream'))
def attachment(identifier: str, user: CurrentUser = Depends(require_admin)):
    row = settlement_operations.attachment(user.id, identifier)
    return Response(bytes(row['content']), media_type=row['media_type'], headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(row['name']), 'X-Content-Type-Options': 'nosniff'})


@router.get('/requests/{identifier}/recover', response_model=SettlementsPreviewRecoveryResponse, response_model_exclude_unset=True)
def preview_recovery(identifier: str, user: CurrentUser = Depends(require_admin)):
    return settlement_operations.recovery_preview(user.id, identifier)


@router.post('/requests/{identifier}/recover', response_model=SettlementsRecoverResponse, response_model_exclude_unset=True)
def recover(identifier: str, body: RecoveryInput, user: CurrentUser = Depends(require_recent_admin)):
    return settlement_operations.recover(user.id, identifier, body)


@router.get('/notices', response_model=SettlementsNoticesResponse, response_model_exclude_unset=True)
def notices(personal: bool = False, user: CurrentUser = Depends(require_admin)):
    return settlement_operations.notices(user.id, personal)


@router.post('/notices/read', response_model=SettlementsReadNoticesResponse, response_model_exclude_unset=True)
def read_notices(through: int = Query(ge=0), personal: bool = False, user: CurrentUser = Depends(require_admin)):
    return settlement_operations.read_notices(user.id, through, personal)


@router.get('/bills/template', response_class=Response, responses=binary_responses('text/csv'))
def bill_template(user: CurrentUser = Depends(require_admin)):
    settlement_bills.listing(user.id)
    return Response(settlement_bills.template(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="channel-bill.csv"'})


@router.get('/bills', response_model=SettlementsBillsResponse, response_model_exclude_unset=True)
def bills(user: CurrentUser = Depends(require_admin)):
    return settlement_bills.listing(user.id)


@router.post('/bills', response_model=SettlementsImportBillResponse, response_model_exclude_unset=True)
def import_bill(body: BillImportInput, user: CurrentUser = Depends(require_recent_admin)):
    return settlement_bills.import_bill(user.id, body)


@router.get('/bills/{identifier}', response_model=SettlementsBillDetailResponse, response_model_exclude_unset=True)
def bill_detail(identifier: str, user: CurrentUser = Depends(require_admin)):
    return settlement_bills.listing(user.id, identifier)


@router.put('/rewards/{identifier}/costs', response_model=SettlementsCostsResponse, response_model_exclude_unset=True)
def costs(identifier: str, body: CostsInput, user: CurrentUser = Depends(require_recent_admin)):
    return settlements.confirm_costs(user.id, identifier, body)


@router.post('/statements', response_model=SettlementsCreateResponse, response_model_exclude_unset=True)
def create(body: StatementInput, user: CurrentUser = Depends(require_recent_admin)):
    return settlements.create_statement(user.id, body)


@router.post('/statements/{identifier}/approve', response_model=SettlementsApproveResponse, response_model_exclude_unset=True)
def approve(identifier: str, body: ReviewInput, user: CurrentUser = Depends(require_recent_admin)):
    return settlements.approve(user.id, identifier, body)


@router.post('/statements/{identifier}/paid', response_model=SettlementsPaidResponse, response_model_exclude_unset=True)
def paid(identifier: str, body: ReceiptInput, user: CurrentUser = Depends(require_recent_admin)):
    return settlements.record_payout(user.id, identifier, body)


@router.post('/statements/{identifier}/void', response_model=SettlementsVoidResponse, response_model_exclude_unset=True)
def void(identifier: str, body: VoidInput, user: CurrentUser = Depends(require_recent_admin)):
    return settlements.cancel_statement(user.id, identifier, body)


@router.post('/adjustments', response_model=SettlementsAdjustmentResponse, response_model_exclude_unset=True)
def adjustment(body: AdjustmentInput, user: CurrentUser = Depends(require_recent_admin)):
    return settlements.manual_adjustment(user.id, body)


@router.post('/requests/preview', response_model=SettlementsPreviewRequestResponse, response_model_exclude_unset=True)
def preview_request(body: SettlementPreviewInput, user: CurrentUser = Depends(require_admin)):
    return settlements.preview_request(user.id, body)


@router.post('/requests', response_model=SettlementsApplyRequestResponse, response_model_exclude_unset=True)
def apply_request(body: SettlementApplyInput, user: CurrentUser = Depends(require_recent_admin)):
    return settlements.apply_request(user.id, body)


@router.get('/requests/{identifier}', response_model=SettlementsRequestDetailResponse, response_model_exclude_unset=True)
def request_detail(identifier: str, user: CurrentUser = Depends(require_admin)):
    return settlements.request_detail(user.id, identifier)


@router.post('/requests/{identifier}/start', response_model=SettlementsStartRequestResponse, response_model_exclude_unset=True)
def start_request(identifier: str, body: Revision, user: CurrentUser = Depends(require_recent_admin)):
    return settlements.start_request(user.id, identifier, body)


@router.put('/requests/{identifier}/costs', response_model=SettlementsBatchCostsResponse, response_model_exclude_unset=True)
def batch_costs(identifier: str, body: BatchCostsInput, user: CurrentUser = Depends(require_recent_admin)):
    return settlements.confirm_request_costs(user.id, identifier, body)


@router.post('/requests/{identifier}/reject', response_model=SettlementsRejectRequestResponse, response_model_exclude_unset=True)
def reject_request(identifier: str, body: VoidInput, user: CurrentUser = Depends(require_recent_admin)):
    return settlements.close_request(user.id, identifier, body)


@router.post('/requests/{identifier}/cancel', response_model=SettlementsCancelRequestResponse, response_model_exclude_unset=True)
def cancel_request(identifier: str, body: VoidInput, user: CurrentUser = Depends(require_recent_admin)):
    return settlements.close_request(user.id, identifier, body, cancel=True)


router.include_router(finance_router)
