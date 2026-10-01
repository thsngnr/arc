#!/bin/bash
set -euo pipefail

# LVS-DR VIP setup (privileged container'da)
if [[ "${ENABLE_LVS_DR:-1}" == "1" ]]; then
  /usr/local/bin/setup-lvs-dr.sh || true
fi

mkdir -p /var/log/remote
rm -f /var/run/rsyslogd.pid

# rsyslog foreground
exec rsyslogd -n -f /etc/rsyslog.conf
