"""跨服务共享的租约和 advisory lock 编号；变更须兼容滚动发布。"""

UPLOAD_LEASE = 180
LOCK_IDS = {"content": 70634191, "accounts": 70634192, "generation": 70634193, "schema": 70634194}
MAINTENANCE_LOCK = 70634195
EXPIRY_SWEEP_LOCK = 70634196
