@echo off
chcp 65001>nul
title MES MQTT 数据采集程序

cd /d "%~dp0"

set "MQTT_PASSWORD=Mqttadmin@123"

echo 正在启动MQTT数据采集系统...
echo.

python mqtt_monitor.py

echo.
echo 程序已停止或发生错误。
pause