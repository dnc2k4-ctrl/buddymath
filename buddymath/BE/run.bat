@echo off
chcp 65001 >nul
title BuddyMath Server
echo.
echo  ====================================================
echo   BuddyMath - Hoc thong minh, Tien vung vang!
echo  ====================================================
echo.

cd /d "%~dp0"

:: Dung venv neu co (uu tien ..\venv, sau do .\venv)
set PYTHON=python
if exist "..\venv\Scripts\python.exe" (
    set PYTHON=..\venv\Scripts\python.exe
    echo [OK] Dung moi truong ao: ..\venv
) else if exist "venv\Scripts\python.exe" (
    set PYTHON=venv\Scripts\python.exe
    echo [OK] Dung moi truong ao: .\venv
) else (
    echo [INFO] Khong tim thay venv, dung Python he thong
)

%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Chua cai Python! Tai tai: https://python.org/downloads
    pause & exit /b 1
)

if not exist ".env" (
    echo [THONG BAO] Tao .env tu .env.example - hay mo va dien API key!
    copy ".env.example" ".env" >nul
    notepad .env
)

echo [1/2] Kiem tra thu vien...
%PYTHON% -m pip install -r requirements.txt -q --disable-pip-version-check

echo [2/2] Khoi dong server tai http://localhost:8000 ...
start /b cmd /c "timeout /t 3 >nul & start http://localhost:8000/"
%PYTHON% -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause
