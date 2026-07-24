from pathlib import Path

from desktop.launcher import backup_data, configure_windowed_runtime, default_config, protect_secret, unprotect_secret
from app.services.rag import _cosine_distance


def test_desktop_config_has_local_ai_and_protected_key_field():
    config = default_config()
    assert config["ai_mode"] == "local"
    assert "openai_api_key_protected" in config
    assert "openai_api_key" not in config
    assert config["admin_username"] == "henrique"
    assert unprotect_secret(config["admin_password_protected"]) == "horus123"


def test_secret_round_trip_on_current_platform():
    protected = protect_secret("sk-test-local")
    assert protected != "sk-test-local"
    assert unprotect_secret(protected) == "sk-test-local"


def test_cosine_distance_for_equal_vectors_is_zero():
    assert _cosine_distance([1.0, 0.0], [1.0, 0.0]) == 0.0


def test_backup_does_not_include_desktop_settings(tmp_path: Path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    (root / "horus_connective.db").write_bytes(b"sqlite")
    (root / "desktop_settings.json").write_text('{"openai_api_key_protected":"secret"}')
    documents = root / "documents"
    documents.mkdir()
    (documents / "edital.txt").write_text("conteudo")

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    backup = backup_data(root)

    import zipfile

    with zipfile.ZipFile(backup) as archive:
        names = set(archive.namelist())
    assert "horus_connective.db" in names
    assert "documents/edital.txt" in names
    assert "desktop_settings.json" not in names


def test_windowed_runtime_recovers_missing_standard_streams(tmp_path: Path, monkeypatch):
    import sys

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    configure_windowed_runtime(tmp_path)

    assert sys.stdout is not None
    assert sys.stderr is not None
    assert (tmp_path / "logs" / "horus-connective-desktop.log").exists()


def test_uvicorn_config_does_not_use_default_windowed_formatter(tmp_path: Path, monkeypatch):
    import sys
    import uvicorn

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    configure_windowed_runtime(tmp_path)

    config = uvicorn.Config(
        lambda scope, receive, send: None,
        host="127.0.0.1",
        port=8765,
        log_level="warning",
        access_log=False,
        log_config=None,
        use_colors=False,
    )
    assert config.log_config is None
