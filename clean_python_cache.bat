@echo off
setlocal

rem Always clean the project containing this script, regardless of current directory.
set "PROJECT_DIR=%~dp0"

echo Cleaning safe Python cache directories in:
echo   %PROJECT_DIR%
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = [System.IO.Path]::GetFullPath('%PROJECT_DIR%');" ^
  "$names = @('__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache');" ^
  "$dirs = @(Get-ChildItem -LiteralPath $root -Directory -Force -Recurse -ErrorAction SilentlyContinue | Where-Object { $names -contains $_.Name });" ^
  "foreach ($dir in ($dirs | Sort-Object { $_.FullName.Length } -Descending)) {" ^
  "  try { Remove-Item -LiteralPath $dir.FullName -Recurse -Force -ErrorAction Stop; Write-Host ('Deleted: ' + $dir.FullName) }" ^
  "  catch { Write-Warning ('Could not delete: ' + $dir.FullName + ' - ' + $_.Exception.Message) }" ^
  "}" ^
  "Write-Host ''; Write-Host ('Done. Deleted ' + $dirs.Count + ' cache directorie(s).')"

if errorlevel 1 (
  echo.
  echo Cleanup encountered an error.
  pause
  exit /b 1
)

echo.
echo Protected: .git, .github, *.egg-info, and application data were not touched.
pause
endlocal
