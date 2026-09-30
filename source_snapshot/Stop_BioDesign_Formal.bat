@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\stop_biodesign_formal_safe.ps1" %*
exit /b %ERRORLEVEL%
