#!/usr/bin/env python3
"""Sentetik syslog trafiği — farklı kaynak IP'lerinden hacim farkı yaratır.

Lab'da HF'lere doğrudan TCP ile yazar (VIP/LVS olmadan da klasörleri doldurur)
veya --via-vip ile LB TCP portuna gönderir.

Örnek:
  ./generate-traffic.py --target 10.20.0.11 --heavy 3 --light 5 --seconds 30
  ./generate-traffic.py --target 127.0.0.1 --port 8514 --via-haproxy
"""

from __future__ import annotations

import argparse
import random
import socket
import time


def make_sources(heavy_n: int, light_n: int) -> list[tuple[str, int]]:
    """(kaynak_ip, msgs_per_sec) listesi."""
    sources = []
    for i in range(heavy_n):
        sources.append((f"192.168.10.{i+1}", random.randint(80, 150)))
    for i in range(light_n):
        sources.append((f"192.168.20.{i+1}", random.randint(1, 5)))
    return sources


def send_tcp(host: str, port: int, msg: bytes) -> None:
    with socket.create_connection((host, port), timeout=3) as s:
        s.sendall(msg)


def send_udp(host: str, port: int, msg: bytes) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(msg, (host, port))
    finally:
        sock.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=514)
    ap.add_argument("--proto", choices=["tcp", "udp"], default="tcp")
    ap.add_argument("--heavy", type=int, default=3)
    ap.add_argument("--light", type=int, default=5)
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument(
        "--seed-dirs",
        action="store_true",
        help="Ağ yerine doğrudan /data/hf*/remote altına dosya yaz (unit test)",
    )
    ap.add_argument("--out-root", default="/tmp/syslog-seed")
    args = ap.parse_args()

    sources = make_sources(args.heavy, args.light)
    print("Kaynaklar:")
    for ip, rate in sources:
        print(f"  {ip} @ ~{rate} msg/s")

    if args.seed_dirs:
        from pathlib import Path

        root = Path(args.out_root)
        # 3 HF'e dağıtılmış gibi yaz
        for idx, (ip, rate) in enumerate(sources):
            hf = root / f"hf{(idx % 3) + 1}" / "remote" / ip
            hf.mkdir(parents=True, exist_ok=True)
            lines = rate * max(1, args.seconds // 10)
            (hf / "syslog.log").write_text(
                "".join(
                    f"<134>1 {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
                    f"{ip} pan - - - synthetic message {i}\n"
                    for i in range(lines)
                ),
                encoding="utf-8",
            )
        print(f"Seed yazıldı: {root}")
        return 0

    deadline = time.time() + args.seconds
    sent = 0
    while time.time() < deadline:
        for ip, rate in sources:
            for _ in range(max(1, rate // 10)):
                pri = 134
                ts = time.strftime("%b %d %H:%M:%S")
                body = f"<{pri}>{ts} {ip} app: synthetic load msg id={sent}\n"
                payload = body.encode()
                try:
                    if args.proto == "tcp":
                        send_tcp(args.target, args.port, payload)
                    else:
                        send_udp(args.target, args.port, payload)
                    sent += 1
                except OSError as exc:
                    print(f"send error: {exc}")
        time.sleep(0.1)
    print(f"Toplam gönderilen: {sent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
