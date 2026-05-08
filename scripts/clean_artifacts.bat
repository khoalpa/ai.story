@echo off
setlocal

set "ROOT=%~dp0..\\"
set "PYTHON=python"
where python >nul 2>nul
if errorlevel 1 (
    if exist "%LocalAppData%\Programs\Python\Python310\python.exe" (
        set "PYTHON=%LocalAppData%\Programs\Python\Python310\python.exe"
    )
)

"%PYTHON%" "%ROOT%scripts\clean_project.py" --apply --include-runtime --root "%ROOT%"
echo.
pause
