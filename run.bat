@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe"
)

start "finance-app" "%PYTHON_EXE%" -m uvicorn main:app --host 127.0.0.1 --port 8000
endlocal
