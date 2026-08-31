@echo off
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ============================================
echo  AutoTrigger V10 - Build .EXE + Instalador + Release
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

REM -- Gera icone e assets do instalador ------------------------------------
echo [1/6] Gerando icone e imagens do instalador...
python create_icon.py
if %ERRORLEVEL% NEQ 0 echo AVISO: Falha ao gerar icone -- usando icone existente.
python create_wizard_assets.py
if %ERRORLEVEL% NEQ 0 echo AVISO: Falha ao gerar assets do wizard -- usando existentes.

REM -- Dependencias -------------------------------------------------------
echo.
echo [2/6] Instalando dependencias...
pip install -r requirements.txt --quiet
if %ERRORLEVEL% NEQ 0 (
    echo ERRO ao instalar dependencias.
    pause
    exit /b 1
)

REM -- Sincroniza version_info.txt com version.py --------------------------
echo.
echo [3/6] Sincronizando version_info.txt (v%APP_VERSION%)...
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

REM -- Build .exe -----------------------------------------------------------
echo.
echo [4/6] Compilando AutoTriggerV10.exe v%APP_VERSION%...
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
  --hidden-import "PySide6.QtNetwork" ^
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
    echo ERRO durante a compilacao.
    pause
    exit /b 1
)

REM -- Instalador (Inno Setup) -----------------------------------------------
echo.
echo [5/6] Gerando instalador com Inno Setup...
set ISCC=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
    echo AVISO: Inno Setup 6 nao encontrado ^(https://jrsoftware.org/isdl.php^).
    echo        Pulando geracao do instalador -- so o .exe sera publicado.
) else (
    "%ISCC%" "installer.iss"
    if %ERRORLEVEL% NEQ 0 (
        echo ERRO durante a geracao do instalador com Inno Setup.
        pause
        exit /b 1
    )
    echo Instalador: dist\AutoTriggerV10_Setup_v%APP_VERSION%.exe
)

REM -- Publicar no GitHub Releases ----------------------------------------
echo.
echo [6/6] Publicando GitHub Release v%APP_VERSION%...
where gh >NUL 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo AVISO: GitHub CLI ^(gh^) nao encontrado. Publique manualmente.
    goto :done
)

git tag "v%APP_VERSION%" 2>NUL
git push origin "v%APP_VERSION%" 2>NUL

gh release create "v%APP_VERSION%" ^
  "dist\AutoTriggerV10.exe#AutoTriggerV10.exe" ^
  --title "v%APP_VERSION%" ^
  --notes-file RELEASE_NOTES.md 2>NUL

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
