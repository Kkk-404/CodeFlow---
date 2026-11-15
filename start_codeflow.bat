@echo off
setlocal
chcp 65001 >nul
title Codeflow Desktop — офлайн
cd /d "%~dp0"

if not exist "Codeflow-Desktop.py" goto files_missing
if not exist "desktop-course-data.json" goto files_missing
if not exist "desktop-reference-data.json" goto files_missing

rem Prefer the Python Launcher so the window can start without a console.
where pyw >nul 2>&1
if not errorlevel 1 (
  py -3 -c "import tkinter, json, re" >nul 2>&1
  if not errorlevel 1 (
    start "" pyw -3 "%~dp0Codeflow-Desktop.py"
    exit /b 0
  )
)

rem Some installations provide pythonw.exe but not pyw.exe.
where pythonw >nul 2>&1
if not errorlevel 1 (
  python -c "import tkinter, json, re" >nul 2>&1
  if not errorlevel 1 (
    start "" pythonw "%~dp0Codeflow-Desktop.py"
    exit /b 0
  )
)

rem Last resort: show the native window from this console if pythonw is missing.
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -c "import tkinter, json, re" >nul 2>&1
  if not errorlevel 1 (
    py -3 "%~dp0Codeflow-Desktop.py"
    exit /b 0
  )
)
where python >nul 2>&1
if not errorlevel 1 (
  python -c "import tkinter, json, re" >nul 2>&1
  if not errorlevel 1 (
    python "%~dp0Codeflow-Desktop.py"
    exit /b 0
  )
)

echo [ОШИБКА] Не найден Python 3 с модулем Tkinter.
echo Codeflow Desktop запускается офлайн, но для самого окна нужен установленный Python 3.
echo Установи Python с компонентом Tcl/Tk, затем запусти этот BAT ещё раз.
pause
exit /b 1

:files_missing
echo [ОШИБКА] Не найдены файлы настольной версии Codeflow.
echo Распакуй весь Codeflow-Windows.zip и запускай BAT из распакованной папки.
pause
exit /b 1
