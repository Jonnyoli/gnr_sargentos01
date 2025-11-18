#!/bin/bash
# Permite que o container use a porta do Render
echo "Starting FastAPI on port $PORT..."

# Executa o Uvicorn com host 0.0.0.0 e porta do Render
exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --reload
