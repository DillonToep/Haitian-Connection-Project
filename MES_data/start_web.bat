@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动 MES 网页服务...
echo 本机地址：http://127.0.0.1:8000
echo 局域网地址：http://192.168.1.9:8000
echo.
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
echo.
echo 程序已停止或发生错误。
pause

