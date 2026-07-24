from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import BidPipeline, ChecklistItem, Edital, NotificationConfig, User
from app.services.local_secrets import protect_local_secret, unprotect_local_secret
from app.services.notifications import _bitrix_method_url, _pending_by_user, notification_config_payload, send_test_notification


def make_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return Session(engine, expire_on_commit=False)


def test_local_secret_roundtrip():
    protected = protect_local_secret("segredo-local")
    assert protected != "segredo-local"
    assert unprotect_local_secret(protected) == "segredo-local"


def test_bitrix_webhook_method_is_normalized():
    assert _bitrix_method_url("https://empresa.bitrix24.com.br/rest/1/token/").endswith("/im.message.add.json")
    assert _bitrix_method_url("https://empresa.bitrix24.com.br/rest/1/token/im.message.add.json").endswith("/im.message.add.json")


def test_pending_checklist_items_are_grouped_by_responsible_user():
    with make_session() as database:
        user = User(username="maria", email="maria@example.com", full_name="Maria Silva", department="Licitações", password_hash="x", is_active=True, permissions=["base_editais"])
        edital = Edital(title="Concorrência 001", proposal_end=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc))
        database.add_all([user, edital])
        database.flush()
        database.add_all([
            ChecklistItem(edital_id=edital.id, title="Preparar declaração", category="Declarações", status="pendente", responsible_user_id=user.id, responsible=user.full_name),
            ChecklistItem(edital_id=edital.id, title="Item concluído", category="Geral", status="concluido", responsible_user_id=user.id, responsible=user.full_name),
        ])
        database.commit()
        grouped = _pending_by_user(database)
        assert list(grouped) == [user.id]
        assert len(grouped[user.id]) == 1
        assert grouped[user.id][0][0].title == "Preparar declaração"



def test_five_day_alert_reaches_admin_competition_owner_and_task_owner():
    with make_session() as database:
        admin = User(username="admin2", email="admin2@example.com", full_name="Admin", department="Diretoria", password_hash="x", is_admin=True, is_active=True, permissions=[])
        owner = User(username="owner", email="owner@example.com", full_name="Responsável geral", department="Licitações", password_hash="x", is_active=True, permissions=[])
        task_user = User(username="task", email="task@example.com", full_name="Responsável tarefa", department="Licitações", password_hash="x", is_active=True, permissions=[])
        deadline = datetime.now(timezone.utc) + timedelta(days=5)
        edital = Edital(title="Concorrência com alerta", proposal_end=deadline)
        database.add_all([admin, owner, task_user, edital])
        database.flush()
        database.add(BidPipeline(edital_id=edital.id, responsible=owner.full_name, responsible_user_id=owner.id))
        database.add(ChecklistItem(edital_id=edital.id, title="Entregar documento", category="Habilitação", status="pendente", responsible_user_id=task_user.id, responsible=task_user.full_name))
        database.commit()
        grouped = _pending_by_user(database, only_five_days=True)
        assert set(grouped) == {admin.id, owner.id, task_user.id}
        assert all(rows[0][0].title == "Entregar documento" for rows in grouped.values())


def test_notification_config_hides_saved_secrets():
    config = NotificationConfig(
        id="default",
        bitrix_webhook_protected=protect_local_secret("https://bitrix.example/rest/1/token"),
        smtp_password_protected=protect_local_secret("senha"),
    )
    payload = notification_config_payload(config)
    assert payload["bitrix_webhook_configured"] is True
    assert payload["smtp_password_configured"] is True
    assert "bitrix_webhook_protected" not in payload
    assert "smtp_password_protected" not in payload


def test_test_notification_records_both_channels(monkeypatch):
    with make_session() as database:
        user = User(username="joao", email="joao@example.com", full_name="João", department="Licitações", password_hash="x", is_active=True, permissions=["base_editais"], bitrix_user_id="42")
        config = NotificationConfig(id="default", email_enabled=True, bitrix_enabled=True)
        database.add_all([user, config])
        database.commit()
        monkeypatch.setattr("app.services.notifications._send_email", lambda *_: ("Teste", "joao@example.com"))
        monkeypatch.setattr("app.services.notifications._send_bitrix", lambda *_: ("Teste", "42"))
        result = send_test_notification(database, config, user, ["email", "bitrix"])
        assert result["ok"] is True
        assert {item["channel"] for item in result["results"]} == {"email", "bitrix"}
