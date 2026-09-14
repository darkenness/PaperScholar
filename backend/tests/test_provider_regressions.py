from types import SimpleNamespace

import pytest

from app.schemas.api_key import ApiKeyCreate, ApiKeyUpdate
from app.services.provider_service import probe_config, update_config_fields


def make_config(**overrides):
    values = {
        "provider": "openai_compat",
        "base_url": "https://old-relay.example/v1",
        "model_name": "old-model",
        "api_key_encrypted": "encrypted",
        "api_options": {},
        "model_type": "chat",
        "priority": 0,
        "is_verified": True,
        "capability_status": {"chat": {"status": "passed"}},
        "last_error": None,
        "last_verified_at": "yesterday",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_changing_provider_requires_explicit_base_url():
    cfg = make_config()

    with pytest.raises(ValueError, match="base_url"):
        update_config_fields(cfg, ApiKeyUpdate(provider="gemini"))

    assert cfg.provider == "openai_compat"
    assert cfg.base_url == "https://old-relay.example/v1"


def test_openai_compat_create_requires_model_name():
    with pytest.raises(ValueError, match="模型 ID"):
        ApiKeyCreate(
            model_type="chat",
            provider="openai_compat",
            api_key="secret",
        )


def test_openai_compat_update_rejects_empty_model_name():
    cfg = make_config()

    with pytest.raises(ValueError, match="模型 ID"):
        update_config_fields(cfg, ApiKeyUpdate(model_name="   "))

    assert cfg.model_name == "old-model"


@pytest.mark.asyncio
async def test_probe_rejects_missing_openai_compat_model_before_client_call():
    cfg = make_config(model_name=None, api_key_encrypted="not-a-real-key")

    with pytest.raises(ValueError, match="模型 ID"):
        await probe_config(cfg)
