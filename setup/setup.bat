@echo off
setlocal enabledelayedexpansion

:: 배치 파일이 실행되는 폴더로 작업 디렉토리 변경 (관리자 권한 실행 대비)
cd /d "%~dp0"

echo ==========================================
echo  KITECH MLOps Platform Setup (Windows)
echo ==========================================

:: 0. .env 파일 존재 확인 및 변수 로드
if not exist ".env" (
    echo [ERROR] .env file not found! 
    echo Current Directory: %cd%
    echo Please make sure .env file exists in the same folder.
    pause
    exit /b 1
)

echo [0/4] Loading configurations from .env...
:: .env에서 값을 읽어올 때 주석(#)과 공백을 처리하는 로직으로 보강
for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
    set "var=%%a"
    set "val=%%b"
    :: 주석 제외 및 값 할당 (공백 포함 주의)
    if not "!var:~0,1!"=="#" (
        for /f "tokens=1" %%c in ("!val!") do set "%%a=%%c"
    )
)

:: 1. 포트 충돌 확인
echo [1/4] Checking port availability...
set "CONFLICT=0"
set "CHECK_PORTS=%UI_PORT% %BACKEND_PORT% %MLFLOW_PORT% %POSTGRES_PORT% %MINIO_PORT% %MINIO_CONSOLE_PORT%"

for %%P in (%CHECK_PORTS%) do (
    netstat -ano | findstr /R /C:":%%P " > nul
    if !errorlevel! equ 0 (
        echo [ERROR] Port %%P is already in use by another program.
        set "CONFLICT=1"
    )
)

if "!CONFLICT!"=="1" (
    echo.
    echo Please change the conflicting port values in your .env file and try again.
    pause
    exit /b 1
)
echo [OK] All ports are available.

:: 2. 필수 폴더 생성
echo [2/4] Creating necessary directories...
if not exist "pg_data" mkdir pg_data
if not exist "training_results" mkdir training_results
if not exist "minio_data" mkdir minio_data

:: 3. 도커 이미지 로드
echo [3/4] Loading Docker images from /images folder...
echo This may take a few minutes depending on your system performance.
if not exist "images" (
    echo [ERROR] 'images' folder not found!
    pause
    exit /b 1
)

for %%f in (images\*.tar) do (
    echo Loading %%f...
    docker load -i "%%f"
)

:: 4. 플랫폼 실행
echo [4/4] Starting MLOps Platform...
docker compose up -d

echo.
echo ==========================================
echo  Setup Complete! 
echo  - Frontend: http://localhost:%UI_PORT%
echo  - Backend: http://localhost:%BACKEND_PORT%
echo  - MLflow: http://localhost:%MLFLOW_PORT%
echo  - MinIO: http://localhost:%MINIO_CONSOLE_PORT% (Console)
echo ==========================================
pause