# MES MQTT 数据采集系统

## 目录说明

```text
sql-mqtt/
├─ backend/                 FastAPI 后端
│  ├─ main.py               Web 服务入口
│  ├─ config.py             SQL Server 配置
│  ├─ database.py           数据库连接
│  ├─ security.py           登录与权限
│  └─ routers/              按业务分类的接口
│     ├─ auth.py            登录、退出、修改密码
│     ├─ devices.py         设备、实时、工艺、SPC
│     └─ molds.py           模具资料与装卸记录
├─ frontend/                网页前端
│  ├─ index.html            设备看板
│  ├─ login.html            登录页
│  ├─ css/                  页面样式
│  └─ js/                   页面逻辑与接口调用
├─ sql/                     SQL Server 建表及查询脚本
├─ api_server.py            旧启动命令兼容入口
├─ mqtt_monitor.py          MQTT 数据采集脚本
├─ start_web.bat            双击启动网页
└─ start_mqtt.bat           双击启动采集程序
```

## 启动网页

推荐直接双击 `start_web.bat`。

也可以在任意命令行目录执行：

```bat
python -m uvicorn backend.main:app --app-dir "E:\Project main\sql-mqtt" --host 0.0.0.0 --port 8000
```

访问地址：

- 本机：`http://127.0.0.1:8000`
- 局域网：`http://这台电脑的IPv4地址:8000`

如果先进入项目目录，也可使用兼容命令：

```bat
cd /d "E:\Project main\sql-mqtt"
python -m uvicorn api_server:app --host 0.0.0.0 --port 8000
```

