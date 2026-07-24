from pathlib import Path

from app.auth import hash_password, verify_password
from app.models import User
from app.services.users import ALL_MODULE_PERMISSIONS, first_allowed_view, has_permission, normalize_email, normalize_permissions, normalize_username


def test_passwords_are_hashed_and_verified():
    encoded = hash_password("senha-segura-123")
    assert "senha-segura-123" not in encoded
    assert verify_password("senha-segura-123", encoded)
    assert not verify_password("senha-errada", encoded)


def test_user_normalization_and_permissions():
    assert normalize_username("  Carlos.Henrique ") == "carlos.henrique"
    assert normalize_email(" USUARIO@EXEMPLO.COM ") == "usuario@exemplo.com"
    assert normalize_permissions(["dashboard", "pipeline", "inexistente"]) == ["dashboard", "pipeline"]


def test_admin_has_all_permissions_and_regular_user_is_restricted():
    admin = User(username="admin", email="admin@local.horus", full_name="Admin", department="Administração", password_hash="x", is_admin=True, is_active=True, permissions=[])
    regular = User(username="user", email="user@local.horus", full_name="User", department="Licitações", password_hash="x", is_admin=False, is_active=True, permissions=["pipeline"])
    assert all(has_permission(admin, permission) for permission in ALL_MODULE_PERMISSIONS)
    assert has_permission(regular, "pipeline")
    assert not has_permission(regular, "relatorios")
    assert first_allowed_view(regular) == "pipeline"


def test_user_management_assets_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "app" / "templates" / "views" / "users.html").exists()
    assert (root / "app" / "static" / "css" / "users.css").exists()
    sidebar = (root / "app" / "templates" / "components" / "sidebar.html").read_text(encoding="utf-8")
    assert "Usuários e permissões" in sidebar
    assert "current_user.is_admin" in sidebar


def test_local_database_name_and_migration_are_configured():
    root = Path(__file__).resolve().parents[1]
    launcher = (root / "desktop" / "launcher.py").read_text(encoding="utf-8")
    assert 'root / "horus_connective.db"' in launcher
    assert 'legacy_database = root / "alfred.db"' in launcher
