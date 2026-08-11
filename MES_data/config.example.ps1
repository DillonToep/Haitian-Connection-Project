# Copy this file to config.ps1, fill in passwords, then run: .\config.ps1

$env:MQTT_HOST = "192.168.72.173"
$env:MQTT_PORT = "1883"
$env:MQTT_USERNAME = "mqttadmin"
$env:MQTT_PASSWORD = "replace-with-mqtt-password"
$env:MQTT_TOPIC = "#"
$env:MQTT_CLIENT_ID = "mes_sql_collector"
$env:MQTT_QOS = "1"

# Examples: localhost, localhost\SQLEXPRESS, COMPUTER-NAME\MSSQLSERVER
$env:SQL_SERVER = "localhost\SQLDEVELOP"
$env:SQL_DATABASE = "MES_MQTT"
$env:SQL_DRIVER = "ODBC Driver 18 for SQL Server"

# Leave these empty to use the current Windows account.
$env:SQL_USERNAME = ""
$env:SQL_PASSWORD = ""

python "$PSScriptRoot\mqtt_monitor.py"
