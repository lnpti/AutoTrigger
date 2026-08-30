@echo off
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ============================================================
echo  AutoTrigger V10 -- Build Instalador Completo
echo ============================================================
echo.

REM ── Lê versão ────────────────────────────────────────────────────────────
for /f "tokens=*" %%i in ('python -c "from version import __version__; print(__version__)"') do set APP_VERSION=%%i
echo Versao: v%APP_VERSION%
echo.

REM ── Passo 1: Gerar ícone e assets do wizard ──────────────────────────────
echo [1/5] Gerando icone e imagens do instalador...
python create_icon.py
if %ERRORLEVEL% NEQ 0 (echo ERRO ao gerar icone. & pause & exit /b 1)
python create_wizard_assets.py
if %ERRORLEVEL% NEQ 0 (echo ERRO ao gerar assets do wizard. & pause & exit /b 1)
echo.

REM ── Passo 2: Instalar dependências ───────────────────────────────────────
echo [2/5] Instalando dependencias Python...
pip install -r requirements.txt --quiet
if %ERRORLEVEL% NEQ 0 (echo ERRO ao instalar dependencias. & pause & exit /b 1)
echo.

REM ── Passo 3: Compilar .exe com PyInstaller ───────────────────────────────
echo [3/5] Compilando AutoTriggerV10.exe com PyInstaller...
echo (Isso pode levar alguns minutos)
echo.

REM Localiza o PyInstaller
set PYINSTALLER=%APPDATA%\Python\Python311\Scripts\pyinstaller.exe
if not exist "%PYINSTALLER%" (
    set PYINSTALLER=%LOCALAPPDATA%\Programs\Python\Python311\Scripts\pyinstaller.exe
)
if not exist "%PYINSTALLER%" (
    where pyinstaller >NUL 2>&1
    if %ERRORLEVEL% EQU 0 (set PYINSTALLER=pyinstaller) else (
        echo ERRO: PyInstaller nao encontrado.
        echo Execute: pip install pyinstaller
        pause & exit /b 1
    )
)

"%PYINSTALLER%" ^
  --onefile ^
  --windowed ^
  --name "AutoTriggerV10" ^
  --icon "assets\icon.ico" ^
  --version-file "version_info.txt" ^
  --add-data "config.json;." ^
  --add-data "assets;assets" ^
  --hidden-import "pycaw" ^
  --hidden-import "comtypes.stream" ^
  --hidden-import "watchdog.observers.winapi" ^
  --hidden-import "customtkinter" ^
  --hidden-import "requests" ^
  --collect-all "customtkinter" ^
  --collect-all "pystray" ^
  --noconfirm ^
  main.py

if %ERRORLEVEL% NEQ 0 (
    echo ERRO durante a compilacao com PyInstaller.
    pause & exit /b 1
)
echo.

REM ── Passo 4: Encontrar Inno Setup ────────────────────────────────────────
set ISCC=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
)
if "%ISCC%"=="" (
    echo.
    echo ============================================================
    echo  ATENCAO: Inno Setup 6 nao encontrado!
    echo ============================================================
    echo.
    echo Para gerar o instalador .exe:
    echo  1. Baixe o Inno Setup 6 em: https://jrsoftware.org/isdl.php
    echo  2. Instale e execute este script novamente
    echo.
    echo O AutoTriggerV10.exe foi gerado em: dist\AutoTriggerV10.exe
    echo Voce pode distribuir esse .exe diretamente (requer VLC instalado).
    pause
    exit /b 0
)

REM ── Passo 5: Compilar instalador com Inno Setup ──────────────────────────
echo [5/5] Gerando instalador com Inno Setup...
echo.

REM Atualiza a versão no version_info.txt
python -c "
import re, sys
with open('version_info.txt', 'r', encoding='utf-8') as f:
    content = f.read()
v = '%APP_VERSION%'
parts = v.split('.')
while len(parts) < 4:
    parts.append('0')
filevers = ','.join(parts)
content = re.sub(r'filevers=\([^)]+\)', f'filevers=({filevers})', content)
content = re.sub(r'prodvers=\([^)]+\)', f'prodvers=({filevers})', content)
content = re.sub(r\"'FileVersion',\s*u'[^']+'\", f\"'FileVersion', u'{v}.0'\", content)
content = re.sub(r\"'ProductVersion',\s*u'[^']+'\", f\"'ProductVersion', u'{v}'\", content)
with open('version_info.txt', 'w', encoding='utf-8') as f:
    f.write(content)
print('version_info.txt atualizado.')
"

"%ISCC%" /DAppVersion=%APP_VERSION% "installer.iss"

if %ERRORLEVEL% NEQ 0 (
    echo ERRO durante a geracao do instalador com Inno Setup.
    pause & exit /b 1
)

echo.
echo ============================================================
echo  BUILD CONCLUIDO COM SUCESSO!
echo.
echo  Instalador: dist\AutoTriggerV10_Setup_v%APP_VERSION%.exe
echo  Executavel: dist\AutoTriggerV10.exe
echo ============================================================
echo.
echo Para publicar no GitHub Releases, execute build.bat
echo.
pause
