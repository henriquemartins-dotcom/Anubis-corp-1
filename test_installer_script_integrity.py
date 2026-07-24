from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_inno_setup_icon_path_is_valid():
    script = (ROOT / "desktop" / "installer" / "HORUS_CONNECTIVE.iss").read_text(encoding="utf-8")
    assert r"SetupIconFile=..\assets\horus.ico" in script


def test_inno_setup_script_has_no_invalid_control_characters():
    data = (ROOT / "desktop" / "installer" / "HORUS_CONNECTIVE.iss").read_bytes()
    invalid = [value for value in data if value < 32 and value not in (9, 10, 13)]
    assert invalid == []
