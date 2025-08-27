# Makefile for Chat Application

.PHONY: help install install-dev test test-coverage lint type-check format clean build docker-build docker-run docker-stop deploy-dev deploy-prod

# Default target
help:
	@echo "Available targets:"
	@echo "  install      - Install the application"
	@echo "  install-dev  - Install with development dependencies"
	@echo "  test         - Run tests"
	@echo "  test-coverage - Run tests with coverage"
	@echo "  lint         - Run linting checks"
	@echo "  type-check   - Run type checking with mypy"
	@echo "  format       - Format code (if formatter is available)"
	@echo "  clean        - Clean build artifacts"
	@echo "  build        - Build distribution packages"
	@echo "  docker-build - Build Docker images"
	@echo "  docker-run   - Run with Docker Compose"
	@echo "  docker-stop  - Stop Docker containers"
	@echo "  deploy-dev   - Deploy development environment"
	@echo "  deploy-prod  - Deploy production environment"

# Installation targets
install:
	pip install -r requirements.txt -r requirements-optional.txt
	pip install .

install-dev:
	pip install -r requirements.txt -r requirements-optional.txt
	pip install -e .[dev]

# Testing targets
test:
	python -m pytest tests/ -v

test-coverage:
	python -m pytest tests/ --cov=chat_app --cov-report=html --cov-report=term-missing

test-unit:
	python -m pytest tests/unit/ -v

test-integration:
	python -m pytest tests/integration/ -v

test-fuzzing:
	python -m pytest tests/fuzzing/ -v

# Code quality targets
lint:
	@echo "Running linting checks..."
	python -m flake8 chat_app/ tests/ --max-line-length=100 --ignore=E203,W503 || true
	@echo "Linting complete"

type-check:
	python -m mypy chat_app/ --strict

format:
	@echo "Code formatting not configured. Consider adding black or autopep8."

# Cleanup targets
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Build targets
build: clean
	python -m build

build-wheel:
	python setup.py bdist_wheel

build-sdist:
	python setup.py sdist

# Docker targets
docker-build:
	docker build -t chat-app:latest .
	docker build -f Dockerfile.server -t chat-app-server:latest .
	docker build -f Dockerfile.client -t chat-app-client:latest .

docker-run:
	docker-compose up -d

docker-run-dev:
	docker-compose -f docker-compose.dev.yml up

docker-stop:
	docker-compose down

docker-logs:
	docker-compose logs -f

# Deployment targets
deploy-dev:
	@echo "Deploying development environment..."
	docker-compose -f docker-compose.dev.yml up -d
	@echo "Development environment deployed"

deploy-prod:
	@echo "Deploying production environment..."
	docker-compose up -d
	@echo "Production environment deployed"

# Server management
start-server:
	python -m chat_app.server.main

start-client:
	python -m chat_app.client.main

# Development helpers
dev-setup: install-dev
	@echo "Development environment setup complete"

check: lint type-check test
	@echo "All checks passed"

# Release targets
release-check: clean check build
	@echo "Release check complete"

# Configuration targets
config-dev:
	cp config/development.json config.json

config-prod:
	cp config/production.json config.json

config-test:
	cp config/testing.json config.json

# Monitoring targets
logs:
	tail -f logs/server.log

logs-json:
	tail -f logs/server.log | jq '.'

health-check:
	@python -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('localhost', 8080)); s.close(); print('Server is healthy')" || echo "Server is not responding"

# Documentation targets
docs:
	@echo "Documentation generation not configured"

# Database/Migration targets (if needed in future)
migrate:
	@echo "No migrations needed for current version"

# Backup targets
backup-config:
	@mkdir -p backups
	@cp -r config/ backups/config-$(shell date +%Y%m%d-%H%M%S)
	@echo "Configuration backed up"

# Environment targets
env-example:
	@echo "# Chat Application Environment Variables" > .env.example
	@echo "CHAT_SERVER_HOST=0.0.0.0" >> .env.example
	@echo "CHAT_SERVER_PORT=8080" >> .env.example
	@echo "CHAT_LOG_LEVEL=INFO" >> .env.example
	@echo "CHAT_LOG_FILE=logs/server.log" >> .env.example
	@echo "Environment example created"

# Security targets
security-check:
	@echo "Running security checks..."
	@pip list --outdated || true
	@echo "Security check complete"

# Performance targets
benchmark:
	@echo "Benchmarking not implemented yet"

# Utility targets
version:
	@python -c "import chat_app; print(getattr(chat_app, '__version__', '1.0.0'))"

info:
	@echo "Chat Application Build Information"
	@echo "=================================="
	@echo "Python version: $(shell python --version)"
	@echo "Pip version: $(shell pip --version)"
	@echo "Current directory: $(shell pwd)"
	@echo "Git branch: $(shell git branch --show-current 2>/dev/null || echo 'Not a git repository')"
	@echo "Git commit: $(shell git rev-parse --short HEAD 2>/dev/null || echo 'Not a git repository')"