#!/bin/bash
set -euo pipefail

ROLE="${LB_ROLE:-master}"
CONF_SRC="/etc/keepalived/keepalived-${ROLE}.conf"

if [[ -f "$CONF_SRC" ]]; then
  cp "$CONF_SRC" /etc/keepalived/keepalived.conf
fi

# IP forward (LVS)
sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1 || true
sysctl -w net.ipv4.vs.conntrack=1 >/dev/null 2>&1 || true

# HAProxy
haproxy -f /etc/haproxy/haproxy.cfg -D -p /run/haproxy.pid

# Keepalived (foreground log)
mkdir -p /etc/keepalived/conf.d
[[ -f /etc/keepalived/conf.d/fwmark-pins.conf ]] || \
  echo "# empty pins" > /etc/keepalived/conf.d/fwmark-pins.conf

exec keepalived --dont-fork --log-console --log-detail -f /etc/keepalived/keepalived.conf
