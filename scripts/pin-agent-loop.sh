#!/bin/bash
# pin-agent döngüsü: periyodik volume_pin
set -euo pipefail
INTERVAL="${PIN_INTERVAL:-60}"
pip install -q pyyaml
while true; do
  echo "[pin-agent] $(date -Is) volume_pin çalışıyor…"
  python3 /opt/automation/volume_pin.py \
    --config /etc/syslog-pin/config.yaml \
    --vip 10.20.0.100 \
    --udp-port 514 || true
  sleep "$INTERVAL"
done
