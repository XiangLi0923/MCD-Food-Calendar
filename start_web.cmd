@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYEXE=
where py >nul 2>nul && set PYEXE=py -3
if not defined PYEXE (where python >nul 2>nul && set PYEXE=python)
if not defined PYEXE set PYEXE=C://Users//lenovo//.workbuddy//binaries//python//versions//3.13.12//python.exe
echo.
echo  MaiBox web server starting ...
echo  Open in browser:  http://127.0.0.1:8000
echo  Close this window to stop the server.
echo.
%PYEXE% server.py --port 8000
pause
