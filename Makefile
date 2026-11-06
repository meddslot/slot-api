.PHONY: up down build migrate logs test lint fmt

## Start the full stack: build images, run migrations, then start all services.
up:
	docker compose up --build -d migrate
	docker compose up --build -d api

## Stop and remove containers (keeps volumes).
down:
	docker compose down

## Build images without starting anything.
build:
	docker compose build

## Run migrations inside Docker against the compose DB.
migrate:
	docker compose run --rm migrate

## Tail logs for all services.
logs:
	docker compose logs -f

## Run the test suite locally.
test:
	uv run pytest -W error::DeprecationWarning -v

## Check linting.
lint:
	uv run ruff check .

## Auto-format all source files.
fmt:
	uv run ruff format .
