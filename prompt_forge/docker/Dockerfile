FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY prompt_forge/ ./prompt_forge/

COPY prompt_forge/docker/supervisord.conf /etc/supervisor/conf.d/promptforge.conf
COPY prompt_forge/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8400

ENTRYPOINT ["/entrypoint.sh"]
