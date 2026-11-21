
"""Tests for the strict VSPAERO polar reader."""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from research.concorde_metaopt.dreal001.geometry.polar_rows import (
    PolarFormatError, read_polar_rows)

HEADER = ("Beta Mach AoA Re/1e6 CLo CLi CLtot CDo CDi CDtot CSo CSi CStot L/D E "
          "CMox CMoy CMoz CMix CMiy CMiz CMxtot CMytot CMztot")
TMP_ROOT = Path(__file__).resolve().parent / "_polar_rows_tmp"


def render(rows):
    lines = ["banner", HEADER]
    for beta, mach, alpha, cl, cdi in rows:
        cells = ["0.0"] * 24
        cells[0] = repr(beta); cells[1] = repr(mach); cells[2] = repr(alpha)
        cells[6] = repr(cl); cells[8] = repr(cdi)
        lines.append(" ".join(cells))
    return "\n".join(lines) + "\n"


class PolarRowsTests(unittest.TestCase):
    def setUp(self):
        self.dir = TMP_ROOT / self.id().rsplit(".", 1)[-1]
        shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "case.polar"

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_reads_rows_and_sorts(self):
        self.path.write_text(render([(0.0, 1.8, 6.2, 0.23, 0.024),
                                     (0.0, 1.8, 6.1, 0.22, 0.023),
                                     (1.0, 1.8, 6.3, 0.25, 0.026)]), encoding="utf-8")
        rows = read_polar_rows(self.path, mach=1.8)
        self.assertEqual([r.alpha_deg for r in rows], [6.1, 6.2])
        self.assertAlmostEqual(rows[0].cl, 0.22)
        self.assertAlmostEqual(rows[0].cdi, 0.023)

    def test_mach_filter_must_match_exactly(self):
        self.path.write_text(render([(0.0, 1.6, 6.0, 0.2, 0.02),
                                     (0.0, 1.8, 6.0, 0.22, 0.021)]), encoding="utf-8")
        rows = read_polar_rows(self.path, mach=1.6)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0].mach, 1.6)

    def test_missing_header_fails_closed(self):
        self.path.write_text("banner\n1 2 3\n", encoding="utf-8")
        with self.assertRaises(PolarFormatError):
            read_polar_rows(self.path)

    def test_no_rows_fails_closed(self):
        self.path.write_text(render([(1.0, 1.8, 6.0, 0.2, 0.02)]), encoding="utf-8")
        with self.assertRaises(PolarFormatError):
            read_polar_rows(self.path)


if __name__ == "__main__":
    unittest.main()
