"""Bounded, loopback-only UI fixture. All WeChat traffic uses a signed MockTransport.

Run after building admin and mini H5: py -3.12 tests/growth_ui_fixture.py --port 8317
Accounts: admin_console/admin-pass-123, ui_reader/reader-pass-123, ui_vip/vip-pass-123.
No production data, credentials, provider requests, background jobs or Docker volumes.
"""

import argparse
import base64
import hashlib
import io
import json
import threading
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import ui_fixture as base  # Establish disposable environment before importing services.
import httpx
import uvicorn
from PIL import Image
from fastapi.staticfiles import StaticFiles
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from app.config import get_settings
from app.db import db
from app.security import encrypt_secret, decrypt_secret
from app.models.commerce import PlanInput, OrderInput, RefundInput
from app.models.engagement import TagInput, PaperLabels, ContentRequest, EditionInput
from app.models.experience import FeedbackCreate, FeedbackUpdate, TopicInput
from app.models.library import ArchiveCreate
from app.services import mini_auth, mini_orders, mini_refunds, payment_bills, mini_messages, mini_experience, catalog_discovery, catalog_editions, catalog_ops, paper_library
from app.services.wechat_pay import WeChatPay


def configure_provider():
    settings = get_settings()
    merchant = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    platform = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private, public = Path(base.TEMP.name) / 'merchant.pem', Path(base.TEMP.name) / 'platform.pem'
    private.write_bytes(merchant.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    public.write_bytes(platform.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    for key, value in {'wechat_pay_enabled': True, 'wechat_app_id': 'wx0123456789abcdef', 'wechat_pay_mchid': '1900000001', 'wechat_pay_serial_no': 'FIXTURE_MERCHANT', 'wechat_pay_private_key_path': str(private), 'wechat_pay_platform_serial': 'PUB_KEY_ID_FIXTURE', 'wechat_pay_platform_key_path': str(public), 'wechat_pay_api_v3_key': '12345678901234567890123456789012', 'wechat_pay_notify_origin': 'https://fixture.example.test'}.items():
        setattr(settings, key, value)

    def signed(data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode() if data is not None else b''
        stamp, nonce = str(int(time.time())), 'fixture-notice'
        signature = platform.sign(stamp.encode() + b'\n' + nonce.encode() + b'\n' + raw + b'\n', padding.PKCS1v15(), hashes.SHA256())
        return httpx.Response(status, content=raw, headers={'Wechatpay-Timestamp': stamp, 'Wechatpay-Nonce': nonce, 'Wechatpay-Serial': settings.wechat_pay_platform_serial, 'Wechatpay-Signature': base64.b64encode(signature).decode()})

    def refund_result(identifier, success):
        with db() as conn:
            refund = conn.execute('SELECT * FROM mini_refunds WHERE id = ?', (identifier,)).fetchone()
            order = mini_orders.owned(conn, refund['order_id'])
            return {'out_refund_no': identifier, 'refund_id': 'fixture-refund-' + identifier, 'out_trade_no': order['id'], 'transaction_id': order['transaction_id'], 'mchid': settings.wechat_pay_mchid, 'amount': {'total': order['amount_fen'], 'refund': order['amount_fen'], 'currency': 'CNY'}, 'status': 'SUCCESS' if success else 'PROCESSING', 'success_time': datetime.now(timezone.utc).isoformat()}

    bill = '微信订单号,商户订单号,交易状态,订单金额,商户退款单号,申请退款金额,退款状态\n总交易单数\n`0\n'.encode()

    def handle(request):
        assert request.url.host == 'api.mch.weixin.qq.com', 'Only the test provider host is accepted'
        path = request.url.path
        if path == '/v3/pay/transactions/jsapi':
            return signed({'prepay_id': 'fixture-prepay'})
        if path.endswith('/close'):
            return signed(None, 204)
        if path.startswith('/v3/pay/transactions/out-trade-no/'):
            with db() as conn:
                order = dict(mini_orders.owned(conn, path.rsplit('/', 1)[1]))
            value = {'out_trade_no': order['id'], 'appid': order['appid'], 'mchid': order['mchid'], 'payer': {'openid': decrypt_secret(order['payer_enc'])}, 'amount': {'total': order['amount_fen'], 'currency': 'CNY'}, 'transaction_id': order['transaction_id'] or 'fixture-trade-' + order['id'], 'trade_state': 'CLOSED' if order['status'] == 'closed' else 'SUCCESS', 'success_time': datetime.fromtimestamp(order['paid_at'] or time.time(), timezone.utc).isoformat()}
            return signed(value)
        if path == '/v3/refund/domestic/refunds' and request.method == 'POST':
            return signed(refund_result(json.loads(request.content)['out_refund_no'], False))
        if path.startswith('/v3/refund/domestic/refunds/'):
            return signed(refund_result(path.rsplit('/', 1)[1], True))
        if path == '/v3/bill/tradebill':
            return signed({'download_url': 'https://api.mch.weixin.qq.com/v3/bill/downloadurl?token=fixture', 'hash_type': 'SHA1', 'hash_value': hashlib.sha1(bill).hexdigest()})
        if path == '/v3/bill/downloadurl':
            return httpx.Response(200, content=bill)
        return signed({'code': 'RESOURCE_NOT_EXISTS'}, 404)

    class FixturePay(WeChatPay):
        def __init__(self, transport=None):
            super().__init__(httpx.MockTransport(handle))

    for module in (mini_orders, mini_refunds, payment_bills, base.commerce):
        module.WeChatPay = FixturePay


def edition_bundle():
    # A real, tiny PDF so browser download/open paths can also be exercised.
    stream = b'BT /F1 16 Tf 40 780 Td (UI FIXTURE - Answer edition) Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>', b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>', b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream']
    pdf, offsets = bytearray(b'%PDF-1.4\n'), [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(pdf)); pdf.extend(str(index).encode() + b' 0 obj\n' + value + b'\nendobj\n')
    start = len(pdf)
    pdf.extend(b'xref\n0 6\n0000000000 65535 f \n')
    for offset in offsets[1:]: pdf.extend(f'{offset:010d} 00000 n \n'.encode())
    pdf.extend(f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode())
    page = io.BytesIO(); Image.new('RGB', (210, 297), 'white').save(page, 'JPEG')
    result = io.BytesIO()
    with zipfile.ZipFile(result, 'w') as archive:
        archive.writestr('paper.pdf', pdf); archive.writestr('page-1.jpg', page.getvalue())
    return result.getvalue()


def seed_growth():
    configure_provider()
    with db() as conn:
        admin = conn.execute("SELECT id FROM users WHERE username = 'admin_console'").fetchone()[0]
        reader = conn.execute("SELECT id FROM mini_users WHERE username = 'ui_reader'").fetchone()[0]
        vip = conn.execute("SELECT id FROM mini_users WHERE username = 'ui_vip'").fetchone()[0]
        for identifier in (reader, vip):
            openid = 'fixture-openid-' + identifier
            conn.execute('UPDATE mini_users SET wechat_identity = ?, wechat_openid_enc = ? WHERE id = ?', (mini_auth.digest(get_settings().wechat_app_id + ':' + openid), encrypt_secret(openid), identifier))
        paper = conn.execute("SELECT c.*, a.snapshot_json FROM catalog_papers c JOIN paper_archives a ON a.id = c.paper_id WHERE c.status = 'published' AND a.file_status = 'ready' ORDER BY c.title LIMIT 1").fetchone()
    plan = mini_orders.save_plan(PlanInput(name='验收月会员', description='仅隔离验收使用，所有支付请求由本地测试响应完成。', days=30, price_fen=1990, is_active=True))
    for owner in (reader, vip):
        order = mini_orders.create(owner, OrderInput(plan_id=plan['id'], plan_revision=plan['revision'], request_id='fixture-' + owner))
        if owner == vip:
            mini_orders.sync(order['id'])
            mini_refunds.request(order['id'], owner, RefundInput(reason='验收：核对退款处理流程'))
    if paper:
        tags = [catalog_discovery.save(TagInput(kind=kind, name=name)) for kind, name in [('textbook', '人教版'), ('term', '上学期'), ('unit', '第一单元'), ('knowledge', '两位数加法')]]
        labels = catalog_discovery.assign(paper['id'], PaperLabels(revision=paper['revision'], tag_ids=[tag['id'] for tag in tags]))
        snapshot = json.loads(paper['snapshot_json']); snapshot['export_options']['mode'] = 'answersOnly'
        alternate = paper_library.create_paper(admin, ArchiveCreate(request_id='fixture-answers', source_id='fixture-answer-source', snapshot=snapshot))
        paper_library.publish_bundle(admin, alternate['id'], edition_bundle())
        catalog_editions.assign(admin, paper['id'], EditionInput(revision=labels['revision'], kind='answers', paper_id=alternate['id'], confirm_publication=True))
        catalog_ops.save_topic(TopicInput(title='验收专题：每日练习', description='查看教材标签、分享入口和原稿文件。', is_visible=True, paper_ids=[paper['id']]))
        with db() as conn:
            mini_messages.notify(conn, reader, 'fixture-update', 'paper', '你收藏的资料有更新', '可查看资料标签和答案版 PDF。', 'paper', paper['id'])
    from app.services import content_requests
    for owner in (reader, vip):
        content_requests.create(owner, ContentRequest(title='六年级分数应用题', grade='小学六年级', subject='数学', details='希望增加带答案解析的专项训练。'))
    feedback = mini_experience.create_feedback(reader, FeedbackCreate(kind='other', body='验收：希望补充使用说明。'))
    mini_experience.update_feedback(admin, feedback['id'], FeedbackUpdate(revision=1, status='resolved', reply='使用说明已更新，请在服务页查看。', internal_note='仅后台可见'))


@asynccontextmanager
async def lifespan(app):
    async with base.lifespan(app):
        seed_growth()
        yield


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8317)
    parser.add_argument('--seconds', type=int, default=1800)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 3600:
        raise ValueError('Fixture lifetime must be between 1 and 3600 seconds')
    app = base.fixture
    app.router.lifespan_context = lifespan
    app.state.demo_library = base.ROOT / 'artifacts' / 'miniprogram' / 'demo'
    app.router.routes[:] = [route for route in app.router.routes if getattr(route, 'name', '') != 'web']
    app.mount('/', StaticFiles(directory=base.ROOT / 'miniprogram' / 'dist' / 'build' / 'h5', html=True), name='mini')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=args.port, log_level='warning'))
    timer = threading.Timer(args.seconds, lambda: setattr(server, 'should_exit', True)); timer.daemon = True; timer.start()
    print(f'Disposable growth UI: http://127.0.0.1:{args.port} — auto-stop in {args.seconds}s', flush=True)
    try:
        server.run()
    finally:
        timer.cancel(); base.TEMP.cleanup()
