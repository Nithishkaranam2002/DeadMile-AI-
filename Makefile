.PHONY: dev build up down seed parse-text parse-pdf db-reset logs clean help test-ingestion

COMPOSE := docker compose
ENV_FILE := .env
POSTGRES_USER := $(shell grep -E '^POSTGRES_USER=' $(ENV_FILE) 2>/dev/null | cut -d= -f2-)
POSTGRES_DB := $(shell grep -E '^POSTGRES_DB=' $(ENV_FILE) 2>/dev/null | cut -d= -f2-)
POSTGRES_USER := $(if $(POSTGRES_USER),$(POSTGRES_USER),deadmile)
POSTGRES_DB := $(if $(POSTGRES_DB),$(POSTGRES_DB),deadmile)

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-14s\033[0m %s\n", $$1, $$2}'

dev: ## Start full stack in development mode (build + up + logs)
	@if [ ! -f $(ENV_FILE) ]; then cp .env.example $(ENV_FILE) && echo "Created $(ENV_FILE) from .env.example"; fi
	$(COMPOSE) up --build -d
	@echo "DeadMile AI is starting. Run 'make logs' to follow output."
	@echo "  Frontend:    http://localhost:3000"
	@echo "  API Gateway: http://localhost:8000"
	@echo "  Agent Core:  http://localhost:8001"
	@echo "  Grafana:     http://localhost:3001"
	@echo "  Temporal UI: http://localhost:8080"

build: ## Build all Docker images
	$(COMPOSE) build

up: ## Start all containers (detached)
	@if [ ! -f $(ENV_FILE) ]; then cp .env.example $(ENV_FILE) && echo "Created $(ENV_FILE) from .env.example"; fi
	$(COMPOSE) up -d

down: ## Stop and remove all containers
	$(COMPOSE) down

seed: ## Run full data seeding pipeline (ingest → Kafka → DB → market scores)
	@echo "Running full seed pipeline..."
	$(COMPOSE) exec -T load-processor python /app/scripts/seed.py --mode http
	@echo "Seed complete."

parse-text: ## Parse text files and print ingestion stats
	$(COMPOSE) exec -T load-ingestion curl -sf -X POST http://localhost:8002/ingest/text | python3 -m json.tool

parse-pdf: ## Parse PDF files and print ingestion stats
	$(COMPOSE) exec -T load-ingestion curl -sf -X POST http://localhost:8002/ingest/pdf | python3 -m json.tool

db-reset: ## Drop and recreate all database tables
	@echo "Resetting database..."
	$(COMPOSE) exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -f /docker-entrypoint-initdb.d/002_reset.sql
	$(COMPOSE) exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -f /docker-entrypoint-initdb.d/001_init.sql
	@echo "Database reset complete."

test-ingestion: ## Run load-ingestion unit tests
	cd services/load-ingestion && pip install -q -r requirements.txt && PYTHONPATH="../../:." pytest tests/ -v

logs: ## Tail logs from all services
	$(COMPOSE) logs -f --tail=100

logs-%: ## Tail logs from a specific service (e.g. make logs-api-gateway)
	$(COMPOSE) logs -f --tail=100 $*

clean: ## Stop containers and remove volumes (destructive)
	@echo "WARNING: This removes all data volumes."
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	$(COMPOSE) down -v --remove-orphans
	@echo "Clean complete."

ps: ## Show container status
	$(COMPOSE) ps

restart: ## Restart all services
	$(COMPOSE) restart

health: ## Check health of all services
	@for port in 8000 8001 8002 8003 8004 8005 3000; do \
		printf "Port $$port: "; \
		curl -sf "http://localhost:$$port/health" > /dev/null 2>&1 && echo "OK" || echo "FAIL"; \
	done
