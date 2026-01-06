@echo off
setlocal enabledelayedexpansion

:: 작업 디렉토리 설정
cd /d "%~dp0"

echo ==========================================
echo  KITECH MLOps Platform - Quick Start
echo ==========================================

:: 1. 관리자 권한 체크
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Please run this script as Administrator.
    pause
    exit /b 1
)

:: 2. .env 파일에서 변수 로드
if not exist ".env" (
    echo [ERROR] .env file not found!
    pause
    exit /b 1
)

for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
    set "var=%%a"
    set "val=%%b"
    if not "!var:~0,1!"=="#" (
        for /f "tokens=1" %%c in ("!val!") do set "%%a=%%c"
    )
)

:: 3. 플랫폼 실행
echo Starting Docker containers...
docker compose up -d

echo.
echo ==========================================
echo  Platform is Running!
echo  - Frontend: http://localhost:%UI_PORT%
echo  - Backend: http://localhost:%BACKEND_PORT%
echo  - MLflow: http://localhost:%MLFLOW_PORT%
echo  - MinIO: http://localhost:%MINIO_CONSOLE_PORT% (Console)
echo ==========================================
echo To stop the platform, use stop.bat or 'docker compose down'
pause