@echo off
setlocal
py -m streamlit run "%~dp0gui_entry.py"
endlocal
