# CMDB 私有化部署 (FastAPI + MySQL + Nginx + Redfish-mock)

整套 CMDB 平台的内网一键部署包。一台 Linux 主机上 `./deploy.sh` 即可起全栈：

| 服务 | 镜像 | 暴露端口 | 说明 |
| --- | --- | --- | --- |
| `web` | nginx 1.27 (前端打包) | 8080 → 80 | 控制台 + `/api` 反代 |
| `api` | 本地构建 (FastAPI) | 仅内网 | 业务逻辑、JWT、BMC 采集 |
| `mysql` | mysql:8.0 | 仅内网 | 资产 / 备件 / 流水 / 审计 |
| `redfish-mock` | dmtf/redfish-mockup-server | 仅内网 | 默认 BMC，用于演示和回退 |

> 只对外暴露 `WEB_PORT`（默认 8080），其余服务全部走 docker 内网，安全审计友好。

## 一、系统要求

- Linux x86_64 / arm64
- Docker Engine **24+**
- `docker compose` v2 plugin（`docker compose version` 能正常输出）
- 可访问公网，能 `docker pull` 镜像（如需离线请额外打包，本仓库未提供）

## 二、一键部署

```bash
# 把整个仓库 clone 到目标机器，然后：
cd reference-backend
./deploy.sh
```

完成后控制台访问：

- 控制台:        `http://<主机IP>:8080`
- API 文档:      `http://<主机IP>:8080/api/docs`
- 健康探针:      `http://<主机IP>:8080/healthz`

### 默认账号

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `admin123` | admin |
| `operator` | `123456` | operator |
| `viewer` | `123456` | viewer |

> 上线前请务必通过 系统设置 → 用户管理 修改密码或重置 SQL 中的 bcrypt hash。

## 三、常用运维命令

```bash
./deploy.sh up      # 启动 / 重新构建（默认）
./deploy.sh logs    # 滚动查看所有服务日志
./deploy.sh down    # 停止容器，保留数据
./deploy.sh reset   # 销毁数据库卷（不可恢复）
```

## 四、配置项 (.env)

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `WEB_PORT` | 8080 | 对宿主暴露的 HTTP 端口 |
| `MYSQL_*` | cmdb / cmdb123 / cmdb | 数据库账号 |
| `JWT_SECRET` | change-me-... | JWT 签名密钥（**生产务必替换**） |
| `JWT_TTL_HOURS` | 12 | Token 有效期 |
| `REDFISH_DEFAULT_BASE` | http://redfish-mock:8000 | 默认 BMC 端点 |
| `REDFISH_TIMEOUT_SECONDS` | 4 | Redfish 请求超时 |
| `POLL_INTERVAL_SECONDS` | 60 | 后台 BMC 巡检周期，0 关闭 |

## 五、对接真实 BMC

每台服务器记录里的字段：

- `mgmt_ip`：BMC 管理口 IP，前端"BMC IP"输入
- `bmc_protocol`：`redfish` 或 `ipmi`
- `bmc_user` / `bmc_password`：BMC 登录凭据
  - 密码字段当前未在前端表单暴露，请用 SQL 直接更新 `servers.bmc_password`，或在系统设置中扩展（已留 schema 字段）

`api` 容器内置 `httpx`（Redfish）+ `ipmitool`（IPMI）；当真实 BMC 不可达时会回落到模拟数据，UI 不会黑屏。

## 六、前端在云端 / 内网两种模式

前端构建时通过环境变量切换 API 后端：

```bash
# Enter Cloud 模式（默认，平台内继续验证）
pnpm run build

# 内网 FastAPI 模式（本部署包默认走此模式）
VITE_API_MODE=internal pnpm run build:prod
```

`Dockerfile.web` 已固定使用 internal 模式构建，无需手动设置。

## 七、目录结构

```
reference-backend/
├── deploy.sh                # 一键部署脚本
├── docker-compose.yml       # mysql + api + web + redfish-mock
├── Dockerfile               # FastAPI 镜像
├── Dockerfile.web           # Vite build → Nginx 镜像（构建上下文 = 仓库根）
├── nginx/default.conf       # SPA fallback + /api 反代
├── .env.example
├── init-db/
│   ├── 01_schema.sql        # MySQL DDL（与 Postgres 等价）
│   └── 02_seed.sql          # 8 服务器 + 10 备件 + 流水 + 3 账号
├── requirements.txt
└── app/
    ├── main.py              # FastAPI + APScheduler
    ├── settings.py
    ├── auth.py              # JWT + bcrypt + 角色守卫
    ├── db/{base,models}.py  # SQLAlchemy 2 ORM
    ├── schemas/             # Pydantic
    ├── services/
    │   ├── inventory.py     # 出/入/还/废库存联动
    │   └── bmc.py           # Redfish (httpx) + IPMI (ipmitool)
    └── api/                 # /api/auth /servers /parts /stock-movements /users /audit-logs
```

## 八、升级流程

```bash
git pull
./deploy.sh up   # 自动重新构建 web + api 镜像，mysql 数据卷保留
```

## 九、卸载

```bash
./deploy.sh reset   # 删除容器 + 数据卷
docker image prune  # 可选，清理无引用镜像
```
