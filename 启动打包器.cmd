@echo off
setlocal
cd /d "%~dp0"
python apk_builder_gui.py
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" echo GUI exited with code: %EXITCODE%
pause
exit /b %EXITCODE%
