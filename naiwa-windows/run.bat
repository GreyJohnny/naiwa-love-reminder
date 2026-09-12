@echo off
rem Naiwa Love Reminder - run without a console window.
rem Launches with pythonw.exe, so no black console pops up.
rem (ASCII-only on purpose: .bat files are read with the OEM codepage.)
setlocal
set "PYW=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw.exe"
start "" "%PYW%" "%~dp0app\naiwa_app.py" %*
endlocal
