@echo off
setlocal
set ROOT=%~dp0..
pushd "%ROOT%"
py scripts\sync_version.py || goto :fail
py scripts\release_smoke.py || goto :fail
py scripts\build_dist.py || goto :fail
py scripts\make_clean_release.py || goto :fail
echo.
echo Release build completed successfully.
popd
exit /b 0
:fail
echo.
echo Release build failed.
popd
exit /b 1
