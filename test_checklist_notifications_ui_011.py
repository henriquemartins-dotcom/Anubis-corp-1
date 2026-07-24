from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_checklist_modal_uses_large_operational_layout():
    css = (ROOT / "app/static/css/checklist.css").read_text(encoding="utf-8")
    js = (ROOT / "app/static/js/app.js").read_text(encoding="utf-8")
    assert "width:min(1320px,98vw)" in css
    assert ".checklist-item-grid" in css
    assert "Responsável cadastrado" in js
    assert "responsible_user_id" in js
    assert "/api/team/assignable" in js


def test_notifications_admin_view_and_windows_task_exist():
    index = (ROOT / "app/templates/index.html").read_text(encoding="utf-8")
    sidebar = (ROOT / "app/templates/components/sidebar.html").read_text(encoding="utf-8")
    launcher = (ROOT / "desktop/launcher.py").read_text(encoding="utf-8")
    installer = (ROOT / "desktop/installer/HORUS_CONNECTIVE.iss").read_text(encoding="utf-8")
    assert 'views/notifications.html' in index
    assert "Notificações diárias" in sidebar
    assert '"--notify-once"' in launcher
    assert "AGENDAR_NOTIFICACOES_DIARIAS_WINDOWS.bat" in installer
    assert (ROOT / "AGENDAR_NOTIFICACOES_DIARIAS_WINDOWS.bat").exists()


def test_user_form_contains_bitrix_mapping_and_channel_preferences():
    template = (ROOT / "app/templates/views/users.html").read_text(encoding="utf-8")
    assert "userBitrixId" in template
    assert "userNotifyEmail" in template
    assert "userNotifyBitrix" in template
