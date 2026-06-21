.PHONY: help dev demo build up down start stop restart seed seed-vectors train-models setup validate logs logs-agent logs-gateway clean ps health test test-ingestion parse-text parse-pdf db-reset

COMPOSE := docker compose
COMPOSE_FULL := docker compose --profile full
ENV_FILE := .env
POSTGRES_USER := $(shell grep -E '^POSTGRES_USER=' $(ENV_FILE) 2>/dev/null | cut -d= -f2-)
POSTGRES_DB := $(shell grep -E '^POSTGRES_DB=' $(ENV_FILE) 2>/dev/null | cut -d= -f2-)
POSTGRES_USER := $(if $(POSTGRES_USER),$(POSTGRES_USER),deadmile)
POSTGRES_DB := $(if $(POSTGRES_DB),$(POSTGRES_DB),deadmile)

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

start: up ## Start core containers (alias)

stop: down ## Stop all containers (alias)

dev: ## Light mode — core services only (~8 containers)
	@if [ ! -f $(ENV_FILE) ]; then cp .env.example $(ENV_FILE) && echo "Created $(ENV_FILE) from .env.example"; fi
	$(COMPOSE) up --build -d
	@echo "DeadMile AI (light mode) is starting."
	@echo "  Frontend:    http://localhost:3000"
	@echo "  API Gateway: http://localhost:8010/docs"
	@echo "  For full demo: make demo"

demo: ## Full mode — all 19 containers (for demos)
	@if [ ! -f $(ENV_FILE) ]; then cp .env.example $(ENV_FILE) && echo "Created $(ENV_FILE) from .env.example"; fi
	$(COMPOSE_FULL) up --build -d
	@echo "DeadMile AI (full stack) is starting."
	@echo "  Frontend:    http://localhost:3000"
	@echo "  Nginx:       http://localhost:8888"
	@echo "  API Gateway: http://localhost:8010/docs"
	@echo "  Grafana:     http://localhost:3001"
	@echo "  Temporal UI: http://localhost:8081"
	@echo "  Kafka UI:    http://localhost:8090"

build: ## Build all Docker images
	$(COMPOSE_FULL) build

up: ## Start core containers (detached)
	@if [ ! -f $(ENV_FILE) ]; then cp .env.example $(ENV_FILE) && echo "Created $(ENV_FILE) from .env.example"; fi
	$(COMPOSE) up -d

down: ## Stop and remove all containers
	$(COMPOSE_FULL) down

restart: ## Restart all services
	$(COMPOSE_FULL) restart

validate: ## Validate required .env variables
	python3 scripts/validate_env.py

setup: demo seed seed-vectors train-models ## Full first-time demo setup
	@echo ""
	@echo "DeadMile AI is ready!"
	@echo "  Frontend: http://localhost:3000"
	@echo "  API Docs: http://localhost:8010/docs"
	@echo "  Grafana:  http://localhost:3001"
	@echo "  Temporal: http://localhost:8081"
	@echo ""
	@echo "See DEMO.md for the 5-minute walkthrough."

seed: ## Run full data seeding pipeline (requires full profile)
	@echo "Running full seed pipeline..."
	$(COMPOSE_FULL) exec -T load-processor python /app/scripts/seed.py --mode http
	@echo "Seed complete."

seed-vectors: ## Seed Qdrant vector store for semantic search
	curl -sf -X POST http://localhost:8001/seed-vectors | python3 -m json.tool || echo "Agent core not ready yet"

train-models: ## Train rate prediction models
	curl -sf -X POST http://localhost:8005/rates/train | python3 -m json.tool || echo "Market intelligence not ready yet"

parse-text: ## Parse text files and print ingestion stats
	$(COMPOSE_FULL) exec -T load-ingestion curl -sf -X POST http://localhost:8002/ingest/text | python3 -m json.tool

parse-pdf: ## Parse PDF files and print ingestion stats
	$(COMPOSE_FULL) exec -T load-ingestion curl -sf -X POST http://localhost:8002/ingest/pdf | python3 -m json.tool

db-reset: ## Drop and recreate all database tables
	@echo "Resetting database..."
	$(COMPOSE) exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -f /docker-entrypoint-initdb.d/002_reset.sql
	$(COMPOSE) exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -f /docker-entrypoint-initdb.d/001_init.sql
	$(COMPOSE) exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -f /docker-entrypoint-initdb.d/003_production.sql
	@echo "Database reset complete."

db-migrate-prod: ## Apply production schema (carrier profiles, audit)
	@echo "Applying production migration..."
	$(COMPOSE) exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -f /docker-entrypoint-initdb.d/003_production.sql
	@echo "Production schema ready."

test-ingestion: ## Run load-ingestion unit tests
	cd services/load-ingestion && pip install -q -r requirements.txt && PYTHONPATH="../../:." pytest tests/ -v

test: ## Run api-gateway tests (when available)
	@echo "No api-gateway tests yet — use make test-ingestion"

logs: ## Tail logs from all services
	$(COMPOSE_FULL) logs -f --tail=100

logs-agent: ## Tail agent-core logs
	$(COMPOSE_FULL) logs -f --tail=100 agent-core

logs-gateway: ## Tail api-gateway logs
	$(COMPOSE_FULL) logs -f --tail=100 api-gateway

logs-%: ## Tail logs from a specific service (e.g. make logs-api-gateway)
	$(COMPOSE_FULL) logs -f --tail=100 $*

clean: ## Stop containers and remove volumes (destructive)
	@echo "WARNING: This removes all data volumes."
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	$(COMPOSE_FULL) down -v --remove-orphans
	@echo "Clean complete."

ps: ## Show container status
	$(COMPOSE_FULL) ps

health: ## Check health of all services via gateway
	@curl -sf http://localhost:8000/health/all | python3 -m json.tool 2>/dev/null || \
	for port in 8000 8001 8002 8003 8004 8005 3000; do \
		printf "Port $$port: "; \
		curl -sf "http://localhost:$$port/health" > /dev/null 2>&1 && echo "OK" || echo "FAIL"; \
	done
