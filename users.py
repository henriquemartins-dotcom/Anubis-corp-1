from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models import User

MODULE_PERMISSIONS: dict[str, str] = {
    "dashboard": "Central Hórus",
    "base_editais": "Base de editais",
    "radar": "Radar de Licitações",
    "consultor": "Consultor Hórus",
    "pipeline": "Hórus Pipeline",
    "monitoramento": "Monitoramento",
    "relatorios": "Relatórios",
    "docs": "Hórus Docs",
    "historico": "Histórico",
}
ALL_MODULE_PERMISSIONS = tuple(MODULE_PERMISSIONS)
VIEW_PERMISSION_MAP = {
    "dashboard": "dashboard",
    "base": "base_editais",
    "radar": "radar",
    "analysis": "consultor",
    "pipeline": "pipeline",
    "monitoring": "monitoramento",
    "reports": "relatorios",
    "upload": "docs",
    "history": "historico",
}


def normalize_username(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9._-]+", "", value.strip().lower())
    if len(normalized) < 3:
        raise ValueError("O usuário deve ter ao menos 3 caracteres válidos")
    return normalized


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) > 255 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
        raise ValueError("Informe um e-mail válido")
    return normalized


def normalize_permissions(values: Iterable[str] | None) -> list[str]:
    supplied = set(values or [])
    return [permission for permission in ALL_MODULE_PERMISSIONS if permission in supplied]


def has_permission(user: User, *permissions: str) -> bool:
    if user.is_admin:
        return True
    granted = set(user.permissions or [])
    return any(permission in granted for permission in permissions)


def effective_permissions(user: User) -> list[str]:
    return list(ALL_MODULE_PERMISSIONS) if user.is_admin else normalize_permissions(user.permissions)


def first_allowed_view(user: User) -> str:
    allowed = set(effective_permissions(user))
    for view, permission in VIEW_PERMISSION_MAP.items():
        if permission in allowed:
            return view
    return "dashboard"


def bootstrap_default_admin(database: Session, *, username: str, password: str, display_name: str) -> User:
    existing_admin = database.scalar(select(User).where(User.is_admin.is_(True)).order_by(User.created_at.asc()))
    if existing_admin:
        changed = False
        if set(existing_admin.permissions or []) != set(ALL_MODULE_PERMISSIONS):
            existing_admin.permissions = list(ALL_MODULE_PERMISSIONS)
            changed = True
        if not existing_admin.is_active:
            existing_admin.is_active = True
            changed = True
        if changed:
            database.commit()
            database.refresh(existing_admin)
        return existing_admin

    normalized_username = normalize_username(username or "henrique")
    admin = User(
        username=normalized_username,
        email=f"{normalized_username}@local.horus",
        full_name=(display_name or "Administrador Hórus").strip(),
        department="Administração",
        phone_voip=None,
        password_hash=hash_password(password or "horus123"),
        is_admin=True,
        is_active=True,
        permissions=list(ALL_MODULE_PERMISSIONS),
    )
    database.add(admin)
    database.commit()
    database.refresh(admin)
    return admin
