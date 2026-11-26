# Camada de agentes do Founders OS.
# Construa a partir da raiz do repositório, para a imagem levar as Skills junto:
#   docker build -f agentes/Dockerfile -t founders-agentes .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FOUNDERS_AGENTES_HOST=0.0.0.0 \
    FOUNDERS_AGENTES_PORTA=8787 \
    FOUNDERS_AGENTES_DADOS=/dados

RUN pip install --no-cache-dir "anthropic>=1,<2" "openpyxl>=3.1" \
    && useradd --create-home --uid 10001 agentes \
    && mkdir -p /dados && chown agentes /dados

WORKDIR /app
# As Skills e o catálogo são a fonte das instruções; o site fornece ícones e marca.
COPY .claude-plugin ./.claude-plugin
COPY plugins ./plugins
COPY catalogo.json ./catalogo.json
COPY site/icones.js ./site/icones.js
COPY site/img ./site/img
COPY agentes ./agentes

USER agentes
WORKDIR /app/agentes
EXPOSE 8787
VOLUME ["/dados"]
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/saude', timeout=4)"
CMD ["python", "-m", "founders_agentes", "servir"]
