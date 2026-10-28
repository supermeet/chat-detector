@echo off
rem Start SafeSphere (UI + API) at http://localhost:8000
rem First time only:  cd backend && python -m venv .venv && .venv\Scripts\python -m pip install --use-feature=truststore -r requirements.txt
cd /d "%~dp0backend"
if not exist .venv\Scripts\python.exe (
  echo No backend\.venv yet. Run the first-time setup line at the top of this file.
  pause
  exit /b 1
)
start "" http://localhost:8000
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
