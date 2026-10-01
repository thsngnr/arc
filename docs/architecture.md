# Syslog HF Dağıtım Mimarisi

5 hostluk, hacme duyarlı syslog toplama mimarisi.

## Host Envanteri

| Rol | Host | Servisler | Ağ |
|-----|------|-----------|-----|
| LB-A | `lb1` | keepalived (MASTER) + HAProxy | VIP: `10.20.0.100` |
| LB-B | `lb2` | keepalived (BACKUP) + HAProxy | VIP: `10.20.0.100` |
| HF-1 | `hf1` | rsyslog (IP klasörleme) | `10.20.0.11` |
| HF-2 | `hf2` | rsyslog (IP klasörleme) | `10.20.0.12` |
| HF-3 | `hf3` | rsyslog (IP klasörleme) | `10.20.0.13` |

## Trafik Akışı

```
  Kaynak cihazlar (PAN, firewall, switch, …)
              │  UDP/TCP 514
              ▼
     VIP 10.20.0.100
     ┌─────────────────────────┐
     │  lb1 (MASTER) / lb2     │
     │  keepalived LVS+fwmark  │
     │  HAProxy (TCP 514/6514) │
     └───────────┬─────────────┘
        ┌────────┼────────┐
        ▼        ▼        ▼
      hf1      hf2      hf3
   rsyslog  rsyslog  rsyslog
   /var/log/remote/<src-ip>/
```

## Deterministik Ayrışma (fwmark)

Ağır (yüksek hacimli) kaynaklar iptables `MARK` ile işaretlenir; keepalived `virtual_server fwmark` bloğu o mark'ı tek bir HF real-server'a yönlendirir. Böylece aynı kaynak her zaman aynı HF'e düşer (oturum tutarlılığı + disk I/O dengesi).

Kalan (hafif) trafik varsayılan round-robin / least-conn havuzuna gider.

## Otomatik Keşif Katmanı

`automation/volume_pin.py` periyodik çalışır:

1. Üç HF üzerindeki `/var/log/remote/<ip>/` dizinlerinde son pencere (örn. 1 saat) mesaj/satır sayar.
2. En çok log üreten **N** kaynağı seçer.
3. Bunları HF'lere round-robin dağıtır (pin map).
4. `iptables` fwmark kurallarını ve keepalived include dosyasını yazar.
5. `keepalived` reload eder.

Elle "bu 3'ü PAN" listesi tutmaya gerek kalmaz; liste değişkense sistem kendi ayarlar. Sabit 3 kaynak için manuel pin de desteklenir (`automation/config.yaml` → `static_pins`).

## Portlar

| Port | Protokol | Katman |
|------|----------|--------|
| 514 | UDP | keepalived LVS → HF rsyslog |
| 514 | TCP | HAProxy → HF rsyslog |
| 6514 | TCP/TLS | HAProxy → HF rsyslog (opsiyonel) |
| 8404 | TCP | HAProxy stats |

## Failover

- VRRP: `lb1` MASTER, `lb2` BACKUP; VIP taşınır.
- HAProxy health check: HF TCP 514 down ise backend çıkarılır.
- keepalived `real_server` HTTP/TCP check ile HF sağlığı izlenir.
