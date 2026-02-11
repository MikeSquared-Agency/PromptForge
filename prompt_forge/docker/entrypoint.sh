#!/bin/bash
set -e

# Read Docker Swarm secrets and export as environment variables
for secret_file in /run/secrets/*; do
    if [ -f "$secret_file" ]; then
        secret_name=$(basename "$secret_file")
        export_name=$(echo "$secret_name" | tr '[:lower:]' '[:upper:]')
        export "$export_name"="$(cat "$secret_file")"
        echo "Loaded secret: $secret_name → $export_name"
    fi
done

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/promptforge.conf
