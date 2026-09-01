# MES MQTT 数据采集系统

注塑机 MES（生产数据采集与管理）系统。通过 MQTT 采集机台数据写入 SQL
Server，并提供一个 FastAPI + 原生 JS 的网页看板（设备状态、工艺参数、SPC
数据、模具管理、变更记录、预警通知、利用率报表），以及一个可选的
Streamlit 管理端。

## 目录说明

```text
sql-mqtt/
├─ backend/                     FastAPI 后端
│  ├─ main.py                   Web 服务入口 / 路由挂载 / 静态文件 / 登录跳转
│  ├─ config.py                 SQL Server 连接、会话时长、上传目录等配置
│  ├─ database.py               数据库连接池（PooledConnection）
│  ├─ security.py               密码哈希（PBKDF2）、会话校验、权限检查
│  ├─ schemas.py                Pydantic 请求体模型
│  ├─ parameter_labels.py       工艺参数 tag -> 中文名称 / 分类 字典
│  ├─ export_xlsx.py            试模成型参数表导出（生成 / 覆盖写入模板）
│  ├─ import_xlsx.py            试模成型参数表导入（.xlsx/.xls/.csv 解析）
│  ├─ label_scan_xlsx.py        按文字标签定位单元格（而非固定坐标）
│  ├─ extended_field_scan.py    注塑成型条件参数表扩展字段的标签式解析
│  ├─ xls_convert.py            旧版 .xls -> .xlsx 转换（用于保留上传模板）
│  ├─ template_storage.py       每个机型的试模参数表原始模板存取
│  └─ routers/                  按业务分类的接口
│     ├─ auth.py                登录 / 退出 / 修改密码 / 当前用户
│     ├─ devices.py             设备列表、看板、实时数据、工艺参数、机型
│     ├─ molds.py               模具档案、机型（Machine Type）、装卸模具
│     ├─ changelog.py           工艺参数变更记录查询
│     ├─ warnings.py            预警通知（参数超差 / 产量超限 / 自动识别装机）
│     ├─ favorites.py           工艺参数快照收藏
│     ├─ export.py              试模参数表导出 / 导入 / 模板管理
│     └─ uptime.py              设备利用率（稼动率）统计
├─ frontend/                    网页前端（纯静态文件，由 FastAPI /static 提供）
│  ├─ index.html                设备看板等主界面（SPA，单文件承载所有页面）
│  ├─ login.html                登录页
│  ├─ css/                      页面样式（app.css / login.css）
│  ├─ js/                       页面逻辑与接口调用（app.js / login.js）
│  └─ uploads/                  运行时生成：模具图片、试模参数表模板
├─ sql/                         SQL Server 建表 / 迁移脚本（见下方"数据库初始化"）
├─ api_server.py                旧启动命令兼容入口（`import app` 自 backend.main）
├─ add_user.py                  命令行工具：创建后台账号（见"账号管理"）
├─ mqtt_monitor.py              MQTT 数据采集脚本（写库 + 变更检测 + 预警逻辑）
├─ streamlit_app.py             可选的 Streamlit 管理前端（调用同一套后端 API）
├─ config.example.ps1           mqtt_monitor.py 的环境变量配置示例（PowerShell）
├─ requirements.txt             Python 依赖
├─ start_web.bat                双击启动网页后端
└─ start_mqtt.bat               双击启动 MQTT 采集程序
```

## 从零开始部署（全新环境）

以下按顺序列出在一台**全新机器**上，从只有这份代码仓库开始，到网页可以
正常打开、可以登录为止，所需要的**全部**步骤。以 Windows 为主（因为
`.bat` 启动脚本和默认的 `SQL_SERVER=localhost\SQLDEVELOP` 都假设本机装
了 SQL Server），Linux/Mac 的差异在各步骤里单独说明。

### 0. 获取代码

把本仓库克隆或解压到本地任意目录，例如 `E:\Project main\sql-mqtt`
（`README.md` 中出现的示例路径）。之后所有命令均假设当前目录已 `cd`
到仓库根目录（即 `backend/`、`sql/`、`requirements.txt` 所在的目录）。

### 1. 安装 Python

需要 **Python 3.10 及以上**（代码中大量使用了 `str | None` 这种 PEP 604
写法，3.10 以下会直接报语法错误）。可执行 `python --version` 确认。

（可选但推荐）创建独立虚拟环境，避免和系统其它 Python 项目的依赖冲突：

```bat
python -m venv .venv
.venv\Scripts\activate          REM Linux/Mac 用: source .venv/bin/activate
```

### 2. 安装 Python 依赖

仓库根目录下的 `requirements.txt` 列出了全部依赖（FastAPI/uvicorn、
pyodbc、paho-mqtt、openpyxl/xlrd/xls2xlsx、streamlit、pandas、
requests）。在仓库根目录执行：

```bat
pip install -r requirements.txt
```

这一步会自动从 PyPI 下载安装上述所有包，**不需要额外手动安装其它 pip
包**。如果 `pip install` 因网络原因失败，可加 `-i` 换用国内镜像源。

### 3. 安装 SQL Server 本体 + ODBC 驱动

这两者都**不包含**在 `requirements.txt` 里，需要单独安装：

- **SQL Server**：任意版本均可（Express / Developer / 标准版），只要能
  用 Windows 身份验证或 SQL 账号密码连接即可。默认配置假设实例名为
  `localhost\SQLDEVELOP`（见下方"配置"一节如何改成你自己的实例名）。
  Linux 环境下可以用 Docker 跑
  `mcr.microsoft.com/mssql/server` 镜像代替本机安装。
- **ODBC Driver 18 for SQL Server**：`pyodbc` 通过它连接数据库，需要
  单独从微软官网下载安装（不是 pip 包，Windows/Linux 都有对应安装包）。
  装好之后 `pyodbc` 才能识别驱动名 `ODBC Driver 18 for SQL Server`。

### 4. 创建数据库

`sql/` 目录下的脚本全部以 `USE MES_MQTT;` 开头，**假设这个数据库已经存
在**，脚本本身不负责创建数据库。先用 SSMS（SQL Server Management
Studio）或任意 SQL 客户端连接你的 SQL Server 实例，执行：

```sql
CREATE DATABASE MES_MQTT;
```

（如果想用别的库名，记得后面"配置"一节里的 `SQL_DATABASE` 环境变量、
`add_user.py`、`mqtt_monitor.py` 里硬编码的库名也要一并改掉，三处必须
保持一致。）

### 5. 按顺序执行建表脚本

在刚创建的 `MES_MQTT` 库里，**按以下顺序**执行 `sql/` 目录下的脚本
（`setup_web_database.sql` 必须最先执行，建出 `app_users`/`molds` 等
基础表；后面大多数脚本是幂等的增量迁移，可重复执行不会报错）：

```
setup_web_database.sql        -- app_users / app_sessions / molds / device_mold_assignments
setup_changelog.sql
setup_warnings.sql
setup_mold_projects.sql
setup_mold_parameter_targets.sql
setup_mold_parameter_defaults.sql
setup_cleaning_alerts.sql
setup_mold_cleaning.sql
setup_mold_output.sql
setup_cycle_reset.sql
setup_mold_extended_info.sql
setup_device_profiles.sql
setup_mold_machine_types.sql
setup_favorites.sql
setup_favorites_backup_flag.sql
setup_trial_templates.sql
setup_mold_auto_detect.sql
tempFix.sql
one_time_migration.sql
```

`setup_mold_machine_types.sql` 假设 `dbo.mold_machine_types` 表已存在
（该表由更早的一版迁移创建，但当前仓库的 `sql/` 目录里没有单独一份
"建 `mold_machine_types` 表"的脚本）——如果从这份仓库全新建库时报"表不
存在"，需要先手动建这张表（结构可参照 `setup_mold_machine_types.sql`
里对它列的引用：`id`、`mold_id`、`machine_type`、`is_main`、
`created_by`、`created_at`），再继续执行后面的脚本。

### 6. 确认试模参数表默认模板（可选，非阻塞项）

`backend/config.py` 里的 `DEFAULT_TRIAL_TEMPLATE_PATH` 指向
`backend/assets/default_trial_template.xlsx`，用作"试模成型参数表"导
出的默认空白模板。这个文件**不在本次提供的代码内容里**——如果你的仓库
里也没有这个文件，不影响系统启动和绝大部分功能，只是 GET
`.../export` 在还没给某个机型上传过 Excel 模板时会自动降级为用
`export_xlsx.py` 内置的静态模板生成（代码里已经做了 try/except 兜底，
不会报错，只是导出的表格样式会略有不同）。

### 7. 配置数据库连接

后端（`backend/config.py`）默认连接
`localhost\SQLDEVELOP` 上的 `MES_MQTT` 库、Windows 集成认证。如果你的
实例名/库名/账号不同，通过环境变量覆盖（见下方"配置"一节），例如
PowerShell 里：

```powershell
$env:SQL_SERVER = "localhost\MSSQLSERVER"
$env:SQL_DATABASE = "MES_MQTT"
$env:SQL_USERNAME = "sa"
$env:SQL_PASSWORD = "你的密码"
```

注意 `add_user.py` 和 `mqtt_monitor.py` 里的连接配置是**各自独立硬编
码**的（不读取这些环境变量），如果改了后端的连接信息，这两个脚本顶部
的 `SQL_SERVER`/`SQL_DATABASE` 等常量也要手动同步修改。

### 8. 创建第一个登录账号

数据库建好之后网页还打不开（没有任何账号能登录）。在仓库根目录、且
上一步的数据库连接配置生效的前提下运行：

```bat
python add_user.py
```

按提示创建一个 `role` 为 `admin` 的账号（详见下方"账号管理"）。

### 9. 启动网页后端

```bat
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

或直接双击 `start_web.bat`。启动后浏览器访问
`http://127.0.0.1:8000`，应自动跳转到 `/login`，用第 8 步创建的账号登
录即可看到设备看板。

至此，**网页系统本身**已经可以完整使用（模具管理、账号、变更记录等）；
如果还需要接收真实机台的 MQTT 数据，继续下一步。

### 10.（可选）启动 MQTT 采集程序

`mqtt_monitor.py` 顶部硬编码了 MQTT broker 地址/账号密码
（`MQTT_HOST`/`MQTT_USERNAME`/`MQTT_PASSWORD`）和数据库连接串，需要按
你的实际 MQTT broker 信息手动修改这些常量（或参照
`config.example.ps1` 的写法改造成读环境变量），然后：

```bat
python mqtt_monitor.py
```

或双击 `start_mqtt.bat`。没有这一步，网页依然能打开和管理模具/账号，
只是设备看板不会有任何真实设备数据（因为设备列表本身是从
`dbo.mqtt_messages` 里已出现过的 `device_id` 反推出来的）。

---

## 环境准备（快速参考）

已经按上面"从零开始部署"走完一遍的，之后重新拉起服务只需要：

1. 安装 Python 依赖：

   ```bat
   pip install -r requirements.txt
   ```

2. 确认 **ODBC Driver 18 for SQL Server** 已安装（一次性，见上方第 3 步）。

3. 确认数据库已按上方第 4-5 步建好并执行过全部 `sql/` 脚本。

4. 确认至少有一个登录账号，见下方"账号管理"。

## 启动网页后端

推荐直接双击 `start_web.bat`，或在项目根目录执行：

```bat
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

也可以指定 `--app-dir`，或先 `cd` 进项目目录后用兼容入口
`api_server:app` 启动（见 `README.md` 顶部脚本内容）。

访问地址：
- 本机：`http://127.0.0.1:8000`
- 局域网：`http://这台电脑的IPv4地址:8000`

未登录访问任意页面会被重定向到 `/login`（见 `backend/main.py` 的
`spa_fallback`）。

## 启动 MQTT 采集程序

推荐双击 `start_mqtt.bat`（其中设置了 `MQTT_PASSWORD` 环境变量后运行
`python mqtt_monitor.py`）。也可以复制 `config.example.ps1` 为
`config.ps1`，填好 MQTT/SQL 连接信息后用 PowerShell 运行。

`mqtt_monitor.py` 负责：
- 将每条 MQTT 消息写入 `dbo.mqtt_messages`；
- 检测 `tech`（工艺参数）消息中的字段变化，写入
  `dbo.tech_parameter_changelog`，并按当前装机模具的机型公差判断是否
  超差（预警）；
- 检测批量参数变化（一次性改变的字段数超过 `BURST_CHANGE_THRESHOLD`），
  尝试自动识别并装机匹配的模具（"自动识别模具"功能，写入
  `dbo.mold_detection_alerts` / `dbo.mold_match_attempts`）；
- 在 `spc`（周期完成）消息到达时，累计模具产量并在超过 `max_output`
  时触发产量预警；
- 已删除的设备（`dbo.deleted_devices`）不会被重新写入。

## 可选：Streamlit 管理端

`streamlit_app.py` 是后端 API 的一个瘦客户端（不直接连数据库），提供
模具批量编辑、试模参数表导入导出、变更记录/预警的表格查看与导出为
Excel。运行：

```bat
streamlit run streamlit_app.py
```

默认连接 `http://127.0.0.1:8000`，可通过环境变量 `MES_API_BASE` 指定
其它地址（例如局域网内的后端地址）。同样需要用 MES 账号登录。

---

## 账号管理

系统**没有自助注册入口**——网页上只有登录页（`/login`），新增账号必须
由管理员在服务器上直接操作数据库。账号数据存于 `dbo.app_users`
（见 `sql/setup_web_database.sql`）：

| 字段 | 说明 |
|---|---|
| `username` | 唯一，登录用 |
| `password_hash` / `password_salt` | PBKDF2-HMAC-SHA256，310,000 次迭代（见 `backend/security.py` / `add_user.py`，两处哈希方式必须保持一致） |
| `role` | `admin` \| `operator` \| `viewer` |
| `is_active` | 停用账号只需置 0，无需删除 |

### 新增账号

在项目根目录（保证能 `import backend.security/config`）运行：

```bat
python add_user.py
```

脚本会交互式询问：
1. 用户名
2. 角色（`admin`/`operator`/`viewer`，默认 `operator`）
3. 密码（并二次确认，至少 8 位）

它会用与 `backend/security.py` 完全一致的 PBKDF2 参数生成哈希，并直接
写入 `dbo.app_users`。如果 `add_user.py` 顶部的 `SQL_SERVER` /
`SQL_DATABASE` 等连接信息与你的环境不同，需要先手动改一下脚本里的
`SQL_CONNECTION_STRING` 配置（它不读取 `backend/config.py` 的环境变量，
是独立的一份连接配置，需要与后端保持一致）。

### 角色权限

- **admin / operator**：可以编辑（`require_editor`）——包括修改模具、
  装卸模具、修改工艺参数目标值、清除预警、删除设备等所有写操作。
- **viewer**：只读，所有写接口会返回 403（"当前账号没有修改权限"）。
  前端会自动禁用对应的按钮/表单。

代码里没有区分 `admin` 和 `operator` 的权限（两者当前等效），仅作为
展示/分类用途，未来如需差异化权限可在 `security.require_editor` 中
细化。

### 停用 / 删除账号

- 停用：`UPDATE dbo.app_users SET is_active = 0 WHERE username = ?;`
  （不会清除历史操作记录里 `created_by`/`updated_by` 等外键引用）
- 目前没有专门删除账号的脚本/接口；若确需删除，注意
  `dbo.app_sessions` 对 `app_users(id)` 有 `ON DELETE CASCADE`，会一并
  清掉该用户的会话，但其它表（`molds.created_by`、
  `device_mold_assignments.operator_user_id` 等）多为普通外键，删除前
  需确认没有历史记录仍引用该用户 id，否则删除会失败或需要先置空。

### 修改密码

已登录用户可在网页右上角"修改密码"自助修改（`POST
/api/auth/change-password`，需要验证当前密码）。管理员无法代替他人重置
密码——如需强制重置，只能通过再次运行 `add_user.py`（会因用户名已存在
而报错）之外的方式，即直接用一段一次性脚本按 `password_digest()` 的同
样算法生成新哈希并 `UPDATE`。

### 登录 / 会话机制

- `POST /api/auth/login`：校验用户名密码，成功后生成随机
  token（`secrets.token_urlsafe(48)`），仅存储其 SHA-256 摘要于
  `dbo.app_sessions`，明文 token 通过 `httponly` Cookie
  （`mes_session`）下发给浏览器。
- 会话有效期由 `backend/config.py` 的 `SESSION_HOURS`（默认 12 小时）
  控制；登录时会顺带清理所有已过期会话。
- `POST /api/auth/logout`：删除对应会话记录并清除 Cookie。
- 所有需要登录的接口通过 `Depends(require_user)` 校验 Cookie 对应的
  会话是否有效且账号 `is_active`；未登录/会话失效会返回 401，前端会
  自动跳转回 `/login`。

---

## 配置

后端连接参数（`backend/config.py`）读取以下环境变量，未设置则使用默认值：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SQL_DRIVER` | `ODBC Driver 18 for SQL Server` | |
| `SQL_SERVER` | `localhost\SQLDEVELOP` | |
| `SQL_DATABASE` | `MES_MQTT` | |
| `SQL_USERNAME` / `SQL_PASSWORD` | 空（使用 Windows 集成认证） | 留空则用 `Trusted_Connection=yes` |
| `SQL_POOL_SIZE` | `8` | 数据库连接池大小 |

`mqtt_monitor.py` 的 MQTT/SQL 连接目前在脚本顶部硬编码（`MQTT_HOST`、
`MQTT_USERNAME`、`SQL_CONNECTION_STRING` 等），如需改为读环境变量，可
参考 `config.example.ps1` 的写法自行调整，或直接编辑脚本常量。

---

## 数据模型速览

- 设备（machine/device）不是一张独立的表，而是 `dbo.mqtt_messages` 中
  出现过的所有 `device_id` 去重后的集合；"删除设备"实质是清空该
  `device_id` 的全部历史数据并记入 `dbo.deleted_devices` 防止复活。
- 层级关系：**物理机台 → 模具 → 机型（Machine Type）→
  规格（工艺参数目标值 / 扩展字段 / 试模参数表模板）**。同一模具可以
  配置多个机型（不同机台跑同一模具但参数不同的场景），每台设备的当前
  装机记录（`dbo.device_mold_assignments`）会指定具体用哪个机型的规格
  做超差判断。
- 工艺参数字典集中在 `backend/parameter_labels.py`
  （`PARAMETER_LABELS`），前端 `frontend/js/app.js` 里的
  `PARAMETER_GRID_BLOCKS` 是同一套 tag 的分组/表格布局定义，两者需保持
  同步。