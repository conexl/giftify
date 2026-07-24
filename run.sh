#!/usr/bin/env bash
set -e

# Переход в директорию скрипта
cd "$(dirname "$0")"

echo "=== Запуск приложения Giftify ==="

# Создание папок для сессий и базы данных
mkdir -p .secrets state

# Запуск API-сервера с авторестартом
echo "Запускаем Uvicorn API сервер на http://0.0.0.0:8000..."
export PYTHONPATH=src
exec .venv/bin/python -m uvicorn giftify.api:create_app --factory --host 0.0.0.0 --port 8000
