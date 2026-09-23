"""Authenticated order operations and signature-verified payment notifications."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.deps import require_admin
from app.library_deps import no_store, require_mini_user
from app.models.commerce import BillInput, OrderInput, PlanInput, RefundInput, RefundReview
from app.models.membership_cards import CardCreate, CardRedeem
from app.services import membership_cards, mini_orders, mini_refunds, payment_bills
from app.services.mini_auth import MiniUser
from app.services.user_store import CurrentUser
from app.services.wechat_pay import PaymentError, WeChatPay

router = APIRouter(prefix="/api/v1", tags=["会员订单与支付"], dependencies=[Depends(no_store)])
OrderStatus = Literal["", "created", "pending", "paid", "closed", "refunded", "refund_requested", "refund_processing", "refund_abnormal", "refund_closed"]


def payment_call(function, *args):
    try:
        return function(*args)
    except PaymentError as error:
        raise HTTPException(503, detail={"error": str(error), "code": "payment_unavailable"}) from error


@router.get("/mini/membership/plans")
def plans(user: MiniUser = Depends(require_mini_user)):
    return mini_orders.plans()

@router.post('/mini/membership/redeem')
def redeem_card(body: CardRedeem, user: MiniUser = Depends(require_mini_user)):
    return membership_cards.redeem(user.id, body.code)

@router.get('/admin/commerce/cards')
def admin_cards(status: str = '', limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), user: CurrentUser = Depends(require_admin)):
    return membership_cards.listing(status, limit, offset)

@router.post('/admin/commerce/cards', status_code=201)
def create_cards(body: CardCreate, user: CurrentUser = Depends(require_admin)):
    return membership_cards.create(user.id, body.days, body.quantity, body.expires_at)

@router.post('/admin/commerce/cards/{identifier}/disable')
def disable_card(identifier: str, user: CurrentUser = Depends(require_admin)):
    return membership_cards.disable(identifier)


@router.get("/mini/orders")
def orders(limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000), user: MiniUser = Depends(require_mini_user)):
    return mini_orders.listing(user.id, limit=limit, offset=offset)


@router.post("/mini/orders", status_code=201)
def create_order(body: OrderInput, user: MiniUser = Depends(require_mini_user)):
    return mini_orders.create(user.id, body)


@router.get("/mini/orders/{identifier}")
def order(identifier: str, user: MiniUser = Depends(require_mini_user)):
    return mini_orders.detail(identifier, user.id)


@router.post("/mini/orders/{identifier}/pay")
def pay(identifier: str, user: MiniUser = Depends(require_mini_user)):
    return payment_call(mini_orders.pay, identifier, user.id)


@router.post("/mini/orders/{identifier}/sync")
def sync_order(identifier: str, user: MiniUser = Depends(require_mini_user)):
    return payment_call(mini_orders.sync, identifier, user.id)


@router.post("/mini/orders/{identifier}/cancel")
def cancel_order(identifier: str, user: MiniUser = Depends(require_mini_user)):
    return payment_call(mini_orders.cancel, identifier, user.id)


@router.post("/mini/orders/{identifier}/refund")
def request_refund(identifier: str, body: RefundInput, user: MiniUser = Depends(require_mini_user)):
    return mini_refunds.request(identifier, user.id, body)


@router.post("/mini/refunds/{identifier}/sync")
def sync_refund(identifier: str, user: MiniUser = Depends(require_mini_user)):
    return payment_call(mini_refunds.sync, identifier, user.id)


@router.get("/admin/commerce/plans")
def admin_plans(user: CurrentUser = Depends(require_admin)):
    return mini_orders.plans(True)


@router.post("/admin/commerce/plans", status_code=201)
def create_plan(body: PlanInput, user: CurrentUser = Depends(require_admin)):
    return mini_orders.save_plan(body)


@router.put("/admin/commerce/plans/{identifier}")
def update_plan(identifier: str, body: PlanInput, user: CurrentUser = Depends(require_admin)):
    return mini_orders.save_plan(body, identifier)


@router.get("/admin/commerce/orders")
def admin_orders(status: OrderStatus = "", q: str = Query("", max_length=120), start_date: str = Query("", max_length=10), end_date: str = Query("", max_length=10), limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000), user: CurrentUser = Depends(require_admin)):
    return mini_orders.listing(status=status, q=q, limit=limit, offset=offset, start_date=start_date, end_date=end_date)


@router.get("/admin/commerce/orders/export")
def export_orders(status: OrderStatus = "", q: str = Query("", max_length=120), start_date: str = Query("", max_length=10), end_date: str = Query("", max_length=10), user: CurrentUser = Depends(require_admin)):
    return Response(payment_bills.export_orders(status, q, start_date, end_date), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="membership-orders.csv"'})


@router.post("/admin/commerce/orders/{identifier}/sync")
def admin_sync(identifier: str, user: CurrentUser = Depends(require_admin)):
    return payment_call(mini_orders.sync, identifier)


@router.get("/admin/commerce/orders/{identifier}")
def admin_order(identifier: str, user: CurrentUser = Depends(require_admin)):
    return mini_orders.detail(identifier)


@router.post("/admin/commerce/orders/{identifier}/cancel")
def admin_cancel(identifier: str, user: CurrentUser = Depends(require_admin)):
    return payment_call(mini_orders.cancel, identifier)


@router.put("/admin/commerce/refunds/{identifier}")
def review_refund(identifier: str, body: RefundReview, user: CurrentUser = Depends(require_admin)):
    return payment_call(mini_refunds.review, user.id, identifier, body)


@router.post("/admin/commerce/refunds/{identifier}/sync")
def admin_sync_refund(identifier: str, user: CurrentUser = Depends(require_admin)):
    return payment_call(mini_refunds.sync, identifier)


@router.get("/admin/commerce/reconciliations")
def bills(limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=100000), user: CurrentUser = Depends(require_admin)):
    return payment_bills.listing(limit, offset)


@router.get("/admin/commerce/reconciliations/{identifier}")
def bill(identifier: str, user: CurrentUser = Depends(require_admin)):
    return payment_bills.get(identifier)


@router.post("/admin/commerce/reconciliations")
def reconcile(body: BillInput, user: CurrentUser = Depends(require_admin)):
    return payment_call(payment_bills.reconcile, user.id, body.bill_date)


def _verify_callback(headers, raw: bytes):
    """RSA 验签 + AES-GCM 解密 + 读取密钥文件都是同步 CPU/IO，放线程池执行，别占事件循环。"""
    return WeChatPay().callback(headers, raw)


async def receive(request, refund=False):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 1048576:
            raise HTTPException(413, detail={"error": "通知过大"})
    try:
        identifier, kind, value = await asyncio.to_thread(_verify_callback, request.headers, bytes(raw))
    except PaymentError as error:
        raise HTTPException(400 if error.code in ("INVALID_CALLBACK", "INVALID_SIGNATURE") else 503, detail={"error": "无法验证支付通知"}) from error
    if refund:
        if kind not in ("REFUND.SUCCESS", "REFUND.ABNORMAL", "REFUND.CLOSED") or value.get("refund_status") != kind.split(".")[-1]:
            raise HTTPException(400, detail={"error": "通知类型不匹配"})
        await asyncio.to_thread(mini_refunds.apply, value, identifier)
    else:
        if kind != "TRANSACTION.SUCCESS":
            raise HTTPException(400, detail={"error": "通知类型不匹配"})
        await asyncio.to_thread(mini_orders.confirm_payment, value, identifier)
    return Response(status_code=204)


@router.post("/payments/wechat/notify")
async def paid_notification(request: Request):
    return await receive(request)


@router.post("/payments/wechat/refund-notify")
async def refund_notification(request: Request):
    return await receive(request, True)
