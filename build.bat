@echo off
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ============================================
echo  AutoTrigger V10 - Build .EXE
echo ============================================
echo.

REM -- Le a versao direto do version.py ------------------------------------
for /f "tokens=*" %%i in ('python -c "from version import __version__; print(__version__)"') do set APP_VERSION=%%i
echo Versao detectada: v%APP_VERSION%
echo.

REM -- Localiza a instalacao do VLC (para embutir libVLC) ------------------
REM  Pode sobrescrever definindo VLC_DIR antes de chamar este script.
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

REM -- Gera icone atualizado ----------------------------------------------
echo [1/4] Gerando icone...
python create_icon.py
if %ERRORLEVEL% NEQ 0 echo AVISO: Falha ao gerar icone -- usando icone existente.

REM -- Dependencias -------------------------------------------------------
echo [2/4] Instalando dependencias...
pip install -r requirements.txt --quiet
if %ERRORLEVEL% NEQ 0 (
    echo ERRO ao instalar dependencias.
    pause
    exit /b 1
)

REM -- Build --------------------------------------------------------------
echo.
echo [3/4] Compilando AutoTriggerV10.exe v%APP_VERSION%...
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
  main.py

if %ERRORLEVEL% NEQ 0 (
    echo ERRO durante a compilacao.
    pause
    exit /b 1
)

REM -- Renomear com versao ------------------------------------------------
echo.
echo [4/4] Preparando release...
if exist "dist\AutoTriggerV10_v%APP_VERSION%.exe" del "dist\AutoTriggerV10_v%APP_VERSION%.exe"
copy "dist\AutoTriggerV10.exe" "dist\AutoTriggerV10_v%APP_VERSION%.exe" >NUL
echo Executavel versionado: dist\AutoTriggerV10_v%APP_VERSION%.exe

REM -- Publicar no GitHub Releases ----------------------------------------
echo.
echo Publicando GitHub Release v%APP_VERSION%...
where gh >NUL 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo AVISO: GitHub CLI ^(gh^) nao encontrado. Publique manualmente.
    goto :done
)

git tag "v%APP_VERSION%" 2>NUL

gh release create "v%APP_VERSION%" ^
  "dist\AutoTriggerV10.exe#AutoTriggerV10.exe" ^
  --title "v%APP_VERSION%" ^
  --generate-notes 2>NUL

if exist "dist\AutoTriggerV10_Setup_v%APP_VERSION%.exe" (
    gh release upload "v%APP_VERSION%" ^
      "dist\AutoTriggerV10_Setup_v%APP_VERSION%.exe#AutoTriggerV10_Setup_v%APP_VERSION%.exe" ^
      --clobber
    echo Instalador adicionado ao release.
)

:done
echo.
echo ============================================
echo  Build concluido: dist\AutoTriggerV10.exe
echo  Versao: v%APP_VERSION%
echo ============================================
echo.
pause
