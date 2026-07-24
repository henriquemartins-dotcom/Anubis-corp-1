from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_horus_visual_assets_exist():
    img = ROOT / "app" / "static" / "img"
    assert (img / "horus-connective-logo-ui.png").exists()
    assert (img / "horus-connective-logo-native.png").exists()
    assert (img / "horus-emblem-ui.png").exists()


def test_sidebar_uses_horus_emblem():
    sidebar = (ROOT / "app" / "templates" / "components" / "sidebar.html").read_text(encoding="utf-8")
    assert "horus-emblem-ui.png" in sidebar
    assert "DESKTOP BETA 0.16" in sidebar


def test_login_uses_smaller_centered_logo_and_translucent_splash():
    template = (ROOT / "app" / "templates" / "login.html").read_text(encoding="utf-8")
    css = (ROOT / "app" / "static" / "css" / "login.css").read_text(encoding="utf-8")
    assert template.count("horus-connective-logo-ui.png") == 2
    assert "login-brand-lockup{justify-content:center" in css
    assert "background:rgba(247,242,233,.73)" in css
    assert "place-items:center" in css


def test_native_splash_uses_full_horus_logo():
    launcher = (ROOT / "desktop" / "launcher.py").read_text(encoding="utf-8")
    assert "horus-connective-logo-native.png" in launcher
    assert 'APP_VERSION = "0.17.2-desktop-beta"' in launcher
