"""Exporter without business metric allocation (safe in the supervisor process)."""
import os

from prometheus_client import REGISTRY, CollectorRegistry, multiprocess, start_http_server


def start_metrics_server(port: int = 9090, host: str = "127.0.0.1"):
    registry = REGISTRY
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    return start_http_server(port, addr=host, registry=registry)
