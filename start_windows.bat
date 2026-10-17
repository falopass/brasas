@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo           BRASA CHILE - MVP
 echo ============================================
where py >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
  echo Se necesita Python 3.10 o superior instalado desde python.org
  pause
  exit /b 1
)
if not exist ".env" copy ".env.example" ".env" >nul
py -3 -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
  echo Error al instalar las dependencias. Revisa tu conexion.
  pause
  exit /b 1
)
start "" "http://127.0.0.1:8000"
py -3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
pause
