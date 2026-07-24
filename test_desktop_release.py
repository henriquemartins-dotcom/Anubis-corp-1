from pathlib import Path

from desktop import launcher


def test_desktop_release_version():
    assert launcher.APP_VERSION == "0.17.2-desktop-beta"


def test_official_installer_assets_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "desktop" / "version_info.txt").exists()
    assert (root / "desktop" / "installer" / "HORUS_CONNECTIVE.iss").exists()
    assert (root / "CRIAR_INSTALADOR_OFICIAL_WINDOWS.bat").exists()
    assert (root / "AGENDAR_MONITORAMENTO_DIARIO_WINDOWS.bat").exists()
    assert (root / "REMOVER_MONITORAMENTO_DIARIO_WINDOWS.bat").exists()


def test_self_test_entrypoint_is_available():
    assert callable(launcher.run_self_test)


def test_monitor_once_entrypoint_is_available():
    assert callable(launcher.run_monitor_once)


def test_desktop_spec_packages_pdf_and_timezone_resources():
    root = Path(__file__).resolve().parents[1]
    spec = (root / "desktop" / "HORUS_CONNECTIVE.spec").read_text(encoding="utf-8")
    assert 'collect_data_files("reportlab"' in spec
    assert 'collect_data_files("tzdata"' in spec


def test_report_center_assets_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "app" / "templates" / "views" / "reports.html").exists()
    assert (root / "app" / "static" / "css" / "reports.css").exists()


def test_desktop_launcher_has_splash_screen():
    assert hasattr(launcher, "StartupSplash")


def test_login_splash_uses_external_script_allowed_by_csp():
    root = Path(__file__).resolve().parents[1]
    template = (root / "app" / "templates" / "login.html").read_text(encoding="utf-8")
    script = root / "app" / "static" / "js" / "login-splash.js"
    assert script.exists()
    assert 'src="/static/js/login-splash.js' in template
    assert "<script>" not in template
    assert 'href="/login?skip_splash=1"' in template


def test_login_splash_has_css_safety_exit():
    root = Path(__file__).resolve().parents[1]
    css = (root / "app" / "static" / "css" / "login.css").read_text(encoding="utf-8")
    assert "horusSplashSafetyExit" in css
