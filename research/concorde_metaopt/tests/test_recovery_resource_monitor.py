"""Guard tests for the CPU/memory sampler used by the D-REAL-EXP-003 runs."""
import json
import platform
import shutil
import time
import unittest
from pathlib import Path

from research.concorde_metaopt.dreal001.ops import resource_monitor as rm

# Sandbox-blocked default temp dirs are not usable on this host: keep scratch
# files inside the repository instead of %TEMP%.
_SCRATCH = Path(__file__).resolve().parent / "_resource_monitor_scratch"


def _scratch_dir() -> Path:
    _SCRATCH.mkdir(parents=True, exist_ok=True)
    return _SCRATCH


class ResourceMonitorTests(unittest.TestCase):
    def test_sampler_records_cpu_and_memory(self):
        if platform.system() != "Windows":
            self.skipTest("sampler targets Windows kernel32 APIs")
        if True:
            out = _scratch_dir() / "samples.jsonl"
            if out.exists():
                out.unlink()
            monitor = rm.ResourceMonitor(out, interval_s=0.2, label="unit-test")
            monitor.start()
            try:
                deadline = time.time() + 3.0
                while time.time() < deadline and monitor.summary()["sample_count"] < 3:
                    time.sleep(0.1)
            finally:
                summary = monitor.stop()
            self.assertGreaterEqual(summary["sample_count"], 3, summary)
            self.assertTrue(summary["cpu_available"])
            self.assertIsNotNone(summary["cpu_busy_fraction_mean"])
            self.assertGreaterEqual(summary["cpu_busy_fraction_mean"], 0.0)
            self.assertLessEqual(summary["cpu_busy_fraction_mean"], 1.0)
            self.assertIsNotNone(summary["memory_load_percent_mean"])
            self.assertGreater(summary["phys_total_bytes"] if "phys_total_bytes" in summary
                               else 1, 0)
            rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), summary["sample_count"])
            self.assertEqual(rows[0]["schema"], rm.SCHEMA)
            self.assertGreater(rows[0]["phys_total_bytes"], 0)
            self.assertIn("tracked_working_set_bytes", rows[0])

    def test_summary_declares_cpu_is_host_wide(self):
        if platform.system() != "Windows":
            self.skipTest("sampler targets Windows kernel32 APIs")
        if True:
            monitor = rm.ResourceMonitor(_scratch_dir() / "summary.jsonl",
                                         interval_s=0.2, label="t")
            monitor.start()
            try:
                time.sleep(0.6)
            finally:
                summary = monitor.stop()
        self.assertIn("host-wide", summary["note"])
        self.assertIn("lower bound", summary["note"])

    def test_unwritable_output_is_reported_not_raised(self):
        """A broken output path must degrade the record, never the run."""
        if platform.system() != "Windows":
            self.skipTest("sampler targets Windows kernel32 APIs")
        blocker = _scratch_dir() / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        monitor = rm.ResourceMonitor(blocker / "samples.jsonl",
                                     interval_s=0.2, label="t")
        monitor.start()
        try:
            time.sleep(0.4)
        finally:
            summary = monitor.stop()
        self.assertEqual(summary["sample_count"], 0)
        self.assertIsNotNone(summary["failure"])
        self.assertIn("cannot create", summary["failure"])
        blocker.unlink()

    def test_interval_must_be_positive(self):
        with self.assertRaises(ValueError):
            rm.ResourceMonitor(Path("x.jsonl"), interval_s=0.0)


if __name__ == "__main__":
    unittest.main()