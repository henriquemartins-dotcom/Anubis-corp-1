@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "VERSION=0.16.0"
set "OUTPUT=installer-output\HORUS_Connective_Setup_0.16.0_Desktop_Beta.exe"
set "HASHFILE=installer-output\HORUS_Connective_Setup_0.16.0_Desktop_Beta.sha256"
set "LOG_DIR=%LOCALAPPDATA%\Anubis\HORUS_CONNECTIVE\logs"
set "LOG_FILE=%LOG_DIR%\build-installer-0.16.0.log"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

call :log "Inicio da compilacao do instalador HORUS CONNECTIVE %VERSION%"
echo ==============================================================
echo       HORUS CONNECTIVE DESKTOP BETA 0.16.0 - INSTALADOR OFICIAL
echo ==============================================================
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher nao encontrado.
  echo Instale o Python 3.12 x64 em https://www.python.org/downloads/
  call :log "ERRO: Python Launcher nao encontrado"
  pause
  exit /b 1
)

set "PYTHON_CMD=py -3.12"
%PYTHON_CMD% --version >nul 2>nul
if errorlevel 1 set "PYTHON_CMD=py -3"
%PYTHON_CMD% --version >nul 2>nul
if errorlevel 1 (
  echo Nao foi encontrada uma instalacao compativel do Python.
  call :log "ERRO: Python compativel nao encontrado"
  pause
  exit /b 1
)

if not exist .venv-installer (
  echo [1/7] Criando ambiente de compilacao...
  call :log "Criando .venv-installer"
  %PYTHON_CMD% -m venv .venv-installer >> "%LOG_FILE%" 2>&1
  if errorlevel 1 goto :error
) else (
  echo [1/7] Ambiente de compilacao encontrado.
)

call .venv-installer\Scripts\activate.bat

echo [2/7] Atualizando ferramentas...
python -m pip install --upgrade pip wheel >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :error

echo [3/7] Instalando dependencias...
pip install -r requirements-desktop.txt >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :error

set "DATABASE_URL=sqlite+pysqlite:///%TEMP%/horus_installer_test.db"
set "DATA_DIR=%TEMP%\horus_installer_data"
set "DESKTOP_MODE=true"
set "ENVIRONMENT=desktop"
set "AI_MODE=local"

echo [4/7] Executando testes automatizados...
python -m pytest -q >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :error

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist installer-output rmdir /s /q installer-output

echo [5/7] Validando ambiente grafico e compilando HORUS_CONNECTIVE.exe...
python -c "import webview, clr, clr_loader; print('pywebview/pythonnet OK')" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  call :log "ERRO: pywebview/pythonnet nao carregou. Recriando ambiente na proxima tentativa."
  goto :error
)
pyinstaller --noconfirm --clean --log-level INFO desktop\HORUS_CONNECTIVE.spec >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :error
if not exist "dist\HORUS_CONNECTIVE\HORUS_CONNECTIVE.exe" (
  call :log "ERRO: dist\HORUS_CONNECTIVE\HORUS_CONNECTIVE.exe nao foi criado"
  goto :error
)

echo [6/7] Validando o executavel compilado...
"dist\HORUS_CONNECTIVE\HORUS_CONNECTIVE.exe" --self-test >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto :error

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Inno Setup 6 nao encontrado. Tentando instalar automaticamente...
  where winget >nul 2>nul
  if errorlevel 1 (
    echo O Inno Setup precisa ser instalado para gerar o Setup.exe.
    echo Baixe em https://jrsoftware.org/isdl.php
    call :log "ERRO: Inno Setup e winget indisponiveis"
    pause
    exit /b 1
  )
  winget install --id JRSoftware.InnoSetup -e --silent --accept-package-agreements --accept-source-agreements >> "%LOG_FILE%" 2>&1
  if errorlevel 1 goto :error
  set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  if not exist "!ISCC!" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
)
if not exist "%ISCC%" (
  call :log "ERRO: ISCC.exe nao encontrado apos instalacao"
  goto :error
)

echo [7/7] Gerando o instalador oficial...
"%ISCC%" desktop\installer\HORUS_CONNECTIVE.iss >> "%LOG_FILE%" 2>&1
set "ISCC_EXIT=!errorlevel!"
if not "!ISCC_EXIT!"=="0" goto :error
for /l %%W in (1,1,10) do (
  if exist "%OUTPUT%" goto :installer_ready
  timeout /t 1 /nobreak >nul
)
goto :error

:installer_ready

for /f "tokens=*" %%H in ('powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 ''%OUTPUT%'').Hash.ToLower()"') do set "HASH=%%H"
> "%HASHFILE%" echo !HASH!  HORUS_Connective_Setup_0.16.0_Desktop_Beta.exe

call :log "SUCESSO: instalador criado em %OUTPUT%"
echo.
echo ==============================================================
echo INSTALADOR CRIADO COM SUCESSO
echo.
echo Arquivo: %OUTPUT%
echo Hash:    %HASHFILE%
echo Log:     %LOG_FILE%
echo ==============================================================
start "" explorer.exe "%CD%\installer-output"
pause
exit /b 0

:error
call :log "ERRO: falha durante a compilacao. Codigo !errorlevel!"
echo.
echo A compilacao falhou. Consulte o log:
echo %LOG_FILE%
pause
exit /b 1

:log
>> "%LOG_FILE%" echo [%date% %time%] %~1
exit /b 0
