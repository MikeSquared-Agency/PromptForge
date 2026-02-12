FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY prompt_forge/ prompt_forge/
RUN pip install --no-cache-dir -e .

EXPOSE 8083

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8083/health || exit 1

CMD ["uvicorn", "prompt_forge.main:app", "--host", "0.0.0.0", "--port", "8083"]
