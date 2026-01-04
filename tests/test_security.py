import os

import pytest
from fastapi import HTTPException

from fire_uav.api.security import require_api_key


class _Req:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}


@pytest.mark.asyncio
async def test_require_api_key_passes_when_not_configured(monkeypatch):
    monkeypatch.delenv("FIRE_UAV_API_TOKEN", raising=False)
    await require_api_key(_Req())  # should not raise


@pytest.mark.asyncio
async def test_require_api_key_rejects_invalid_token(monkeypatch):
    monkeypatch.setenv("FIRE_UAV_API_TOKEN", "secret")
    with pytest.raises(HTTPException):
        await require_api_key(_Req({"x-api-key": "bad"}))


@pytest.mark.asyncio
async def test_require_api_key_accepts_valid_token(monkeypatch):
    monkeypatch.setenv("FIRE_UAV_API_TOKEN", "secret")
    await require_api_key(_Req({"authorization": "Bearer secret"}))
