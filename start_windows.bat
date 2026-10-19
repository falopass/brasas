@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title BRASA Chile
echo ============================================
echo            BRASA CHILE  ·  v0.6
echo   Alertas de incendios por lugar (prototipo)
echo ============================================
echo.

where py >nul 2>&1
if errorlevel 1 (
  echo Se necesita Python 3.12 o superior: https://www.python.org/downloads/
  echo Durante la instalacion marca "Add python.exe to PATH" y el lanzador "py".
  pause
  exit /b 1
)
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
if errorlevel 1 (
  echo Tu Python es anterior a 3.12. Instala una version mas reciente.
  pause
  exit /b 1
)

if not exist ".env" copy ".env.example" ".env" >nul

if not exist ".venv\Scripts\python.exe" (
  echo Creando entorno de Python en .venv ...
  py -3 -m venv .venv
  if errorlevel 1 ( echo No se pudo crear el entorno. & pause & exit /b 1 )
)
set "PY=.venv\Scripts\python.exe"

rem Reinstala dependencias solo si requirements.txt cambio desde la ultima vez.
set "REQHASH="
for /f "delims=" %%h in ('certutil -hashfile requirements.txt SHA256 ^| findstr /v ":"') do if not defined REQHASH set "REQHASH=%%h"
set "OLDHASH="
if exist ".venv\requirements.sha" set /p OLDHASH=<".venv\requirements.sha"
if not "%REQHASH%"=="%OLDHASH%" (
  echo Instalando dependencias ^(la primera vez tarda unos minutos y requiere internet^)...
  "%PY%" -m pip install --disable-pip-version-check -q -r requirements.txt
  if errorlevel 1 ( echo Error al instalar las dependencias. Revisa tu conexion. & pause & exit /b 1 )
  > ".venv\requirements.sha" echo %REQHASH%
)

set "PORT=8000"
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo El puerto 8000 esta ocupado; se usara el 8001.
  set "PORT=8001"
)

echo.
echo Abriendo http://127.0.0.1:%PORT% cuando el servidor este listo...
echo Manten esta ventana abierta. Para cerrar BRASA, cierra la ventana o presiona Ctrl+C.
echo.
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 90;$i++){try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:%PORT%/api/health | Out-Null; Start-Process 'http://127.0.0.1:%PORT%'; break}catch{Start-Sleep -Milliseconds 700}}"
"%PY%" -m uvicorn backend.main:app --host 127.0.0.1 --port %PORT%
pause
