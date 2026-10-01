#!/bin/bash
# Lab ayağa kaldır
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

chmod +x \
  lb/scripts/*.sh \
  hf/scripts/*.sh \
  scripts/*.sh \
  automation/volume_pin.py \
  scripts/generate-traffic.py 2>/dev/null || true

echo "==> docker compose build & up"
docker compose up -d --build

echo "==> durum"
docker compose ps
echo
echo "HAProxy stats: http://localhost:8404/stats  (admin/sysloglab)"
echo "TCP syslog (host→lb1): localhost:8514"
echo "Pin state volume: docker volume inspect \$(basename \$PWD)_pin_state"
