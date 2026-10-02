@echo off
setlocal
chcp 65001 >nul
title Codeflow — локальный запуск
cd /d "%~dp0"

set "PORT=8765"
set "PY_RUN="

if not exist "index.html" (
  echo [ОШИБКА] Рядом с этим BAT-файлом не найден index.html.
  echo Помести start_codeflow.bat в ту же папку, где лежат index.html и reference.html.
  pause
  exit /b 1
)

rem Сначала пробуем Python Launcher, затем обычные команды Python.
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -c "import http.server" >nul 2>&1
  if not errorlevel 1 set "PY_RUN=py -3"
  if not defined PY_RUN (
    py -V:3.14 -c "import http.server" >nul 2>&1
    if not errorlevel 1 set "PY_RUN=py -V:3.14"
  )
)

if not defined PY_RUN (
  call :check_python_cmd python
  if not errorlevel 1 set "PY_RUN=python"
)

if not defined PY_RUN (
  call :check_python_cmd python3
  if not errorlevel 1 set "PY_RUN=python3"
)

if not defined PY_RUN (
  echo [ОШИБКА] Не удалось найти установленный Python 3.
  echo Установи Python 3 и включи его в PATH либо проверь команду py -3.
  pause
  exit /b 1
)

rem Не открываем чужой сайт, если выбранный локальный порт уже занят.
%PY_RUN% -c "import socket,sys; s=socket.socket(); s.settimeout(0.5); r=s.connect_ex(('127.0.0.1', %PORT%)); s.close(); sys.exit(10 if r == 0 else 0)"
if errorlevel 10 goto port_busy
if errorlevel 1 goto port_check_failed

 echo Запускаю Codeflow через %PY_RUN% на порту %PORT%...
start "Codeflow — локальный сервер" /min cmd /k "cd /d ""%~dp0"" && %PY_RUN% -m http.server %PORT% --bind 127.0.0.1"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:%PORT%/index.html"
echo Сайт открыт в браузере. Сервер доступен только на этом компьютере.
echo Чтобы остановить сервер, закрой окно «Codeflow — локальный сервер».
exit /b 0

:check_python_cmd
set "PY_PATH="
for /f "delims=" %%P in ('where %~1 2^>nul') do (
  if not defined PY_PATH set "PY_PATH=%%P"
)
if not defined PY_PATH exit /b 1
echo "%PY_PATH%" | findstr /i "WindowsApps" >nul
if not errorlevel 1 exit /b 1
%~1 -c "import http.server" >nul 2>&1
if not errorlevel 1 exit /b 0
exit /b 1

:port_busy
echo [ОШИБКА] Порт %PORT% уже занят.
echo Закрой другое приложение на этом порту или измени PORT в начале этого BAT-файла.
pause
exit /b 1

:port_check_failed
echo [ОШИБКА] Не удалось проверить доступность локального порта.
pause
exit /b 1
