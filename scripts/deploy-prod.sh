#!/bin/bash
# Üretim hostlarına config kopyalama iskeleti (ansible/ssh)
# Kullanım: ./scripts/deploy-prod.sh inventory/hosts.yaml
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INV="${1:-$ROOT/inventory/hosts.yaml}"

echo "Envanter: $INV"
echo
echo "Manuel adımlar (özet):"
echo "  1. lb1/lb2: keepalived + haproxy + ipvsadm kur"
echo "  2. keepalived-lb{1,2}.conf → /etc/keepalived/keepalived.conf"
echo "  3. haproxy.cfg → /etc/haproxy/haproxy.cfg"
echo "  4. hf1..3: rsyslog.conf + LVS-DR setup-lvs-dr.sh"
echo "  5. automation/ config + volume_pin.py → lb MASTER (cron */5)"
echo "  6. systemctl enable --now keepalived haproxy rsyslog"
echo
echo "Cron örneği (lb1):"
echo "  */5 * * * * root /usr/bin/python3 /opt/syslog-pin/volume_pin.py --config /etc/syslog-pin/config.yaml"
