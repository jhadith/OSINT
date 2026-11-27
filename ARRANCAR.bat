@echo off
chcp 65001 >nul
title Sentinel Salud
cd /d "%~dp0"

rem El .venv del proyecto es de Linux (tiene bin\ en vez de Scripts\) y no sirve en Windows.
rem Este script usa su propio entorno .venv-win y no toca el otro.
if not exist ".venv-win\Scripts\python.exe" (
  echo Creando el entorno de Python para Windows. Solo la primera vez, tarda unos minutos...
  py -3 -m venv .venv-win 2>nul || python -m venv .venv-win
  if not exist ".venv-win\Scripts\python.exe" (
    echo.
    echo No se encontro Python. Instala Python 3.11 o superior desde python.org
    echo y marca "Add python.exe to PATH" durante la instalacion.
    pause
    exit /b 1
  )
)

rem Para usar PostgreSQL, quita "rem" de la línea siguiente y pon tu clave:
rem set SENTINEL_DB_URL=postgresql://postgres:TU_CLAVE@localhost:5432/sentinel

echo Revisando dependencias...
".venv-win\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r backend\requirements.txt
if errorlevel 1 (
  echo.
  echo Fallo la instalacion de dependencias. Revisa tu conexion a internet y vuelve a intentar.
  pause
  exit /b 1
)

if not exist "web\dist\index.html" (
  echo Falta la consola compilada en web\dist. Ejecuta en la carpeta web:  npm install  y luego  npm run build
  pause
  exit /b 1
)

echo.
echo Sentinel Salud en http://127.0.0.1:8000   (cierra esta ventana para apagarlo)
echo Usuarios: jefe, analista, ti, salud, auditor    Clave: demo2026
echo.
start "" cmd /c "timeout /t 5 >nul & start http://127.0.0.1:8000"
cd backend
"..\.venv-win\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
