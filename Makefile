SHELL := /bin/bash

COMPOSE ?= docker compose
ENV_FILE ?= .env
COMPOSE_ARGS := --env-file $(ENV_FILE)

.PHONY: help init config build up demo down restart ps logs health ai-up model

help:
	@printf '%s\n' \
		'init       create .env from .env.example if it is missing' \
		'config     validate and print the resolved Compose configuration' \
		'build      build backend and frontend images' \
		'up         start the local stack in the background' \
		'demo       start with DEMO_MODE=true (the default local path)' \
		'ai-up      start the stack plus the optional local Ollama service' \
		'model      pull the configured local Ollama model' \
		'down       stop and remove containers (named data volumes remain)' \
		'restart    restart the application services' \
		'ps         show service state and health' \
		'logs       follow all service logs' \
		'health     check application and dependency health'

init:
	@if [[ ! -f $(ENV_FILE) ]]; then cp .env.example $(ENV_FILE); echo 'Created $(ENV_FILE). Review local credentials if needed.'; else echo '$(ENV_FILE) already exists.'; fi

config: init
	$(COMPOSE) $(COMPOSE_ARGS) config --quiet

build: init
	$(COMPOSE) $(COMPOSE_ARGS) build backend frontend

up: init
	$(COMPOSE) $(COMPOSE_ARGS) up -d --build

demo: init
	DEMO_MODE=true $(COMPOSE) $(COMPOSE_ARGS) up -d --build

ai-up: init
	DEMO_MODE=true $(COMPOSE) $(COMPOSE_ARGS) --profile ai up -d --build

model: init
	$(COMPOSE) $(COMPOSE_ARGS) --profile ai exec ollama ollama pull "$${OLLAMA_MODEL:-qwen2.5:3b}"

down: init
	$(COMPOSE) $(COMPOSE_ARGS) down

restart: init
	$(COMPOSE) $(COMPOSE_ARGS) restart backend frontend

ps: init
	$(COMPOSE) $(COMPOSE_ARGS) ps

logs: init
	$(COMPOSE) $(COMPOSE_ARGS) logs -f --tail=200

health: init
	bash scripts/healthcheck.sh
