@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
  set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe"
)

echo Starting Finance API on http://127.0.0.1:8000 ...
"%PYTHON_EXE%" -m uvicorn main:app --host 127.0.0.1 --port 8000
if errorlevel 1 (
  echo.
  echo Application stopped with an error. Check logs above.
  echo Common cause: invalid or missing GEMINI_API_KEY while GEMINI_REQUIRED is enabled.
  pause
)
endlocal
