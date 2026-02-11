.PHONY: dev run test lint docker-build

dev:
	uvicorn prompt_forge.main:app --host 0.0.0.0 --port 8400 --reload

run:
	uvicorn prompt_forge.main:app --host 0.0.0.0 --port 8400

test:
	pytest tests/ -v

lint:
	ruff check prompt_forge/ tests/
	ruff format --check prompt_forge/ tests/

format:
	ruff format prompt_forge/ tests/

docker-build:
	docker build -f prompt_forge/docker/Dockerfile -t promptforge:latest .
