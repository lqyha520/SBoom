"""Review regressions: no business database, paid requests or live notifications."""

import asyncio
import base64
from contextlib import asynccontextmanager
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.config import get_settings
from app.provider_policy import pin_provider_request
from app.routers import auth
from app.services import image_generation, resource_admission


def test_registration_capabilities_are_public_minimal_and_not_cached():
    app = FastAPI()
    app.include_router(auth.router)
    with TestClient(app) as client:
        for enabled in (False, True):
            with patch.object(auth.settings, "registration_enabled", enabled):
                result = client.get("/api/v1/auth/capabilities")
            assert result.status_code == 200
            assert result.json() == {"registration_enabled": enabled}
            assert result.headers["cache-control"] == "no-store"


def test_runtime_provider_policy_pins_public_ip_and_rechecks_dns():
    async def check():
        sent = []
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: sent.append(request) or httpx.Response(200)),
            event_hooks={"request": [pin_provider_request]}, follow_redirects=False) as client:
            with patch.object(get_settings(), "provider_allow_private", False):
                with patch("app.provider_policy.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("8.8.8.8", 8443))]):
                    await client.post("https://provider.example:8443/v1/chat/completions", headers={"Authorization": "Bearer fixture"})
                assert str(sent[0].url) == "https://8.8.8.8:8443/v1/chat/completions"
                assert sent[0].headers["host"] == "provider.example:8443"
                assert sent[0].extensions["sni_hostname"] == "provider.example"
                for addresses in ([], [(2, 1, 6, "", ("127.0.0.1", 443))],
                                  [(2, 1, 6, "", ("8.8.8.8", 443)), (10, 1, 6, "", ("::1", 443))]):
                    with patch("app.provider_policy.socket.getaddrinfo", return_value=addresses), pytest.raises(HTTPException):
                        await client.post("https://provider.example/v1/chat/completions")
                assert len(sent) == 1
            with patch.object(get_settings(), "provider_allow_private", True):
                await client.post("http://127.0.0.1:8888/v1/chat/completions")
                assert sent[-1].url.host == "127.0.0.1"
    asyncio.run(check())


def test_slow_image_providers_do_not_exhaust_local_media_capacity():
    async def check():
        entered, release = asyncio.Event(), asyncio.Event()
        count = 0
        async def provider(request):
            nonlocal count
            count += 1
            if count == 2:
                entered.set()
            await release.wait()
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(b"fixture").decode()}]})
        @asynccontextmanager
        async def borrow(*args, **kwargs):
            async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
                yield client
        config = {"model": "fixture", "size": "1024x1024", "responseFormat": "auto", "timeout": 5,
                  "baseUrl": "https://fixture.invalid/v1", "api_key": "fixture"}
        with patch.object(image_generation, "borrow_client", borrow), \
                patch.object(image_generation, "normalize_image", return_value={"width": 1}), \
                patch("app.services.generation_budget.reserve"):
            tasks = [asyncio.create_task(image_generation.generate_image(config, "fixture")) for _ in range(2)]
            try:
                await asyncio.wait_for(entered.wait(), 2)
                with resource_admission.admitted_media():
                    pass
                with pytest.raises(HTTPException) as error:
                    await image_generation.generate_image(config, "third")
                assert error.value.status_code == 429
                assert count == 2
            finally:
                release.set()
                await asyncio.gather(*tasks)
        with resource_admission.admitted_image_request():
            pass
    asyncio.run(check())
