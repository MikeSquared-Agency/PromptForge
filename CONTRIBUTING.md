# Contributing to PromptForge

## Getting Started

1. Fork the repo and clone locally
2. Create a virtual environment: `python -m venv .venv && source .venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and configure
5. Run tests: `make test`

## Development

- Use `make dev` for hot-reload development server
- Run `make lint` before committing
- Write tests for new features in `tests/`

## Code Style

- Python 3.12+ with full type hints
- Pydantic models for all request/response schemas
- Docstrings on all public functions
- structlog for logging (no print statements)

## Pull Requests

1. Create a feature branch from `main`
2. Write tests
3. Ensure `make test` and `make lint` pass
4. Submit PR with clear description

## Architecture

See [SPEC.md](SPEC.md) and [docs/architecture.md](docs/architecture.md) for design details.
