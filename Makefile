COMPOSE = docker compose -p cmdb

.PHONY: up down logs restart status build

# 构建前端并启动全部服务
up: build
	$(COMPOSE) up -d
	@echo ""
	@echo "========================================"
	@echo " 控制台:  http://localhost:${WEB_PORT:-8080}"
	@echo " API文档: http://localhost:${WEB_PORT:-8080}/api/docs"
	@echo "========================================"

# 停止全部服务
down:
	$(COMPOSE) down

# 重启服务（不重新构建前端）
restart:
	$(COMPOSE) restart

# 查看日志
logs:
	$(COMPOSE) logs -f --tail=200

# 查看服务状态
status:
	$(COMPOSE) ps

# 本地构建前端
build:
	VITE_API_MODE=internal pnpm run build:prod
