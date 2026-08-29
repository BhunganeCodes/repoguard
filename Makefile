.PHONY: install test lint format format-check typecheck run docker-up docker-down

install:
	python -m pip install --upgrade pip
	pip install -e ".[dev]"

test:
	python -m pytest

lint:
	ruff check .

format:
	ruff format .

format-check:
	ruff format --check .

typecheck:
	mypy app evaluation

run:
	python -m uvicorn repoguard.main:app --reload

docker-up:
	docker compose up --build

docker-down:
	docker compose down