@echo off
setlocal
chcp 65001 >nul
title Установка Codeflow

set "SOURCE=%~dp0"
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
set "INSTALL_DIR=%LOCALAPPDATA%\Codeflow"

if not exist "%SOURCE%index.html" goto source_missing
if not exist "%SOURCE%reference.html" goto source_missing
if not exist "%SOURCE%start_codeflow.bat" goto source_missing

if exist "%INSTALL_DIR%\index.html" (
  echo Найдена предыдущая установка в "%INSTALL_DIR%".
  choice /c YN /m "Обновить файлы Codeflow"
  if errorlevel 2 goto cancelled
)

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%index.html" "%INSTALL_DIR%\index.html" >nul
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%reference.html" "%INSTALL_DIR%\reference.html" >nul
if errorlevel 1 goto copy_failed
copy /y "%SOURCE%start_codeflow.bat" "%INSTALL_DIR%\start_codeflow.bat" >nul
if errorlevel 1 goto copy_failed
if exist "%SOURCE%README-Запуск.txt" copy /y "%SOURCE%README-Запуск.txt" "%INSTALL_DIR%\README-Запуск.txt" >nul

call :check_python
if not errorlevel 1 goto python_ready

echo Python 3 не найден. Для локального запуска Codeflow нужен Python.
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
powershell -NoProfile -ExecutionPolicy Bypass -Command "$desktop=[Environment]::GetFolderPath('Desktop'); $target=Join-Path $env:LOCALAPPDATA 'Codeflow\start_codeflow.bat'; $shell=New-Object -ComObject WScript.Shell; $link=$shell.CreateShortcut((Join-Path $desktop 'Codeflow.lnk')); $link.TargetPath=$target; $link.WorkingDirectory=(Split-Path $target); $link.Description='Запуск учебного сайта Codeflow'; $link.Save()" >nul 2>&1
if errorlevel 1 echo Не удалось создать ярлык. Запусти "%INSTALL_DIR%\start_codeflow.bat" вручную.

echo.
echo Codeflow установлен в "%INSTALL_DIR%".
echo Создан ярлык на рабочем столе, если Windows разрешила его создать.
echo Запускаю сайт...
call "%INSTALL_DIR%\start_codeflow.bat"
exit /b 0

:check_python
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -c "import http.server" >nul 2>&1
  if not errorlevel 1 exit /b 0
  py -V:3.14 -c "import http.server" >nul 2>&1
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
%~1 -c "import http.server" >nul 2>&1
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
echo [ОШИБКА] Python установился, но проверка модуля http.server не прошла.
echo Запусти install_codeflow.bat повторно либо открой страницу https://www.python.org/downloads/windows/.
pause
exit /b 1
