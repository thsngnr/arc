# Syslog HF Dağıtım Mimarisi (5 host)

Keepalived + HAProxy (2 LB) ve rsyslog IP-klasörleme (3 HF) ile **hacme duyarlı otomatik fwmark pinleme**.

## Mimari

```
Kaynaklar ──UDP/TCP 514──► VIP 10.20.0.100
                              │
              ┌───────────────┴───────────────┐
              │  lb1 MASTER / lb2 BACKUP      │
              │  keepalived (LVS + fwmark)    │
              │  HAProxy (TCP 514 + stats)    │
              └───────────────┬───────────────┘
                 ┌────────────┼────────────┐
                 ▼            ▼            ▼
               hf1          hf2          hf3
            /var/log/remote/<kaynak-ip>/syslog.log
```

Detay: [`docs/architecture.md`](docs/architecture.md)

| Host | IP | Rol |
|------|-----|-----|
| lb1 | 10.20.0.1 | keepalived MASTER + HAProxy |
| lb2 | 10.20.0.2 | keepalived BACKUP + HAProxy |
| hf1 | 10.20.0.11 | rsyslog HF |
| hf2 | 10.20.0.12 | rsyslog HF |
| hf3 | 10.20.0.13 | rsyslog HF |
| VIP | 10.20.0.100 | syslog giriş noktası |

## Ne yapar?

1. **Varsayılan denge:** Pinlenmemiş UDP syslog VIP üzerinden LVS round-robin ile 3 HF'e gider; TCP HAProxy `leastconn` ile.
2. **Hacim ölçümü:** `automation/volume_pin.py` HF log klasörlerinde son penceredeki satırları sayar.
3. **Otomatik pin:** En ağır N kaynağı iptables `fwmark` + keepalived `virtual_server fwmark` ile farklı HF'lere sabitler, keepalived reload eder.
4. **Statik alternatif:** Bilinen sabit PAN'lar için `config.yaml` → `static_pins` ile elle pin de mümkün.

## Hızlı lab (Docker Compose)

```bash
chmod +x scripts/*.sh lb/scripts/*.sh hf/scripts/*.sh
./scripts/deploy-lab.sh
```

- HAProxy stats: http://localhost:8404/stats (`admin` / `sysloglab`)
- TCP syslog (host → lb1): `localhost:8514`

Sentetik trafik:

```bash
python3 scripts/generate-traffic.py --target 127.0.0.1 --port 8514 --proto tcp --seconds 30
```

## Test

```bash
pip install -r automation/requirements.txt
python3 -m unittest tests/test_volume_pin.py -v
```

## Üretim yerleşimi

```bash
./scripts/deploy-prod.sh inventory/hosts.yaml
```

- LB'lere: `lb/keepalived/`, `lb/haproxy/`, `automation/`
- HF'lere: `hf/rsyslog/rsyslog.conf`, `hf/scripts/setup-lvs-dr.sh`
- Timer: `automation/systemd/syslog-volume-pin.timer` (5 dk)

## Dizin yapısı

```
automation/     volume_pin + config + systemd/cron
docs/           mimari
hf/             rsyslog + LVS-DR
inventory/      hosts.yaml
lb/             keepalived + haproxy
scripts/        lab deploy, trafik üreteci
tests/          birim testler
```
