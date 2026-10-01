# İşletim Notları

## Manuel (statik) pin

Kaynak listesi sabitse `automation/config.yaml`:

```yaml
static_pins:
  - source_ip: 192.168.10.1
    hf: hf1
  - source_ip: 192.168.10.2
    hf: hf2
  - source_ip: 192.168.10.3
    hf: hf3
top_n: 3
```

`volume_pin.py` statik pinleri önce yerleştirir; kalan slotları otomatik keşifle doldurur.

## Otomatik pin döngüsü

1. HF'lerde `/var/log/remote/<ip>/` satır sayımı (pencere: `window_seconds`)
2. `top_n` ağır kaynağı HF'lere round-robin
3. `/etc/syslog-pin/apply-fwmark.sh` + `/etc/keepalived/conf.d/fwmark-pins.conf`
4. iptables uygula, keepalived HUP/reload

Durum: `/var/lib/syslog-pin/state.json` ve `pin-map.json`

## Failover kontrol

```bash
# VIP hangi LB'de?
ip -br addr show | grep 10.20.0.100

# LVS tablosu
ipvsadm -Ln

# HAProxy
curl -u admin:sysloglab http://VIP:8404/stats
```

## HF disk düzeni

```
/var/log/remote/
  192.168.10.1/syslog.log
  192.168.10.2/syslog.log
  …
```

Logrotate önerisi: `hf/rsyslog/logrotate-remote` (boyut/gün bazlı).
