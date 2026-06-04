# CMDB 主机资产管理平台 — 私有化部署文档

## 目录

- [1. 系统要求](#1-系统要求)
- [2. 环境初始化](#2-环境初始化)
- [3. 获取部署包](#3-获取部署包)
- [4. 在线部署（推荐）](#4-在线部署推荐)
- [5. 离线部署（无外网环境）](#5-离线部署无外网环境)
- [6. 部署后验证](#6-部署后验证)
- [7. HTTPS 配置](#7-https-配置)
- [8. 日常运维](#8-日常运维)
- [9. 升级指南](#9-升级指南)
- [10. 常见问题](#10-常见问题)

---

## 1. 系统要求

| 项目 | 最低要求 | 推荐配置 |
|------|---------|---------|
| 操作系统 | Ubuntu 20.04+ / Debian 11+ / CentOS 7+ / RHEL 8+ | Ubuntu 22.04 LTS |
| CPU | 2 核 | 4 核+ |
| 内存 | 4 GB | 8 GB+ |
| 磁盘 | 20 GB | 50 GB+ (SSD) |
| Docker | 24.0+ | 27.0+ |
| Docker Compose | v2 (插件版) | v2.30+ |
| 网络 | 能访问镜像仓库（在线部署）/ 端口已放行 |

> **注意**：Docker Compose v1（`docker-compose` 命令）已停止维护，本文档使用 `docker compose`（无连字符的 v2 版本）。

## 2. 环境初始化

### 2.1 安装 Docker

```bash
# 使用 Docker 官方一键安装脚本
curl -fsSL https://get.docker.com | bash

# 启动 Docker 并设置开机自启
sudo systemctl enable docker
sudo systemctl start docker

# 将当前用户加入 docker 组，避免每次使用 sudo
sudo usermod -aG docker $USER
# 退出重新登录使权限生效
```

### 2.2 安装 Docker Compose v2 插件

```bash
# Ubuntu / Debian
sudo apt update
sudo apt install -y docker-compose-v2

# CentOS / RHEL / Fedora
sudo yum install -y docker-compose-plugin

# 验证安装
docker compose version
# 输出示例: Docker Compose version v2.30.3
```

### 2.3 防火墙放行端口

```bash
# 默认 WEB_PORT，按实际修改
sudo ufw allow 8080/tcp    # Ubuntu/Debian
# 或
sudo firewall-cmd --add-port=8080/tcp --permanent   # CentOS/RHEL
sudo firewall-cmd --reload
```

### 2.4 系统参数调优（可选）

```bash
# 调整 vm.max_map_count（Elasticsearch 等场景需要，MySQL 非必需但建议设置）
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# 如果服务器内存较小，建议配置 swap（Docker 宿主机推荐最少 2GB swap）
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab
```

## 3. 获取部署包

### 3.1 在线部署 — 克隆代码

```bash
# 在目标服务器上
cd /opt
git clone <你的仓库地址> cmdb
cd cmdb
```

### 3.2 离线部署 — 制作部署包

在一台能访问外网的机器上构建离线包：

```bash
# 在开发机上
cd /path/to/enter-ServerAssetSpares
./export-for-offline.sh
# 生成 cmdb-offline.tar.gz（约 1-2 GB）
```

将部署包传输到目标服务器：

```bash
scp cmdb-offline.tar.gz user@目标服务器IP:/opt/
```

在目标服务器上解压：

```bash
cd /opt
tar xzf cmdb-offline.tar.gz
cd cmdb
```

## 4. 在线部署（推荐）

本方式从源码构建所有镜像，适用于目标服务器有外网访问能力。

### 4.1 部署架构

```
                    Internet / 内网
                          │
                    ┌─────▼──────┐
                    │   Nginx    │  :8080 (对外)
                    │  (web)     │
                    │  SPA +     │
                    │  反向代理  │
                    └─────┬──────┘
                          │ /api → proxy_pass
                    ┌─────▼──────┐
                    │  FastAPI   │  :8000 (仅容器网络)
                    │  (api)     │
                    └─────┬──────┘
                          │
                    ┌─────▼──────┐
                    │  MySQL 8.0 │  :3306 (仅容器网络)
                    │  (mysql)   │
                    └─┬──────┬──┘
                      │      │
              mysql-data    init-db/
                volume      自动初始化
```

三个核心服务，web 容器对外暴露唯一端口，api 和 mysql 仅容器网络内通信，安全隔离。

### 4.2 一键部署

```bash
cd /opt/cmdb

# 使用 reference-backend 目录下的 docker-compose.yml（完整构建）
cd reference-backend
./deploy.sh
```

脚本会自动完成：
1. 检测 Docker 和 docker compose 是否安装
2. 从 `.env.example` 复制创建 `.env`（首次）
3. 自动生成 64 位随机 JWT_SECRET
4. 设置 `.env` 文件权限为 600
5. `docker compose up -d --build` 构建并启动所有服务
6. MySQL 容器首次启动时自动执行 `init-db/` 下的 SQL 初始化脚本

### 4.3 部署成功标志

```
================================================================
 CMDB 私有化部署完成
----------------------------------------------------------------
 控制台:        http://<服务器IP>:8080
 API 文档:      http://<服务器IP>:8080/api/docs
 健康检查:      http://<服务器IP>:8080/healthz

 默认账号:
   admin    / admin123     管理员
   operator / 123456       运维
   viewer   / 123456       只读
================================================================
```

### 4.4 登录后立即修改密码

管理员首次登录后，请立即修改所有默认账号的密码。进入控制台 → 用户管理 → 修改密码。

## 5. 离线部署（无外网环境）

适用于目标服务器完全隔离、无法访问 Docker Hub 和 npm registry 的场景。

### 5.1 文件说明

离线部署包 `cmdb-offline.tar.gz` 包含：

| 文件 | 说明 |
|------|------|
| `cmdb-images.tar` | 所有 Docker 镜像（mysql、python、node、nginx、api） |
| `dist/` | 预构建的前端静态文件 |
| `docker-compose.yml` | 使用预构建镜像的 Compose 编排文件 |
| `reference-backend/.env.example` | 环境变量模板 |
| `reference-backend/init-db/` | 数据库初始化 SQL 脚本 |
| `reference-backend/nginx/` | Nginx 配置文件 |
| `deploy-offline.sh` | 离线部署脚本 |
| `update.sh` | 离线升级脚本 |

### 5.2 部署步骤

```bash
# 1. 解压
cd /opt
tar xzf cmdb-offline.tar.gz
cd cmdb

# 2. 运行离线部署脚本
./deploy-offline.sh
```

脚本执行流程：

1. **前置检查** — 验证 Docker、docker compose 已安装，`cmdb-images.tar` 存在
2. **导入镜像** — `docker load -i cmdb-images.tar`（首次需几分钟）
3. **初始化 .env** — 从 `.env.example` 复制，自动生成 JWT_SECRET
4. **启动服务** — `docker compose up -d`

### 5.3 离线部署的 docker-compose.yml

```yaml
# 根目录的 docker-compose.yml（离线部署使用）
services:
  mysql:
    image: mysql:8.0
    # ... 同上

  api:
    image: reference-backend-api:latest    # 预构建镜像，无需 build
    # ...

  web:
    image: nginx:latest
    volumes:
      - ./dist:/usr/share/nginx/html:ro    # 挂载预构建的 dist/
      - ./reference-backend/nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
    # ...
```

> 在线部署时 web 容器是 `build` 模式（用 Dockerfile.web 多阶段构建前端），离线部署时改为直接挂载 `dist/` 目录，因此无需 Node.js 环境或 pnpm。

## 6. 部署后验证

### 6.1 快速健康检查

```bash
# 检查服务状态
docker compose -f docker-compose.yml -p cmdb ps

# 输出示例:
# NAME              STATUS
# cmdb-mysql-1      Up (healthy)
# cmdb-api-1        Up
# cmdb-web-1        Up

# 查看日志
docker compose -f docker-compose.yml -p cmdb logs --tail=50
```

### 6.2 API 端点验证

```bash
# 健康检查（无需认证）
curl http://<服务器IP>:8080/healthz
# 返回: {"ok":true}

# API 文档（无需认证）
curl -s http://<服务器IP>:8080/api/docs
# 返回 OpenAPI JSON

# 登录获取 Token
curl -X POST http://<服务器IP>:8080/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 获取服务器列表（需要 Token）
curl http://<服务器IP>:8080/api/servers \
  -H "Authorization: Bearer <上一步返回的 access_token>"
```

### 6.3 使用验证脚本

```bash
# 完整 API 验证（需要 python3）
./verify-api.sh http://<服务器IP>:8080

# 如果配置了 AI_API_KEY
./verify-api.sh http://<服务器IP>:8080 "sk-your-ai-key"
```

## 7. HTTPS 配置

生产环境强烈建议配置 HTTPS。参考 `reference-backend/nginx/default-https.conf.example`。

### 7.1 准备证书

```bash
mkdir -p reference-backend/nginx/certs

# 将证书文件放入
#   reference-backend/nginx/certs/fullchain.pem
#   reference-backend/nginx/certs/privkey.pem

# 设置权限
chmod 600 reference-backend/nginx/certs/privkey.pem
```

### 7.2 修改 docker-compose.yml

编辑 `reference-backend/docker-compose.yml`，修改 web 服务配置：

```yaml
  web:
    # ...
    ports:
      - "443:443"
      - "80:80"            # HTTP → HTTPS 跳转用
    volumes:
      # 挂载 HTTPS 配置（替换 HTTP 配置）
      - ./nginx/default-https.conf:/etc/nginx/conf.d/default.conf:ro
      - ./nginx/certs:/etc/nginx/certs:ro
```

### 7.3 修改 HTTPS 配置文件

编辑 `reference-backend/nginx/default-https.conf.example`，修改 `server_name` 为实际域名，然后重命名为 `default-https.conf`。

重启 web 容器：

```bash
docker compose -f reference-backend/docker-compose.yml -p cmdb up -d --force-recreate web
```

## 8. 日常运维

### 8.1 环境变量说明

所有配置在 `reference-backend/.env` 中，以下是完整说明：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MYSQL_ROOT_PASSWORD` | `rootpw` | MySQL root 密码，**生产环境必须修改** |
| `MYSQL_HOST` | `mysql` | MySQL 主机名（容器网络内不变） |
| `MYSQL_PORT` | `3306` | MySQL 端口 |
| `MYSQL_USER` | `cmdb` | 应用数据库用户 |
| `MYSQL_PASSWORD` | `cmdb123` | 应用数据库密码，**生产环境必须修改** |
| `MYSQL_DATABASE` | `cmdb` | 数据库名 |
| `JWT_SECRET` | 自动生成 | JWT 签名密钥，部署时自动生成 64 位随机串 |
| `JWT_ALG` | `HS256` | JWT 签名算法 |
| `JWT_TTL_HOURS` | `12` | Token 有效期（小时） |
| `WEB_PORT` | `8080` | 对外暴露的 Web 端口 |
| `CORS_ORIGINS` | `*` | CORS 允许的来源（同源部署用 `*`） |
| `REDFISH_DEFAULT_BASE` | `http://redfish-mock:8000` | 默认 BMC Redfish 地址 |
| `REDFISH_TIMEOUT_SECONDS` | `15` | Redfish 请求超时（秒） |
| `AI_API_KEY` | (空) | AI 查询接口的 API Key，用于飞书 Aily/Dify 集成 |
| `POLL_INTERVAL_SECONDS` | `60` | BMC 后台轮询间隔（秒），0 禁用 |

修改 `.env` 后重启 API 容器使配置生效：

```bash
docker compose -f docker-compose.yml -p cmdb restart api
```

### 8.2 服务管理

```bash
# 使用 deploy.sh（在线）/ deploy-offline.sh（离线）

./deploy.sh status     # 或 ./deploy-offline.sh status
./deploy.sh logs       # 查看实时日志
./deploy.sh down       # 停止所有服务（保留数据卷）
./deploy.sh reset      # 停止并清空数据库（危险操作！）
```

### 8.3 数据库备份

```bash
# 备份（自动保存到 backups/ 目录）
./deploy.sh backup
# 生成: backups/cmdb-backup-20260526-143000.sql.gz

# 从备份恢复
./deploy.sh restore backups/cmdb-backup-20260526-143000.sql.gz
```

建议设置 crontab 定时备份：

```bash
# 每天凌晨 2 点自动备份
crontab -e
# 添加:
0 2 * * * cd /opt/cmdb && ./deploy.sh backup >> backups/cron.log 2>&1
```

### 8.4 数据库手动操作

```bash
# 进入 MySQL 容器
docker compose -f docker-compose.yml -p cmdb exec mysql mysql -u cmdb -pcmdb123 cmdb

# 直接执行 SQL
docker compose -f docker-compose.yml -p cmdb exec -T mysql \
  mysql -u cmdb -pcmdb123 cmdb -e "SHOW TABLES;"
```

### 8.5 日志查看

```bash
# 全部服务日志
./deploy.sh logs

# 仅查看 API 日志
docker compose -f docker-compose.yml -p cmdb logs -f api

# 仅查看 MySQL 日志
docker compose -f docker-compose.yml -p cmdb logs -f mysql
```

### 8.6 容器资源监控

```bash
# 实时资源使用
docker stats

# 磁盘使用
docker system df
docker system df -v   # 详细
```

### 8.7 磁盘清理

```bash
# 清理未使用的镜像、容器、网络（不影响运行中的服务）
docker system prune -f

# 清理构建缓存（释放更多空间）
docker builder prune -f
```

## 9. 升级指南

### 9.1 在线升级（update.sh）

```bash
# 获取最新的 GitHub zip 包
# 例如: enter-ServerAssetSpares-enter-main.zip

# 运行升级脚本
./update.sh /path/to/enter-ServerAssetSpares-enter-main.zip
```

升级脚本执行流程：
1. **备份数据库** → `backups/pre-update-<时间戳>.sql.gz`
2. **备份 .env** → 保留当前环境配置
3. **解压 zip** → 覆盖源代码
4. **优先使用预构建 dist/** → 跳过编译（zip 包中自带）
5. **后端热更新** → `docker cp` 将新代码注入 api 容器
6. **重建 web 镜像** → 包含新的 dist/
7. **重启 api + web** → 应用变更

### 9.2 离线升级

将新版本的 `cmdb-offline.tar.gz` 传输到服务器，然后：

```bash
# 备份当前数据
./deploy-offline.sh backup

# 解压新版
tar xzf cmdb-offline.tar.gz

# 导入新镜像（如更新）
docker load -i cmdb-images.tar

# 重新部署
./deploy-offline.sh
```

### 9.3 数据库迁移

如果新版本包含数据库变更，需要手动执行 SQL 脚本：

```bash
# 运行迁移脚本
docker compose -f docker-compose.yml -p cmdb exec -T mysql \
  mysql -u cmdb -pcmdb123 cmdb < reference-backend/init-db/03_part_items.sql
```

> 新部署时 MySQL 容器会自动按文件名顺序执行 `init-db/` 下所有 `.sql` 文件。已运行的数据库需要手动执行新增的 SQL 脚本。

## 10. 常见问题

### Q: 端口 8080 被占用

修改 `reference-backend/.env` 中的 `WEB_PORT`：

```bash
WEB_PORT=9090
```

然后重启：

```bash
docker compose -f reference-backend/docker-compose.yml -p cmdb up -d --force-recreate web
```

### Q: MySQL 容器启动失败 — "Different lower_case_table_names"

MySQL 8.0 的 `lower_case_table_names` 必须在首次初始化时设置，之后不可更改。如果需要修改：

```bash
# 清空数据库重新初始化
./deploy.sh reset
# 然后再启动
./deploy.sh
```

### Q: 前端页面正常但 API 请求 502

```bash
# 检查 api 容器状态
docker compose -f docker-compose.yml -p cmdb ps api

# 查看 api 日志
docker compose -f docker-compose.yml -p cmdb logs api --tail=100

# 常见原因:
# 1. MySQL 健康检查未通过 — 等 MySQL 状态变为 healthy 后 api 才启动
# 2. .env 中数据库密码不匹配
# 3. api 镜像构建失败 — 检查 Dockerfile 构建日志
```

### Q: 中文字符显示乱码（Mojibake）

系统的 docker-compose.yml 已配置 MySQL 强制 utf8mb4：

```yaml
command:
  - --character-set-server=utf8mb4
  - --collation-server=utf8mb4_unicode_ci
  - --skip-character-set-client-handshake
```

如果仍有问题，检查数据来源端是否使用了正确的连接字符集。

### Q: JWT Token 过期

默认有效期 12 小时。过期后需重新登录。可在 `.env` 中调整：

```bash
JWT_TTL_HOURS=24
```

### Q: 忘记管理员密码

```bash
# 使用 MySQL 重置密码
docker compose -f docker-compose.yml -p cmdb exec mysql mysql -u root -p<root密码> cmdb

# 生成新 bcrypt 哈希（Python）
python3 -c "
from passlib.context import CryptContext
ctx = CryptContext(schemes=['bcrypt'])
print(ctx.hash('新密码'))
"

# 更新密码
UPDATE profiles SET password_hash = '<上面的哈希值>' WHERE username = 'admin';
```

### Q: 检查 Redfish Mock 状态（开发环境）

```bash
# 启动 Mock 服务器
./deploy.sh mock-on

# 停止
./deploy.sh mock-off
```

> Redfish Mock 仅用于开发/演示，生产环境不需要。

### Q: Docker 镜像占用过多磁盘

```bash
# 查看各组件占用
docker system df -v

# 清理无用镜像和构建缓存
docker image prune -a -f
docker builder prune -a -f

# 保留最近 3 天的日志
echo '{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}' \
  | sudo tee /etc/docker/daemon.json
sudo systemctl restart docker
```

---

## 附录 A：完整部署命令速查

```bash
# === 首次部署 ===
# 在线
cd /opt/cmdb/reference-backend && ./deploy.sh

# 离线
cd /opt/cmdb && ./deploy-offline.sh

# === 日常操作 ===
./deploy.sh status          # 查看状态
./deploy.sh logs            # 实时日志
./deploy.sh backup          # 备份数据库
./deploy.sh down            # 停止服务
./deploy.sh up              # 启动服务

# === 升级 ===
./update.sh <新版本zip包路径>

# === 直接 docker compose 命令 ===
docker compose -f docker-compose.yml -p cmdb ps          # 容器状态
docker compose -f docker-compose.yml -p cmdb restart api # 重启 API
docker compose -f docker-compose.yml -p cmdb logs -f     # 日志流

# === API 验证 ===
./verify-api.sh http://<IP>:8080
```

## 附录 B：目录结构说明

```
/opt/cmdb/
├── docker-compose.yml          # Docker Compose 编排文件
├── deploy.sh                   # 在线部署脚本
├── deploy-offline.sh           # 离线部署脚本
├── update.sh                   # 升级脚本
├── verify-api.sh               # API 验证脚本
├── Makefile                    # make 快捷命令
├── dist/                       # 前端构建产物（预构建或 build 生成）
│   ├── index.html
│   └── assets/
├── reference-backend/
│   ├── Dockerfile              # API 镜像构建文件
│   ├── Dockerfile.web          # Web 镜像构建文件（多阶段构建前端+Nginx）
│   ├── docker-compose.yml      # 在线部署 Compose 文件（含 build 指令）
│   ├── deploy.sh               # 后端独立部署脚本
│   ├── .env                    # 环境变量（敏感信息，权限 600）
│   ├── .env.example            # 环境变量模板
│   ├── requirements.txt        # Python 依赖清单
│   ├── app/                    # FastAPI 应用代码
│   │   ├── main.py             # 应用入口（FastAPI 实例、lifespan、路由注册）
│   │   ├── settings.py         # pydantic-settings 配置类
│   │   ├── auth.py             # JWT 认证逻辑
│   │   ├── api/                # API 路由（servers、parts、auth_users、ai_query）
│   │   ├── db/                 # 数据库（SQLAlchemy ORM 模型、session）
│   │   ├── schemas/            # Pydantic 数据模型
│   │   └── services/           # 业务逻辑（BMC Redfish/IPMI 采集器）
│   ├── init-db/                # 数据库初始化 SQL 脚本
│   │   ├── 01_schema.sql       # 建表语句
│   │   ├── 02_seed.sql         # 种子数据
│   │   └── ...
│   └── nginx/
│       ├── default.conf        # Nginx HTTP 配置
│       └── default-https.conf.example  # HTTPS 配置模板
├── src/                        # React 前端源代码
├── backups/                    # 数据库备份目录
└── cmdb-images.tar             # 离线镜像包（仅离线部署）
```
