from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = (ROOT / "desktop" / "HORUS_CONNECTIVE.spec").read_text(encoding="utf-8")
BUILD = (ROOT / "CRIAR_INSTALADOR_OFICIAL_WINDOWS.bat").read_text(encoding="utf-8")
VERSION_INFO = (ROOT / "desktop" / "version_info.txt").read_text(encoding="utf-8")


def test_webview_collection_regression_is_removed():
    assert 'collect_all("webview")' not in SPEC
    assert 'collect_submodules("webview")' not in SPEC
    assert '"webview.platforms.edgechromium"' in SPEC
    assert '"webview.platforms.winforms"' in SPEC


def test_build_is_optimized_and_deterministic():
    assert 'collect_dynamic_libs("pymupdf")' in SPEC
    assert "upx=False" in SPEC
    assert '"webview.platforms.qt"' in SPEC
    assert '"webview.platforms.gtk"' in SPEC


def test_release_version_is_consistent():
    assert 'set "VERSION=0.16.0"' in BUILD
    assert "0.16.0 Desktop Beta" in VERSION_INFO
    assert "filevers=(0, 14, 0, 0)" in VERSION_INFO
