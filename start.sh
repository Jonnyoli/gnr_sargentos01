#!/usr/bin/env bash
# start.sh — Inicia o FastAPI no Render
# Certifique-se de ter uvicorn instalado no requirements.txt

# Saia se qualquer comando falhar
set -e

# Mostra o comando que está rodando
echo "Iniciando FastAPI..."

# Usa a variável $PORT que o Render fornece
exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --reload
