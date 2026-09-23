"""Exercise two independent ASGI workers and a shared Prometheus exporter."""
import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

async def worker():
    import httpx
    from fastapi import FastAPI

    from app.metrics import RequestMetrics
    app = FastAPI()
    app.add_middleware(RequestMetrics)
    @app.get('/papers/{paper_id}')
    def paper(paper_id: str):
        return {'id': paper_id}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        for index in range(100):
            await client.get(f'/papers/{index}')
            await client.get(f'/missing-{index}')

if '--worker' in sys.argv:
    asyncio.run(worker())
else:
    with tempfile.TemporaryDirectory(prefix='lc-metrics-test-') as directory:
        os.environ['PROMETHEUS_MULTIPROC_DIR'] = directory
        from app.metrics_exporter import start_metrics_server
        server, thread = start_metrics_server(0)
        try:
            children = [subprocess.Popen([sys.executable, __file__, '--worker']) for _ in range(2)]
            for child in children:
                assert child.wait(timeout=30) == 0
            text = urlopen(f'http://127.0.0.1:{server.server_port}/metrics').read().decode()
            counts = [line for line in text.splitlines() if line.startswith('api_requests_total{')]
            assert len(counts) == 2, counts
            assert all(line.endswith(' 200.0') for line in counts), counts
            assert any('endpoint="/papers/{paper_id}"' in line for line in counts)
            assert any('endpoint="__static_or_unmatched__"' in line for line in counts)
            print('PASS: 2 processes, 400 requests, 2 bounded label sets, exact aggregate counts')
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=5)
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
