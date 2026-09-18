"""Prometheus 监控指标

跟踪关键业务和系统指标，便于生产环境监控。
"""

from prometheus_client import Counter, Histogram, Gauge, Info
from prometheus_client import start_http_server as prometheus_start_http_server
import logging

logger = logging.getLogger(__name__)

# API 请求计数器
api_requests_total = Counter(
    'api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status']
)

# API 请求延迟
api_request_duration = Histogram(
    'api_request_duration_seconds',
    'API request duration',
    ['method', 'endpoint'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

# LLM 调用计数器
llm_calls_total = Counter(
    'llm_calls_total',
    'Total LLM API calls',
    ['model', 'status']
)

# LLM 请求延迟
llm_request_duration = Histogram(
    'llm_request_duration_seconds',
    'LLM request duration',
    ['model'],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)
)

# Token 使用量
llm_tokens_total = Counter(
    'llm_tokens_total',
    'Total LLM tokens consumed',
    ['model', 'token_type']  # token_type: prompt, completion
)

# 生成任务计数器
generation_requests_total = Counter(
    'generation_requests_total',
    'Total generation requests',
    ['kind', 'status']  # kind: single, batch, stream, validate; status: success, error
)

# 数据库连接池状态
db_pool_connections = Gauge(
    'db_pool_connections',
    'Database connection pool size',
    ['state']  # state: active, idle
)

# 用户活跃数
active_users = Gauge(
    'active_users',
    'Number of active users'
)

# 系统信息
app_info = Info(
    'app_info',
    'Application information'
)


def init_metrics(app_version: str) -> None:
    """初始化应用信息指标"""
    app_info.info({
        'version': app_version,
        'name': 'learning-coach'
    })


def start_metrics_server(port: int = 9090) -> None:
    """启动 Prometheus metrics 服务器

    Args:
        port: metrics 服务端口，默认 9090
    """
    try:
        prometheus_start_http_server(port)
        logger.info(f"Prometheus metrics server started on port {port}")
    except Exception as e:
        logger.warning(f"Failed to start metrics server: {e}")


def update_db_pool_metrics(active: int, idle: int) -> None:
    """更新数据库连接池指标"""
    db_pool_connections.labels(state='active').set(active)
    db_pool_connections.labels(state='idle').set(idle)


def update_active_users(count: int) -> None:
    """更新活跃用户数"""
    active_users.set(count)
