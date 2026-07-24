from pathlib import Path

from app.config import Settings
from desktop import launcher

ROOT = Path(__file__).resolve().parents[1]


def test_horus_brand_identity():
    settings = Settings(database_url="sqlite+pysqlite:///:memory:")
    assert settings.app_name == "Hórus Connective Licitações"
    assert launcher.APP_NAME == "Hórus Connective Licitações"


def test_horus_assets_are_packaged():
    assert (ROOT / "app" / "static" / "img" / "horus-connective-logo.png").exists()
    assert (ROOT / "app" / "static" / "img" / "horus-accent.jpg").exists()
    assert (ROOT / "desktop" / "assets" / "horus.ico").exists()


def test_horus_theme_and_interaction_fix_are_loaded_in_order():
    css = (ROOT / "app" / "static" / "css" / "main.css").read_text(encoding="utf-8")
    horus_import = "@import url('/static/css/horus-theme.css?v=0.16.0-desktop-beta');"
    interaction_import = "@import url('/static/css/interaction-fix.css?v=0.16.0-desktop-beta');"
    assert horus_import in css
    assert css.index(horus_import) < css.index(interaction_import)
    assert css.strip().endswith(interaction_import)


def test_horus_installer_and_spec_exist():
    assert (ROOT / "desktop" / "HORUS_CONNECTIVE.spec").exists()
    assert (ROOT / "desktop" / "installer" / "HORUS_CONNECTIVE.iss").exists()
