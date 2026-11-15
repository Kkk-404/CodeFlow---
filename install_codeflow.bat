@echo off
setlocal
chcp 65001 >nul
title Установка Codeflow

set "SOURCE=%~dp0"
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
set "INSTALL_DIR=%LOCALAPPDATA%\Codeflow"

if not exist "%SOURCE%index.html" goto source_missing
if not exist "%SOURCE%app.js" goto source_missing
if not exist "%SOURCE%reference.html" goto source_missing
if not exist "%SOURCE%reference.js" goto source_missing
if not exist "%SOURCE%Codeflow-Desktop.py" goto source_missing
if not exist "%SOURCE%desktop-course-data.json" goto source_missing
if not exist "%SOURCE%desktop-reference-data.json" goto source_missing
if not exist "%SOURCE%start_codeflow.bat" goto source_missing
if not exist "%SOURCE%start_codeflow-web.bat" goto source_missing
if not exist "%SOURCE%_headers" goto source_missing
if not exist "%SOURCE%codeflow_server.py" goto source_missing
if not exist "%SOURCE%codeflow.ico" goto source_missing
if not exist "%SOURCE%manifest.json" goto source_missing
if not exist "%SOURCE%service-worker.js" goto source_missing
if not exist "%SOURCE%python-runner-worker.js" goto source_missing
if not exist "%SOURCE%pyodide\pyodide.js" goto source_missing
if not exist "%SOURCE%pyodide\pyodide.asm.mjs" goto source_missing
if not exist "%SOURCE%pyodide\pyodide.asm.wasm" goto source_missing
if not exist "%SOURCE%pyodide\pyodide-lock.json" goto source_missing
if not exist "%SOURCE%pyodide\python_stdlib.zip" goto source_missing
if not exist "%SOURCE%icons\codeflow-180.png" goto source_missing
if not exist "%SOURCE%icons\codeflow-192.png" goto source_missing
if not exist "%SOURCE%icons\codeflow-512.png" goto source_missing
if not exist "%SOURCE%third-party-notices.txt" goto source_missing

if exist "%INSTALL_DIR%\index.html" (
  echo Найдена предыдущая установка в "%INSTALL_DIR%".
  choice /c YN /m "Обновить файлы Codeflow"
  if errorlevel 2 goto cancelled
)

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%index.html" "%INSTALL_DIR%\index.html" >nul
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%app.js" "%INSTALL_DIR%\app.js" >nul
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%reference.html" "%INSTALL_DIR%\reference.html" >nul
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%reference.js" "%INSTALL_DIR%\reference.js" >nul
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%Codeflow-Desktop.py" "%INSTALL_DIR%\Codeflow-Desktop.py" >nul
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%desktop-course-data.json" "%INSTALL_DIR%\desktop-course-data.json" >nul
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%desktop-reference-data.json" "%INSTALL_DIR%\desktop-reference-data.json" >nul
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%start_codeflow.bat" "%INSTALL_DIR%\start_codeflow.bat" >nul
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%start_codeflow-web.bat" "%INSTALL_DIR%\start_codeflow-web.bat" >nul
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%_headers" "%INSTALL_DIR%\_headers" >nul
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%codeflow_server.py" "%INSTALL_DIR%\codeflow_server.py" >nul
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%codeflow.ico" "%INSTALL_DIR%\codeflow.ico" >nul
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%manifest.json" "%INSTALL_DIR%\manifest.json" >nul
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%service-worker.js" "%INSTALL_DIR%\service-worker.js" >nul
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%python-runner-worker.js" "%INSTALL_DIR%\python-runner-worker.js" >nul
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%third-party-notices.txt" "%INSTALL_DIR%\third-party-notices.txt" >nul
if errorlevel 1 goto copy_failed
xcopy /e /i /y /q "%SOURCE%assets" "%INSTALL_DIR%\assets" >nul
if errorlevel 1 goto copy_failed
xcopy /e /i /y /q "%SOURCE%icons" "%INSTALL_DIR%\icons" >nul
if errorlevel 1 goto copy_failed
xcopy /e /i /y /q "%SOURCE%pyodide" "%INSTALL_DIR%\pyodide" >nul
if errorlevel 1 goto copy_failed
if exist "%SOURCE%README-Запуск.txt" copy /y "%SOURCE%README-Запуск.txt" "%INSTALL_DIR%\README-Запуск.txt" >nul

call :check_python
if not errorlevel 1 goto python_ready

echo Python 3 с Tkinter не найден. Он нужен для офлайн-окна; модуль http.server нужен для web-версии.
where winget >nul 2>&1
if errorlevel 1 goto manual_install
choice /c YN /m "Установить официальный менеджер Python и Python 3.14 через WinGet"
if errorlevel 2 goto cancelled

echo Устанавливаю официальный Python Install Manager...
winget install 9NQ7512CXL7T -e --accept-package-agreements --accept-source-agreements --disable-interactivity
if errorlevel 1 (
  where py >nul 2>&1
  if errorlevel 1 goto winget_failed
)

where py >nul 2>&1
if errorlevel 1 goto manager_not_ready
echo Устанавливаю runtime Python 3.14...
py install 3.14
if errorlevel 1 goto runtime_failed

call :check_python
if errorlevel 1 goto python_not_ready

:python_ready
rem Shortcut creation is optional; the app can still be started from its folder.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$desktop=[Environment]::GetFolderPath('Desktop'); $target=Join-Path $env:LOCALAPPDATA 'Codeflow\start_codeflow.bat'; $shell=New-Object -ComObject WScript.Shell; $link=$shell.CreateShortcut((Join-Path $desktop 'Codeflow.lnk')); $link.TargetPath=$target; $link.WorkingDirectory=(Split-Path $target); $link.Description='Codeflow Desktop — офлайн-программа без браузера'; $link.IconLocation=(Join-Path $env:LOCALAPPDATA 'Codeflow\codeflow.ico')+',0'; $link.Save()" >nul 2>&1
if errorlevel 1 echo Не удалось создать ярлык. Запусти "%INSTALL_DIR%\start_codeflow.bat" вручную.

echo.
echo Codeflow установлен в "%INSTALL_DIR%".
echo Создан ярлык Codeflow с иконкой приложения, если Windows разрешила его создать.
echo Запускаю Codeflow Desktop в отдельном окне...
call "%INSTALL_DIR%\start_codeflow.bat"
exit /b 0

:check_python
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -c "import http.server, tkinter" >nul 2>&1
  if not errorlevel 1 exit /b 0
  py -V:3.14 -c "import http.server, tkinter" >nul 2>&1
  if not errorlevel 1 exit /b 0
)
call :check_python_cmd python
if not errorlevel 1 exit /b 0
call :check_python_cmd python3
if not errorlevel 1 exit /b 0
exit /b 1

:check_python_cmd
set "PY_PATH="
for /f "delims=" %%P in ('where %~1 2^>nul') do (
  if not defined PY_PATH set "PY_PATH=%%P"
)
if not defined PY_PATH exit /b 1
echo "%PY_PATH%" | findstr /i "WindowsApps" >nul
if not errorlevel 1 exit /b 1
%~1 -c "import http.server, tkinter" >nul 2>&1
if not errorlevel 1 exit /b 0
exit /b 1

:source_missing
echo [ОШИБКА] В папке запуска не найдены файлы Codeflow.
echo Распакуй весь архив Codeflow-Windows.zip и запусти install_codeflow.bat из распакованной папки.
pause
exit /b 1

:copy_failed
echo [ОШИБКА] Не удалось скопировать файлы в "%INSTALL_DIR%".
echo Проверь свободное место и права на папку профиля пользователя.
pause
exit /b 1

:manual_install
echo WinGet не найден. Открою официальную страницу установки Python.
start "" "https://www.python.org/downloads/windows/"
echo Установи Python Install Manager / Python 3, затем запусти install_codeflow.bat ещё раз.
pause
exit /b 1

:cancelled
echo Установка отменена. Файлы сайта оставлены в "%INSTALL_DIR%".
pause
exit /b 0

:winget_failed
echo [ОШИБКА] WinGet не смог установить Python Install Manager.
echo Проверь подключение к интернету или установи Python вручную, затем запусти установщик повторно.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1

:manager_not_ready
echo Python Install Manager установлен, но команда py пока недоступна в этом окне.
echo Закрой окно, запусти install_codeflow.bat ещё раз или перезапусти Windows.
pause
exit /b 1

:runtime_failed
echo [ОШИБКА] Python Install Manager не смог установить runtime Python 3.14.
echo Проверь подключение к интернету, затем повтори запуск или установи Python с официальной страницы.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1

:python_not_ready
echo [ОШИБКА] Python установлен, но не найдены нужные модули tkinter / http.server.
echo Запусти install_codeflow.bat повторно либо открой страницу https://www.python.org/downloads/windows/.
pause
exit /b 1
