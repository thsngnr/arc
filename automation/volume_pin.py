#!/usr/bin/env python3
"""
Hacme duyarlı kaynak pinleme.

HF log dizinlerinde (IP klasörleri) son penceredeki satır sayısını ölçer,
en ağır N kaynağı tespit eder, iptables fwmark + keepalived include üretir
ve keepalived'i reload eder.

Kullanım:
  volume_pin.py --config /etc/syslog-pin/config.yaml
  volume_pin.py --config ./config.yaml --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

try:
    import yaml
except ImportError:
    yaml = None


@dataclass
class HFHost:
    name: str
    ip: str
    fwmark: int
    log_root: str


@dataclass
class Pin:
    source_ip: str
    hf_name: str
    hf_ip: str
    fwmark: int
    lines: int


def load_config(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text)
    # Minimal YAML-ish fallback for simple key: value (not used if PyYAML present)
    raise RuntimeError("PyYAML gerekli: pip install pyyaml")


def count_lines_in_tree(root: Path, since_mtime: float) -> Dict[str, int]:
    """Her kaynak IP klasörü için son pencerede değişen dosyalardaki satır sayısı."""
    counts: Dict[str, int] = {}
    if not root.is_dir():
        return counts
    for src_dir in sorted(root.iterdir()):
        if not src_dir.is_dir():
            continue
        source_ip = src_dir.name
        total = 0
        for fp in src_dir.rglob("*"):
            if not fp.is_file():
                continue
            try:
                st = fp.stat()
            except OSError:
                continue
            if st.st_mtime < since_mtime:
                continue
            # Hızlı sayım: dosya boyutu yerine satır (POC uyumlu)
            try:
                with fp.open("rb") as f:
                    total += sum(1 for _ in f)
            except OSError:
                continue
        if total > 0:
            counts[source_ip] = counts.get(source_ip, 0) + total
    return counts


def gather_counts(cfg: dict, hfs: List[HFHost]) -> Dict[str, int]:
    """Tüm HF'lerden kaynak bazlı satır sayılarını birleştir."""
    window = int(cfg.get("window_seconds", 3600))
    since = time.time() - window
    merged: Dict[str, int] = defaultdict(int)

    use_local = bool(cfg.get("use_local_mounts", False))
    mount_map = cfg.get("local_mount_map") or {}

    for hf in hfs:
        if use_local and hf.name in mount_map:
            root = Path(mount_map[hf.name])
            part = count_lines_in_tree(root, since)
        else:
            # Uzak: SSH ile find+wc (basit POC)
            part = remote_count_via_ssh(cfg, hf, since)
        for ip, n in part.items():
            merged[ip] += n
    return dict(merged)


def remote_count_via_ssh(cfg: dict, hf: HFHost, since: float) -> Dict[str, int]:
    user = cfg.get("ssh_user", "root")
    key = cfg.get("ssh_key", "")
    cmd = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ConnectTimeout=5",
    ]
    if key:
        cmd += ["-i", key]
    cmd.append(f"{user}@{hf.ip}")
    # Uzakta python one-liner yerine basit shell: klasör başına satır
    remote = (
        f"python3 - <<'PY'\n"
        f"import os,time\n"
        f"root={hf.log_root!r}\n"
        f"since={since}\n"
        f"counts={{}}\n"
        f"if os.path.isdir(root):\n"
        f"  for name in os.listdir(root):\n"
        f"    d=os.path.join(root,name)\n"
        f"    if not os.path.isdir(d): continue\n"
        f"    n=0\n"
        f"    for dirpath,_,files in os.walk(d):\n"
        f"      for fn in files:\n"
        f"        p=os.path.join(dirpath,fn)\n"
        f"        try:\n"
        f"          st=os.stat(p)\n"
        f"          if st.st_mtime<since: continue\n"
        f"          with open(p,'rb') as f:\n"
        f"            n+=sum(1 for _ in f)\n"
        f"        except OSError: pass\n"
        f"    if n: counts[name]=n\n"
        f"import json; print(json.dumps(counts))\n"
        f"PY"
    )
    cmd.append(remote)
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True, timeout=120)
        return json.loads(out.strip() or "{}")
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
        print(f"[warn] HF {hf.name} sayım başarısız: {exc}", file=sys.stderr)
        return {}


def select_pins(
    counts: Dict[str, int],
    hfs: List[HFHost],
    top_n: int,
    min_lines: int,
    static_pins: List[dict],
) -> List[Pin]:
    pins: List[Pin] = []
    used_sources = set()
    hf_by_name = {h.name: h for h in hfs}

    for sp in static_pins or []:
        src = sp["source_ip"]
        hf = hf_by_name[sp["hf"]]
        pins.append(
            Pin(
                source_ip=src,
                hf_name=hf.name,
                hf_ip=hf.ip,
                fwmark=hf.fwmark,
                lines=counts.get(src, 0),
            )
        )
        used_sources.add(src)

    ranked = sorted(
        ((ip, n) for ip, n in counts.items() if ip not in used_sources and n >= min_lines),
        key=lambda x: x[1],
        reverse=True,
    )
    slots = max(0, top_n - len(pins))
    for i, (src, n) in enumerate(ranked[:slots]):
        hf = hfs[i % len(hfs)]
        pins.append(
            Pin(
                source_ip=src,
                hf_name=hf.name,
                hf_ip=hf.ip,
                fwmark=hf.fwmark,
                lines=n,
            )
        )
    return pins


def render_iptables(pins: List[Pin], vip: str, udp_port: int) -> str:
    lines = [
        "#!/bin/bash",
        "# AUTO-GENERATED by volume_pin.py — elle düzenlemeyin",
        "set -euo pipefail",
        "",
        "# Önceki syslog-pin zincirini temizle",
        "iptables -t mangle -D PREROUTING -j SYSLOG_PIN 2>/dev/null || true",
        "iptables -t mangle -F SYSLOG_PIN 2>/dev/null || true",
        "iptables -t mangle -X SYSLOG_PIN 2>/dev/null || true",
        "iptables -t mangle -N SYSLOG_PIN",
        "iptables -t mangle -A PREROUTING -j SYSLOG_PIN",
        "",
    ]
    for p in pins:
        lines.append(
            f"# {p.source_ip} → {p.hf_name} (fwmark {p.fwmark}, ~{p.lines} lines)"
        )
        lines.append(
            "iptables -t mangle -A SYSLOG_PIN "
            f"-p udp -d {vip} --dport {udp_port} -s {p.source_ip} "
            f"-j MARK --set-mark {p.fwmark}"
        )
        lines.append(
            "iptables -t mangle -A SYSLOG_PIN "
            f"-p tcp -d {vip} --dport {udp_port} -s {p.source_ip} "
            f"-j MARK --set-mark {p.fwmark}"
        )
        lines.append("")
    lines.append("echo \"[syslog-pin] applied {0} pin(s)\"".format(len(pins)))
    return "\n".join(lines) + "\n"


def render_keepalived_fwmark(pins: List[Pin], hfs: List[HFHost], udp_port: int) -> str:
    """Her HF fwmark için virtual_server bloğu — pinlenen kaynaklar o HF'e gider."""
    # Hangi fwmark'lar kullanılıyor?
    used_marks = sorted({p.fwmark for p in pins})
    hf_by_mark = {h.fwmark: h for h in hfs}
    blocks = [
        "# AUTO-GENERATED by volume_pin.py — elle düzenlemeyin",
        "",
    ]
    for mark in used_marks:
        hf = hf_by_mark.get(mark)
        if not hf:
            continue
        sources = [p.source_ip for p in pins if p.fwmark == mark]
        blocks.append(f"# fwmark {mark} → {hf.name} ({hf.ip}) sources: {', '.join(sources)}")
        blocks.append(f"virtual_server fwmark {mark} {{")
        blocks.append("    delay_loop 6")
        blocks.append("    lb_algo rr")
        blocks.append("    lb_kind DR")
        blocks.append("    protocol UDP")
        blocks.append(f"    real_server {hf.ip} {udp_port} {{")
        blocks.append("        weight 100")
        blocks.append("        TCP_CHECK {")
        blocks.append("            connect_timeout 3")
        blocks.append("            connect_port 514")
        blocks.append("        }")
        blocks.append("    }")
        blocks.append("}")
        blocks.append("")
    return "\n".join(blocks)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def atomic_write(path: Path, content: str, mode: int = 0o644) -> None:
    ensure_parent(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.chmod(tmp, mode)
    tmp.replace(path)


def apply_and_reload(cfg: dict, dry_run: bool) -> None:
    ipt = Path(cfg["output"]["iptables_script"])
    if dry_run:
        print(f"[dry-run] iptables script yazıldı: {ipt}")
        return
    subprocess.check_call(["bash", str(ipt)])
    reload_cmd = cfg.get("keepalived_reload") or "systemctl reload keepalived"
    print(f"[syslog-pin] reload: {reload_cmd}")
    subprocess.call(reload_cmd, shell=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Hacme duyarlı syslog fwmark pinleme")
    ap.add_argument("--config", required=True, help="config.yaml yolu")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--vip", default="10.20.0.100")
    ap.add_argument("--udp-port", type=int, default=514)
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    dry = args.dry_run or bool(cfg.get("dry_run", False))

    hfs = [
        HFHost(
            name=h["name"],
            ip=h["ip"],
            fwmark=int(h["fwmark"]),
            log_root=h.get("log_root", cfg.get("log_root", "/var/log/remote")),
        )
        for h in cfg["hf_hosts"]
    ]

    print("[syslog-pin] kaynak hacimleri ölçülüyor…")
    counts = gather_counts(cfg, hfs)
    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    for ip, n in ranked[:20]:
        print(f"  {ip:20s} {n:8d} lines")

    pins = select_pins(
        counts,
        hfs,
        top_n=int(cfg.get("top_n", 6)),
        min_lines=int(cfg.get("min_lines_to_pin", 100)),
        static_pins=cfg.get("static_pins") or [],
    )
    print(f"[syslog-pin] {len(pins)} pin seçildi:")
    for p in pins:
        print(f"  {p.source_ip} → {p.hf_name} (mark={p.fwmark}, lines={p.lines})")

    out = cfg["output"]
    ipt_script = render_iptables(pins, args.vip, args.udp_port)
    kv_conf = render_keepalived_fwmark(pins, hfs, args.udp_port)

    ipt_path = Path(out["iptables_script"])
    kv_path = Path(out["keepalived_include"])
    state_path = Path(out["state_file"])
    map_path = Path(out["pin_map_file"])

    atomic_write(ipt_path, ipt_script, 0o755)
    atomic_write(kv_path, kv_conf, 0o644)
    state = {
        "generated_at": time.time(),
        "window_seconds": cfg.get("window_seconds"),
        "counts": counts,
        "pins": [p.__dict__ for p in pins],
        "dry_run": dry,
    }
    atomic_write(state_path, json.dumps(state, indent=2) + "\n")
    pin_map = {p.source_ip: {"hf": p.hf_name, "fwmark": p.fwmark} for p in pins}
    atomic_write(map_path, json.dumps(pin_map, indent=2) + "\n")

    print(f"[syslog-pin] yazıldı: {ipt_path}")
    print(f"[syslog-pin] yazıldı: {kv_path}")
    apply_and_reload(cfg, dry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
