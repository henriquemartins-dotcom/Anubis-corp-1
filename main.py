from __future__ import annotations

from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import hmac
import time
from typing import Annotated

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
except ImportError:  # Ambiente de testes/minimalista; o desktop instala APScheduler.
    class _FallbackJob:
        def __init__(self, job_id: str) -> None:
            self.id = job_id
            self.next_run_time = None

    class BackgroundScheduler:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs) -> None:
            self._jobs: dict[str, _FallbackJob] = {}
        def add_job(self, _func, _trigger=None, id: str | None = None, **_kwargs):
            job = _FallbackJob(id or "job")
            self._jobs[job.id] = job
            return job
        def get_job(self, job_id: str):
            return self._jobs.get(job_id)
        def remove_job(self, job_id: str) -> None:
            self._jobs.pop(job_id, None)
        def start(self) -> None:
            return None
        def shutdown(self, wait: bool = False) -> None:
            return None

    class CronTrigger:  # type: ignore[no-redef]
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.auth import create_session_token, decode_session_token, hash_password, verify_password
from app.config import Settings, get_settings
from app.db import SessionLocal, get_db, init_db
from app.models import BidPipeline, BidPipelineEvent, ChecklistItem, Chunk, Document, Edital, MonitorConfig, NotificationConfig, NotificationDelivery, SyncJob, User
from app.schemas import (
    AskRequest,
    AskResponse,
    BulkDeleteEditaisRequest,
    AssignableUserOut,
    ChecklistGenerateRequest,
    ChecklistGenerationOut,
    ChecklistItemOut,
    ChecklistItemUpdateRequest,
    EditalOut,
    EditalUpdateRequest,
    JobOut,
    MonitorConfigOut,
    MonitorConfigUpdateRequest,
    NotificationConfigOut,
    NotificationConfigUpdateRequest,
    NotificationDeliveryOut,
    NotificationTestRequest,
    PipelineEventOut,
    PipelineUpdateRequest,
    ReportRequest,
    SyncPNCPRequest,
    UploadResponse,
    UserCreateRequest,
    UserOut,
    UserPasswordResetRequest,
    UserUpdateRequest,
)
from app.pipeline import (
    ACTIVE_STAGES,
    ANALYSIS_STAGES,
    PIPELINE_PRIORITIES,
    PIPELINE_STAGES,
    priority_label,
    stage_label,
)
from app.services.ai import AIConfigurationError
from app.services.checklists import generate_checklist
from app.services.ingestion import ingest_file_into_edital, ingest_uploaded_file, run_pncp_sync_job
from app.services.amunes import sync_amunes
from app.services.opportunity_status import classify_opportunity
from app.services.monitoring import get_or_create_monitor_config, queue_monitor_job, run_daily_monitor_job
from app.services.notifications import get_or_create_notification_config, notification_config_payload, run_daily_notifications, send_test_notification, update_notification_secrets
from app.services.reports import generate_checklist_report, generate_competition_report
from app.services.report_library import delete_saved_report, list_saved_reports, resolve_saved_report
from app.services.pncp import MODALIDADES
from app.services.rag import answer_question
from app.services.users import (
    MODULE_PERMISSIONS,
    ALL_MODULE_PERMISSIONS,
    effective_permissions,
    first_allowed_view,
    has_permission,
    normalize_email,
    normalize_permissions,
    normalize_username,
)

settings = get_settings()
scheduler: BackgroundScheduler | None = None
login_attempts: dict[str, deque[float]] = defaultdict(deque)
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_ATTEMPTS = 5
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
PUBLIC_PATHS = {"/login", "/health", "/favicon.ico"}
MONITOR_JOB_ID = "daily-competition-monitor"
NOTIFICATION_JOB_ID = "daily-checklist-notifications"


def _commit_with_retry(database: Session, *, attempts: int = 4) -> None:
    """Commit com tolerância a bloqueios transitórios do SQLite no desktop."""
    for attempt in range(attempts):
        try:
            database.commit()
            return
        except OperationalError as exc:
            database.rollback()
            message = str(exc).lower()
            if "database is locked" not in message or attempt >= attempts - 1:
                raise
            time.sleep(0.25 * (attempt + 1))



def create_scheduled_job() -> None:
    end = date.today()
    start = end - timedelta(days=max(settings.scheduler_lookback_days - 1, 0))
    payload = SyncPNCPRequest(
        data_inicial=start,
        data_final=end,
        modalidades=settings.modality_ids,
        baixar_documentos=settings.scheduler_download_documents,
        max_paginas=settings.scheduler_max_pages,
    )
    with SessionLocal() as database:
        job = SyncJob(job_type="scheduled_pncp_sync", payload=payload.model_dump(mode="json"))
        database.add(job)
        database.commit()
        database.refresh(job)
        job_id = job.id
    run_pncp_sync_job(job_id, payload.model_dump(mode="json"))


def apply_monitor_schedule(config: MonitorConfig) -> None:
    if scheduler is None:
        return
    existing = scheduler.get_job(MONITOR_JOB_ID)
    if existing:
        scheduler.remove_job(MONITOR_JOB_ID)
    if config.enabled:
        scheduler.add_job(
            run_daily_monitor_job,
            CronTrigger(
                hour=int(config.hour),
                minute=int(config.minute),
                timezone=settings.scheduler_timezone,
            ),
            id=MONITOR_JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )


def monitor_next_run() -> datetime | None:
    if scheduler is None:
        return None
    job = scheduler.get_job(MONITOR_JOB_ID)
    return job.next_run_time if job else None


def apply_notification_schedule(config: NotificationConfig) -> None:
    if scheduler is None:
        return
    existing = scheduler.get_job(NOTIFICATION_JOB_ID)
    if existing:
        scheduler.remove_job(NOTIFICATION_JOB_ID)
    scheduler.add_job(
            run_daily_notifications,
            CronTrigger(
                hour=int(config.hour),
                minute=int(config.minute),
                timezone=settings.scheduler_timezone,
            ),
            id=NOTIFICATION_JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
            kwargs={"require_enabled": False},
        )


def notification_next_run() -> datetime | None:
    if scheduler is None:
        return None
    job = scheduler.get_job(NOTIFICATION_JOB_ID)
    return job.next_run_time if job else None


def validate_runtime_settings(config: Settings) -> None:
    if not config.is_production:
        return
    unsafe_defaults = {"change-me-in-production", "alfred123", "horus123", ""}
    if config.secret_key in unsafe_defaults:
        raise RuntimeError("Defina SECRET_KEY com um valor seguro antes de iniciar em produção")
    if config.admin_password in unsafe_defaults:
        raise RuntimeError("Defina ADMIN_PASSWORD com um valor seguro antes de iniciar em produção")
    if not config.auth_cookie_secure:
        raise RuntimeError("AUTH_COOKIE_SECURE deve ser true em produção")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler
    validate_runtime_settings(settings)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    init_db()

    scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)
    if settings.scheduler_enabled:
        scheduler.add_job(
            create_scheduled_job,
            CronTrigger(
                hour=settings.scheduler_hour,
                minute=settings.scheduler_minute,
                timezone=settings.scheduler_timezone,
            ),
            id="daily-pncp-sync",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    scheduler.start()
    with SessionLocal() as database:
        apply_monitor_schedule(get_or_create_monitor_config(database))
        apply_notification_schedule(get_or_create_notification_config(database))

    yield

    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"] ,
    allow_headers=["*"] ,
)

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _login_is_allowed(client_key: str) -> bool:
    now = time.monotonic()
    attempts = login_attempts[client_key]
    while attempts and now - attempts[0] > LOGIN_WINDOW_SECONDS:
        attempts.popleft()
    return len(attempts) < LOGIN_MAX_ATTEMPTS


def _record_login_failure(client_key: str) -> None:
    login_attempts[client_key].append(time.monotonic())


def _safe_next_path(value: str | None) -> str:
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return "/"



def _permission_requirements(path: str, method: str) -> tuple[str, ...]:
    if path.startswith("/api/users") or path.startswith("/api/notifications"):
        return ("__admin__",)
    if path.startswith("/api/team/assignable"):
        return ("base_editais", "pipeline")
    if path == "/api/dashboard":
        return ("dashboard",)
    if path == "/api/pipeline/meta" or "/pipeline" in path:
        return ("pipeline",)
    if "/checklist" in path:
        return ("base_editais", "pipeline")
    if path.startswith("/api/monitor") or path.startswith("/api/sync/pncp") or path.startswith("/api/jobs"):
        return ("monitoramento", "historico")
    if path.startswith("/api/reports"):
        return ("relatorios",)
    if path == "/api/upload":
        return ("docs",)
    if path == "/api/ask":
        return ("consultor",)
    if path.startswith("/api/documents/"):
        return ("base_editais", "docs", "consultor")
    if path.startswith("/api/editais"):
        if method in SAFE_METHODS:
            return ("dashboard", "base_editais", "radar", "pipeline", "consultor", "relatorios")
        return ("base_editais", "pipeline")
    return ()


def _user_context(user: User) -> dict[str, object]:
    permissions = effective_permissions(user)
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.full_name,
        "full_name": user.full_name,
        "email": user.email,
        "department": user.department,
        "phone_voip": user.phone_voip,
        "bitrix_user_id": user.bitrix_user_id,
        "role": "Administrador" if user.is_admin else user.department,
        "is_admin": user.is_admin,
        "permissions": permissions,
    }


def _find_user_by_username(database: Session, username: str) -> User | None:
    normalized = username.strip().lower()
    return database.scalar(select(User).where(User.username == normalized))


@app.middleware("http")
async def require_authentication(request: Request, call_next) -> Response:
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/static/"):
        return await call_next(request)

    session = decode_session_token(
        request.cookies.get(settings.auth_cookie_name),
        settings.secret_key,
        settings.session_max_age_seconds,
    )
    request.state.auth_session = session
    if session is None:
        if path.startswith("/api/") or request.headers.get("accept", "").startswith("application/json"):
            return JSONResponse({"detail": "Sessão expirada ou acesso não autorizado"}, status_code=401)
        return RedirectResponse(url=f"/login?next={path}", status_code=303)

    with SessionLocal() as database:
        current_user = _find_user_by_username(database, session.username)
        if current_user is None or not current_user.is_active:
            current_user = None
        elif not current_user.is_admin:
            current_user.permissions = normalize_permissions(current_user.permissions)
    if current_user is None:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Usuário inativo ou removido"}, status_code=401)
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie(settings.auth_cookie_name, path="/")
        return response
    request.state.current_user = current_user

    required = _permission_requirements(path, request.method)
    if required:
        allowed = current_user.is_admin if required == ("__admin__",) else has_permission(current_user, *required)
        if not allowed:
            return JSONResponse({"detail": "Seu usuário não possui permissão para este módulo"}, status_code=403)

    if request.method not in SAFE_METHODS:
        supplied_csrf = request.headers.get("x-csrf-token", "")
        if not supplied_csrf or not hmac.compare_digest(supplied_csrf, session.csrf_token):
            return JSONResponse({"detail": "Token de segurança inválido"}, status_code=403)

    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'"
    )
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    if not request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/", skip_splash: int = 0):
    existing = decode_session_token(
        request.cookies.get(settings.auth_cookie_name),
        settings.secret_key,
        settings.session_max_age_seconds,
    )
    if existing:
        with SessionLocal() as database:
            existing_user = _find_user_by_username(database, existing.username)
            if existing_user and existing_user.is_active:
                return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "app_name": settings.app_name,
            "app_version": settings.app_version,
            "next_path": _safe_next_path(next),
            "error": None,
            "desktop_mode": settings.desktop_mode,
            "display_name": "Usuário Hórus",
            "desktop_username": "",
            "show_splash": bool(settings.desktop_mode and not skip_splash),
        },
    )


@app.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next_path: Annotated[str, Form()] = "/",
):
    client_key = _client_key(request)
    if not _login_is_allowed(client_key):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            status_code=429,
            context={
                "app_name": settings.app_name,
                "app_version": settings.app_version,
                "next_path": _safe_next_path(next_path),
                "error": "Muitas tentativas. Aguarde alguns minutos antes de tentar novamente.",
                "desktop_mode": settings.desktop_mode,
                "display_name": settings.admin_display_name,
                "desktop_username": settings.admin_username,
                "show_splash": False,
            },
        )

    with SessionLocal() as database:
        user = _find_user_by_username(database, username)
        valid = bool(user and user.is_active and verify_password(password, user.password_hash))
        if valid and user is not None:
            user.last_login_at = datetime.now(timezone.utc)
            database.commit()
            authenticated_username = user.username
        else:
            authenticated_username = ""

    if not valid:
        _record_login_failure(client_key)
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            status_code=401,
            context={
                "app_name": settings.app_name,
                "app_version": settings.app_version,
                "next_path": _safe_next_path(next_path),
                "error": "Usuário ou senha inválidos.",
                "desktop_mode": settings.desktop_mode,
                "display_name": "Usuário Hórus",
                "desktop_username": "",
                "show_splash": False,
            },
        )

    login_attempts.pop(client_key, None)
    token, _ = create_session_token(authenticated_username, settings.secret_key)
    response = RedirectResponse(url=_safe_next_path(next_path), status_code=303)
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=None if settings.desktop_mode else settings.session_max_age_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure or settings.is_production,
        samesite="lax",
        path="/",
    )
    return response


@app.post("/logout")
def logout() -> Response:
    response = JSONResponse({"ok": True})
    response.delete_cookie(settings.auth_cookie_name, path="/")
    return response


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    session = request.state.auth_session
    user: User = request.state.current_user
    current_user = _user_context(user)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": settings.app_name,
            "app_version": settings.app_version,
            "modalidades": MODALIDADES,
            "pipeline_stages": PIPELINE_STAGES,
            "pipeline_priorities": PIPELINE_PRIORITIES,
            "module_permissions": MODULE_PERMISSIONS,
            "csrf_token": session.csrf_token,
            "current_user": current_user,
            "landing_view": first_allowed_view(user),
            "desktop_mode": settings.desktop_mode,
        },
    )


@app.get("/api/team/assignable", response_model=list[AssignableUserOut])
def assignable_users(database: Session = Depends(get_db)) -> list[dict[str, object]]:
    users = database.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name.asc())).all()
    return [
        {
            "id": user.id,
            "full_name": user.full_name,
            "department": user.department,
            "email": user.email,
            "bitrix_user_id": user.bitrix_user_id,
        }
        for user in users
    ]


@app.get("/api/users/modules")
def user_modules() -> dict[str, str]:
    return MODULE_PERMISSIONS


@app.get("/api/users", response_model=list[UserOut])
def list_users(database: Session = Depends(get_db)) -> list[User]:
    users = list(database.scalars(select(User).order_by(User.is_admin.desc(), User.full_name.asc())).all())
    for user in users:
        user.permissions = effective_permissions(user)
    return users


@app.post("/api/users", response_model=UserOut, status_code=201)
def create_user(payload: UserCreateRequest, database: Session = Depends(get_db)) -> User:
    try:
        username = normalize_username(payload.username)
        email = normalize_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    duplicate = database.scalar(select(User).where(or_(User.username == username, User.email == email)))
    if duplicate:
        field = "usuário" if duplicate.username == username else "e-mail"
        raise HTTPException(status_code=409, detail=f"Já existe uma conta com este {field}")
    permissions = normalize_permissions(payload.permissions)
    if not permissions:
        raise HTTPException(status_code=422, detail="Selecione ao menos um módulo para o usuário")
    user = User(
        username=username,
        email=email,
        full_name=payload.full_name.strip(),
        department=payload.department.strip(),
        phone_voip=(payload.phone_voip or "").strip() or None,
        bitrix_user_id=(payload.bitrix_user_id or "").strip() or None,
        notify_email=payload.notify_email,
        notify_bitrix=payload.notify_bitrix,
        password_hash=hash_password(payload.password),
        is_admin=False,
        is_active=payload.is_active,
        permissions=permissions,
    )
    database.add(user)
    database.commit()
    database.refresh(user)
    return user


@app.put("/api/users/{user_id}", response_model=UserOut)
def update_user(user_id: str, payload: UserUpdateRequest, request: Request, database: Session = Depends(get_db)) -> User:
    user = database.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    try:
        username = normalize_username(payload.username)
        email = normalize_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    duplicate = database.scalar(select(User).where(User.id != user_id, or_(User.username == username, User.email == email)))
    if duplicate:
        raise HTTPException(status_code=409, detail="Usuário ou e-mail já cadastrado")
    if user.is_admin:
        username = user.username
    user.username = username
    user.email = email
    user.full_name = payload.full_name.strip()
    user.department = payload.department.strip()
    user.phone_voip = (payload.phone_voip or "").strip() or None
    user.bitrix_user_id = (payload.bitrix_user_id or "").strip() or None
    user.notify_email = payload.notify_email
    user.notify_bitrix = payload.notify_bitrix
    if user.is_admin:
        user.is_active = True
        user.permissions = list(ALL_MODULE_PERMISSIONS)
    else:
        user.is_active = payload.is_active
        user.permissions = normalize_permissions(payload.permissions)
    database.commit()
    database.refresh(user)
    return user


@app.post("/api/users/{user_id}/reset-password")
def reset_user_password(user_id: str, payload: UserPasswordResetRequest, database: Session = Depends(get_db)) -> dict[str, bool]:
    user = database.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.password_hash = hash_password(payload.password)
    database.commit()
    return {"ok": True}


@app.get("/api/notifications/config", response_model=NotificationConfigOut)
def get_notification_config(database: Session = Depends(get_db)) -> dict[str, object]:
    config = get_or_create_notification_config(database)
    payload = notification_config_payload(config)
    payload["next_run_at"] = notification_next_run()
    return payload


@app.put("/api/notifications/config", response_model=NotificationConfigOut)
def save_notification_config(payload: NotificationConfigUpdateRequest, database: Session = Depends(get_db)) -> dict[str, object]:
    config = get_or_create_notification_config(database)
    config.enabled = payload.enabled
    config.hour = payload.hour
    config.minute = payload.minute
    config.email_enabled = payload.email_enabled
    config.bitrix_enabled = payload.bitrix_enabled
    config.smtp_host = payload.smtp_host
    config.smtp_port = payload.smtp_port
    config.smtp_username = payload.smtp_username
    config.smtp_sender_email = payload.smtp_sender_email
    config.smtp_sender_name = payload.smtp_sender_name
    config.smtp_use_tls = payload.smtp_use_tls
    config.smtp_use_ssl = payload.smtp_use_ssl
    update_notification_secrets(
        config,
        bitrix_webhook_url=payload.bitrix_webhook_url,
        clear_bitrix_webhook=payload.clear_bitrix_webhook,
        smtp_password=payload.smtp_password,
        clear_smtp_password=payload.clear_smtp_password,
    )
    database.commit()
    database.refresh(config)
    apply_notification_schedule(config)
    response = notification_config_payload(config)
    response["next_run_at"] = notification_next_run()
    return response


@app.post("/api/notifications/run")
def run_notifications_now(background_tasks: BackgroundTasks) -> dict[str, bool]:
    background_tasks.add_task(run_daily_notifications, require_enabled=False)
    return {"queued": True}


@app.post("/api/notifications/test")
def test_notifications(payload: NotificationTestRequest, database: Session = Depends(get_db)) -> dict[str, object]:
    user = database.get(User, payload.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="Usuário não encontrado ou inativo")
    config = get_or_create_notification_config(database)
    return send_test_notification(database, config, user, payload.channels)


@app.get("/api/notifications/history", response_model=list[NotificationDeliveryOut])
def notification_history(limit: int = Query(default=50, ge=1, le=200), database: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = database.execute(
        select(NotificationDelivery, User.full_name)
        .outerjoin(User, User.id == NotificationDelivery.user_id)
        .order_by(NotificationDelivery.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": delivery.id,
            "user_id": delivery.user_id,
            "user_name": user_name,
            "channel": delivery.channel,
            "status": delivery.status,
            "recipient": delivery.recipient,
            "subject": delivery.subject,
            "item_count": delivery.item_count,
            "error_message": delivery.error_message,
            "sent_at": delivery.sent_at,
            "created_at": delivery.created_at,
        }
        for delivery, user_name in rows
    ]


@app.get("/health")
def health(database: Session = Depends(get_db)) -> dict[str, object]:
    database.execute(text("SELECT 1"))
    if settings.is_production:
        return {"status": "ok", "version": settings.app_version}
    return {
        "status": "ok",
        "version": settings.app_version,
        "database": "ok",
        "ai_configured": bool(settings.openai_api_key),
        "scheduler_enabled": settings.scheduler_enabled,
        "monitor_next_run": monitor_next_run().isoformat() if monitor_next_run() else None,
        "notification_next_run": notification_next_run().isoformat() if notification_next_run() else None,
    }


@app.get("/api/modalidades")
def modalities() -> dict[int, str]:
    return MODALIDADES


@app.get("/api/dashboard")
def dashboard(database: Session = Depends(get_db)) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    next_7 = now + timedelta(days=7)
    next_30 = now + timedelta(days=30)

    editais = list(
        database.scalars(
            select(Edital).options(selectinload(Edital.pipeline), selectinload(Edital.checklist_items))
        ).all()
    )
    total_editais = len(editais)
    indexed = sum(1 for item in editais if item.indexing_status in {"indexed", "completed"})
    pipeline_new = sum(1 for item in editais if item.pipeline_stage == "nova_oportunidade")
    pipeline_analysis = sum(1 for item in editais if item.pipeline_stage in ANALYSIS_STAGES)
    pipeline_proposals = sum(1 for item in editais if item.pipeline_stage == "proposta_enviada")
    pipeline_wins = sum(1 for item in editais if item.pipeline_stage == "ganha")
    active_items = [item for item in editais if item.pipeline_stage in ACTIVE_STAGES]
    pipeline_mapped_value = sum(float(item.estimated_value or 0) for item in active_items)

    open_now = database.scalar(select(func.count(Edital.id)).where(Edital.proposal_end >= now)) or 0
    closing_7 = database.scalar(select(func.count(Edital.id)).where(Edital.proposal_end.between(now, next_7))) or 0
    closing_30 = database.scalar(select(func.count(Edital.id)).where(Edital.proposal_end.between(now, next_30))) or 0
    avg_value = (pipeline_mapped_value / len(active_items)) if active_items else 0
    states = list(database.execute(select(Edital.uf, func.count(Edital.id)).where(Edital.uf.is_not(None)).group_by(Edital.uf).order_by(func.count(Edital.id).desc())).all())
    modalities = list(database.execute(select(Edital.modality_name, func.count(Edital.id)).where(Edital.modality_name.is_not(None)).group_by(Edital.modality_name).order_by(func.count(Edital.id).desc()).limit(8)).all())
    organizations = list(database.execute(select(Edital.organization, func.count(Edital.id)).where(Edital.organization.is_not(None)).group_by(Edital.organization).order_by(func.count(Edital.id).desc()).limit(6)).all())
    latest_job = database.scalar(select(SyncJob).order_by(SyncJob.created_at.desc()).limit(1))

    recent_events = list(
        database.scalars(
            select(BidPipelineEvent)
            .options(selectinload(BidPipelineEvent.edital))
            .order_by(BidPipelineEvent.created_at.desc())
            .limit(6)
        ).all()
    )
    pipeline_activity = [
        {
            "id": event.id,
            "event_type": event.event_type,
            "description": event.description or "Pipeline atualizado",
            "created_at": event.created_at.isoformat(),
            "edital_id": event.edital_id,
            "edital_title": event.edital.title if event.edital else "Edital",
            "organization": event.edital.organization if event.edital else None,
            "from_stage": event.from_stage,
            "to_stage": event.to_stage,
            "to_stage_label": stage_label(event.to_stage),
        }
        for event in recent_events
    ]

    return {
        "total_editais": total_editais,
        "indexed_editais": indexed,
        "open_opportunities": open_now,
        "closing_7_days": closing_7,
        "closing_30_days": closing_30,
        "estimated_value_open": pipeline_mapped_value,
        "average_value_open": avg_value,
        "indexing_rate": round((indexed / total_editais * 100), 1) if total_editais else 0,
        "pipeline_new": pipeline_new,
        "pipeline_analysis": pipeline_analysis,
        "pipeline_proposals": pipeline_proposals,
        "pipeline_wins": pipeline_wins,
        "pipeline_active": len(active_items),
        "pipeline_mapped_value": pipeline_mapped_value,
        "pipeline_activity": pipeline_activity,
        "states": [{"uf": uf, "count": count} for uf, count in states],
        "modalities": [{"name": name, "count": count} for name, count in modalities],
        "organizations": [{"name": name, "count": count} for name, count in organizations],
        "latest_sync": JobOut.model_validate(latest_job).model_dump(mode="json") if latest_job else None,
    }


@app.get("/api/editais", response_model=list[EditalOut])
def list_editais(
    q: str | None = Query(default=None, max_length=200),
    uf: str | None = Query(default=None, min_length=2, max_length=2),
    modalidade: int | None = Query(default=None),
    somente_abertos: bool = Query(default=False),
    situacao: str | None = Query(default=None, pattern="^(open|closed|unknown|all)$"),
    fonte: str | None = Query(default=None, max_length=40),
    valor_minimo: float | None = Query(default=None, ge=0),
    pipeline_stage: str | None = Query(default=None, max_length=40),
    pipeline_priority: str | None = Query(default=None, max_length=20),
    pipeline_responsible: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=100, ge=1, le=500),
    database: Session = Depends(get_db),
) -> list[Edital]:
    statement = select(Edital).options(selectinload(Edital.pipeline), selectinload(Edital.checklist_items))
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(or_(Edital.title.ilike(pattern), Edital.object_text.ilike(pattern), Edital.organization.ilike(pattern), Edital.pncp_id.ilike(pattern)))
    if uf:
        statement = statement.where(Edital.uf == uf.upper())
    if modalidade is not None:
        statement = statement.where(Edital.modality_id == modalidade)
    if somente_abertos:
        statement = statement.where(Edital.proposal_end >= datetime.now(timezone.utc))
    if fonte:
        statement = statement.where(Edital.source == fonte)
    if valor_minimo is not None:
        statement = statement.where(Edital.estimated_value >= valor_minimo)
    statement = statement.order_by(Edital.proposal_end.asc().nullslast(), Edital.created_at.desc()).limit(500)
    items = list(database.scalars(statement).all())
    if pipeline_stage:
        items = [item for item in items if item.pipeline_stage == pipeline_stage]
    if pipeline_priority:
        items = [item for item in items if item.pipeline_priority == pipeline_priority]
    if pipeline_responsible:
        needle = pipeline_responsible.strip().lower()
        items = [item for item in items if needle in (item.pipeline_responsible or "").lower()]
    if situacao and situacao != "all":
        items = [item for item in items if classify_opportunity(item.status_name, item.proposal_end) == situacao]
    return items[:limit]


@app.get("/api/pipeline/meta")
def pipeline_meta() -> dict[str, object]:
    return {
        "stages": [{"key": key, "label": label} for key, label in PIPELINE_STAGES],
        "priorities": [{"key": key, "label": label} for key, label in PIPELINE_PRIORITIES],
    }


@app.get("/api/editais/{edital_id}/pipeline-history", response_model=list[PipelineEventOut])
def pipeline_history(
    edital_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    database: Session = Depends(get_db),
) -> list[BidPipelineEvent]:
    if not database.get(Edital, edital_id):
        raise HTTPException(status_code=404, detail="Edital não encontrado")
    statement = (
        select(BidPipelineEvent)
        .where(BidPipelineEvent.edital_id == edital_id)
        .order_by(BidPipelineEvent.created_at.desc())
        .limit(limit)
    )
    return list(database.scalars(statement).all())


@app.patch("/api/editais/{edital_id}/pipeline", response_model=EditalOut)
def update_pipeline(
    edital_id: str,
    payload: PipelineUpdateRequest,
    database: Session = Depends(get_db),
) -> Edital:
    edital = database.scalar(
        select(Edital)
        .options(selectinload(Edital.pipeline))
        .where(Edital.id == edital_id)
    )
    if not edital:
        raise HTTPException(status_code=404, detail="Edital não encontrado")

    pipeline = edital.pipeline
    if pipeline is None:
        pipeline = BidPipeline(edital=edital)
        database.add(pipeline)

    if not pipeline.stage:
        pipeline.stage = "nova_oportunidade"
    if not pipeline.priority:
        pipeline.priority = "normal"
    old_stage = pipeline.stage
    changes: dict[str, object] = {}
    if "stage" in payload.model_fields_set and payload.stage is not None and payload.stage != pipeline.stage:
        changes["stage"] = {"from": pipeline.stage, "to": payload.stage}
        pipeline.stage = payload.stage
    if "priority" in payload.model_fields_set and payload.priority is not None and payload.priority != pipeline.priority:
        changes["priority"] = {"from": pipeline.priority, "to": payload.priority}
        pipeline.priority = payload.priority
    if "responsible_user_id" in payload.model_fields_set:
        if payload.responsible_user_id:
            responsible_user = database.get(User, payload.responsible_user_id)
            if responsible_user is None or not responsible_user.is_active:
                raise HTTPException(status_code=422, detail="Responsável da concorrência não encontrado ou inativo")
            if responsible_user.id != pipeline.responsible_user_id:
                changes["responsible"] = {"from": pipeline.responsible, "to": responsible_user.full_name}
            pipeline.responsible_user_id = responsible_user.id
            pipeline.responsible = responsible_user.full_name
        else:
            if pipeline.responsible_user_id or pipeline.responsible:
                changes["responsible"] = {"from": pipeline.responsible, "to": None}
            pipeline.responsible_user_id = None
            pipeline.responsible = None
    elif "responsible" in payload.model_fields_set and payload.responsible != pipeline.responsible:
        changes["responsible"] = {"from": pipeline.responsible, "to": payload.responsible}
        pipeline.responsible = payload.responsible
        pipeline.responsible_user_id = None
    if "internal_notes" in payload.model_fields_set and payload.internal_notes != pipeline.internal_notes:
        changes["internal_notes"] = True
        pipeline.internal_notes = payload.internal_notes

    if not changes:
        return edital

    stage_changed = "stage" in changes
    event_type = "stage_changed" if stage_changed else "details_updated"
    description = payload.change_note
    if not description:
        if stage_changed:
            description = f"Movido de {stage_label(old_stage)} para {stage_label(pipeline.stage)}"
        else:
            description = "Responsável, prioridade ou observações atualizados"
    database.add(
        BidPipelineEvent(
            edital=edital,
            event_type=event_type,
            from_stage=old_stage if stage_changed else pipeline.stage,
            to_stage=pipeline.stage,
            description=description,
            details=changes,
        )
    )
    database.commit()
    database.refresh(edital)
    return edital


@app.get("/api/editais/{edital_id}/checklist", response_model=list[ChecklistItemOut])
def get_checklist(edital_id: str, database: Session = Depends(get_db)) -> list[ChecklistItem]:
    if not database.get(Edital, edital_id):
        raise HTTPException(status_code=404, detail="Edital não encontrado")
    statement = (
        select(ChecklistItem)
        .where(ChecklistItem.edital_id == edital_id)
        .order_by(ChecklistItem.position.asc(), ChecklistItem.created_at.asc())
    )
    return list(database.scalars(statement).all())


@app.post("/api/editais/{edital_id}/checklist/generate", response_model=ChecklistGenerationOut)
def create_checklist(
    edital_id: str,
    payload: ChecklistGenerateRequest,
    database: Session = Depends(get_db),
) -> ChecklistGenerationOut:
    try:
        items, mode = generate_checklist(
            database,
            edital_id,
            replace_existing=payload.replace_existing,
        )
        return ChecklistGenerationOut(mode=mode, items=[ChecklistItemOut.model_validate(item) for item in items])
    except (ValueError, AIConfigurationError) as exc:
        database.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        database.rollback()
        raise HTTPException(status_code=500, detail=f"Falha ao gerar checklist: {exc}") from exc


@app.patch("/api/checklist-items/{item_id}", response_model=ChecklistItemOut)
def update_checklist_item(
    item_id: str,
    payload: ChecklistItemUpdateRequest,
    database: Session = Depends(get_db),
) -> ChecklistItem:
    item = database.get(ChecklistItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item do checklist não encontrado")
    if "status" in payload.model_fields_set and payload.status is not None:
        item.status = payload.status
    if "responsible_user_id" in payload.model_fields_set:
        if payload.responsible_user_id:
            responsible_user = database.get(User, payload.responsible_user_id)
            if responsible_user is None or not responsible_user.is_active:
                raise HTTPException(status_code=422, detail="Responsável não encontrado ou inativo")
            item.responsible_user_id = responsible_user.id
            item.responsible = responsible_user.full_name
        else:
            item.responsible_user_id = None
            item.responsible = None
    elif "responsible" in payload.model_fields_set:
        item.responsible = payload.responsible
        if not payload.responsible:
            item.responsible_user_id = None
    if "due_date" in payload.model_fields_set:
        item.due_date = payload.due_date
    if "notes" in payload.model_fields_set:
        item.notes = payload.notes
    database.commit()
    database.refresh(item)
    return item


@app.post("/api/editais/{edital_id}/checklist/report")
def create_checklist_report(
    edital_id: str,
    database: Session = Depends(get_db),
) -> FileResponse:
    try:
        path = generate_checklist_report(database, edital_id)
        return FileResponse(path, media_type="application/pdf", filename=path.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Falha ao gerar checklist PDF: {exc}") from exc


@app.get("/api/reports/saved")
def get_saved_reports() -> dict[str, object]:
    items = list_saved_reports(settings.data_dir)
    return {
        "items": items,
        "count": len(items),
        "total_size_bytes": sum(int(item["size_bytes"]) for item in items),
    }


@app.get("/api/reports/saved/{report_id}")
def open_saved_report(report_id: str) -> FileResponse:
    try:
        path = resolve_saved_report(settings.data_dir, report_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline")


@app.delete("/api/reports/saved/{report_id}")
def remove_saved_report(report_id: str) -> dict[str, object]:
    try:
        path = delete_saved_report(settings.data_dir, report_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "deleted": path.name}


@app.post("/api/reports/competitions")
def create_competition_report(
    payload: ReportRequest,
    database: Session = Depends(get_db),
) -> FileResponse:
    try:
        path = generate_competition_report(database, payload.edital_ids, title=payload.title)
        return FileResponse(path, media_type="application/pdf", filename=path.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Falha ao gerar relatório: {exc}") from exc


@app.get("/api/monitor/config", response_model=MonitorConfigOut)
def get_monitor_config(database: Session = Depends(get_db)) -> MonitorConfigOut:
    config = get_or_create_monitor_config(database)
    output = MonitorConfigOut.model_validate(config)
    output.next_run_at = monitor_next_run()
    return output


@app.put("/api/monitor/config", response_model=MonitorConfigOut)
def update_monitor_config(
    payload: MonitorConfigUpdateRequest,
    database: Session = Depends(get_db),
) -> MonitorConfigOut:
    config = get_or_create_monitor_config(database)
    for field in (
        "enabled", "hour", "minute", "lookback_days", "modalities", "uf", "keywords",
        "segment_name", "exact_match_enabled", "exact_phrases", "max_pages", "download_documents", "generate_report",
    ):
        setattr(config, field, getattr(payload, field))
    database.commit()
    database.refresh(config)
    apply_monitor_schedule(config)
    output = MonitorConfigOut.model_validate(config)
    output.next_run_at = monitor_next_run()
    return output


@app.post("/api/monitor/run", response_model=JobOut, status_code=202)
def run_monitor_now(
    background_tasks: BackgroundTasks,
    database: Session = Depends(get_db),
) -> SyncJob:
    job = queue_monitor_job(database)
    if job.status == "queued":
        background_tasks.add_task(run_daily_monitor_job, job.id)
    return job


@app.get("/api/monitor/report")
def get_monitor_report(database: Session = Depends(get_db)) -> FileResponse:
    config = get_or_create_monitor_config(database)
    if not config.last_report_path:
        raise HTTPException(status_code=404, detail="Nenhum relatório diário foi gerado")
    path = Path(config.last_report_path).resolve()
    reports_root = (settings.data_dir / "reports").resolve()
    if reports_root not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail="Relatório diário não encontrado")
    return FileResponse(path, media_type="application/pdf", filename=path.name)


@app.put("/api/editais/{edital_id}", response_model=EditalOut)
def update_edital(edital_id: str, payload: EditalUpdateRequest, database: Session = Depends(get_db)) -> Edital:
    edital = database.get(Edital, edital_id)
    if not edital:
        raise HTTPException(status_code=404, detail="Edital não encontrado")

    edital.title = payload.title.strip()
    edital.organization = payload.organization
    edital.uf = payload.uf
    edital.municipality = payload.municipality
    edital.modality_name = payload.modality_name
    edital.status_name = payload.status_name
    edital.estimated_value = payload.estimated_value
    edital.proposal_end = payload.proposal_end
    edital.object_text = payload.object_text
    database.commit()
    database.refresh(edital)
    return edital



def _delete_editais_by_ids(database: Session, edital_ids: list[str]) -> int:
    ids = list(dict.fromkeys(edital_ids))
    if not ids:
        return 0
    document_ids = list(database.scalars(select(Document.id).where(Document.edital_id.in_(ids))).all())
    database.execute(delete(Chunk).where(Chunk.edital_id.in_(ids)))
    if document_ids:
        database.execute(delete(Document).where(Document.id.in_(document_ids)))
    database.execute(delete(ChecklistItem).where(ChecklistItem.edital_id.in_(ids)))
    database.execute(delete(BidPipelineEvent).where(BidPipelineEvent.edital_id.in_(ids)))
    database.execute(delete(BidPipeline).where(BidPipeline.edital_id.in_(ids)))
    result = database.execute(delete(Edital).where(Edital.id.in_(ids)))
    return int(result.rowcount or 0)


@app.post("/api/editais/bulk-delete")
def bulk_delete_editais(payload: BulkDeleteEditaisRequest, database: Session = Depends(get_db)) -> dict[str, int | bool]:
    ids = list(payload.edital_ids)
    if payload.delete_closed:
        candidates = list(database.scalars(select(Edital)).all())
        ids.extend(item.id for item in candidates if item.opportunity_status == "closed")
    ids = list(dict.fromkeys(ids))
    if not ids:
        return {"ok": True, "deleted": 0}
    try:
        deleted = _delete_editais_by_ids(database, ids)
        _commit_with_retry(database)
    except OperationalError as exc:
        database.rollback()
        if "database is locked" in str(exc).lower():
            raise HTTPException(status_code=503, detail="O banco local está ocupado. Feche outras instâncias do Hórus e tente novamente.") from exc
        raise HTTPException(status_code=500, detail=f"Falha de banco ao excluir editais em lote: {exc}") from exc
    except SQLAlchemyError as exc:
        database.rollback()
        raise HTTPException(status_code=500, detail=f"Falha de banco ao excluir editais em lote: {exc}") from exc
    return {"ok": True, "deleted": deleted}

@app.delete("/api/editais/{edital_id}")
def delete_edital(edital_id: str, database: Session = Depends(get_db)) -> dict[str, bool | str]:
    edital = database.get(Edital, edital_id)
    if not edital:
        raise HTTPException(status_code=404, detail="Edital não encontrado")

    try:
        _delete_editais_by_ids(database, [edital_id])
        _commit_with_retry(database)
    except OperationalError as exc:
        database.rollback()
        if "database is locked" in str(exc).lower():
            raise HTTPException(status_code=503, detail="O banco local está ocupado. Feche outras instâncias do Hórus e tente novamente.") from exc
        raise HTTPException(status_code=500, detail=f"Falha de banco ao excluir edital: {exc}") from exc
    except SQLAlchemyError as exc:
        database.rollback()
        raise HTTPException(status_code=500, detail=f"Falha de banco ao excluir edital: {exc}") from exc
    return {"ok": True, "deleted_id": edital_id}


@app.post("/api/sync/pncp", response_model=JobOut, status_code=202)
def sync_pncp(
    payload: SyncPNCPRequest,
    background_tasks: BackgroundTasks,
    database: Session = Depends(get_db),
) -> SyncJob:
    try:
        monitor_config = get_or_create_monitor_config(database)
        exact_phrases = list(monitor_config.exact_phrases or []) if monitor_config.exact_match_enabled else []
    except SQLAlchemyError:
        database.rollback()
        exact_phrases = []
    effective_payload = payload.model_copy(update={"exact_phrases": exact_phrases})
    job = SyncJob(job_type="pncp_sync", payload=effective_payload.model_dump(mode="json"))
    database.add(job)
    try:
        _commit_with_retry(database)
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="O banco local está ocupado. Feche outras instâncias do Hórus e tente novamente.") from exc
    database.refresh(job)
    background_tasks.add_task(run_pncp_sync_job, job.id, effective_payload.model_dump(mode="json"))
    return job



@app.post("/api/sync/amunes", response_model=JobOut, status_code=202)
def sync_amunes_source(background_tasks: BackgroundTasks, database: Session = Depends(get_db)) -> SyncJob:
    job = SyncJob(job_type="amunes_sync", payload={"source": "amunes_licitamunes"})
    database.add(job)
    try:
        _commit_with_retry(database)
    except OperationalError as exc:
        raise HTTPException(status_code=503, detail="O banco local está ocupado. Feche outras instâncias do Hórus e tente novamente.") from exc
    database.refresh(job)

    def runner(job_id: str) -> None:
        with SessionLocal() as session:
            current = session.get(SyncJob, job_id)
            if current is None:
                return
            current.status = "running"
            session.commit()
            try:
                monitor_config = get_or_create_monitor_config(session)
                result = sync_amunes(session, exact_phrases=list(monitor_config.exact_phrases or []) if monitor_config.exact_match_enabled else [])
                current = session.get(SyncJob, job_id)
                current.status = "completed_with_warnings" if result.get("errors") else "completed"
                current.processed = int(result.get("records_found") or 0)
                current.total = current.processed
                current.result = result
            except Exception as exc:  # noqa: BLE001
                current = session.get(SyncJob, job_id)
                current.status = "failed"
                current.error_message = str(exc)[:1000]
            session.commit()

    background_tasks.add_task(runner, job.id)
    return job


@app.get("/api/jobs", response_model=list[JobOut])
def list_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    database: Session = Depends(get_db),
) -> list[SyncJob]:
    statement = select(SyncJob).order_by(SyncJob.created_at.desc()).limit(limit)
    return list(database.scalars(statement).all())


@app.post("/api/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, database: Session = Depends(get_db)) -> SyncJob:
    job = database.get(SyncJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    if job.status in {"completed", "completed_with_warnings", "failed", "cancelled"}:
        return job
    job.status = "cancelling"
    database.commit()
    database.refresh(job)
    return job



@app.post("/api/jobs/{job_id}/resume", response_model=JobOut, status_code=202)
def resume_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    database: Session = Depends(get_db),
) -> SyncJob:
    original = database.get(SyncJob, job_id)
    if not original:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    failed_queries = list((original.result or {}).get("failed_queries") or [])
    if not failed_queries:
        raise HTTPException(status_code=400, detail="Esta sincronização não possui consultas pendentes")
    payload = dict(original.payload or {})
    payload["retry_queries"] = failed_queries
    resumed = SyncJob(
        job_type="pncp_sync_resume",
        payload=payload,
        result={
            "resumed_from": original.id,
            "progress": {
                "phase": "queued",
                "percent": 0,
                "message": f"Retomando {len(failed_queries)} consulta(s) pendente(s)",
            },
        },
    )
    database.add(resumed)
    database.commit()
    database.refresh(resumed)
    background_tasks.add_task(run_pncp_sync_job, resumed.id, payload)
    return resumed

@app.get("/api/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, database: Session = Depends(get_db)) -> SyncJob:
    job = database.get(SyncJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return job


@app.post("/api/upload", response_model=UploadResponse)
def upload_edital(
    title: Annotated[str, Form(min_length=2, max_length=500)],
    file: Annotated[UploadFile, File()],
    database: Session = Depends(get_db),
) -> UploadResponse:
    try:
        data = file.file.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            raise ValueError(f"Arquivo excede o limite de {settings.max_upload_mb} MB")
        edital, documents, chunks = ingest_uploaded_file(
            database=database,
            title=title,
            data=data,
            filename=file.filename or "documento.pdf",
            mime_type=file.content_type,
        )
        return UploadResponse(
            edital=EditalOut.model_validate(edital),
            documents_indexed=documents,
            chunks_created=chunks,
        )
    except (ValueError, AIConfigurationError) as exc:
        database.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        database.rollback()
        raise HTTPException(status_code=500, detail=f"Falha ao processar o documento: {exc}") from exc
    finally:
        file.file.close()



@app.get("/api/editais/{edital_id}/documents")
def list_workspace_documents(edital_id: str, database: Session = Depends(get_db)) -> list[dict[str, object]]:
    if not database.get(Edital, edital_id):
        raise HTTPException(status_code=404, detail="Edital não encontrado")
    docs = list(database.scalars(select(Document).where(Document.edital_id == edital_id).order_by(Document.created_at.desc())).all())
    return [{
        "id": doc.id, "title": doc.title, "document_type": doc.document_type,
        "mime_type": doc.mime_type, "status": doc.status, "created_at": doc.created_at,
        "download_url": f"/api/documents/{doc.id}/file" if doc.local_path else None,
        "error_message": doc.error_message,
    } for doc in docs if not (doc.external_key or "").startswith("metadata:")]


@app.post("/api/editais/{edital_id}/documents")
def upload_workspace_document(
    edital_id: str,
    file: Annotated[UploadFile, File()],
    category: Annotated[str, Form()] = "Documento da concorrência",
    database: Session = Depends(get_db),
) -> dict[str, object]:
    edital = database.get(Edital, edital_id)
    if not edital:
        raise HTTPException(status_code=404, detail="Edital não encontrado")
    try:
        data = file.file.read(settings.max_upload_bytes + 1)
        documents, chunks = ingest_file_into_edital(database, edital, data, file.filename or "documento.pdf", file.content_type, category)
        database.add(BidPipelineEvent(edital=edital, event_type="document_uploaded", from_stage=edital.pipeline_stage, to_stage=edital.pipeline_stage, description=f"Documento enviado: {file.filename or 'documento'}", details={"category": category, "documents": len(documents), "chunks": chunks}))
        database.commit()
        return {"documents": len(documents), "chunks_created": chunks}
    except (ValueError, AIConfigurationError) as exc:
        database.rollback(); raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        file.file.close()

@app.post("/api/ask", response_model=AskResponse)
def ask(payload: AskRequest, database: Session = Depends(get_db)) -> AskResponse:
    try:
        return answer_question(database, payload)
    except (ValueError, AIConfigurationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Falha ao analisar os editais: {exc}") from exc


@app.get("/api/documents/{document_id}/file")
def get_document_file(document_id: str, database: Session = Depends(get_db)) -> FileResponse:
    document = database.get(Document, document_id)
    if not document or not document.local_path:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    path = Path(document.local_path).resolve()
    data_root = settings.data_dir.resolve()
    if data_root not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    return FileResponse(path, media_type=document.mime_type, filename=path.name.split("_", 1)[-1])
