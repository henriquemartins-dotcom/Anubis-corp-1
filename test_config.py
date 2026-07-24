import pytest

from app.config import Settings
from app.main import validate_runtime_settings


def test_render_database_url_uses_psycopg_driver():
    settings = Settings(database_url="postgresql://user:pass@host:5432/alfred")
    assert settings.database_url == "postgresql+psycopg://user:pass@host:5432/alfred"


def test_production_rejects_default_credentials():
    settings = Settings(environment="production", auth_cookie_secure=True)
    with pytest.raises(RuntimeError):
        validate_runtime_settings(settings)


def test_production_accepts_secure_runtime_settings():
    settings = Settings(
        environment="production",
        secret_key="a-secure-random-secret-value",
        admin_password="a-unique-password-with-12-chars",
        auth_cookie_secure=True,
    )
    validate_runtime_settings(settings)
