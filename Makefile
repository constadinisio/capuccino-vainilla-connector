.PHONY: help install dev test cov lint type check sync serve docker

help:
	@echo "Targets disponibles:"
	@echo "  install   Instala el paquete (runtime)"
	@echo "  dev       Instala el paquete + dependencias de desarrollo"
	@echo "  test      Ejecuta la suite de tests"
	@echo "  cov       Tests con reporte de cobertura"
	@echo "  lint      Linter (ruff)"
	@echo "  type      Chequeo de tipos (mypy)"
	@echo "  check     lint + type + cov (lo que corre la CI)"
	@echo "  sync      Sincroniza el catálogo (Odoo -> Woo)"
	@echo "  serve     Levanta el servidor de webhooks"
	@echo "  docker    Construye la imagen Docker"

install:
	pip install .

dev:
	pip install -e ".[dev]"

test:
	pytest

cov:
	pytest --cov --cov-report=term-missing --cov-fail-under=80

lint:
	ruff check src tests

type:
	mypy

check: lint type cov

sync:
	capuccino-vainilla sync-catalog

serve:
	capuccino-vainilla serve

docker:
	docker build -t capuccino-vainilla:latest .
