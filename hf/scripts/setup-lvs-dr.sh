# HF gerçek sunucu (LVS-DR) — VIP'i loopback'e al
# Her HF hostunda boot sırasında çalıştırılır

VIP="10.20.0.100"
MASK="255.255.255.255"

# ARP cevaplarını bastır (DR için)
if [ -f /etc/sysctl.d/99-lvs-dr.conf ]; then
  sysctl -p /etc/sysctl.d/99-lvs-dr.conf >/dev/null 2>&1 || true
fi

ip addr show lo | grep -q "$VIP" || ip addr add ${VIP}/32 dev lo

# iptables: VIP'e gelen syslog'u kabul et
iptables -C INPUT -d "$VIP" -p udp --dport 514 -j ACCEPT 2>/dev/null || \
  iptables -A INPUT -d "$VIP" -p udp --dport 514 -j ACCEPT
iptables -C INPUT -d "$VIP" -p tcp --dport 514 -j ACCEPT 2>/dev/null || \
  iptables -A INPUT -d "$VIP" -p tcp --dport 514 -j ACCEPT

echo "[hf-dr] VIP $VIP bound on lo"
