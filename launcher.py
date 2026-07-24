from __future__ import annotations

import argparse
import base64
import ctypes
import json
import logging
import os
import secrets
import shutil
import subprocess
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

# Quando o launcher e executado diretamente (python desktop\launcher.py),
# o Python adiciona apenas a pasta desktop ao sys.path. Incluimos a raiz do
# projeto explicitamente para que o pacote app seja localizado no Windows.
PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if sys.platform == "win32":
    from ctypes import wintypes

APP_VERSION = "0.17.2-desktop-beta"
APP_NAME = "Hórus Connective Licitações"


def user_data_root() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    root = base / "Anubis" / "HORUS_CONNECTIVE"
    legacy_root = base / "Anubis" / "ALFRED"
    if not root.exists() and legacy_root.exists():
        try:
            shutil.copytree(legacy_root, root, dirs_exist_ok=True)
        except OSError:
            root.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def default_config() -> dict[str, Any]:
    return {
        "version": 2,
        "display_name": "Henrique",
        "admin_username": "henrique",
        "admin_password_protected": protect_secret("horus123"),
        "ai_mode": "local",
        "openai_api_key_protected": "",
        "secret_key": secrets.token_urlsafe(48),
    }


def protect_secret(value: str) -> str:
    if not value:
        return ""
    raw = value.encode("utf-8")
    if sys.platform != "win32":
        return "plain:" + base64.urlsafe_b64encode(raw).decode("ascii")

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    buffer = ctypes.create_string_buffer(raw)
    input_blob = DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    output_blob = DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(input_blob), None, None, None, None, 0, ctypes.byref(output_blob)
    ):
        raise ctypes.WinError()
    try:
        encrypted = ctypes.string_at(output_blob.pbData, output_blob.cbData)
        return "dpapi:" + base64.urlsafe_b64encode(encrypted).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


def unprotect_secret(value: str) -> str:
    if not value:
        return ""
    if value.startswith("plain:"):
        return base64.urlsafe_b64decode(value[6:].encode("ascii")).decode("utf-8")
    if not value.startswith("dpapi:"):
        return value  # Compatibilidade com configuracoes Beta antigas.
    if sys.platform != "win32":
        return ""

    encrypted = base64.urlsafe_b64decode(value[6:].encode("ascii"))

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    buffer = ctypes.create_string_buffer(encrypted)
    input_blob = DataBlob(len(encrypted), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    output_blob = DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(input_blob), None, None, None, None, 0, ctypes.byref(output_blob)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(output_blob.pbData)


def config_path(root: Path) -> Path:
    return root / "desktop_settings.json"


def load_config(root: Path) -> dict[str, Any]:
    path = config_path(root)
    if not path.exists():
        config = default_config()
        save_config(root, config)
        return config
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = default_config()
    if "openai_api_key" in data and "openai_api_key_protected" not in data:
        data["openai_api_key_protected"] = protect_secret(str(data.pop("openai_api_key") or ""))
    defaults = default_config()
    defaults.update({key: value for key, value in data.items() if key in defaults})
    defaults["version"] = 2
    if not defaults.get("secret_key"):
        defaults["secret_key"] = secrets.token_urlsafe(48)
    if not defaults.get("admin_username"):
        defaults["admin_username"] = "henrique"
    if not defaults.get("admin_password_protected"):
        defaults["admin_password_protected"] = protect_secret("horus123")
    save_config(root, defaults)
    return defaults


def save_config(root: Path, config: dict[str, Any]) -> None:
    path = config_path(root)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        os.system(f'open "{path}"')
    else:
        os.system(f'xdg-open "{path}" >/dev/null 2>&1 &')


def backup_data(root: Path) -> Path:
    backup_dir = Path.home() / "Documents" / "Hórus Connective Backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target = backup_dir / f"HORUS_Connective_Backup_{timestamp}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        database = root / "horus_connective.db"
        if database.exists():
            archive.write(database, "horus_connective.db")
        documents = root / "documents"
        if documents.exists():
            for item in documents.rglob("*"):
                if item.is_file():
                    archive.write(item, Path("documents") / item.relative_to(documents))
        manifest = {
            "application": APP_NAME,
            "version": APP_VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "note": "O banco local é incluído no backup; segredos permanecem protegidos pelo perfil do Windows.",
        }
        archive.writestr("backup_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return target


def show_message(title: str, message: str, error: bool = False) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        (messagebox.showerror if error else messagebox.showinfo)(title, message, parent=root)
        root.destroy()
    except Exception:
        print(f"{title}: {message}", file=sys.stderr if error else sys.stdout)


def settings_dialog(root: Path) -> bool:
    import tkinter as tk
    from tkinter import messagebox, ttk

    current = load_config(root)
    changed = False

    window = tk.Tk()
    window.title("Configurações do Hórus Connective")
    window.geometry("610x680")
    window.minsize(570, 640)
    try:
        window.iconbitmap(str(PROJECT_ROOT / "desktop" / "assets" / "horus.ico"))
    except Exception:
        pass

    canvas = tk.Canvas(window, highlightthickness=0)
    scrollbar = ttk.Scrollbar(window, orient="vertical", command=canvas.yview)
    frame = ttk.Frame(canvas, padding=24)
    frame.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    ttk.Label(frame, text="Hórus Connective", font=("Segoe UI", 18, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text="Configurações locais e inteligência deste computador. Usuários e permissões são gerenciados dentro do sistema.",
        wraplength=530,
    ).pack(anchor="w", pady=(4, 18))

    ttk.Label(frame, text="PERFIL", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 8))
    ttk.Label(frame, text="Nome exibido").pack(anchor="w")
    name_var = tk.StringVar(value=str(current.get("display_name", "Henrique")))
    ttk.Entry(frame, textvariable=name_var).pack(fill="x", pady=(4, 14))

    ttk.Separator(frame).pack(fill="x", pady=(2, 16))
    ttk.Label(frame, text="USUÁRIOS E PERMISSÕES", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 8))
    ttk.Label(
        frame,
        text="Contas, senhas, setores, telefones/VoIP e permissões de módulos são gerenciados pelo administrador dentro do Hórus Connective.",
        wraplength=530,
    ).pack(anchor="w", pady=(0, 16))
    username_var = tk.StringVar(value=str(current.get("admin_username", "henrique")))
    password_var = tk.StringVar()
    password_confirm_var = tk.StringVar()

    ttk.Separator(frame).pack(fill="x", pady=(2, 16))
    ttk.Label(frame, text="INTELIGÊNCIA ARTIFICIAL", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 8))
    ttk.Label(frame, text="Modo de inteligência").pack(anchor="w")
    mode_var = tk.StringVar(value=str(current.get("ai_mode", "local")))
    mode = ttk.Combobox(frame, textvariable=mode_var, values=("local", "auto", "openai"), state="readonly")
    mode.pack(fill="x", pady=(4, 12))

    ttk.Label(frame, text="Chave da API OpenAI (opcional)").pack(anchor="w")
    key_var = tk.StringVar(value=unprotect_secret(str(current.get("openai_api_key_protected", ""))))
    ttk.Entry(frame, textvariable=key_var, show="•").pack(fill="x", pady=(4, 6))
    ttk.Label(
        frame,
        text="No modo local, o Hórus Connective funciona sem chave. O modo auto usa a API quando uma chave estiver cadastrada.",
        wraplength=530,
    ).pack(anchor="w", pady=(0, 18))

    actions = ttk.Frame(frame)
    actions.pack(fill="x", pady=(8, 4))

    def save() -> None:
        nonlocal changed
        selected_mode = mode_var.get().strip().lower()
        username = username_var.get().strip().lower()
        new_password = password_var.get()
        confirmation = password_confirm_var.get()
        if len(username) < 3:
            messagebox.showerror("Usuário inválido", "Informe um usuário com ao menos 3 caracteres.", parent=window)
            return
        if new_password or confirmation:
            if len(new_password) < 6:
                messagebox.showerror("Senha inválida", "A nova senha deve ter ao menos 6 caracteres.", parent=window)
                return
            if new_password != confirmation:
                messagebox.showerror("Senha inválida", "A confirmação da senha não confere.", parent=window)
                return
        if selected_mode not in {"local", "auto", "openai"}:
            messagebox.showerror("Configuração inválida", "Selecione local, auto ou openai.", parent=window)
            return
        if selected_mode == "openai" and not key_var.get().strip():
            messagebox.showerror("Chave necessária", "Informe a chave da API para usar o modo openai.", parent=window)
            return
        current["display_name"] = name_var.get().strip() or "Henrique"
        current["admin_username"] = username
        if new_password:
            current["admin_password_protected"] = protect_secret(new_password)
        current["ai_mode"] = selected_mode
        current["openai_api_key_protected"] = protect_secret(key_var.get().strip())
        current["version"] = 2
        save_config(root, current)
        changed = True
        messagebox.showinfo("Configurações salvas", "Reinicie o Hórus Connective para aplicar as alterações.", parent=window)
        window.destroy()

    def create_backup() -> None:
        try:
            path = backup_data(root)
            messagebox.showinfo("Backup concluído", f"Backup criado em:\n{path}", parent=window)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Falha no backup", str(exc), parent=window)

    ttk.Button(actions, text="Abrir pasta de dados", command=lambda: open_folder(root)).pack(side="left")
    ttk.Button(actions, text="Criar backup", command=create_backup).pack(side="left", padx=8)
    ttk.Button(actions, text="Cancelar", command=window.destroy).pack(side="right")
    ttk.Button(actions, text="Salvar", command=save).pack(side="right", padx=8)

    window.mainloop()
    return changed


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def configure_windowed_runtime(root: Path) -> None:
    """Prepare logging and standard streams for a PyInstaller windowed executable.

    Applications built with ``console=False`` can start with ``sys.stdout`` and
    ``sys.stderr`` set to ``None``. Uvicorn's default logging formatter probes
    ``sys.stderr.isatty()``, which crashes before the local server starts.
    """
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115

    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "horus-connective-desktop.log"
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8")],
        force=True,
    )


def configure_environment(root: Path, port: int) -> None:
    config = load_config(root)
    database = root / "horus_connective.db"
    legacy_database = root / "alfred.db"
    if not database.exists() and legacy_database.exists():
        shutil.copy2(legacy_database, database)
    documents = root / "documents"
    documents.mkdir(parents=True, exist_ok=True)

    values = {
        "APP_NAME": APP_NAME,
        "APP_VERSION": APP_VERSION,
        "ENVIRONMENT": "desktop",
        "DESKTOP_MODE": "true",
        "DATABASE_URL": f"sqlite+pysqlite:///{database.as_posix()}",
        "DATA_DIR": str(documents),
        "SECRET_KEY": str(config["secret_key"]),
        "ADMIN_DISPLAY_NAME": str(config.get("display_name", "Henrique")),
        "ADMIN_USERNAME": str(config.get("admin_username", "henrique")),
        "ADMIN_PASSWORD": unprotect_secret(str(config.get("admin_password_protected", ""))) or "horus123",
        "AI_MODE": str(config.get("ai_mode", "local")),
        "OPENAI_API_KEY": unprotect_secret(str(config.get("openai_api_key_protected", ""))),
        "AUTH_COOKIE_SECURE": "false",
        "TRUSTED_HOSTS": "127.0.0.1,localhost",
        "CORS_ORIGINS": f"http://127.0.0.1:{port}",
        "SCHEDULER_ENABLED": "false",
    }
    os.environ.update(values)


def wait_for_server(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=1.0) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"O núcleo local do Hórus Connective não iniciou no prazo esperado: {last_error}")


class DesktopApi:
    def __init__(self, root: Path) -> None:
        self.root = root

    def open_settings(self) -> dict[str, Any]:
        command = [sys.executable, "--config"] if getattr(sys, "frozen", False) else [
            sys.executable, str(Path(__file__).resolve()), "--config"
        ]
        subprocess.Popen(command, close_fds=True)
        return {"ok": True, "message": "Janela de configurações aberta."}

    def open_data_folder(self) -> dict[str, Any]:
        open_folder(self.root)
        return {"ok": True}

    def open_reports_folder(self) -> dict[str, Any]:
        reports = self.root / "documents" / "reports"
        open_folder(reports)
        return {"ok": True, "path": str(reports)}

    def open_saved_report(self, report_id: str) -> dict[str, Any]:
        try:
            from app.services.report_library import resolve_saved_report

            path = resolve_saved_report(self.root / "documents", report_id)
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                webbrowser.open(path.as_uri())
            return {"ok": True, "name": path.name}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    def create_backup(self) -> dict[str, Any]:
        try:
            path = backup_data(self.root)
            return {"ok": True, "path": str(path)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}


def run_self_test() -> int:
    """Valida os componentes essenciais sem abrir a interface."""
    root = user_data_root()
    configure_windowed_runtime(root)
    port = find_free_port()
    configure_environment(root, port)
    try:
        from app.db import init_db
        from app.main import app as _app

        init_db()
        if _app is None:
            raise RuntimeError("Aplicacao FastAPI indisponivel")
        logging.info("Self-test do Hórus Connective concluído com sucesso - versão %s", APP_VERSION)
        return 0
    except Exception:
        logging.exception("Falha no self-test do Hórus Connective Desktop")
        return 1


def run_monitor_once() -> int:
    """Executa o monitoramento diário sem abrir a janela do aplicativo."""
    root = user_data_root()
    configure_windowed_runtime(root)
    port = find_free_port()
    configure_environment(root, port)
    try:
        from app.db import init_db
        from app.services.monitoring import run_daily_monitor_job

        init_db()
        job_id = run_daily_monitor_job(require_enabled=True)
        if job_id:
            logging.info("Monitoramento diário concluído. Tarefa: %s", job_id)
        else:
            logging.info("Monitoramento diário ignorado porque está pausado no Hórus Connective.")
        return 0
    except Exception:
        logging.exception("Falha no monitoramento diário do Hórus Connective Desktop")
        return 1


def run_notifications_once() -> int:
    """Envia as notificações diárias sem abrir a janela do aplicativo."""
    root = user_data_root()
    configure_windowed_runtime(root)
    port = find_free_port()
    configure_environment(root, port)
    try:
        from app.db import init_db
        from app.services.notifications import run_daily_notifications

        init_db()
        result = run_daily_notifications(require_enabled=True)
        logging.info("Notificações diárias concluídas: %s", result)
        return 0
    except Exception:
        logging.exception("Falha no envio diário de notificações do Hórus Connective Desktop")
        return 1


def show_diagnostics() -> int:
    root = user_data_root()
    configure_windowed_runtime(root)
    details = [
        f"Hórus Connective: {APP_VERSION}",
        f"Sistema: {sys.platform}",
        f"Python: {sys.version.split()[0]}",
        f"Executavel: {sys.executable}",
        f"Modo compilado: {'sim' if getattr(sys, 'frozen', False) else 'nao'}",
        f"Pasta de dados: {root}",
        f"Banco local: {root / 'horus_connective.db'}",
        f"Log: {root / 'logs' / 'horus-connective-desktop.log'}",
    ]
    show_message("Diagnóstico do Hórus Connective", "\n".join(details))
    return 0


class StartupSplash:
    def __init__(self) -> None:
        self.window = None
        self.status = None
        self.progress = None
        try:
            import tkinter as tk
            from tkinter import ttk

            window = tk.Tk()
            window.overrideredirect(True)
            window.configure(bg="#F1ECE3")
            width, height = 620, 350
            x = max((window.winfo_screenwidth() - width) // 2, 0)
            y = max((window.winfo_screenheight() - height) // 2, 0)
            window.geometry(f"{width}x{height}+{x}+{y}")
            window.attributes("-topmost", True)

            panel = tk.Frame(window, bg="#F1ECE3", padx=44, pady=34)
            panel.pack(fill="both", expand=True)
            logo_path = PROJECT_ROOT / "app" / "static" / "img" / "horus-connective-logo-native.png"
            try:
                image = tk.PhotoImage(file=str(logo_path))
                max_width = 250
                factor = max(1, image.width() // max_width)
                image = image.subsample(factor, factor)
                logo = tk.Label(panel, image=image, bg="#F1ECE3")
                logo.image = image
                logo.pack(anchor="center")
            except Exception:
                tk.Label(panel, text="A", fg="#B89453", bg="#F1ECE3", font=("Georgia", 46, "bold")).pack()

            tk.Label(panel, text="FAMÍLIA CONNECTIVE", fg="#B89453", bg="#F1ECE3", font=("Segoe UI", 8, "bold")).pack(pady=(10, 20))

            style = ttk.Style(window)
            style.theme_use("clam")
            style.configure("Horus.Horizontal.TProgressbar", troughcolor="#E3D8C9", background="#315C78", bordercolor="#E3D8C9", lightcolor="#315C78", darkcolor="#315C78")
            progress = ttk.Progressbar(panel, style="Horus.Horizontal.TProgressbar", maximum=100, value=8, length=480)
            progress.pack(fill="x")
            status = tk.Label(panel, text="Preparando o Hórus Connective...", fg="#5D6D79", bg="#F1ECE3", font=("Segoe UI", 9))
            status.pack(pady=(12, 0))
            tk.Label(panel, text=f"Desktop Beta {APP_VERSION.split('-')[0]}", fg="#86796C", bg="#F1ECE3", font=("Segoe UI", 8)).pack(side="bottom", pady=(16, 0))
            window.update_idletasks()
            self.window = window
            self.status = status
            self.progress = progress
        except Exception:
            self.window = None

    def update(self, message: str, value: int) -> None:
        if not self.window:
            return
        try:
            self.status.configure(text=message)
            self.progress.configure(value=value)
            self.window.update_idletasks()
            self.window.update()
        except Exception:
            self.window = None

    def close(self) -> None:
        if not self.window:
            return
        try:
            self.progress.configure(value=100)
            self.status.configure(text="Hórus Connective pronto.")
            self.window.update_idletasks()
            self.window.update()
            time.sleep(0.25)
            self.window.destroy()
        except Exception:
            pass
        finally:
            self.window = None


def run_desktop(browser_only: bool = False) -> int:
    root = user_data_root()
    configure_windowed_runtime(root)
    splash = StartupSplash()
    splash.update("Carregando configurações locais...", 18)
    port = find_free_port()
    configure_environment(root, port)
    splash.update("Inicializando banco de dados e serviços...", 36)

    import uvicorn
    from app.main import app

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        server_header=False,
        log_config=None,
        use_colors=False,
    )
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, name="horus-local-server", daemon=True)
    server_thread.start()

    url = f"http://127.0.0.1:{port}"
    splash.update("Ativando o Hórus Core...", 62)
    try:
        wait_for_server(url)
    except Exception as exc:  # noqa: BLE001
        splash.close()
        show_message("Falha ao iniciar o Hórus Connective", str(exc), error=True)
        server.should_exit = True
        return 1

    splash.update("Preparando a tela de acesso...", 88)
    splash.close()
    try:
        if browser_only:
            webbrowser.open(url)
            while server_thread.is_alive():
                time.sleep(0.5)
        else:
            import webview

            api = DesktopApi(root)
            webview.create_window(
                APP_NAME,
                url=url,
                js_api=api,
                width=1440,
                height=900,
                min_size=(1100, 700),
                focus=True,
                easy_drag=False,
                draggable=False,
                confirm_close=False,
                text_select=True,
            )
            webview.start(debug=False, private_mode=True)
    except Exception as exc:  # noqa: BLE001
        webbrowser.open(url)
        show_message(
            "Hórus Connective aberto no navegador",
            "A janela desktop não pôde ser iniciada. O Hórus Connective foi aberto no navegador padrão.\n\n"
            f"Detalhes: {exc}",
            error=False,
        )
        try:
            while server_thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    finally:
        server.should_exit = True
        server_thread.join(timeout=5)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Hórus Connective Licitações Desktop")
    parser.add_argument("--config", action="store_true", help="Abrir apenas as configurações locais")
    parser.add_argument("--data-folder", action="store_true", help="Abrir a pasta de dados do Hórus Connective")
    parser.add_argument("--reports-folder", action="store_true", help="Abrir a pasta de relatórios do Hórus Connective")
    parser.add_argument("--backup", action="store_true", help="Criar um backup local do Hórus Connective")
    parser.add_argument("--browser", action="store_true", help="Abrir no navegador em modo de compatibilidade")
    parser.add_argument("--version", action="store_true", help="Exibir a versao instalada")
    parser.add_argument("--diagnostics", action="store_true", help="Exibir diagnostico local")
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--monitor-once", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--notify-once", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.version:
        show_message("Versão do Hórus Connective", APP_VERSION)
        return 0
    if args.self_test:
        return run_self_test()
    if args.monitor_once:
        return run_monitor_once()
    if args.notify_once:
        return run_notifications_once()
    if args.diagnostics:
        return show_diagnostics()

    root = user_data_root()
    if args.config:
        settings_dialog(root)
        return 0
    if args.data_folder:
        open_folder(root)
        return 0
    if args.reports_folder:
        open_folder(root / "documents" / "reports")
        return 0
    if args.backup:
        path = backup_data(root)
        show_message("Backup concluído", f"Backup criado em:\n{path}")
        return 0
    return run_desktop(browser_only=args.browser)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        try:
            root = user_data_root()
            configure_windowed_runtime(root)
            logging.exception("Falha não tratada ao iniciar o Hórus Connective Desktop")
        except Exception:
            pass
        show_message(
            "Falha ao iniciar o Hórus Connective",
            "O Hórus Connective encontrou um erro durante a inicialização. "
            "O diagnóstico foi salvo na pasta de logs.\n\n"
            f"Detalhes: {exc}",
            error=True,
        )
        raise SystemExit(1)
