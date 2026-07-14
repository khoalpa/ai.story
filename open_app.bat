@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
py -m streamlit run "studio\gui_entry.py" %*
endlocal
