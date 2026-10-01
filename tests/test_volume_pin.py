#!/usr/bin/env python3
"""volume_pin birim testleri — Docker gerektirmez."""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "automation"))

from volume_pin import (  # noqa: E402
    HFHost,
    count_lines_in_tree,
    render_iptables,
    render_keepalived_fwmark,
    select_pins,
)


class VolumePinTests(unittest.TestCase):
    def test_count_lines_by_source_ip(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            heavy = root / "192.168.10.1"
            light = root / "192.168.20.1"
            heavy.mkdir()
            light.mkdir()
            (heavy / "syslog.log").write_text("a\n" * 500, encoding="utf-8")
            (light / "syslog.log").write_text("b\n" * 20, encoding="utf-8")
            since = time.time() - 60
            counts = count_lines_in_tree(root, since)
            self.assertEqual(counts["192.168.10.1"], 500)
            self.assertEqual(counts["192.168.20.1"], 20)

    def test_select_pins_round_robin_across_hfs(self):
        hfs = [
            HFHost("hf1", "10.20.0.11", 1, "/var/log/remote"),
            HFHost("hf2", "10.20.0.12", 2, "/var/log/remote"),
            HFHost("hf3", "10.20.0.13", 3, "/var/log/remote"),
        ]
        counts = {
            "192.168.10.1": 10000,
            "192.168.10.2": 9000,
            "192.168.10.3": 8000,
            "192.168.20.1": 5,
        }
        pins = select_pins(counts, hfs, top_n=3, min_lines=100, static_pins=[])
        self.assertEqual(len(pins), 3)
        self.assertEqual({p.hf_name for p in pins}, {"hf1", "hf2", "hf3"})
        self.assertEqual(pins[0].source_ip, "192.168.10.1")

    def test_static_pins_take_precedence(self):
        hfs = [
            HFHost("hf1", "10.20.0.11", 1, "/var/log/remote"),
            HFHost("hf2", "10.20.0.12", 2, "/var/log/remote"),
            HFHost("hf3", "10.20.0.13", 3, "/var/log/remote"),
        ]
        counts = {"192.168.10.1": 1000, "192.168.10.9": 9999}
        static = [{"source_ip": "192.168.10.1", "hf": "hf2"}]
        pins = select_pins(counts, hfs, top_n=2, min_lines=100, static_pins=static)
        self.assertEqual(pins[0].hf_name, "hf2")
        self.assertEqual(pins[0].fwmark, 2)
        self.assertEqual(pins[1].source_ip, "192.168.10.9")

    def test_render_iptables_and_keepalived(self):
        hfs = [
            HFHost("hf1", "10.20.0.11", 1, "/var/log/remote"),
            HFHost("hf2", "10.20.0.12", 2, "/var/log/remote"),
        ]
        pins = select_pins(
            {"192.168.10.1": 500, "192.168.10.2": 400},
            hfs,
            top_n=2,
            min_lines=10,
            static_pins=[],
        )
        ipt = render_iptables(pins, "10.20.0.100", 514)
        self.assertIn("SYSLOG_PIN", ipt)
        self.assertIn("-s 192.168.10.1", ipt)
        self.assertIn("--set-mark", ipt)
        kv = render_keepalived_fwmark(pins, hfs, 514)
        self.assertIn("virtual_server fwmark", kv)
        self.assertIn("real_server 10.20.0.11 514", kv)

    def test_end_to_end_dry_run_artifacts(self):
        import subprocess

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            # seed 3 HF mounts
            for i, (src, n) in enumerate(
                [
                    ("192.168.10.1", 1000),
                    ("192.168.10.2", 800),
                    ("192.168.10.3", 600),
                ]
            ):
                d = td_path / f"hf{i+1}" / "remote" / src
                d.mkdir(parents=True)
                (d / "syslog.log").write_text("x\n" * n, encoding="utf-8")

            cfg = td_path / "config.yaml"
            out_ipt = td_path / "apply.sh"
            out_kv = td_path / "fwmark-pins.conf"
            out_state = td_path / "state.json"
            out_map = td_path / "pin-map.json"
            cfg.write_text(
                f"""
log_root: /var/log/remote
window_seconds: 3600
top_n: 3
min_lines_to_pin: 10
use_local_mounts: true
local_mount_map:
  hf1: {td_path / 'hf1' / 'remote'}
  hf2: {td_path / 'hf2' / 'remote'}
  hf3: {td_path / 'hf3' / 'remote'}
hf_hosts:
  - name: hf1
    ip: 10.20.0.11
    fwmark: 1
  - name: hf2
    ip: 10.20.0.12
    fwmark: 2
  - name: hf3
    ip: 10.20.0.13
    fwmark: 3
output:
  iptables_script: {out_ipt}
  keepalived_include: {out_kv}
  state_file: {out_state}
  pin_map_file: {out_map}
keepalived_reload: "true"
static_pins: []
dry_run: true
""",
                encoding="utf-8",
            )
            subprocess.check_call(
                [
                    sys.executable,
                    str(ROOT / "automation" / "volume_pin.py"),
                    "--config",
                    str(cfg),
                    "--dry-run",
                ]
            )
            self.assertTrue(out_ipt.exists())
            self.assertTrue(out_kv.exists())
            state = json.loads(out_state.read_text(encoding="utf-8"))
            self.assertEqual(len(state["pins"]), 3)
            pin_map = json.loads(out_map.read_text(encoding="utf-8"))
            self.assertIn("192.168.10.1", pin_map)


if __name__ == "__main__":
    unittest.main()
