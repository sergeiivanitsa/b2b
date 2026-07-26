import pytest
from pydantic import ValidationError

from product_api.settings import Settings


def _values(**override):
    values = {"DATABASE_URL": "postgresql+asyncpg://x", "GATEWAY_URL": "http://gateway", "GATEWAY_SHARED_SECRET": "x", "AUTH_TOKEN_SECRET": "x", "CLAIM_EDIT_TOKEN_SECRET": "x", "CLAIMS_UPLOAD_DIR": "x", "INVITE_TOKEN_SECRET": "x", "SESSION_SECRET": "x", "EMAIL_FROM": "x@example.com"}
    values.update(override)
    return values


def test_seo_defaults_are_fail_closed():
    settings = Settings(**_values())
    assert settings.seo_public_rollout_enabled is False
    assert settings.seo_publish_batch_max_limit >= 1


@pytest.mark.parametrize("key,value", [("SEO_SITEMAP_CHUNK_SIZE", 0), ("SEO_PUBLISH_BATCH_MAX_LIMIT", 0)])
def test_seo_limits_are_validated(key, value):
    with pytest.raises(ValidationError):
        Settings(**_values(**{key: value}))
