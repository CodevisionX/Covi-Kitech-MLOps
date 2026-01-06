@echo off
echo Stopping KITECH MLOps Platform...
cd /d "%~dp0"
docker compose down
echo.
echo 모든 서비스가 중지되었습니다.
pause