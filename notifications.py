from __future__ import annotations

import html
import smtplib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Iterable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import ChecklistItem, Edital, NotificationConfig, NotificationDelivery, User
from app.services.local_secrets import protect_local_secret, unprotect_local_secret

PENDING_STATUSES = {"pendente", "em_andamento"}


def get_or_create_notification_config(database: Session) -> NotificationConfig:
    config = database.get(NotificationConfig, "default")
    if config is None:
        config = NotificationConfig(id="default")
        database.add(config)
        database.commit()
        database.refresh(config)
    return config


def notification_config_payload(config: NotificationConfig) -> dict[str, object]:
    return {
        "id": config.id,
        "enabled": config.enabled,
        "hour": config.hour,
        "minute": config.minute,
        "email_enabled": config.email_enabled,
        "bitrix_enabled": config.bitrix_enabled,
        "bitrix_webhook_configured": bool(config.bitrix_webhook_protected),
        "smtp_host": config.smtp_host,
        "smtp_port": config.smtp_port,
        "smtp_username": config.smtp_username,
        "smtp_password_configured": bool(config.smtp_password_protected),
        "smtp_sender_email": config.smtp_sender_email,
        "smtp_sender_name": config.smtp_sender_name,
        "smtp_use_tls": config.smtp_use_tls,
        "smtp_use_ssl": config.smtp_use_ssl,
        "last_run_at": config.last_run_at,
        "last_status": config.last_status,
        "last_summary": config.last_summary,
        "updated_at": config.updated_at,
    }


def update_notification_secrets(
    config: NotificationConfig,
    *,
    bitrix_webhook_url: str | None = None,
    clear_bitrix_webhook: bool = False,
    smtp_password: str | None = None,
    clear_smtp_password: bool = False,
) -> None:
    if clear_bitrix_webhook:
        config.bitrix_webhook_protected = None
    elif bitrix_webhook_url is not None and bitrix_webhook_url.strip():
        config.bitrix_webhook_protected = protect_local_secret(bitrix_webhook_url.strip())

    if clear_smtp_password:
        config.smtp_password_protected = None
    elif smtp_password is not None and smtp_password:
        config.smtp_password_protected = protect_local_secret(smtp_password)


def _bitrix_method_url(webhook_url: str) -> str:
    value = webhook_url.strip().rstrip("/")
    if value.endswith("/im.message.add") or value.endswith("/im.message.add.json"):
        return value
    return value + "/im.message.add.json"


def _format_deadline(value: datetime | None) -> str:
    if not value:
        return "prazo não informado"
    local_value = value.astimezone() if value.tzinfo else value
    return local_value.strftime("%d/%m/%Y às %H:%M")


def _plain_digest(user: User, rows: list[tuple[ChecklistItem, Edital]]) -> tuple[str, str]:
    today = datetime.now().strftime("%d/%m/%Y")
    subject = f"Hórus Connective · alerta de 5 dias · {len(rows)} tarefa(s) · {today}"
    lines = [
        f"Olá, {user.full_name}.",
        "",
        "Alerta automático: as tarefas abaixo vencem em cinco dias:",
        "",
    ]
    for index, (item, edital) in enumerate(rows[:30], start=1):
        status = "Em andamento" if item.status == "em_andamento" else "Pendente"
        lines.extend(
            [
                f"{index}. [{status}] {item.title}",
                f"   Edital: {edital.title}",
                f"   Categoria: {item.category}",
                f"   Prazo da tarefa/edital: {_format_deadline(item.due_date or edital.proposal_end)}",
                f"   Observação: {item.notes or 'sem observação registrada'}",
                "",
            ]
        )
    if len(rows) > 30:
        lines.append(f"Há mais {len(rows) - 30} etapa(s) pendente(s). Consulte o Hórus Connective para visualizar todas.")
    lines.extend(
        [
            "Acesse o Hórus Connective para atualizar o andamento e registrar observações.",
            "",
            "Mensagem automática · Hórus Connective Licitações",
        ]
    )
    return subject, "\n".join(lines)


def _html_digest(user: User, rows: list[tuple[ChecklistItem, Edital]]) -> str:
    items = []
    for item, edital in rows[:30]:
        status = "Em andamento" if item.status == "em_andamento" else "Pendente"
        items.append(
            "<li style='margin:0 0 14px'>"
            f"<strong>{html.escape(item.title)}</strong><br>"
            f"<span>{html.escape(edital.title)} · {html.escape(item.category)} · {status}</span><br>"
            f"<small>Prazo da tarefa/edital: {html.escape(_format_deadline(item.due_date or edital.proposal_end))}</small>"
            "</li>"
        )
    extra = ""
    if len(rows) > 30:
        extra = f"<p>Há mais {len(rows) - 30} etapa(s) pendente(s) no sistema.</p>"
    return (
        "<div style='font-family:Arial,sans-serif;color:#18324f'>"
        f"<h2>Olá, {html.escape(user.full_name)}.</h2>"
        "<p><strong>Alerta automático:</strong> as tarefas abaixo vencem em cinco dias.</p>"
        f"<ol>{''.join(items)}</ol>{extra}"
        "<p>Acesse o Hórus Connective para atualizar o andamento e registrar observações.</p>"
        "<p style='color:#8b7355;font-size:12px'>Mensagem automática · Hórus Connective Licitações</p>"
        "</div>"
    )


def _send_email(config: NotificationConfig, user: User, rows: list[tuple[ChecklistItem, Edital]]) -> tuple[str, str]:
    if not config.smtp_host:
        raise RuntimeError("Servidor SMTP não configurado")
    sender = (config.smtp_sender_email or config.smtp_username or "").strip()
    if not sender:
        raise RuntimeError("E-mail remetente não configurado")
    password = unprotect_local_secret(config.smtp_password_protected)
    subject, plain = _plain_digest(user, rows)
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{config.smtp_sender_name or 'Hórus Connective'} <{sender}>"
    message["To"] = user.email
    message.set_content(plain)
    message.add_alternative(_html_digest(user, rows), subtype="html")

    smtp_cls = smtplib.SMTP_SSL if config.smtp_use_ssl else smtplib.SMTP
    with smtp_cls(config.smtp_host, int(config.smtp_port or 587), timeout=25) as client:
        if not config.smtp_use_ssl:
            client.ehlo()
            if config.smtp_use_tls:
                client.starttls()
                client.ehlo()
        if config.smtp_username:
            client.login(config.smtp_username, password)
        client.send_message(message)
    return subject, user.email


def _send_bitrix(config: NotificationConfig, user: User, rows: list[tuple[ChecklistItem, Edital]]) -> tuple[str, str]:
    webhook = unprotect_local_secret(config.bitrix_webhook_protected)
    if not webhook:
        raise RuntimeError("Webhook do Bitrix24 não configurado")
    if not user.bitrix_user_id:
        raise RuntimeError("Usuário sem ID do Bitrix24")
    subject, plain = _plain_digest(user, rows)
    response = httpx.post(
        _bitrix_method_url(webhook),
        json={"DIALOG_ID": str(user.bitrix_user_id), "MESSAGE": plain, "SYSTEM": "N", "URL_PREVIEW": "N"},
        headers={"Accept": "application/json"},
        timeout=25.0,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError(str(payload.get("error_description") or payload["error"]))
    return subject, str(user.bitrix_user_id)


def _pending_by_user(database: Session, user_ids: Iterable[str] | None = None, *, only_five_days: bool = False) -> dict[str, list[tuple[ChecklistItem, Edital]]]:
    """Distribui alertas automáticos exatamente cinco dias antes do prazo.

    Cada tarefa pendente é enviada ao administrador, ao responsável geral da
    concorrência e ao responsável específico da tarefa, sem duplicar pessoas.
    """
    now = datetime.now(timezone.utc)
    target_date = (now + timedelta(days=5)).date()
    statement = (
        select(ChecklistItem, Edital)
        .join(Edital, Edital.id == ChecklistItem.edital_id)
        .where(ChecklistItem.status.in_(PENDING_STATUSES))
        .order_by(Edital.proposal_end.asc(), ChecklistItem.position.asc())
    )
    selected_ids = {value for value in (user_ids or []) if value}
    administrators = list(database.scalars(select(User).where(User.is_admin.is_(True), User.is_active.is_(True))).all())
    grouped: dict[str, list[tuple[ChecklistItem, Edital]]] = defaultdict(list)

    for item, edital in database.execute(statement).all():
        deadline = item.due_date or edital.proposal_end
        if only_five_days:
            if deadline is None:
                continue
            deadline_date = (deadline.astimezone(timezone.utc) if deadline.tzinfo else deadline.replace(tzinfo=timezone.utc)).date()
            if deadline_date != target_date:
                continue

        recipient_ids: set[str] = {user.id for user in administrators}
        if item.responsible_user_id:
            recipient_ids.add(item.responsible_user_id)
        if edital.pipeline and edital.pipeline.responsible_user_id:
            recipient_ids.add(edital.pipeline.responsible_user_id)
        if selected_ids:
            recipient_ids &= selected_ids

        for user_id in recipient_ids:
            user = database.get(User, user_id)
            if user is not None and user.is_active:
                grouped[user.id].append((item, edital))
    return grouped


def _record_delivery(
    database: Session,
    *,
    user: User,
    channel: str,
    status: str,
    recipient: str | None,
    subject: str | None,
    item_count: int,
    error: str | None = None,
) -> None:
    database.add(
        NotificationDelivery(
            user_id=user.id,
            channel=channel,
            status=status,
            recipient=recipient,
            subject=subject,
            item_count=item_count,
            error_message=(error or "")[:2000] or None,
            sent_at=datetime.now(timezone.utc) if status == "sent" else None,
        )
    )


def run_daily_notifications(
    *,
    require_enabled: bool = True,
    user_ids: Iterable[str] | None = None,
    channels: Iterable[str] | None = None,
) -> dict[str, int | str]:
    with SessionLocal() as database:
        config = get_or_create_notification_config(database)
        if require_enabled and not config.enabled:
            return {"status": "paused", "users": 0, "sent": 0, "failed": 0, "items": 0}
        grouped = _pending_by_user(database, user_ids, only_five_days=True)
        requested_channels = set(channels or ("email", "bitrix"))
        sent = 0
        failed = 0
        items = sum(len(rows) for rows in grouped.values())

        for user_id, rows in grouped.items():
            user = database.get(User, user_id)
            if user is None:
                continue
            channel_plan: list[str] = []
            if config.email_enabled and user.notify_email and "email" in requested_channels:
                channel_plan.append("email")
            if config.bitrix_enabled and user.notify_bitrix and "bitrix" in requested_channels:
                channel_plan.append("bitrix")
            for channel in channel_plan:
                try:
                    if channel == "email":
                        subject, recipient = _send_email(config, user, rows)
                    else:
                        subject, recipient = _send_bitrix(config, user, rows)
                    _record_delivery(database, user=user, channel=channel, status="sent", recipient=recipient, subject=subject, item_count=len(rows))
                    sent += 1
                except Exception as exc:  # noqa: BLE001
                    recipient = user.email if channel == "email" else user.bitrix_user_id
                    _record_delivery(database, user=user, channel=channel, status="failed", recipient=recipient, subject=None, item_count=len(rows), error=str(exc))
                    failed += 1

        config.last_run_at = datetime.now(timezone.utc)
        config.last_status = "completed" if failed == 0 else ("completed_with_warnings" if sent else "failed")
        config.last_summary = {"users": len(grouped), "sent": sent, "failed": failed, "items": items}
        database.commit()
        return {"status": config.last_status, "users": len(grouped), "sent": sent, "failed": failed, "items": items}


def send_test_notification(database: Session, config: NotificationConfig, user: User, channels: Iterable[str]) -> dict[str, object]:
    fake_edital = Edital(title="Mensagem de teste do Hórus Connective", organization="Hórus Connective")
    fake_item = ChecklistItem(
        edital_id="test",
        category="Teste de integração",
        title="Confirmação de recebimento das notificações diárias",
        status="pendente",
        notes="Esta mensagem confirma que o canal foi configurado corretamente.",
    )
    rows = [(fake_item, fake_edital)]
    results: list[dict[str, str]] = []
    for channel in channels:
        try:
            if channel == "email":
                subject, recipient = _send_email(config, user, rows)
            elif channel == "bitrix":
                subject, recipient = _send_bitrix(config, user, rows)
            else:
                continue
            _record_delivery(database, user=user, channel=channel, status="sent", recipient=recipient, subject=subject, item_count=1)
            results.append({"channel": channel, "status": "sent"})
        except Exception as exc:  # noqa: BLE001
            recipient = user.email if channel == "email" else user.bitrix_user_id
            _record_delivery(database, user=user, channel=channel, status="failed", recipient=recipient, subject="Teste de integração", item_count=1, error=str(exc))
            results.append({"channel": channel, "status": "failed", "error": str(exc)})
    database.commit()
    return {"ok": bool(results) and all(item["status"] == "sent" for item in results), "results": results}
