@echo off
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ============================================================
echo  AutoTrigger V10 -- Build Instalador Local (sem publicar)
echo ============================================================
echo.
echo  Gera o .exe e o instalador para teste local. Para publicar
echo  no GitHub Releases tambem, use build.bat.
echo.

REM -- Le a versao direto do version.py ------------------------------------
for /f "tokens=*" %%i in ('python -c "from version import __version__; print(__version__)"') do set APP_VERSION=%%i
echo Versao: v%APP_VERSION%
echo.

REM -- Localiza a instalacao do VLC (para embutir libVLC) ------------------
if "%VLC_DIR%"=="" set "VLC_DIR=C:\Program Files\VideoLAN\VLC"
if not exist "%VLC_DIR%\libvlc.dll" set "VLC_DIR=C:\Program Files (x86)\VideoLAN\VLC"

set "VLC_ARGS="
if exist "%VLC_DIR%\libvlc.dll" (
    echo VLC encontrado em: %VLC_DIR%  -- sera embutido no .exe.
    set VLC_ARGS=--add-binary "%VLC_DIR%\libvlc.dll;." --add-binary "%VLC_DIR%\libvlccore.dll;." --add-data "%VLC_DIR%\plugins;plugins"
) else (
    echo AVISO: VLC nao encontrado. O .exe sera gerado SEM libVLC embutido.
    echo        Instale o VLC 64-bit ou defina VLC_DIR para embutir.
)
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

REM ── Passo 3: Sincronizar version_info.txt ────────────────────────────────
echo [3/5] Sincronizando version_info.txt (v%APP_VERSION%)...
python -c "
import re
with open('version_info.txt', 'r', encoding='utf-8') as f:
    content = f.read()
v = '%APP_VERSION%'
parts = (v.split('.') + ['0', '0', '0'])[:4]
filevers = ','.join(parts)
content = re.sub(r'filevers=\([^)]+\)', f'filevers=({filevers})', content)
content = re.sub(r'prodvers=\([^)]+\)', f'prodvers=({filevers})', content)
content = re.sub(r\"'FileVersion',(\s*)u'[^']+'\", lambda m: f\"'FileVersion',{m.group(1)}u'{v}.0'\", content)
content = re.sub(r\"'ProductVersion',(\s*)u'[^']+'\", lambda m: f\"'ProductVersion',{m.group(1)}u'{v}'\", content)
with open('version_info.txt', 'w', encoding='utf-8') as f:
    f.write(content)
print('version_info.txt atualizado.')
"
echo.

REM ── Passo 4: Compilar .exe com PyInstaller ───────────────────────────────
echo [4/5] Compilando AutoTriggerV10.exe com PyInstaller...
echo (Isso pode levar alguns minutos)
echo.

python -m PyInstaller ^
  --onefile ^
  --windowed ^
  --name "AutoTriggerV10" ^
  --icon "assets\icon.ico" ^
  --version-file "version_info.txt" ^
  --add-data "config.json;." ^
  --add-data "assets;assets" ^
  %VLC_ARGS% ^
  --hidden-import "pycaw" ^
  --hidden-import "comtypes.stream" ^
  --hidden-import "watchdog.observers.winapi" ^
  --hidden-import "requests" ^
  --hidden-import "win32gui" ^
  --hidden-import "win32con" ^
  --hidden-import "PySide6.QtSvg" ^
  --exclude-module "PySide6.QtQml" ^
  --exclude-module "PySide6.QtQuick" ^
  --exclude-module "PySide6.QtQuick3D" ^
  --exclude-module "PySide6.Qt3DCore" ^
  --exclude-module "PySide6.QtWebEngineCore" ^
  --exclude-module "PySide6.QtWebEngineWidgets" ^
  --exclude-module "PySide6.QtMultimedia" ^
  --exclude-module "PySide6.QtMultimediaWidgets" ^
  --exclude-module "PySide6.QtCharts" ^
  --exclude-module "PySide6.QtDataVisualization" ^
  --exclude-module "PySide6.QtPdf" ^
  --exclude-module "PySide6.QtPositioning" ^
  --exclude-module "PySide6.QtBluetooth" ^
  --exclude-module "PySide6.QtSql" ^
  --exclude-module "PySide6.QtTest" ^
  --exclude-module "tkinter" ^
  --exclude-module "customtkinter" ^
  --exclude-module "pystray" ^
  --noconfirm ^
  main.py

if %ERRORLEVEL% NEQ 0 (
    echo ERRO durante a compilacao com PyInstaller.
    pause & exit /b 1
)
echo.

REM ── Passo 5: Compilar instalador com Inno Setup ──────────────────────────
set ISCC=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"

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
    pause
    exit /b 0
)

echo [5/5] Gerando instalador com Inno Setup...
echo.
"%ISCC%" "installer.iss"

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
