@echo off
setlocal enabledelayedexpansion

:: 1. 관리자 권한 체크
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ==========================================
    echo [ERROR] 반드시 '관리자 권한'으로 실행해야 합니다.
    echo 마우스 우클릭 -> '관리자 권한으로 실행'을 선택하세요.
    echo ==========================================
    pause
    exit /b 1
)

cd /d "%~dp0"

echo ==========================================
echo   KITECH MLOps Platform Setup (Admin)
echo ==========================================

:: 2. .env 로드
if not exist ".env" (
    echo [ERROR] .env 파일이 없습니다.
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

:: 3. 포트 점검
echo [1/4] Checking ports...
set "CONFLICT=0"
for %%P in (%UI_PORT% %BACKEND_PORT% %MLFLOW_PORT% %POSTGRES_PORT% %MINIO_PORT% %MINIO_CONSOLE_PORT%) do (
    netstat -ano | findstr /R /C:":%%P " > nul
    if !errorlevel! equ 0 (
        echo [ERROR] 포트 %%P 가 이미 사용 중입니다.
        set "CONFLICT=1"
    )
)
if "!CONFLICT!"=="1" ( pause & exit /b 1 )

:: 4. 폴더 생성
echo [2/4] Creating directories...
if not exist "pg_data" mkdir pg_data
if not exist "training_results" mkdir training_results
if not exist "minio_data" mkdir minio_data

:: 5. 압축 이미지 로드
echo [3/4] Loading Compressed Images (.tar.gz)...
for %%f in (images\*.tar*) do (
    echo Loading %%f...
    docker load -i "%%f"
)

:: 6. 실행
echo [4/4] Starting Core Infrastructure...
docker rm -f mlops_postgres mlops-minio mlops_mlflow mlops_backend mlops_ui >nul 2>&1
docker compose up -d

echo.
echo ==========================================
echo   Setup 완료! (훈련 서버는 필요 시 자동 호출됩니다)
echo ==========================================
pause